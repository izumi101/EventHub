import { randomBytes } from 'node:crypto';
import { APIRequestContext, APIResponse, expect, Page } from '@playwright/test';
import type { components } from '../../src/app/api/openapi';
import { burnCurrentStep, freshTotp } from './totp';

/**
 * Test data through the public API, so every spec creates the accounts and
 * events it needs and does not depend on (or disturb) another spec's data.
 */
export type Schemas = components['schemas'];

export interface Account {
  username: string;
  email: string;
  password: string;
  /** Base32 secret of the account's authenticator app, if it has one. */
  totpSecret?: string;
  recoveryCodes?: string[];
}

export interface Session {
  access: string;
  refresh: string;
  user: Schemas['User'];
}

/** Publicly known test secret of the seeded organizer and admin (CI and the QA stack). */
export const SEEDED_TOTP_SECRET = process.env['E2E_MFA_TOTP_SECRET'] ?? '';
export const DEFAULT_PASSWORD = 'E2e-pass-2026!';

export async function json<T>(response: APIResponse): Promise<T> {
  return (await response.json()) as T;
}

/** Unique, readable identifiers: the specs run again and again on one stack. */
export function uid(prefix: string): string {
  return `${prefix}${Date.now().toString(36)}${randomBytes(3).toString('hex')}`;
}

export function bearer(session: Session | string) {
  return { Authorization: `Bearer ${typeof session === 'string' ? session : session.access}` };
}

async function ok(response: APIResponse, what: string): Promise<APIResponse> {
  if (!response.ok()) {
    throw new Error(`${what}: HTTP ${response.status()} ${await response.text()}`);
  }
  return response;
}

/**
 * Password + second step. Accounts with an authenticator app answer the
 * challenge with a fresh TOTP code (a code refused as a replay is retried
 * in the next time step).
 */
export async function signIn(request: APIRequestContext, account: Account): Promise<Session> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const first = await json<Schemas['LoginResult'] & { error?: string }>(
      await ok(
        await request.post('/api/v1/auth/login/', {
          data: { username: account.username, password: account.password },
        }),
        `sign in ${account.username}`,
      ),
    );
    if ('tokens' in first) return { ...first.tokens, user: first.user };
    if (!('challenge_token' in first) || !account.totpSecret) {
      throw new Error(`${account.username} needs a second factor this helper cannot give`);
    }
    const verified = await request.post('/api/v1/auth/mfa/login/verify/', {
      data: {
        challenge_token: first.challenge_token,
        method: 'totp',
        code: await freshTotp(account.username, account.totpSecret),
      },
    });
    if (verified.ok()) {
      const payload = await json<Schemas['AuthPayload']>(verified);
      return { ...payload.tokens, user: payload.user };
    }
    burnCurrentStep(account.username);
  }
  throw new Error(`TOTP sign-in of ${account.username} failed twice`);
}

let adminSession: Promise<Session> | undefined;

/** The seeded superuser (DJANGO_SEED_ADMIN_PASSWORD + the seeded TOTP secret). */
export function admin(request: APIRequestContext): Promise<Session> {
  const password = process.env['E2E_ADMIN_PASSWORD'];
  if (!password || !SEEDED_TOTP_SECRET) {
    throw new Error('Set E2E_ADMIN_PASSWORD and E2E_MFA_TOTP_SECRET (see docs/TEST_REPORT.md)');
  }
  adminSession ??= signIn(request, {
    username: 'admin',
    email: '',
    password,
    totpSecret: SEEDED_TOTP_SECRET,
  });
  return adminSession;
}

/** A new attendee through the real sign-up API (DEBUG shows the code in the answer). */
export async function createAttendee(
  request: APIRequestContext,
): Promise<{ account: Account; session: Session }> {
  const username = uid('att');
  const account: Account = {
    username,
    email: `${username}@example.com`,
    password: DEFAULT_PASSWORD,
  };
  const sent = await json<Schemas['SendCodeResponse']>(
    await ok(
      await request.post('/api/v1/auth/register/send-code/', { data: { email: account.email } }),
      'send sign-up code',
    ),
  );
  if (!sent.dev_code) throw new Error('The stack must run with DJANGO_DEBUG=1 (dev_code missing)');
  const registered = await json<Schemas['AuthPayload']>(
    await ok(
      await request.post('/api/v1/auth/register/', {
        data: {
          username,
          email: account.email,
          password: account.password,
          password2: account.password,
          first_name: 'Test',
          last_name: 'Attendee',
          verification_code: sent.dev_code,
        },
      }),
      'register attendee',
    ),
  );
  return { account, session: { ...registered.tokens, user: registered.user } };
}

/**
 * A new organizer account, created by the admin (the only way to get the
 * role). It has no second factor yet: its first sign-in must enroll one.
 */
export async function createUnenrolledOrganizer(request: APIRequestContext): Promise<Account> {
  const username = uid('org');
  const account: Account = {
    username,
    email: `${username}@example.com`,
    password: DEFAULT_PASSWORD,
  };
  await ok(
    await request.post('/api/v1/auth/admin/organizers/', {
      headers: bearer(await admin(request)),
      data: { ...account, first_name: 'Test', last_name: 'Organizer' },
    }),
    'create organizer',
  );
  return account;
}

/**
 * A new organizer that already turned on an authenticator app through the
 * enrollment token, as the SPA does at the first sign-in. Returns its TOTP
 * secret, recovery codes and the session the enrollment started.
 */
export async function createOrganizer(
  request: APIRequestContext,
): Promise<{ account: Account; session: Session }> {
  const account = await createUnenrolledOrganizer(request);
  const { username } = account;
  const first = await json<Schemas['LoginResult']>(
    await ok(
      await request.post('/api/v1/auth/login/', { data: { username, password: account.password } }),
      'organizer first sign-in',
    ),
  );
  if (!('enrollment_token' in first)) throw new Error('Expected mfa_enrollment_required');
  const enrollment = { Authorization: `Bearer ${first.enrollment_token}` };
  const setup = await json<Schemas['TOTPSetupResult']>(
    await ok(
      await request.post('/api/v1/auth/mfa/totp/setup/', { headers: enrollment }),
      'TOTP setup',
    ),
  );
  account.totpSecret = setup.secret;
  const added = await json<Schemas['FactorAdded']>(
    await ok(
      await request.post('/api/v1/auth/mfa/totp/confirm/', {
        headers: enrollment,
        data: { code: await freshTotp(username, setup.secret) },
      }),
      'TOTP confirm',
    ),
  );
  account.recoveryCodes = added.recovery_codes ?? [];
  if (!added.tokens || !added.user) throw new Error('Enrollment did not start a session');
  return { account, session: { ...added.tokens, user: added.user } };
}

let categoryId: number | undefined;

async function anyCategory(request: APIRequestContext): Promise<number> {
  if (categoryId === undefined) {
    const body = await json<Schemas['Category'][] | { results: Schemas['Category'][] }>(
      await ok(await request.get('/api/v1/categories/'), 'categories'),
    );
    categoryId = (Array.isArray(body) ? body : body.results)[0].id;
  }
  return categoryId;
}

export interface EventOptions {
  title?: string;
  currency?: 'KZT' | 'USD';
  price?: string;
  capacity?: number;
  /** Generate a seat map of rows × cols (all standard zone). */
  seats?: { rows: number; cols: number };
  daysAhead?: number;
  /** false: leave the event waiting for admin approval (status `pending`). Default true. */
  publish?: boolean;
}

/** A published event owned by `organizer` (created, then approved by the admin unless `publish: false`). */
export async function createEvent(
  request: APIRequestContext,
  organizer: Session,
  options: EventOptions = {},
): Promise<Schemas['EventList']> {
  const title = options.title ?? uid('E2E event ');
  const date = new Date(Date.now() + (options.daysAhead ?? 30) * 86_400_000);
  date.setUTCHours(14, 0, 0, 0);
  const created = await json<Schemas['EventList']>(
    await ok(
      await request.post('/api/v1/events/', {
        headers: bearer(organizer),
        data: {
          title,
          description: 'Created by the end-to-end tests.',
          date: date.toISOString(),
          location: 'Almaty, Abay Ave 1',
          max_participants: options.capacity ?? 50,
          price: options.price ?? '5000.00',
          currency: options.currency ?? 'KZT',
          category_id: await anyCategory(request),
        },
      }),
      'create event',
    ),
  );
  if (options.publish !== false) {
    await ok(
      await request.post(`/api/v1/events/${created.id}/approve/`, {
        headers: bearer(await admin(request)),
      }),
      'approve event',
    );
  }
  if (options.seats) {
    await ok(
      await request.post(`/api/v1/events/${created.id}/seat-map/create/`, {
        headers: bearer(organizer),
        data: { ...options.seats, sync_capacity: true },
      }),
      'create seat map',
    );
  }
  // An unapproved event is not public yet: the create answer is all there is to read.
  if (options.publish === false) return created;
  return json<Schemas['EventList']>(await request.get(`/api/v1/events/${created.id}/`));
}

/** Buy a ticket of a USD event through the API (mock payments confirm at once). */
export async function buyMockTicket(
  request: APIRequestContext,
  buyer: Session,
  eventId: number,
): Promise<Schemas['Registration']> {
  const registration = await json<Schemas['Registration']>(
    await ok(
      await request.post(`/api/v1/events/${eventId}/register/`, {
        headers: bearer(buyer),
        data: {},
      }),
      'register',
    ),
  );
  await ok(
    await request.post(`/api/v1/payments/create-checkout/${registration.id}/`, {
      headers: bearer(buyer),
    }),
    'mock checkout',
  );
  const mine = await json<Schemas['PaginatedRegistrationList']>(
    await request.get(`/api/v1/my-registrations/?event=${eventId}`, { headers: bearer(buyer) }),
  );
  const confirmed = mine.results.find((r) => r.id === registration.id);
  if (confirmed?.status !== 'confirmed') {
    throw new Error(`Mock checkout left registration ${registration.id} ${confirmed?.status}`);
  }
  return confirmed;
}

/** The Freedom Pay emulator, as the browser and the test runner reach it. */
export const FPAY_URL = process.env['E2E_FPAY_URL'] ?? 'http://localhost:18080';

/**
 * Buy a ticket of a KZT event through Freedom Pay without a browser: the
 * checkout creates the gateway payment, the emulator's control API settles
 * it (its signed Result callback reaches the backend), and we wait until the
 * backend confirmed the ticket.
 */
export async function buyFreedomPayTicket(
  request: APIRequestContext,
  buyer: Session,
  eventId: number,
): Promise<{ registration: Schemas['Registration']; paymentId: number }> {
  const registration = await json<Schemas['Registration']>(
    await ok(
      await request.post(`/api/v1/events/${eventId}/register/`, {
        headers: bearer(buyer),
        data: {},
      }),
      'register',
    ),
  );
  const checkout = await json<Schemas['CheckoutSessionResponse'] & { payment_id: number }>(
    await ok(
      await request.post(`/api/v1/payments/create-checkout/${registration.id}/`, {
        headers: bearer(buyer),
      }),
      'Freedom Pay checkout',
    ),
  );
  expect(checkout.provider).toBe('freedompay');
  await ok(
    await request.post(`${FPAY_URL}/_emulator/payments/${checkout.session_id}/complete`, {
      data: {},
      headers: process.env['E2E_FPAY_CONTROL_TOKEN']
        ? { 'X-Emulator-Token': process.env['E2E_FPAY_CONTROL_TOKEN'] }
        : {},
    }),
    'emulator settles the payment',
  );
  await expect
    .poll(async () => {
      const status = await json<Schemas['PaymentStatusResponse']>(
        await request.get(`/api/v1/payments/status/${checkout.payment_id}/`, {
          headers: bearer(buyer),
        }),
      );
      return status.registration_status;
    })
    .toBe('confirmed');
  return { registration, paymentId: checkout.payment_id };
}

/** Seconds a second-factor proof covers sensitive actions on the stack under test. */
export const STEP_UP_MAX_AGE_SECONDS = Number(process.env['E2E_STEP_UP_MAX_AGE_SECONDS'] ?? 45);

/**
 * Wait until the session's second-factor proof (`mfa_at` in the JWT) is
 * older than the step-up limit, so the next sensitive action must ask
 * "Confirm it's you" again.
 */
export async function waitUntilStepUpExpires(session: Session): Promise<void> {
  const claims = JSON.parse(Buffer.from(session.access.split('.')[1], 'base64url').toString()) as {
    mfa_at?: number;
  };
  const wait = ((claims.mfa_at ?? 0) + STEP_UP_MAX_AGE_SECONDS + 2) * 1000 - Date.now();
  if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
}

/**
 * Open the SPA already signed in as `session` (what the app stores after a
 * successful sign-in), so specs that are not about signing in skip the form.
 */
export async function openSignedIn(page: Page, session: Session, path = '/'): Promise<void> {
  await page.goto('/');
  await page.evaluate((s) => {
    localStorage.setItem('access_token', s.access);
    localStorage.setItem('refresh_token', s.refresh);
    localStorage.setItem('user', JSON.stringify(s.user));
  }, session);
  await page.goto(path);
}
