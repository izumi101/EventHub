import { expect, Page, test } from '@playwright/test';

// Demo data from `seed_data` (DJANGO_SEED_DATA=1 in .env.example).
const PAID_ONLINE_EVENT = 'Online Django REST Workshop';

async function login(page: Page, username: string, password: string) {
  await page.goto('/login');
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);
  const [response] = await Promise.all([
    page.waitForResponse(r => r.url().includes('/api/auth/login/')),
    page.click('button[type="submit"]'),
  ]);
  expect(response.status()).toBe(200);
}

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => {
    // CSP violations and runtime errors show up as console errors.
    if (m.type() !== 'error') return;
    // "No seat map for this event" is an expected 404 the checkout handles.
    if (m.text().startsWith('Failed to load resource') && m.location().url.endsWith('/seat_map/')) return;
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
  const events = await page.request.get('/api/events/?search=Django');
  const id = (await events.json()).results[0].id;
  const token = await page.evaluate(() => localStorage.getItem('access_token'));
  const anonymous = await (await page.request.get(`/api/events/${id}/`, { headers: {} })).json();
  const holder = await (await page.request.get(`/api/events/${id}/`, {
    headers: { Authorization: `Bearer ${token}` },
  })).json();
  expect(anonymous.online_link).toBe('');
  expect(holder.online_link).toContain('meet.example.com');

  expect(errors).toEqual([]);
});

test('seat map updates arrive over the WebSocket through nginx', async ({ page }) => {
  const events = await (await page.request.get('/api/events/?search=Startup')).json();
  const id = events.results[0].id;

  // The demo data has no seat maps: the organizer creates one (400 if it exists).
  const org = await (await page.request.post('/api/auth/login/', {
    data: { username: 'organizer', password: 'password123' },
  })).json();
  await page.request.post(`/api/events/${id}/seat-map/create/`, {
    data: { rows: 2, cols: 4, sync_capacity: false },
    headers: { Authorization: `Bearer ${org.tokens.access}` },
  });

  await login(page, 'attendee', 'password123');

  const snapshot = page.waitForEvent('websocket', ws => ws.url().includes(`/ws/seats/${id}/`))
    .then(ws => ws.waitForEvent('framereceived'));
  await page.goto(`/events/${id}/group`);
  const frame = await snapshot;
  expect(String(frame.payload)).toContain('"type": "snapshot"');
});

test('sign-up code is queued for the worker, not sent in the request', async ({ request }) => {
  const response = await request.post('/api/auth/register/send-code/', {
    data: { email: `e2e-${Date.now()}@example.com` },
  });
  expect(response.status()).toBe(200);
  // DEBUG + console email backend: the code is shown to the developer.
  expect((await response.json()).dev_code).toMatch(/^\d{6}$/);
});
