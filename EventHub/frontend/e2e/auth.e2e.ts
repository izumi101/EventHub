import { expect, test } from '@playwright/test';
import { createAttendee, DEFAULT_PASSWORD, json, openSignedIn, Schemas, uid } from './support/api';
import { waitForCode } from './support/mail';
import { collectErrors, signInWithPassword, signOut, submitPassword } from './support/ui';

/**
 * Accounts without a second factor: sign-up with the emailed code, sign-in,
 * password reset by email code, password change. Codes are read from the
 * email the outbox worker actually sent (console backend in the worker log).
 */

test('sign up with the emailed verification code, sign out, sign in again', async ({ page }) => {
  const errors = collectErrors(page);
  const username = uid('new');
  const email = `${username}@example.com`;
  const password = 'Signup-pass-1';

  await page.goto('/register');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Username').fill(username);
  await page.getByRole('button', { name: /Continue/ }).click();

  // Step 2: the code from the real email, not the DEBUG hint on the page.
  const code = await waitForCode(email, /Your verification code is:/);
  await page.getByLabel('Verification code').fill(code);
  await page.getByRole('button', { name: /Continue/ }).click();

  await page.getByLabel('First name').fill('Aru');
  await page.getByLabel('Last name').fill('Tester');
  await page.getByRole('button', { name: /Continue/ }).click();

  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByLabel('Confirm password').fill(password);
  await page.getByRole('button', { name: 'Create account' }).click();

  // Signed in right away: the profile shows the new account.
  await expect(page).not.toHaveURL(/\/register/);
  await page.goto('/profile');
  await expect(page.getByText(email).first()).toBeVisible();

  await signOut(page, username);
  await signInWithPassword(page, username, password);
  await page.goto('/profile');
  await expect(page.getByText(email).first()).toBeVisible();
  expect(errors).toEqual([]);
});

test('a wrong sign-up code is refused', async ({ request }) => {
  const email = `${uid('bad')}@example.com`;
  await request.post('/api/v1/auth/register/send-code/', { data: { email } });
  const wrong = await request.post('/api/v1/auth/register/verify-code/', {
    data: { email, code: '000000' },
  });
  expect(wrong.status()).toBe(400);
});

test('reset a forgotten password with the emailed code', async ({ page, request }) => {
  const { account } = await createAttendee(request);
  const newPassword = 'Reset-pass-2';

  await page.goto('/login');
  await page.getByRole('link', { name: 'Forgot password?' }).click();
  await expect(page.getByRole('heading', { name: 'Reset your password' })).toBeVisible();
  await page.getByLabel('Username or email').fill(account.email);
  await page.getByRole('button', { name: 'Send reset code' }).click();

  const code = await waitForCode(account.email, /Your password reset code is:/);
  await page.getByLabel('Reset code').fill(code);
  await page.getByRole('button', { name: 'Verify' }).click();

  await page.getByLabel('New password').fill(newPassword);
  await page.getByLabel('Confirm password').fill(newPassword);
  await page.getByRole('button', { name: 'Save new password' }).click();
  await expect(page.getByText(/Password updated/)).toBeVisible();

  // The old password stops working, the new one signs in.
  expect((await submitPassword(page, account.username, DEFAULT_PASSWORD)).status()).toBe(401);
  await expect(page.getByRole('alert')).toBeVisible();
  await signInWithPassword(page, account.username, newPassword);
});

test('change the password from the profile; other sessions are signed out', async ({
  page,
  request,
}) => {
  const { account, session } = await createAttendee(request);
  const newPassword = 'Changed-pass-3';

  await openSignedIn(page, session, '/profile');
  await page.getByLabel('Current password').fill(account.password);
  await page.getByLabel('New password', { exact: true }).fill(newPassword);
  await page.getByLabel('Repeat new password').fill(newPassword);
  await page.getByRole('button', { name: 'Update password' }).click();
  await expect(page.getByText('Password changed.')).toBeVisible();

  // The refresh token of the session from before the change is revoked.
  const refresh = await request.post('/api/v1/auth/token/refresh/', {
    data: { refresh: session.refresh },
  });
  expect(refresh.status()).toBe(401);

  // The page itself got a fresh pair and stays signed in.
  const profile = await page.request.get('/api/v1/auth/profile/', {
    headers: {
      Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem('access_token'))}`,
    },
  });
  expect((await json<Schemas['User']>(profile)).username).toBe(account.username);

  const old = await request.post('/api/v1/auth/login/', {
    data: { username: account.username, password: account.password },
  });
  expect(old.status()).toBe(401);
  const fresh = await request.post('/api/v1/auth/login/', {
    data: { username: account.username, password: newPassword },
  });
  expect(fresh.status()).toBe(200);
});
