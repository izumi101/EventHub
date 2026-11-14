import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { environment } from '../../environments/environment';
import { LanguageService } from './language.service';

/** Tells our own API which language the user reads, so the backend can localise later. */
export const acceptLanguageInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith(`${environment.apiUrl}/`) || req.headers.has('Accept-Language')) {
    return next(req);
  }
  return next(req.clone({ setHeaders: { 'Accept-Language': inject(LanguageService).lang() } }));
};
