import { apiErrorBody, apiErrorMessage, apiErrorStatus } from './api-error';

/** The part of `LanguageService` this helper needs (keeps it easy to test). */
export interface Translator {
  t(key: string, params?: Record<string, unknown>): string;
}

export interface ErrorMessageOptions {
  /**
   * Shown for 400 and 401 when the server sent no more specific message
   * (e.g. "Invalid username or password."). Defaults to the generic message.
   */
  fallback?: string;
  /**
   * Body fields that may carry a user-facing message for 4xx answers other
   * than 429, in order of preference. Never read for 5xx or network errors.
   */
  fields?: readonly string[];
  /** When set, every 401 shows this text and the server's own wording is ignored. */
  unauthorized?: string;
}

/**
 * Seconds to wait before retrying, from the `Retry-After` header of the
 * failed response (a whole number of seconds, as DRF sends it), else from a
 * numeric `retry_after` in the body. Undefined when neither is usable.
 */
export function retryAfterSeconds(err: unknown): number | undefined {
  if (typeof err === 'object' && err !== null && 'headers' in err) {
    const headers = err.headers;
    if (typeof headers === 'object' && headers !== null && 'get' in headers) {
      const get = headers.get;
      const raw: unknown =
        typeof get === 'function' ? (get.call(headers, 'Retry-After') as unknown) : undefined;
      if (typeof raw === 'string' && /^\s*\d+\s*$/.test(raw)) {
        const seconds = Number(raw);
        if (seconds > 0) return seconds;
      }
    }
  }
  const fromBody = apiErrorBody(err)?.['retry_after'];
  return typeof fromBody === 'number' && fromBody > 0 ? Math.ceil(fromBody) : undefined;
}

/**
 * One user-facing message for a failed sign-in call, chosen by HTTP status so
 * an outage is never mistaken for a wrong password:
 *  - 0 (network)  → no connection
 *  - 429          → too many attempts, with the wait when the server gave one
 *  - 5xx          → temporarily unavailable (server text is never shown)
 *  - 401          → `options.unauthorized`, else server message, else `fallback`
 *  - other 4xx    → server message from `options.fields`, else `fallback` (400, 403, 404, 409…;
 *                   a client error belongs to the action, so its domain text fits)
 *  - anything else (no status, 3xx…) → generic
 */
export function errorMessage(
  err: unknown,
  lang: Translator,
  options: ErrorMessageOptions = {},
): string {
  const generic = lang.t('httpError.generic');
  const fields = options.fields ?? [];
  const status = apiErrorStatus(err);

  if (status === undefined) return generic;
  if (status === 0) return lang.t('httpError.noConnection');
  if (status === 429) {
    const seconds = retryAfterSeconds(err);
    return seconds
      ? lang.t('httpError.tooManyAttemptsWait', { seconds })
      : lang.t('httpError.tooManyAttempts');
  }
  if (status >= 500) return lang.t('httpError.unavailable');
  if (status === 401 && options.unauthorized) return options.unauthorized;
  if (status >= 400) return apiErrorMessage(err, options.fallback ?? generic, ...fields);
  return generic;
}
