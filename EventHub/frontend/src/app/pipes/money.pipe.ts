import { Pipe, PipeTransform, inject } from '@angular/core';
import { LanguageService } from '../i18n/language.service';

/** Intl locale tags per UI language: Kazakh and Russian amounts use Kazakhstan's conventions. */
const INTL_LOCALE: Record<string, string> = { en: 'en-US', ru: 'ru-KZ', kk: 'kk-KZ' };

/**
 * Formats an amount in the event's own currency: `{{ price | money: event.currency }}`
 * → "$15.00", "KZT 5,000.00" (en) / "5 000,00 ₸" (ru, kk). Prices are charged in the
 * event currency, so the UI must never assume dollars. Impure so it follows the
 * selected language.
 *
 * `{{ price | money: event.currency : 'short' }}` is the compact form for cards and
 * tight layouts: the narrow symbol (₸ instead of "KZT") and no ".00" on whole amounts
 * ("₸12,000", "$25"). Checkout and payment screens keep the exact form.
 */
@Pipe({ name: 'money', standalone: true, pure: false })
export class MoneyPipe implements PipeTransform {
  private readonly language = inject(LanguageService);

  transform(
    value: string | number | null | undefined,
    currency?: string | null,
    format: 'exact' | 'short' = 'exact',
  ): string {
    if (value === null || value === undefined || value === '') return '';
    const amount = typeof value === 'number' ? value : Number(value);
    const code = (currency || 'USD').toUpperCase();
    if (!Number.isFinite(amount)) return `${value} ${code}`;
    const locale = INTL_LOCALE[this.language.lang()] ?? 'en-US';
    const options: Intl.NumberFormatOptions = { style: 'currency', currency: code };
    if (format === 'short') {
      options.currencyDisplay = 'narrowSymbol';
      (options as { trailingZeroDisplay?: string }).trailingZeroDisplay = 'stripIfInteger';
    }
    try {
      return new Intl.NumberFormat(locale, options).format(amount);
    } catch {
      // Unknown ISO code: still show the amount and the code.
      return `${amount.toFixed(2)} ${code}`;
    }
  }
}
