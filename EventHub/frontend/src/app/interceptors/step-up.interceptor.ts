import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { apiErrorBody } from '../api/api-error';
import { MfaMethod } from '../services/mfa.service';
import { StepUpService } from '../services/step-up.service';
import { isOwnApi } from './auth.interceptor';

export const STEP_UP_REQUIRED = 'mfa_step_up_required';

/** True for the 403 the API sends when a sensitive action needs a fresh second factor. */
export function isStepUpRequired(err: unknown): boolean {
  return (
    err instanceof HttpErrorResponse &&
    err.status === 403 &&
    apiErrorBody(err)?.['code'] === STEP_UP_REQUIRED
  );
}

function methodsOf(err: HttpErrorResponse): MfaMethod[] {
  const methods = apiErrorBody(err)?.['methods'];
  return Array.isArray(methods) ? (methods as MfaMethod[]) : [];
}

/**
 * Sensitive endpoints answer 403 `mfa_step_up_required` when the session's
 * last second-factor proof is too old. This opens the step-up dialog and, once
 * the user verified a factor (the dialog stores the new access token), sends
 * the original request again — once. If the user cancels, the caller gets the
 * original 403.
 *
 * Registered before authInterceptor, so the retry passes through it and
 * carries the new token.
 */
export const stepUpInterceptor: HttpInterceptorFn = (req, next) => {
  if (!isOwnApi(req.url) || req.url.includes('/auth/mfa/step-up/')) return next(req);
  const stepUp = inject(StepUpService);

  return next(req).pipe(
    catchError((err: unknown) => {
      if (!isStepUpRequired(err)) return throwError(() => err);
      return stepUp
        .confirm(methodsOf(err as HttpErrorResponse))
        .pipe(switchMap((verified) => (verified ? next(req) : throwError(() => err))));
    }),
  );
};
