import { expect, Page } from '@playwright/test';

/** Errors the browser reports while a spec runs (CSP violations show up as console errors). */
export function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    const text = m.text();
    // Expected HTTP errors the app handles itself (404 seat map, 403 step-up,
    // 400 business-rule refusals) are logged by the browser as failed loads.
    if (text.startsWith('Failed to load resource')) return;
    errors.push(`console: ${text} (${m.location().url})`);
  });
  return errors;
}

/** The password step of the sign-in form; resolves with the API answer. */
export async function submitPassword(page: Page, username: string, password: string) {
  await page.goto('/login');
  await page.getByLabel('Username or email').fill(username);
  await page.getByLabel('Password', { exact: true }).fill(password);
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/auth/login/')),
    page.getByRole('button', { name: 'Sign in', exact: true }).click(),
  ]);
  return response;
}

/** Sign in with a password only (accounts without 2FA) and wait until signed in. */
export async function signInWithPassword(page: Page, username: string, password: string) {
  const response = await submitPassword(page, username, password);
  expect(response.status()).toBe(200);
  await expect(page).not.toHaveURL(/\/login/);
}

/** Sign out through the profile menu and its confirmation. */
export async function signOut(page: Page, username: string) {
  await page.getByRole('button', { name: username }).click();
  await page.getByRole('button', { name: 'Sign Out' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Sign Out' }).click();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('access_token'))).toBeNull();
}

/**
 * On the Freedom Pay emulator's hosted page: fill a test card with its
 * "Use" button and pay. The emulator then redirects back to the SPA.
 */
export async function payWithTestCard(page: Page, pan: string) {
  await expect(page.getByRole('heading', { name: 'Pay by card' })).toBeVisible();
  await page.getByText(/^Test cards/).click();
  await page.getByRole('button', { name: `Use card ${pan}` }).click();
  await expect(page.getByLabel('Card number')).toHaveValue(pan);
  // The card form's submit ("Pay 6750.00 KZT"), not the one-click "Pay (success)" scenario.
  await page.getByRole('button', { name: /^Pay \d/ }).click();
}
