import { registerLocaleData } from '@angular/common';
import localeKk from '@angular/common/locales/kk';
import localeRu from '@angular/common/locales/ru';

let registered = false;

/** Registers Angular locale data for the non-default languages (`en` is built in). */
export function registerAppLocales(): void {
  if (registered) return;
  registerLocaleData(localeRu, 'ru');
  registerLocaleData(localeKk, 'kk');
  registered = true;
}
