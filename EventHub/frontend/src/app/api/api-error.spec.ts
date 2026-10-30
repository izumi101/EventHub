import { HttpErrorResponse } from '@angular/common/http';
import { apiErrorBody, apiErrorMessage, apiErrorStatus } from './api-error';

describe('api-error helpers', () => {
  const http = (status: number, error: unknown) => new HttpErrorResponse({ status, error });

  it('reads the JSON body of an HttpErrorResponse and of plain error objects', () => {
    expect(apiErrorBody(http(400, { error: 'Sold out' }))).toEqual({ error: 'Sold out' });
    expect(apiErrorBody({ error: { detail: 'Nope' } })).toEqual({ detail: 'Nope' });
  });

  it('has no body for non-object payloads and non-HTTP errors', () => {
    expect(apiErrorBody(http(502, '<html>Bad gateway</html>'))).toBeNull();
    expect(apiErrorBody(http(0, null))).toBeNull();
    expect(apiErrorBody(new Error('boom'))).toBeNull();
    expect(apiErrorBody(undefined)).toBeNull();
  });

  it('picks the first non-empty field, in the order given', () => {
    const err = http(400, { detail: '', error: 'Seat taken', code: ['Duplicate code'] });
    expect(apiErrorMessage(err, 'Failed', 'detail', 'error')).toBe('Seat taken');
    expect(apiErrorMessage(err, 'Failed', 'code', 'error')).toBe('Duplicate code');
  });

  it('falls back when no field holds a message', () => {
    expect(apiErrorMessage(http(400, { error: 42, code: [] }), 'Failed', 'error', 'code')).toBe(
      'Failed',
    );
    expect(apiErrorMessage(http(0, null), 'Offline', 'error')).toBe('Offline');
  });

  it('reports the HTTP status when there is one', () => {
    expect(apiErrorStatus(http(404, null))).toBe(404);
    expect(apiErrorStatus(http(0, null))).toBe(0);
    expect(apiErrorStatus({ error: {} })).toBeUndefined();
    expect(apiErrorStatus(null)).toBeUndefined();
  });
});
