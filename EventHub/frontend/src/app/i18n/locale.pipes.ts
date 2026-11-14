import { formatDate, formatNumber } from '@angular/common';
import { Pipe, PipeTransform, inject } from '@angular/core';
import { LanguageService } from './language.service';

type DateInput = string | number | Date | null | undefined;

/**
 * `date` that follows the selected language. Impure on purpose: the pipe is cheap
 * and must re-run when the language signal changes. English keeps 12-hour times
 * (`h:mm a`); Russian and Kazakh use 24-hour clocks.
 */
@Pipe({ name: 'localDate', standalone: true, pure: false })
export class LocalDatePipe implements PipeTransform {
  private readonly language = inject(LanguageService);

  transform(value: DateInput, format = 'mediumDate'): string | null {
    if (value === null || value === undefined || value === '') return null;
    const localised = this.language.lang() === 'en' ? format : format.replace(/h:mm a/g, 'HH:mm');
    return formatDate(value, localised, this.language.locale());
  }
}

/** `number` that follows the selected language's separators. */
@Pipe({ name: 'localNumber', standalone: true, pure: false })
export class LocalNumberPipe implements PipeTransform {
  private readonly language = inject(LanguageService);

  transform(value: number | string | null | undefined, digitsInfo?: string): string | null {
    if (value === null || value === undefined || value === '') return null;
    return formatNumber(Number(value), this.language.locale(), digitsInfo);
  }
}

/** `{{ 'booking.seats' | tPlural: count }}` picks the plural form for the active language. */
@Pipe({ name: 'tPlural', standalone: true, pure: false })
export class PluralPipe implements PipeTransform {
  private readonly language = inject(LanguageService);

  transform(key: string, count: number, params?: Record<string, unknown>): string {
    return this.language.plural(key, count, params);
  }
}
