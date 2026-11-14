import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests against the full Docker Compose stack
 * (nginx + Django/uvicorn + worker + Postgres + Redis + Freedom Pay
 * emulator), started with the development .env (DEBUG, mock payments for
 * USD, the emulator for KZT, demo data). How to run, the environment
 * variables and the isolated QA stack: docs/TEST_REPORT.md.
 *
 *   E2E_BASE_URL=http://localhost:4200 npx playwright test
 *
 * One worker: the specs share one stack (its outbox worker, rate limits and
 * the emulator), and several of them wait on time (TOTP steps, step-up age).
 * Every spec creates its own accounts and events, so order does not matter.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  workers: 1,
  fullyParallel: false,
  retries: process.env['CI'] ? 1 : 0,
  reporter: process.env['CI'] ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env['E2E_BASE_URL'] || 'http://localhost:4200',
    trace: 'retain-on-failure',
    ...devices['Desktop Chrome'],
    // English UI by default; the i18n spec switches languages itself.
    locale: 'en-US',
    launchOptions: process.env['PW_CHROMIUM_PATH']
      ? { executablePath: process.env['PW_CHROMIUM_PATH'] }
      : {},
  },
});
