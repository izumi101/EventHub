import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests against the full Docker Compose stack
 * (nginx + Django/Daphne + worker + Postgres + Redis), started with the
 * development .env (DEBUG, mock payments, demo data):
 *
 *   docker compose --env-file .env.example up -d --build --wait
 *   E2E_BASE_URL=http://localhost:4200 npx playwright test
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  timeout: 60_000,
  retries: process.env['CI'] ? 1 : 0,
  reporter: process.env['CI'] ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env['E2E_BASE_URL'] || 'http://localhost:4200',
    trace: 'retain-on-failure',
    ...devices['Desktop Chrome'],
    launchOptions: process.env['PW_CHROMIUM_PATH'] ? { executablePath: process.env['PW_CHROMIUM_PATH'] } : {},
  },
});
