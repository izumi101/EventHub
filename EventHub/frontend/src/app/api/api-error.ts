/**
 * Reading failed API calls without `any`.
 *
 * HttpClient reports failures as an HttpErrorResponse whose `error` is the
 * parsed JSON body. The backend answers with DRF-style bodies: `{ "error": "…" }`,
 * `{ "detail": "…" }` or per-field lists such as `{ "code": ["…"] }`. These
 * helpers check the shape structurally (not with `instanceof`), so they also
 * accept the plain `{ error: … }` objects that tests and interceptors throw.
 */

/** The JSON object body of a failed request, or null when there is none. */
export function apiErrorBody(err: unknown): Readonly<Record<string, unknown>> | null {
  if (typeof err !== 'object' || err === null || !('error' in err)) return null;
  const body = err.error;
  return typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : null;
}

/**
 * The first usable message among `fields` of the error body, in order, else
 * `fallback`. A field counts when it is a non-empty string or a list whose
 * first item is one (DRF validation errors are lists of messages).
 */
export function apiErrorMessage(err: unknown, fallback: string, ...fields: string[]): string {
  const body = apiErrorBody(err);
  if (body) {
    for (const field of fields) {
      const value = body[field];
      const message: unknown = Array.isArray(value) ? value[0] : value;
      if (typeof message === 'string' && message) return message;
    }
  }
  return fallback;
}

/** The HTTP status of a failed request (0 for network errors), if known. */
export function apiErrorStatus(err: unknown): number | undefined {
  if (typeof err !== 'object' || err === null || !('status' in err)) return undefined;
  return typeof err.status === 'number' ? err.status : undefined;
}
