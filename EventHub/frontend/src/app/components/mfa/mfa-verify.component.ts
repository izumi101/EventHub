import { Component, computed, effect, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Observable, firstValueFrom } from 'rxjs';
import { apiErrorMessage } from '../../api/api-error';
import {
  EmailCodeSent,
  FactorProof,
  METHOD_LABELS,
  MfaMethod,
  WebAuthnJson,
  isApiError,
  mfaErrorCode,
  mfaRetryAfter,
} from '../../services/mfa.service';
import { Countdown } from '../../utils/countdown';
import { PasskeyClient } from '../../utils/passkey-client';

/** What the form needs from its context (sign-in or step-up). */
export interface MfaVerifier {
  sendEmailCode: () => Observable<EmailCodeSent>;
  passkeyOptions: () => Observable<WebAuthnJson>;
  verify: (proof: FactorProof) => Observable<unknown>;
}

let nextId = 0;

/** Preferred order when choosing the first method to show. */
const ORDER: MfaMethod[] = ['totp', 'webauthn', 'email', 'recovery_code'];

/**
 * Prove one second factor: authenticator code, email code (with send /
 * resend countdown), passkey or recovery code. Shared by the sign-in page and
 * the step-up dialog; emits (verified) with the server's answer.
 */
@Component({
  selector: 'app-mfa-verify',
  standalone: true,
  imports: [FormsModule],
  template: `
    @if (method(); as current) {
      <form (ngSubmit)="submit()" class="space-y-4" novalidate>
        @switch (current) {
          @case ('totp') {
            <p class="text-sm text-muted-foreground">
              Enter the 6-digit code from your authenticator app.
            </p>
          }
          @case ('email') {
            <p class="text-sm text-muted-foreground">
              We email a 6-digit code to the address on your account. It works once and expires in
              10 minutes.
            </p>
          }
          @case ('recovery_code') {
            <p class="text-sm text-muted-foreground">
              Enter one of the recovery codes you saved when you turned on two-factor
              authentication. Each code works once.
            </p>
          }
          @case ('webauthn') {
            <p class="text-sm text-muted-foreground">
              Use the passkey or security key you registered for this account.
            </p>
          }
        }

        @if (current === 'webauthn') {
          @if (!passkeys.supported) {
            <div role="alert" class="note note-warning">
              This browser or connection can't use passkeys (they need https or localhost). Choose
              another method.
            </div>
          }
          <button
            type="button"
            class="btn btn-primary btn-full"
            (click)="usePasskey()"
            [disabled]="busy() || !passkeys.supported"
          >
            @if (busy()) {
              <span class="spinner spinner-sm" aria-hidden="true"></span>
              Waiting for the passkey...
            } @else {
              Use passkey
            }
          </button>
        } @else {
          @if (current === 'email') {
            <div class="flex items-center gap-3 flex-wrap">
              <button
                type="button"
                class="btn btn-secondary btn-sm"
                (click)="sendEmail()"
                [disabled]="sending() || countdown.seconds() > 0"
              >
                {{ emailSent() ? 'Resend code' : 'Send code' }}
              </button>
              <span class="text-xs text-muted-foreground" aria-live="polite">
                @if (countdown.seconds() > 0) {
                  You can ask for a new code in {{ countdown.seconds() }} s.
                } @else if (emailSent()) {
                  Code sent. Check your inbox (and spam).
                }
              </span>
            </div>
          }
          <div>
            <label [attr.for]="inputId" class="block text-sm font-medium text-foreground mb-1.5">
              {{ current === 'recovery_code' ? 'Recovery code' : 'Code' }}
            </label>
            <input
              [id]="inputId"
              name="code"
              class="input font-mono tracking-widest"
              [class.input-error]="!!error()"
              [(ngModel)]="code"
              [attr.inputmode]="current === 'recovery_code' ? 'text' : 'numeric'"
              [attr.maxlength]="current === 'recovery_code' ? 32 : 6"
              [attr.placeholder]="current === 'recovery_code' ? 'xxxx-xxxx-xxxx-xxxx' : '123456'"
              [attr.aria-invalid]="!!error()"
              [attr.aria-describedby]="error() ? inputId + '-error' : null"
              autocomplete="one-time-code"
              autocapitalize="none"
              autocorrect="off"
              spellcheck="false"
            />
          </div>
        }

        @if (error()) {
          <div [id]="inputId + '-error'" role="alert" class="note note-error">{{ error() }}</div>
        }

        @if (current !== 'webauthn') {
          <button
            type="submit"
            class="btn btn-primary btn-full"
            [disabled]="busy() || !code.trim()"
          >
            @if (busy()) {
              <span class="spinner spinner-sm" aria-hidden="true"></span>
              Checking...
            } @else {
              {{ submitLabel() }}
            }
          </button>
        }
      </form>

      @if (otherMethods().length) {
        <div class="mt-5 pt-4 border-t border-border">
          <p class="text-xs text-muted-foreground mb-2" [id]="inputId + '-others'">
            Use another method
          </p>
          <div
            class="flex flex-wrap gap-2"
            role="group"
            [attr.aria-labelledby]="inputId + '-others'"
          >
            @for (m of otherMethods(); track m) {
              <button type="button" class="chip" (click)="choose(m)">{{ labels[m] }}</button>
            }
          </div>
        </div>
      }
    } @else {
      <div role="alert" class="note note-warning">
        No second factor is available for this account. Contact support to regain access.
      </div>
    }
  `,
})
export class MfaVerifyComponent {
  readonly methods = input.required<MfaMethod[]>();
  readonly verifier = input.required<MfaVerifier>();
  readonly submitLabel = input('Verify');
  readonly verified = output<unknown>();

  protected readonly passkeys = inject(PasskeyClient);
  protected readonly labels = METHOD_LABELS;
  protected readonly countdown = new Countdown();
  protected readonly inputId = `mfa-code-${++nextId}`;

  readonly method = signal<MfaMethod | null>(null);
  readonly busy = signal(false);
  readonly sending = signal(false);
  readonly emailSent = signal(false);
  readonly error = signal('');
  code = '';

  protected readonly otherMethods = computed(() =>
    this.sorted().filter((m) => m !== this.method()),
  );

  private readonly sorted = computed(() => ORDER.filter((m) => this.methods().includes(m)));

  constructor() {
    // Start with the first usable method; passkeys only where the browser can.
    effect(() => {
      const available = this.sorted();
      const current = this.method();
      if (current && available.includes(current)) return;
      const preferred = available.find((m) => m !== 'webauthn' || this.passkeys.supported);
      this.method.set(preferred ?? (available.length ? available[0] : null));
    });
  }

  choose(method: MfaMethod): void {
    this.method.set(method);
    this.code = '';
    this.error.set('');
  }

  sendEmail(): void {
    this.sending.set(true);
    this.error.set('');
    this.verifier()
      .sendEmailCode()
      .subscribe({
        next: (res) => {
          this.sending.set(false);
          this.emailSent.set(true);
          this.countdown.start(res.resend_in);
        },
        error: (err: unknown) => {
          this.sending.set(false);
          const wait = mfaRetryAfter(err);
          if (wait) this.countdown.start(wait);
          this.error.set(apiErrorMessage(err, 'Could not send the code. Try again.', 'error'));
        },
      });
  }

  submit(): void {
    const method = this.method();
    const code = this.code.trim();
    if (!method || method === 'webauthn' || !code || this.busy()) return;
    this.run({ method, code });
  }

  async usePasskey(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    let credential: WebAuthnJson;
    try {
      const options = await firstValueFrom(this.verifier().passkeyOptions());
      credential = await this.passkeys.assert(options);
    } catch (err) {
      this.busy.set(false);
      this.error.set(
        isApiError(err)
          ? apiErrorMessage(err, 'Could not start the passkey check.', 'error')
          : this.passkeys.errorMessage(err),
      );
      return;
    }
    this.busy.set(false);
    this.run({ method: 'webauthn', credential });
  }

  private run(proof: FactorProof): void {
    this.busy.set(true);
    this.error.set('');
    this.verifier()
      .verify(proof)
      .subscribe({
        next: (res) => {
          this.busy.set(false);
          this.verified.emit(res);
        },
        error: (err: unknown) => {
          this.busy.set(false);
          this.code = '';
          this.error.set(this.messageFor(err));
        },
      });
  }

  private messageFor(err: unknown): string {
    if (mfaErrorCode(err) === 'mfa_token_invalid') {
      return apiErrorMessage(err, 'This sign-in step has expired. Sign in again.', 'error');
    }
    return apiErrorMessage(err, 'That did not work. Check the code and try again.', 'error');
  }
}
