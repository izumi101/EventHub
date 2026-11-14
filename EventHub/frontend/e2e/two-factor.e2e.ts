import { expect, Locator, Page, test } from '@playwright/test';
import { createUnenrolledOrganizer } from './support/api';
import { waitForCode } from './support/mail';
import { freshTotp } from './support/totp';
import { collectErrors, signOut, submitPassword } from './support/ui';

/**
 * Two-factor authentication in the browser (ADR 0002): enrollment at the
 * first sign-in of an organizer, recovery codes, sign-in with an email code,
 * the step-up dialog, an authenticator app with a computed code, and a
 * recovery code. Each test uses a new organizer created by the admin.
 */

const EMAIL_CODE = /Your EventHub code is:/;

/** Read the recovery codes the page shows once, confirm they were saved, continue. */
async function keepRecoveryCodes(page: Page, continueLabel: string): Promise<string[]> {
  const list = page.getByRole('list', { name: 'Recovery codes' });
  await expect(list.getByRole('listitem')).toHaveCount(10);
  const codes = (await list.getByRole('listitem').allTextContents()).map((c) => c.trim());
  await page.getByLabel('I saved my recovery codes.').check();
  await page.getByRole('button', { name: continueLabel }).click();
  return codes;
}

/** "Send code", read the code from the email sent after the click, type it in. */
async function sendAndEnterEmailCode(scope: Page | Locator, email: string) {
  const since = new Date();
  await scope.getByRole('button', { name: 'Send code' }).click();
  // Sent: the button turns into "Resend code", locked by the countdown.
  await expect(scope.getByRole('button', { name: 'Resend code' })).toBeDisabled();
  await expect(scope.getByText(/You can ask for a new code in \d+ s\./)).toBeVisible();
  const code = await waitForCode(email, EMAIL_CODE, { since });
  await scope.getByLabel('Code', { exact: true }).fill(code);
}

test('organizer: email-code enrollment, recovery codes, email sign-in, step-up dialog', async ({
  page,
  request,
}) => {
  test.setTimeout(240_000);
  const errors = collectErrors(page);
  const account = await createUnenrolledOrganizer(request);

  // First sign-in: the role must use 2FA, so the page asks to set it up.
  const first = await submitPassword(page, account.username, account.password);
  expect(first.status()).toBe(200);
  await expect(
    page.getByRole('heading', { name: 'Set up two-factor authentication' }),
  ).toBeVisible();
  await page.getByRole('button', { name: /Email code/ }).click();
  await sendAndEnterEmailCode(page, account.email);
  await page.getByRole('button', { name: 'Turn on email codes' }).click();

  await expect(page.getByRole('heading', { name: 'Save your recovery codes' })).toBeVisible();
  const codes = await keepRecoveryCodes(page, 'Continue to EventHub');
  expect(new Set(codes).size).toBe(10);
  await expect(page).not.toHaveURL(/\/login/);

  // Next sign-in: password, then an email code.
  await signOut(page, account.username);
  await submitPassword(page, account.username, account.password);
  await expect(page.getByRole('heading', { name: "Confirm it's you" })).toBeVisible();
  await sendAndEnterEmailCode(page, account.email);
  const [verified] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/auth/mfa/login/verify/')),
    page.getByRole('button', { name: 'Sign in', exact: true }).click(),
  ]);
  expect(verified.status()).toBe(200);
  await expect(page).not.toHaveURL(/\/login/);

  // Step-up: once the proof is older than MFA_STEP_UP_MAX_AGE_SECONDS (45 s
  // on the test stack), regenerating recovery codes opens "Confirm it's you",
  // and the original request is retried after the check.
  await page.goto('/profile/security');
  await expect(page.getByRole('heading', { name: 'Security' })).toBeVisible();
  await page.waitForTimeout(Number(process.env['E2E_STEP_UP_MAX_AGE_SECONDS'] ?? 45) * 1000 + 2000);
  await page.getByRole('button', { name: 'Generate new codes' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Continue' }).click();

  const stepUp = page.getByRole('dialog', { name: "Confirm it's you" });
  await expect(stepUp).toBeVisible();
  await sendAndEnterEmailCode(stepUp, account.email);
  const [regenerated] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/mfa/recovery-codes/regenerate/') && r.status() === 200,
    ),
    stepUp.getByRole('button', { name: 'Confirm' }).click(),
  ]);
  expect(regenerated.ok()).toBe(true);
  await expect(page.getByRole('heading', { name: 'Your new recovery codes' })).toBeVisible();
  const fresh = (
    await page.getByRole('list', { name: 'Recovery codes' }).getByRole('listitem').allTextContents()
  ).map((c) => c.trim());
  expect(fresh).toHaveLength(10);
  expect(fresh.filter((c) => codes.includes(c))).toEqual([]);
  expect(errors).toEqual([]);
});

test('organizer: authenticator-app enrollment with a computed code, then a recovery code', async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  const account = await createUnenrolledOrganizer(request);

  await submitPassword(page, account.username, account.password);
  await page.getByRole('button', { name: /Authenticator app/ }).click();
  await expect(page.getByRole('img', { name: 'QR code for your authenticator app' })).toBeVisible();
  const key = page.getByLabel('Setup key');
  const secret = ((await key.inputValue().catch(() => null)) ?? (await key.textContent()) ?? '')
    .replace(/\s+/g, '')
    .trim();
  expect(secret).toMatch(/^[A-Z2-7]{16,}$/);
  await page.getByLabel('Code', { exact: true }).fill(await freshTotp(account.username, secret));
  await page.getByRole('button', { name: 'Turn on authenticator app' }).click();

  const codes = await keepRecoveryCodes(page, 'Continue to EventHub');
  await expect(page).not.toHaveURL(/\/login/);
  await signOut(page, account.username);

  // Lost phone: sign in with one of the recovery codes instead.
  await submitPassword(page, account.username, account.password);
  await expect(page.getByText('Enter the 6-digit code from your authenticator app.')).toBeVisible();
  await page.getByRole('button', { name: 'Recovery code' }).click();
  await page.getByLabel('Recovery code').fill(codes[0]);
  const [verified] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/auth/mfa/login/verify/')),
    page.getByRole('button', { name: 'Sign in', exact: true }).click(),
  ]);
  expect(verified.status()).toBe(200);
  await expect(page).not.toHaveURL(/\/login/);

  // A recovery code works once.
  const again = await request.post('/api/v1/auth/login/', {
    data: { username: account.username, password: account.password },
  });
  const challenge = (await again.json()) as { challenge_token: string };
  const reuse = await request.post('/api/v1/auth/mfa/login/verify/', {
    data: { challenge_token: challenge.challenge_token, method: 'recovery_code', code: codes[0] },
  });
  expect(reuse.status()).toBe(400);
});
