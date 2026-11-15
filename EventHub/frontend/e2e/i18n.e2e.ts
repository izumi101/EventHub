import { expect, Page, Request, test } from '@playwright/test';
import { collectErrors } from './support/ui';

/**
 * Languages (docs/I18N.md): the ҚАЗ / РУС / ENG switcher in the header
 * changes the UI at runtime, `<html lang>`, the language sent to the API
 * and the stored choice, which survives a reload.
 */

const CASES = [
  {
    button: 'Русский',
    short: 'РУС',
    lang: 'ru',
    discover: 'Афиша',
    title: 'Находите события, которые важны',
  },
  {
    button: 'Қазақша',
    short: 'ҚАЗ',
    lang: 'kk',
    discover: 'Шолу',
    title: 'Маңызды іс-шараларды табыңыз',
  },
  {
    button: 'English',
    short: 'ENG',
    lang: 'en',
    discover: 'Discover',
    title: 'Discover Events That Matter',
  },
] as const;

/** The main navigation inside the page header (consumer top nav). */
const nav = (page: Page) => page.getByRole('banner').getByRole('navigation', { name: /./ }).first();

/** The next request to our API, with the language header the SPA set. */
function nextApiRequest(page: Page): Promise<Request> {
  return page.waitForRequest((r) => new URL(r.url()).pathname.startsWith('/api/v1/'));
}

test('switch ҚАЗ / РУС / ENG: text, <html lang>, Accept-Language, kept after reload', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'English' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');

  for (const lang of CASES) {
    await page.getByRole('button', { name: lang.button }).click();
    await expect(page.getByRole('button', { name: lang.button })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.getByRole('button', { name: lang.button })).toHaveText(lang.short);
    await expect(page.locator('html')).toHaveAttribute('lang', lang.lang);
    await expect(nav(page).getByRole('link', { name: lang.discover })).toBeVisible();
    await expect(page).toHaveTitle(new RegExp(lang.title));

    // Persisted and applied before the first render after a reload; the
    // first API calls of the reloaded app already carry the language.
    const request = nextApiRequest(page);
    await page.reload();
    expect((await request).headers()['accept-language']).toBe(lang.lang);
    await expect(page.locator('html')).toHaveAttribute('lang', lang.lang);
    await expect(nav(page).getByRole('link', { name: lang.discover })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem('eventhub.lang'))).toBe(lang.lang);
  }
  expect(errors).toEqual([]);
});

test.describe('a Russian browser', () => {
  test.use({ locale: 'ru-RU' });

  test('gets Russian on the first visit', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('html')).toHaveAttribute('lang', 'ru');
    await expect(page.getByRole('button', { name: 'Русский' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });
});
