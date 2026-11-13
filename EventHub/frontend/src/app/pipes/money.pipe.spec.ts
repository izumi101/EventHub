import { TestBed } from '@angular/core/testing';
import { LanguageService } from '../i18n/language.service';
import { I18nTestingModule } from '../i18n/testing';
import { MoneyPipe } from './money.pipe';

describe('MoneyPipe', () => {
  let money: MoneyPipe;
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [I18nTestingModule] });
    money = TestBed.runInInjectionContext(() => new MoneyPipe());
  });
  // Intl puts a non-breaking space between a currency code and the amount.
  const fmt = (value: string | number | null, currency?: string) =>
    money.transform(value, currency).replace(/\u00a0/g, ' ');

  it('formats in the event currency, not always dollars', () => {
    expect(fmt('15', 'USD')).toBe('$15.00');
    expect(fmt(5000, 'kzt')).toBe('KZT 5,000.00');
    expect(fmt('5000', 'JPY')).toBe('¥5,000');
  });

  it('copes with empty values and invalid codes', () => {
    expect(fmt(null, 'USD')).toBe('');
    expect(fmt('12.5', 'dollars')).toBe('12.50 DOLLARS');
    expect(fmt('abc', 'USD')).toBe('abc USD');
  });

  it('shows KZT with the ISO code and thousands separators (en-US Intl has no tenge symbol)', () => {
    expect(fmt('1234567.5', 'KZT')).toBe('KZT 1,234,567.50');
    expect(fmt(0, 'KZT')).toBe('KZT 0.00');
  });

  it('formats negative and zero amounts (refund lines) without losing the sign', () => {
    expect(fmt(-5, 'USD')).toBe('-$5.00');
    expect(fmt(0, 'USD')).toBe('$0.00');
    expect(fmt('-1200.5', 'USD')).toBe('-$1,200.50');
  });

  it('does not invent decimals for zero-decimal currencies (JPY)', () => {
    expect(fmt(1234.56, 'JPY')).toBe('¥1,235');
  });

  it('treats undefined and empty string as no value, and a missing currency as USD', () => {
    expect(money.transform(undefined, 'USD')).toBe('');
    expect(money.transform('', 'USD')).toBe('');
    expect(fmt(10)).toBe('$10.00');
    expect(money.transform(10, null).replace(/\u00a0/g, ' ')).toBe('$10.00');
  });

  it('follows the selected language and keeps the ISO currency correct', async () => {
    const language = TestBed.inject(LanguageService);
    const norm = (v: string) => v.replace(/[\s\u00a0\u202f]/g, ' ');
    await language.setLang('ru');
    expect(norm(money.transform(5000, 'KZT'))).toBe('5 000,00 ₸');
    expect(norm(money.transform(15, 'USD'))).toContain('15,00');
    await language.setLang('kk');
    expect(norm(money.transform(5000, 'KZT'))).toBe('5 000,00 ₸');
    await language.setLang('en');
    expect(norm(money.transform(5000, 'KZT'))).toBe('KZT 5,000.00');
  });
});
