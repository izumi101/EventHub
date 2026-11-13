import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideZoneChangeDetection,
} from '@angular/core';
import {
  provideRouter,
  withComponentInputBinding,
  withInMemoryScrolling,
  withViewTransitions,
} from '@angular/router';
import { provideHttpClient, withInterceptors, withFetch } from '@angular/common/http';
import { routes } from './app.routes';
import { authInterceptor } from './interceptors/auth.interceptor';
import { SeoService } from './services/seo.service';
import { provideI18n } from './i18n/i18n.providers';
import { acceptLanguageInterceptor } from './i18n/accept-language.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(
      routes,
      withComponentInputBinding(),
      withInMemoryScrolling({ scrollPositionRestoration: 'top' }),
      withViewTransitions(),
    ),
    provideHttpClient(withFetch(), withInterceptors([acceptLanguageInterceptor, authInterceptor])),
    provideI18n(),
    // Eagerly instantiate SeoService so its router subscription starts at boot
    provideAppInitializer(() => {
      inject(SeoService);
    }),
  ],
};
