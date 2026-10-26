import { HttpInterceptorFn, HttpErrorResponse, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';
import { environment } from '../../environments/environment';

/** Only our own API gets the bearer token — never a third-party URL that
 *  merely contains "/api/" somewhere. */
function isOwnApi(url: string): boolean {
  return url.startsWith(`${environment.apiUrl}/`);
}

function withToken(req: HttpRequest<unknown>, token: string | null): HttpRequest<unknown> {
  return token && isOwnApi(req.url)
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  const token = authService.getToken();

  return next(withToken(req, token)).pipe(
    catchError((err: HttpErrorResponse) => {
      // Only attempt refresh for 401 errors on authenticated API requests
      if (
        err.status === 401 &&
        token &&
        isOwnApi(req.url) &&
        !req.url.includes('/auth/token/refresh/') &&
        !req.url.includes('/auth/login/')
      ) {
        // Every request that hits a 401 waits for the same (shared) refresh
        // and is then retried — none of them fails just because another
        // request started the refresh first.
        return authService.refreshToken().pipe(
          switchMap(() => next(withToken(req, authService.getToken()))),
          catchError((refreshErr) => {
            // Refresh failed — full logout
            authService.forceLogout();
            router.navigate(['/login'], {
              queryParams: { returnUrl: router.url }
            });
            return throwError(() => refreshErr);
          })
        );
      }

      return throwError(() => err);
    })
  );
};
