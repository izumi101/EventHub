import { HttpClient } from '@angular/common/http';
import {
  EnvironmentProviders,
  Injectable,
  inject,
  isDevMode,
  makeEnvironmentProviders,
  provideAppInitializer,
} from '@angular/core';
import { Translation, TranslocoLoader, provideTransloco } from '@jsverse/transloco';
import { LanguageService } from './language.service';
import { DEFAULT_LANG, SUPPORTED_LANGS } from './languages';
import { registerAppLocales } from './locales';

@Injectable({ providedIn: 'root' })
export class TranslocoHttpLoader implements TranslocoLoader {
  private readonly http = inject(HttpClient);

  getTranslation(lang: string) {
    return this.http.get<Translation>(`assets/i18n/${lang}.json`);
  }
}

/** Runtime i18n: Transloco, locale data, and language resolution before first render. */
export function provideI18n(): EnvironmentProviders {
  return makeEnvironmentProviders([
    provideTransloco({
      config: {
        availableLangs: [...SUPPORTED_LANGS],
        defaultLang: DEFAULT_LANG,
        fallbackLang: DEFAULT_LANG,
        reRenderOnLangChange: true,
        prodMode: !isDevMode(),
        missingHandler: { useFallbackTranslation: true, logMissingKey: isDevMode() },
      },
      loader: TranslocoHttpLoader,
    }),
    provideAppInitializer(() => {
      registerAppLocales();
      return inject(LanguageService).init();
    }),
  ]);
}
