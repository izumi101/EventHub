import { TestBed } from '@angular/core/testing';
import {
  HttpClient,
  HttpErrorResponse,
  provideHttpClient,
  withInterceptors,
} from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Router } from '@angular/router';
import { authInterceptor } from './auth.interceptor';
import { stepUpInterceptor } from './step-up.interceptor';
import { StepUpService } from '../services/step-up.service';
import { environment } from '../../environments/environment';

const API = environment.apiUrl;
const REFUND = `${API}/payments/7/refund/`;
const STEP_UP_403 = {
  body: {
    error: 'Confirm it is you.',
    code: 'mfa_step_up_required',
    methods: ['totp', 'email'],
    max_age: 600,
  },
  init: { status: 403, statusText: 'Forbidden' },
};

describe('stepUpInterceptor', () => {
  let client: HttpClient;
  let http: HttpTestingController;
  let stepUp: StepUpService;

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('access_token', 'old');
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([stepUpInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        { provide: Router, useValue: { url: '/', navigate: vi.fn() } },
      ],
    });
    client = TestBed.inject(HttpClient);
    http = TestBed.inject(HttpTestingController);
    stepUp = TestBed.inject(StepUpService);
  });

  afterEach(() => http.verify());

  /** What the dialog does on success: store the new token, then resolve. */
  const verifyInDialog = (access: string) => {
    localStorage.setItem('access_token', access);
    stepUp.resolve(true);
  };

  it('opens the dialog and retries the request once with the new token', () => {
    let result: unknown;
    client.post(REFUND, { amount: '10.00' }).subscribe((r) => (result = r));

    const first = http.expectOne(REFUND);
    expect(first.request.headers.get('Authorization')).toBe('Bearer old');
    first.flush(STEP_UP_403.body, STEP_UP_403.init);

    expect(stepUp.request()).toEqual({ methods: ['totp', 'email'] });
    verifyInDialog('fresh');

    const retry = http.expectOne(REFUND);
    expect(retry.request.method).toBe('POST');
    expect(retry.request.body).toEqual({ amount: '10.00' });
    expect(retry.request.headers.get('Authorization')).toBe('Bearer fresh');
    retry.flush({ ok: true });

    expect(result).toEqual({ ok: true });
    expect(stepUp.request()).toBeNull();
  });

  it('gives the caller the original 403 when the user cancels', () => {
    let error: HttpErrorResponse | undefined;
    client.post(REFUND, {}).subscribe({ error: (e: HttpErrorResponse) => (error = e) });
    http.expectOne(REFUND).flush(STEP_UP_403.body, STEP_UP_403.init);

    stepUp.resolve(false);

    expect(error?.status).toBe(403);
    expect(stepUp.request()).toBeNull();
    http.expectNone(REFUND);
  });

  it('does not loop when the retried request needs step-up again', () => {
    let error: HttpErrorResponse | undefined;
    client.post(REFUND, {}).subscribe({ error: (e: HttpErrorResponse) => (error = e) });
    http.expectOne(REFUND).flush(STEP_UP_403.body, STEP_UP_403.init);
    verifyInDialog('fresh');
    http.expectOne(REFUND).flush(STEP_UP_403.body, STEP_UP_403.init);

    expect(error?.status).toBe(403);
    expect(stepUp.request()).toBeNull();
  });

  it('shares one dialog between parallel requests and retries both', () => {
    const done: string[] = [];
    client.delete<string>(`${API}/auth/mfa/totp/`).subscribe((v) => done.push(v));
    client.post<string>(`${API}/auth/mfa/recovery-codes/regenerate/`, null).subscribe((v) => {
      done.push(v);
    });
    http.expectOne(`${API}/auth/mfa/totp/`).flush(STEP_UP_403.body, STEP_UP_403.init);
    http
      .expectOne(`${API}/auth/mfa/recovery-codes/regenerate/`)
      .flush(STEP_UP_403.body, STEP_UP_403.init);

    verifyInDialog('fresh');

    http.expectOne(`${API}/auth/mfa/totp/`).flush('A');
    http.expectOne(`${API}/auth/mfa/recovery-codes/regenerate/`).flush('B');
    expect(done.sort()).toEqual(['A', 'B']);
  });

  it('passes other 403s and the step-up endpoint itself through untouched', () => {
    let status = 0;
    client.post(REFUND, {}).subscribe({ error: (e: HttpErrorResponse) => (status = e.status) });
    http
      .expectOne(REFUND)
      .flush({ error: 'Not your event.' }, { status: 403, statusText: 'Forbidden' });
    expect(status).toBe(403);

    let stepUpStatus = 0;
    client
      .post(`${API}/auth/mfa/step-up/`, {})
      .subscribe({ error: (e: HttpErrorResponse) => (stepUpStatus = e.status) });
    http.expectOne(`${API}/auth/mfa/step-up/`).flush(STEP_UP_403.body, STEP_UP_403.init);
    expect(stepUpStatus).toBe(403);
    expect(stepUp.request()).toBeNull();
  });
});
