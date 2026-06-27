import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

let isRefreshing = false;

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  const token = localStorage.getItem('access_token');
  const authReq = (token && req.url.includes('/api/'))
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;

  return next(authReq).pipe(
    catchError((err: HttpErrorResponse) => {
      // Only attempt refresh for 401 errors on authenticated requests
      if (
        err.status === 401 &&
        token &&
        !req.url.includes('/auth/token/refresh/') &&
        !req.url.includes('/auth/login/') &&
        !isRefreshing
      ) {
        isRefreshing = true;

        return authService.refreshToken().pipe(
          switchMap(() => {
            isRefreshing = false;
            // Retry the original request with new token
            const newToken = localStorage.getItem('access_token');
            const retryReq = req.clone({
              setHeaders: { Authorization: `Bearer ${newToken}` }
            });
            return next(retryReq);
          }),
          catchError((refreshErr) => {
            isRefreshing = false;
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
