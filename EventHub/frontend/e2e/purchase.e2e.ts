import { APIResponse, expect, Page, test } from '@playwright/test';
import { createAttendee, Schemas, SEEDED_TOTP_SECRET, signIn } from './support/api';
import { collectErrors, signInWithPassword } from './support/ui';

/** The JSON body of an API response, typed by the OpenAPI contract. */
async function body<T>(response: APIResponse): Promise<T> {
  return (await response.json()) as T;
}

// Demo data from `seed_data` (DJANGO_SEED_DATA=1 in .env.example).
const PAID_ONLINE_EVENT = 'Online Django REST Workshop';

/** The event's card link in the All events grid (the hero and rails repeat titles). */
const cardLink = (page: Page) =>
  page.locator('#all-events').getByRole('link', { name: PAID_ONLINE_EVENT }).first();

test('home page renders, styled, under the CSP', async ({ page }) => {
  const errors = collectErrors(page);
  const response = await page.goto('/');
  expect(response?.headers()['content-security-policy']).toContain("script-src 'self'");
  await expect(cardLink(page)).toBeVisible();
  // The stylesheet applied (critical-CSS inlining is off for the CSP).
  const background = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(background).not.toBe('rgba(0, 0, 0, 0)');
  expect(errors).toEqual([]);
});

test('attendee buys a paid ticket and gets the online link', async ({ page, request }) => {
  const errors = collectErrors(page);
  // A new attendee each run, so the spec can run again on the same stack.
  const { account } = await createAttendee(request);
  await signInWithPassword(page, account.username, account.password);

  await page.goto('/');
  await cardLink(page).click();
  await page.getByRole('button', { name: /Get tickets/ }).click();
  await page.getByRole('button', { name: /Proceed to payment/ }).click();

  // Mock payments (DEBUG + PAYMENTS_MOCK_MODE=1) confirm on the server first.
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

  // The demo data has no seat maps: the organizer creates one (400 if it
  // exists). The seeded organizer must use 2FA: the stack is seeded with the
  // TOTP secret in E2E_MFA_TOTP_SECRET (DJANGO_SEED_MFA_TOTP_SECRET).
  const org = await signIn(page.request, {
    username: 'organizer',
    email: '',
    password: 'password123',
    totpSecret: SEEDED_TOTP_SECRET,
  });
  await page.request.post(`/api/v1/events/${id}/seat-map/create/`, {
    data: { rows: 2, cols: 4, sync_capacity: false },
    headers: { Authorization: `Bearer ${org.access}` },
  });

  await signInWithPassword(page, 'attendee', 'password123');

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
