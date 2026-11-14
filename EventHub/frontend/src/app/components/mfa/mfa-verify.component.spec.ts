import { I18nTestingModule } from '../../i18n/testing';
import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { MfaVerifier, MfaVerifyComponent } from './mfa-verify.component';
import { MfaMethod } from '../../services/mfa.service';
import { PasskeyClient } from '../../utils/passkey-client';

function setup(methods: MfaMethod[], verifier: Partial<MfaVerifier>, passkeysSupported = true) {
  const passkeys = {
    supported: passkeysSupported,
    assert: vi.fn().mockResolvedValue({ id: 'cred' }),
    errorMessage: () => 'The passkey prompt was closed or timed out. Try again.',
  };
  TestBed.configureTestingModule({
    imports: [MfaVerifyComponent, I18nTestingModule],
    providers: [{ provide: PasskeyClient, useValue: passkeys }],
  });
  const fixture = TestBed.createComponent(MfaVerifyComponent);
  const full: MfaVerifier = {
    sendEmailCode: vi.fn(() => of({ sent: true, expires_in: 600, resend_in: 60 })),
    passkeyOptions: vi.fn(() => of({ challenge: 'x' })),
    verify: vi.fn(() => of({ ok: true })),
    ...verifier,
  };
  fixture.componentRef.setInput('methods', methods);
  fixture.componentRef.setInput('verifier', full);
  const verified = vi.fn();
  fixture.componentInstance.verified.subscribe(verified);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const button = (text: string) =>
    Array.from(el.querySelectorAll('button')).find((b) => b.textContent.trim().startsWith(text))!;
  return { fixture, el, verifier: full, verified, passkeys, button };
}

describe('MfaVerifyComponent', () => {
  afterEach(() => vi.useRealTimers());

  it('prefers the authenticator app and offers the other methods', () => {
    const { fixture, el } = setup(['recovery_code', 'email', 'totp'], {});
    expect(fixture.componentInstance.method()).toBe('totp');
    const others = Array.from(el.querySelectorAll('.chip')).map((b) => b.textContent.trim());
    expect(others).toEqual(['Email code', 'Recovery code']);
  });

  it('skips passkeys as the default where the browser cannot use them', () => {
    const { fixture } = setup(['webauthn', 'email'], {}, false);
    expect(fixture.componentInstance.method()).toBe('email');
  });

  it('counts down before an email code can be sent again', () => {
    vi.useFakeTimers();
    const { fixture, el, verifier, button } = setup(['email'], {});
    button('Send code').click();
    fixture.detectChanges();
    expect(verifier.sendEmailCode).toHaveBeenCalledTimes(1);
    expect(button('Resend code').disabled).toBe(true);
    expect(el.textContent).toContain('new code in 60 s');

    vi.advanceTimersByTime(59_000);
    fixture.detectChanges();
    expect(el.textContent).toContain('new code in 1 s');
    vi.advanceTimersByTime(1_000);
    fixture.detectChanges();
    expect(button('Resend code').disabled).toBe(false);
  });

  it('uses the server retry_after when sending is throttled', () => {
    vi.useFakeTimers();
    const throttled = new HttpErrorResponse({
      status: 429,
      error: { error: 'A code was sent recently.', code: 'mfa_email_throttled', retry_after: 42 },
    });
    const { fixture, el, button } = setup(['email'], {
      sendEmailCode: () => throwError(() => throttled),
    });
    button('Send code').click();
    fixture.detectChanges();
    expect(el.querySelector('[role="alert"]')!.textContent).toContain('A code was sent recently.');
    expect(el.textContent).toContain('new code in 42 s');
  });

  it('verifies with a passkey assertion', async () => {
    const { fixture, verifier, verified, passkeys, button } = setup(['webauthn'], {});
    button('Use passkey').click();
    await fixture.whenStable();
    expect(passkeys.assert).toHaveBeenCalledWith({ challenge: 'x' });
    expect(verifier.verify).toHaveBeenCalledWith({
      method: 'webauthn',
      credential: { id: 'cred' },
    });
    expect(verified).toHaveBeenCalledWith({ ok: true });
  });

  it('explains a cancelled passkey prompt', async () => {
    const { fixture, el, passkeys, verifier, button } = setup(['webauthn'], {});
    passkeys.assert.mockRejectedValue(Object.assign(new Error('x'), { name: 'NotAllowedError' }));
    button('Use passkey').click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el.querySelector('[role="alert"]')!.textContent).toContain('closed or timed out');
    expect(verifier.verify).not.toHaveBeenCalled();
  });
});
