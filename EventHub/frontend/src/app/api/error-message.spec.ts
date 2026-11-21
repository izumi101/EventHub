import { HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { errorMessage, retryAfterSeconds } from './error-message';

/** Echoes the key (and params) so each branch is identified exactly. */
const lang = {
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
};

const http = (status: number, error: unknown = null, headers?: Record<string, string>) =>
  new HttpErrorResponse({ status, error, headers: new HttpHeaders(headers) });

describe('errorMessage', () => {
  const login = { fallback: 'INVALID', unauthorized: 'INVALID', fields: ['detail'] };

  it('401 is always the invalid-credentials text, whatever the body says', () => {
    expect(errorMessage(http(401, { error: 'Invalid credentials' }), lang, login)).toBe('INVALID');
    expect(errorMessage(http(401), lang, login)).toBe('INVALID');
  });

  it('400 uses a specific server message, else the fallback', () => {
    expect(errorMessage(http(400, { detail: 'Account locked.' }), lang, login)).toBe(
      'Account locked.',
    );
    expect(errorMessage(http(400, { username: ['Required'] }), lang, login)).toBe('INVALID');
    expect(errorMessage(http(400), lang, login)).toBe('INVALID');
  });

  it('401 without `unauthorized` falls back to the server message, then the fallback', () => {
    const opts = { fallback: 'FAILED', fields: ['error'] };
    expect(errorMessage(http(401, { error: 'Token expired' }), lang, opts)).toBe('Token expired');
    expect(errorMessage(http(401), lang, opts)).toBe('FAILED');
  });

  it('429 includes the wait from the Retry-After header', () => {
    const err = http(429, { detail: 'Request was throttled.' }, { 'Retry-After': '42' });
    expect(errorMessage(err, lang, login)).toBe('httpError.tooManyAttemptsWait:{"seconds":42}');
  });

  it('429 without a usable Retry-After has no number and never shows server text', () => {
    const body = { detail: 'Request was throttled. Expected available in 42 seconds.' };
    expect(errorMessage(http(429, body), lang, login)).toBe('httpError.tooManyAttempts');
    expect(errorMessage(http(429, body, { 'Retry-After': 'soon' }), lang, login)).toBe(
      'httpError.tooManyAttempts',
    );
    expect(errorMessage(http(429, body, { 'Retry-After': '0' }), lang, login)).toBe(
      'httpError.tooManyAttempts',
    );
  });

  it('status 0 means there is no connection', () => {
    expect(errorMessage(http(0), lang, login)).toBe('httpError.noConnection');
  });

  it('5xx is "temporarily unavailable" and never shows server text', () => {
    for (const status of [500, 502, 503, 504]) {
      const err = http(status, { detail: 'FATAL: remaining connection slots are reserved' });
      expect(errorMessage(err, lang, login)).toBe('httpError.unavailable');
    }
    expect(errorMessage(http(500, '<html>oops</html>'), lang, login)).toBe('httpError.unavailable');
  });

  it('other 4xx show a server message when allowed, else the domain fallback', () => {
    expect(errorMessage(http(403, { detail: 'Account disabled.' }), lang, login)).toBe(
      'Account disabled.',
    );
    expect(errorMessage(http(404), lang, { fallback: 'NOT_FOUND' })).toBe('NOT_FOUND');
    expect(errorMessage(http(409, { detail: 'x' }), lang, { fallback: 'CONFLICT' })).toBe(
      'CONFLICT',
    );
    expect(errorMessage(http(409, { detail: 'x' }), lang)).toBe('httpError.generic');
  });

  it('errors without an HTTP status, and odd statuses, get the generic text', () => {
    expect(errorMessage(new Error('boom'), lang, login)).toBe('httpError.generic');
    expect(errorMessage(undefined, lang)).toBe('httpError.generic');
    expect(errorMessage(http(302), lang, login)).toBe('httpError.generic');
  });

  it('400 and 401 default to the generic text without options', () => {
    expect(errorMessage(http(400), lang)).toBe('httpError.generic');
    expect(errorMessage(http(401), lang)).toBe('httpError.generic');
  });
});

describe('retryAfterSeconds', () => {
  it('reads whole seconds from the header, case-insensitively', () => {
    expect(retryAfterSeconds(http(429, null, { 'retry-after': ' 30 ' }))).toBe(30);
  });

  it('falls back to a numeric retry_after in the body', () => {
    expect(retryAfterSeconds(http(429, { retry_after: 41.2 }))).toBe(42);
  });

  it('prefers the header over the body', () => {
    expect(retryAfterSeconds(http(429, { retry_after: 99 }, { 'Retry-After': '7' }))).toBe(7);
  });

  it('is undefined when nothing usable is present', () => {
    expect(retryAfterSeconds(http(429))).toBeUndefined();
    expect(retryAfterSeconds(http(429, { retry_after: 0 }))).toBeUndefined();
    expect(retryAfterSeconds({ status: 429, headers: {} })).toBeUndefined();
    expect(retryAfterSeconds(null)).toBeUndefined();
  });
});
