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
import { stepUpInterceptor } from './interceptors/step-up.interceptor';
import { SeoService } from './services/seo.service';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(
      routes,
      withComponentInputBinding(),
      withInMemoryScrolling({ scrollPositionRestoration: 'top' }),
      withViewTransitions(),
    ),
    // stepUpInterceptor first: its retry goes through authInterceptor (fresh token).
    provideHttpClient(withFetch(), withInterceptors([stepUpInterceptor, authInterceptor])),
    // Eagerly instantiate SeoService so its router subscription starts at boot
    provideAppInitializer(() => {
      inject(SeoService);
    }),
  ],
};
