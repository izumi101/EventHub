import { Pipe, PipeTransform } from '@angular/core';

/**
 * Formats an amount in the event's own currency: `{{ price | money: event.currency }}`
 * → "$15.00", "KZT 5,000.00", "¥5,000". Prices are charged in the event
 * currency, so the UI must never assume dollars.
 */
@Pipe({ name: 'money', standalone: true })
export class MoneyPipe implements PipeTransform {
  transform(value: string | number | null | undefined, currency?: string | null): string {
    if (value === null || value === undefined || value === '') return '';
    const amount = typeof value === 'number' ? value : Number(value);
    const code = (currency || 'USD').toUpperCase();
    if (!Number.isFinite(amount)) return `${value} ${code}`;
    try {
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: code }).format(amount);
    } catch {
      // Unknown ISO code: still show the amount and the code.
      return `${amount.toFixed(2)} ${code}`;
    }
  }
}
