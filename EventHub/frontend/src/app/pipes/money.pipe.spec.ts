import { MoneyPipe } from './money.pipe';

describe('MoneyPipe', () => {
  const money = new MoneyPipe();
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
});
