import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Router, provideRouter } from '@angular/router';
import { LoginComponent } from './login.component';
import { authInterceptor } from '../../interceptors/auth.interceptor';
import { PasskeyClient } from '../../utils/passkey-client';
import { I18nTestingModule } from '../../i18n/testing';
import { environment } from '../../../environments/environment';

const API = environment.apiUrl;
const USER = {
  id: 1,
  username: 'organizer',
  email: 'org@example.com',
  first_name: '',
  last_name: '',
  is_staff: false,
  is_superuser: false,
  profile: { role: 'organizer' },
};
const TOKENS = { access: 'access-1', refresh: 'refresh-1' };

function setup() {
  localStorage.clear();
  TestBed.configureTestingModule({
    imports: [LoginComponent, I18nTestingModule],
    providers: [
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor])),
      provideHttpClientTesting(),
      {
        provide: PasskeyClient,
        useValue: { supported: false, cancel: vi.fn(), errorMessage: () => 'x' },
      },
    ],
  });
  const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
  const http = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(LoginComponent);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const render = () => fixture.detectChanges();
  const component = fixture.componentInstance;

  const type = async (selector: string, value: string) => {
    // ngModel registers with its form asynchronously.
    await fixture.whenStable();
    const input = el.querySelector<HTMLInputElement>(selector)!;
    input.value = value;
    input.dispatchEvent(new Event('input'));
    render();
  };
  const click = (text: string) => {
    const button = Array.from(el.querySelectorAll('button')).find((b) =>
      b.textContent.trim().startsWith(text),
    );
    if (!button) throw new Error(`No button "${text}"`);
    button.click();
    render();
  };
  const submit = () => {
    el.querySelector('form')!.dispatchEvent(new Event('submit'));
    render();
  };
  const signIn = (answer: object) => {
    component.username = 'organizer';
    component.password = 'secret-123';
    component.onSubmit();
    const req = http.expectOne(`${API}/auth/login/`);
    expect(req.request.body).toEqual({ username: 'organizer', password: 'secret-123' });
    req.flush(answer);
    render();
  };
  return { http, el, component, navigate, render, type, click, submit, signIn };
}

describe('LoginComponent (sign-in state machine)', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('password only: stores the session and goes to the return URL', () => {
    const t = setup();
    t.signIn({ user: USER, tokens: TOKENS });
    expect(t.component.step()).toBe('password');
    expect(localStorage.getItem('access_token')).toBe('access-1');
    expect(t.navigate).toHaveBeenCalledWith('/');
  });

  it('challenge: sends an email code, verifies it and signs in', async () => {
    const t = setup();
    t.signIn({
      mfa_required: true,
      challenge_token: 'chal-1',
      methods: ['email', 'recovery_code'],
      expires_in: 300,
    });
    expect(t.component.step()).toBe('mfa');
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(t.el.querySelector('h1')!.textContent).toContain("Confirm it's you");

    t.click('Send code');
    const send = t.http.expectOne(`${API}/auth/mfa/login/email/send/`);
    expect(send.request.body).toEqual({ challenge_token: 'chal-1' });
    send.flush({ sent: true, expires_in: 600, resend_in: 60 });
    t.render();
    expect(t.el.textContent).toContain('You can ask for a new code in 60 s.');

    await t.type('input[name="code"]', '123456');
    t.submit();
    const verify = t.http.expectOne(`${API}/auth/mfa/login/verify/`);
    expect(verify.request.body).toEqual({
      challenge_token: 'chal-1',
      method: 'email',
      code: '123456',
    });
    verify.flush({ user: USER, tokens: TOKENS });
    expect(localStorage.getItem('access_token')).toBe('access-1');
    expect(t.navigate).toHaveBeenCalledWith('/');
  });

  it('challenge: a wrong code shows the error and keeps the user on the step', async () => {
    const t = setup();
    t.signIn({ mfa_required: true, challenge_token: 'c', methods: ['totp'], expires_in: 300 });
    await t.type('input[name="code"]', '000000');
    t.submit();
    t.http
      .expectOne(`${API}/auth/mfa/login/verify/`)
      .flush(
        { error: 'That code is not valid. Check it and try again.', code: 'mfa_invalid' },
        { status: 400, statusText: 'Bad Request' },
      );
    t.render();
    expect(t.el.querySelector('[role="alert"]')!.textContent).toContain('not valid');
    expect(t.component.step()).toBe('mfa');
    expect(t.navigate).not.toHaveBeenCalled();
  });

  it('challenge: switching to a recovery code and back to sign-in', () => {
    const t = setup();
    t.signIn({
      mfa_required: true,
      challenge_token: 'c',
      methods: ['totp', 'recovery_code'],
      expires_in: 300,
    });
    t.click('Recovery code');
    expect(t.el.querySelector('label')!.textContent).toContain('Recovery code');
    t.click('Back to sign in');
    expect(t.component.step()).toBe('password');
    expect(t.component.challenge()).toBeNull();
  });

  it('enrollment: email code with the enrollment token, then recovery codes once', async () => {
    const t = setup();
    t.signIn({ mfa_enrollment_required: true, enrollment_token: 'enr-1', expires_in: 900 });
    expect(t.component.step()).toBe('enroll');
    expect(localStorage.getItem('access_token')).toBeNull();

    t.click('Email code');
    t.click('Send code');
    const send = t.http.expectOne(`${API}/auth/mfa/email/send/`);
    expect(send.request.body).toEqual({ purpose: 'enroll' });
    expect(send.request.headers.get('Authorization')).toBe('Bearer enr-1');
    send.flush({ sent: true, expires_in: 600, resend_in: 60 });
    t.render();

    await t.type('input[name="code"]', '654321');
    t.submit();
    const enable = t.http.expectOne(`${API}/auth/mfa/email/enable/`);
    expect(enable.request.headers.get('Authorization')).toBe('Bearer enr-1');
    expect(enable.request.body).toEqual({ code: '654321' });
    enable.flush({
      enabled: true,
      recovery_codes: ['aaaa-bbbb-cccc-dddd', 'eeee-ffff-gggg-hhhh'],
      tokens: TOKENS,
      user: USER,
    });
    t.render();

    expect(t.component.step()).toBe('recovery');
    expect(localStorage.getItem('access_token')).toBe('access-1');
    expect(t.el.textContent).toContain('aaaa-bbbb-cccc-dddd');
    const continueButton = Array.from(t.el.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Continue to EventHub'),
    )!;
    expect(continueButton.disabled).toBe(true);
    const saved = t.el.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    saved.click();
    t.render();
    expect(continueButton.disabled).toBe(false);
    continueButton.click();
    expect(t.navigate).toHaveBeenCalledWith('/');
  });

  it('enrollment: an authenticator app shows the secret and confirms the first code', async () => {
    const t = setup();
    t.signIn({ mfa_enrollment_required: true, enrollment_token: 'enr-2', expires_in: 900 });
    t.click('Authenticator app');
    const setupReq = t.http.expectOne(`${API}/auth/mfa/totp/setup/`);
    expect(setupReq.request.headers.get('Authorization')).toBe('Bearer enr-2');
    setupReq.flush({
      secret: 'JBSWY3DPEHPK3PXP',
      otpauth_uri: 'otpauth://totp/EventHub:organizer?secret=JBSWY3DPEHPK3PXP&issuer=EventHub',
    });
    t.render();
    expect(t.el.textContent).toContain('JBSW Y3DP EHPK 3PXP');

    await t.type('input[name="code"]', '111222');
    t.submit();
    t.http.expectOne(`${API}/auth/mfa/totp/confirm/`).flush({
      enabled: true,
      recovery_codes: ['aaaa-bbbb-cccc-dddd'],
      tokens: TOKENS,
      user: USER,
    });
    t.render();
    expect(t.component.step()).toBe('recovery');
  });

  it('a stored stale session does not override the enrollment token', () => {
    const t = setup();
    localStorage.setItem('access_token', 'stale');
    t.signIn({ mfa_enrollment_required: true, enrollment_token: 'enr-3', expires_in: 900 });
    t.click('Email code');
    t.click('Send code');
    const send = t.http.expectOne(`${API}/auth/mfa/email/send/`);
    expect(send.request.headers.get('Authorization')).toBe('Bearer enr-3');
    send.flush({ sent: true, expires_in: 600, resend_in: 60 });
  });
});
