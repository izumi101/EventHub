import { Translation, TranslocoTestingModule, TranslocoTestingOptions } from '@jsverse/transloco';
import en from '../../assets/i18n/en.json';
import kk from '../../assets/i18n/kk.json';
import ru from '../../assets/i18n/ru.json';
import { DEFAULT_LANG, SUPPORTED_LANGS } from './languages';
import { registerAppLocales } from './locales';

const langs: Record<string, Translation> = { en, ru, kk };

/**
 * Test helper: the real translations (all three languages) served synchronously.
 * Add `I18nTestingModule` to `TestBed.configureTestingModule({ imports: [...] })`;
 * English is active by default, call `LanguageService.setLang()` to switch.
 */
export function i18nTestingOptions(): TranslocoTestingOptions {
  registerAppLocales();
  return {
    langs,
    translocoConfig: {
      availableLangs: [...SUPPORTED_LANGS],
      defaultLang: DEFAULT_LANG,
      fallbackLang: DEFAULT_LANG,
      reRenderOnLangChange: true,
    },
    preloadLangs: true,
  };
}

export const I18nTestingModule = TranslocoTestingModule.forRoot(i18nTestingOptions());
