import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { SecuritySettingsComponent } from './security-settings.component';
import { authInterceptor } from '../../interceptors/auth.interceptor';
import { stepUpInterceptor } from '../../interceptors/step-up.interceptor';
import { ModalService } from '../../services/modal.service';
import { ToastService } from '../../services/toast.service';
import { StepUpService } from '../../services/step-up.service';
import { MfaStatus } from '../../services/mfa.service';
import { PasskeyClient } from '../../utils/passkey-client';
import { I18nTestingModule } from '../../i18n/testing';
import { environment } from '../../../environments/environment';

const API = `${environment.apiUrl}/auth/mfa`;

function status(overrides: Partial<MfaStatus> = {}): MfaStatus {
  return {
    enabled: true,
    required: true,
    totp_enabled: true,
    totp_confirmed_at: '2026-11-01T10:00:00Z',
    email_enabled: true,
    email_confirmed_at: '2026-11-02T10:00:00Z',
    email_allowed: true,
    passkeys: [
      {
        id: 5,
        name: 'Laptop',
        created_at: '2026-11-03T10:00:00Z',
        last_used_at: null,
        backed_up: false,
      },
    ],
    recovery_codes_remaining: 8,
    methods: ['totp', 'webauthn', 'email', 'recovery_code'],
    step_up_max_age: 600,
    step_up_valid_until: null,
    ...overrides,
  };
}

async function setup(initial: MfaStatus = status(), confirmAnswer = true) {
  localStorage.clear();
  localStorage.setItem('access_token', 'tok');
  const modal = { open: vi.fn().mockResolvedValue(confirmAnswer) };
  const toast = { success: vi.fn(), error: vi.fn() };
  TestBed.configureTestingModule({
    imports: [SecuritySettingsComponent, I18nTestingModule],
    providers: [
      provideRouter([]),
      provideHttpClient(withInterceptors([stepUpInterceptor, authInterceptor])),
      provideHttpClientTesting(),
      { provide: ModalService, useValue: modal },
      { provide: ToastService, useValue: toast },
      { provide: PasskeyClient, useValue: { supported: true, cancel: vi.fn() } },
    ],
  });
  const http = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(SecuritySettingsComponent);
  fixture.detectChanges();
  http.expectOne(`${API}/status/`).flush(initial);
  fixture.detectChanges();
  await fixture.whenStable();
  const el = fixture.nativeElement as HTMLElement;
  const render = () => fixture.detectChanges();
  /** Click the button whose text or aria-label starts with `text`, then let the confirm resolve. */
  const click = async (text: string) => {
    const button = Array.from(el.querySelectorAll('button')).find(
      (b) =>
        b.textContent.trim().startsWith(text) ||
        (b.getAttribute('aria-label') ?? '').startsWith(text),
    );
    if (!button) throw new Error(`No button "${text}"`);
    button.click();
    await fixture.whenStable();
    render();
  };
  return { http, el, modal, toast, render, click, fixture };
}

describe('SecuritySettingsComponent', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('lists the factors of the account', async () => {
    const { el } = await setup();
    const text = el.textContent;
    expect(text).toContain('Two-factor authentication');
    expect(text).toContain('Required for your account.');
    expect(text).toContain('Laptop');
    expect(text).toContain('8 unused codes left.');
    // Required: no "turn off everything" button.
    expect(text).not.toContain('Turn off two-factor authentication');
  });

  it('removes the authenticator app after confirmation', async () => {
    const { http, click, modal, toast } = await setup();
    await click('Remove');
    expect(modal.open).toHaveBeenCalled();
    const req = http.expectOne(`${API}/totp/`);
    expect(req.request.method).toBe('DELETE');
    req.flush(status({ totp_enabled: false, totp_confirmed_at: null }));
    expect(toast.success).toHaveBeenCalledWith('Authenticator app removed.');
  });

  it('does nothing when the confirmation is declined', async () => {
    const { http, click } = await setup(status(), false);
    await click('Turn off');
    http.expectNone(`${API}/email/disable/`);
  });

  it('goes through step-up before a destructive action and retries it', async () => {
    const { http, click, toast, render } = await setup();
    await click('Turn off');
    http.expectOne(`${API}/email/disable/`).flush(
      {
        error: 'Confirm it is you.',
        code: 'mfa_step_up_required',
        methods: ['totp'],
        max_age: 600,
      },
      { status: 403, statusText: 'Forbidden' },
    );
    const stepUp = TestBed.inject(StepUpService);
    expect(stepUp.request()?.methods).toEqual(['totp']);
    localStorage.setItem('access_token', 'stepped-up');
    stepUp.resolve(true);
    const retry = http.expectOne(`${API}/email/disable/`);
    expect(retry.request.headers.get('Authorization')).toBe('Bearer stepped-up');
    retry.flush(status({ email_enabled: false, email_confirmed_at: null }));
    render();
    expect(toast.success).toHaveBeenCalledWith('Email codes turned off.');
  });

  it('shows no error toast when the user cancels the step-up dialog', async () => {
    const { http, click, toast } = await setup();
    await click('Remove passkey Laptop');
    http
      .expectOne(`${API}/webauthn/credentials/5/`)
      .flush(
        { error: 'Confirm it is you.', code: 'mfa_step_up_required', methods: ['totp'] },
        { status: 403, statusText: 'Forbidden' },
      );
    TestBed.inject(StepUpService).resolve(false);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('renames a passkey', async () => {
    const { http, el, click, render, fixture } = await setup();
    await click('Rename passkey Laptop');
    await fixture.whenStable();
    const input = el.querySelector<HTMLInputElement>('#passkey-name-5')!;
    input.value = 'Work laptop';
    input.dispatchEvent(new Event('input'));
    render();
    await click('Save');
    const req = http.expectOne(`${API}/webauthn/credentials/5/`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ name: 'Work laptop' });
    req.flush(status());
  });

  it('regenerates recovery codes and shows them once', async () => {
    const { http, el, click, render } = await setup();
    await click('Generate new codes');
    http
      .expectOne(`${API}/recovery-codes/regenerate/`)
      .flush({ recovery_codes: ['abcd-efgh-ijkm-npqr'] });
    // The page reloads the status afterwards.
    http.expectOne(`${API}/status/`).flush(status({ recovery_codes_remaining: 10 }));
    render();
    expect(el.textContent).toContain('abcd-efgh-ijkm-npqr');
    expect(el.textContent).toContain('Your new recovery codes');
  });

  it('lets an attendee without 2FA turn on email codes', async () => {
    const { el, click } = await setup(
      status({
        enabled: false,
        required: false,
        totp_enabled: false,
        totp_confirmed_at: null,
        email_enabled: false,
        email_confirmed_at: null,
        passkeys: [],
        recovery_codes_remaining: 0,
        methods: [],
      }),
    );
    expect(el.textContent).toContain('Off. Turn on at least one method below.');
    await click('Turn on');
    expect(el.textContent).toContain('Turn on email codes');
    expect(el.textContent).toContain("We'll send a 6-digit code");
  });

  it('hides email codes when the policy does not allow them for the account', async () => {
    const { el } = await setup(status({ email_enabled: false, email_allowed: false }));
    expect(el.textContent).toContain('Not available for your account');
    expect(
      Array.from(el.querySelectorAll('button')).some((b) => b.textContent.trim() === 'Turn on'),
    ).toBe(false);
  });
});
