import { createHmac } from 'node:crypto';
import { APIRequestContext, APIResponse, expect, Page, test } from '@playwright/test';
import type { components } from '../src/app/api/openapi';

type Schemas = components['schemas'];

/** The JSON body of an API response, typed by the OpenAPI contract. */
async function body<T>(response: APIResponse): Promise<T> {
  return (await response.json()) as T;
}

// Demo data from `seed_data` (DJANGO_SEED_DATA=1 in .env.example).
const PAID_ONLINE_EVENT = 'Online Django REST Workshop';

async function login(page: Page, username: string, password: string) {
  await page.goto('/login');
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/auth/login/')),
    page.click('button[type="submit"]'),
  ]);
  expect(response.status()).toBe(200);
}

/** RFC 6238 code (SHA-1, 6 digits, 30 s) for a base32 secret. */
function totp(secret: string, now = Date.now()): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const ch of secret.replace(/=+$/, '').toUpperCase()) {
    bits += alphabet.indexOf(ch).toString(2).padStart(5, '0');
  }
  const key = Buffer.from(bits.match(/.{8}/g)?.map((b) => parseInt(b, 2)) ?? []);
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(now / 30_000)));
  const mac = createHmac('sha1', key).update(counter).digest();
  const offset = mac[mac.length - 1] & 0xf;
  return ((mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).toString().padStart(6, '0');
}

/**
 * API sign-in that completes the second step for accounts with 2FA (the demo
 * organizer must use it): the stack is seeded with the TOTP secret in
 * E2E_MFA_TOTP_SECRET (DJANGO_SEED_MFA_TOTP_SECRET on the backend).
 */
async function apiLogin(
  request: APIRequestContext,
  username: string,
  password: string,
): Promise<Schemas['AuthPayload']> {
  const first = await body<Schemas['LoginResult']>(
    await request.post('/api/v1/auth/login/', { data: { username, password } }),
  );
  if ('tokens' in first) return first;
  const secret = process.env['E2E_MFA_TOTP_SECRET'];
  if (!('challenge_token' in first) || !secret) {
    throw new Error(`${username} needs 2FA: set E2E_MFA_TOTP_SECRET and seed it`);
  }
  const verified = await request.post('/api/v1/auth/mfa/login/verify/', {
    data: { challenge_token: first.challenge_token, method: 'totp', code: totp(secret) },
  });
  expect(verified.status()).toBe(200);
  return body<Schemas['AuthPayload']>(verified);
}

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    // CSP violations and runtime errors show up as console errors.
    if (m.type() !== 'error') return;
    // "No seat map for this event" is an expected 404 the checkout handles.
    if (m.text().startsWith('Failed to load resource') && m.location().url.endsWith('/seat_map/'))
      return;
    errors.push(`console: ${m.text()} (${m.location().url})`);
  });
  return errors;
}

test('home page renders, styled, under the CSP', async ({ page }) => {
  const errors = collectErrors(page);
  const response = await page.goto('/');
  expect(response?.headers()['content-security-policy']).toContain("script-src 'self'");
  await expect(page.getByText(PAID_ONLINE_EVENT).first()).toBeVisible();
  // The stylesheet applied (critical-CSS inlining is off for the CSP).
  const background = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(background).not.toBe('rgba(0, 0, 0, 0)');
  expect(errors).toEqual([]);
});

test('attendee buys a paid ticket and gets the online link', async ({ page }) => {
  const errors = collectErrors(page);
  await login(page, 'attendee', 'password123');

  await page.goto('/');
  await page.getByText(PAID_ONLINE_EVENT).first().click();
  await page.getByRole('button', { name: /Get tickets/ }).click();
  await page.getByRole('button', { name: /Proceed to payment/ }).click();

  // Mock payments (DEBUG + STRIPE_MOCK_MODE=1) confirm on the server first.
  await expect(page.getByText('Payment confirmed')).toBeVisible();

  await page.goto('/my-registrations');
  await expect(page.getByText(PAID_ONLINE_EVENT).first()).toBeVisible();

  // The join link is only revealed to confirmed ticket holders.
  const events = await page.request.get('/api/v1/events/?search=Django');
  const id = (await body<Schemas['PaginatedEventListList']>(events)).results[0].id;
  const token = await page.evaluate(() => localStorage.getItem('access_token'));
  const anonymous = await body<Schemas['EventList']>(
    await page.request.get(`/api/v1/events/${id}/`, { headers: {} }),
  );
  const holder = await body<Schemas['EventList']>(
    await page.request.get(`/api/v1/events/${id}/`, {
      headers: { Authorization: `Bearer ${token}` },
    }),
  );
  expect(anonymous.online_link).toBe('');
  expect(holder.online_link).toContain('meet.example.com');

  expect(errors).toEqual([]);
});

test('seat map updates arrive over the WebSocket through nginx', async ({ page }) => {
  const events = await body<Schemas['PaginatedEventListList']>(
    await page.request.get('/api/v1/events/?search=Startup'),
  );
  const id = events.results[0].id;

  // The demo data has no seat maps: the organizer creates one (400 if it exists).
  const org = await apiLogin(page.request, 'organizer', 'password123');
  await page.request.post(`/api/v1/events/${id}/seat-map/create/`, {
    data: { rows: 2, cols: 4, sync_capacity: false },
    headers: { Authorization: `Bearer ${org.tokens.access}` },
  });

  await login(page, 'attendee', 'password123');

  const snapshot = page
    .waitForEvent('websocket', (ws) => ws.url().includes(`/ws/seats/${id}/`))
    .then((ws) => ws.waitForEvent('framereceived'));
  await page.goto(`/events/${id}/group`);
  const frame = await snapshot;
  expect(String(frame.payload)).toContain('"type": "snapshot"');
});

test('sign-up code is queued for the worker, not sent in the request', async ({ request }) => {
  const response = await request.post('/api/v1/auth/register/send-code/', {
    data: { email: `e2e-${Date.now()}@example.com` },
  });
  expect(response.status()).toBe(200);
  // DEBUG + console email backend: the code is shown to the developer.
  expect((await body<Schemas['SendCodeResponse']>(response)).dev_code).toMatch(/^\d{6}$/);
});
