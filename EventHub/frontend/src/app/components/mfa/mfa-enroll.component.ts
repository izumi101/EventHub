import { Component, OnInit, inject, input, output, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import * as QRCode from 'qrcode';
import { apiErrorMessage } from '../../api/api-error';
import {
  FactorAdded,
  MfaService,
  TotpSetup,
  isApiError,
  mfaErrorCode,
  mfaRetryAfter,
} from '../../services/mfa.service';
import { Countdown } from '../../utils/countdown';
import { PasskeyClient } from '../../utils/passkey-client';

export type EnrollMethod = 'email' | 'totp' | 'webauthn';
type Step = 'choose' | EnrollMethod;

/**
 * Guided set-up of one second factor: email codes (prove the mailbox with a
 * code), an authenticator app (QR code + manual secret + first code) or a
 * passkey. Used at sign-in (with the enrollment token) and in the security
 * settings (with the session; the API may ask for step-up first).
 */
@Component({
  selector: 'app-mfa-enroll',
  standalone: true,
  imports: [FormsModule, NgTemplateOutlet],
  template: `
    @switch (step()) {
      @case ('choose') {
        <div class="space-y-3" role="group" aria-label="Choose a second factor">
          @if (offer().includes('totp')) {
            <button type="button" class="enroll-option" (click)="go('totp')">
              <span class="font-semibold text-foreground">Authenticator app</span>
              <span class="text-xs text-muted-foreground">
                Google Authenticator, 1Password, Authy… Works offline. Recommended.
              </span>
            </button>
          }
          @if (offer().includes('webauthn') && passkeys.supported) {
            <button type="button" class="enroll-option" (click)="go('webauthn')">
              <span class="font-semibold text-foreground">Passkey</span>
              <span class="text-xs text-muted-foreground">
                Face ID, Touch ID, Windows Hello or a security key. Phishing-resistant.
              </span>
            </button>
          }
          @if (offer().includes('email')) {
            <button type="button" class="enroll-option" (click)="go('email')">
              <span class="font-semibold text-foreground">Email code</span>
              <span class="text-xs text-muted-foreground">
                A code sent to your account email at each sign-in. Simplest, but only as safe as
                your mailbox.
              </span>
            </button>
          }
        </div>
      }

      @case ('email') {
        <form class="space-y-4" (ngSubmit)="confirmEmail()" novalidate>
          <p class="text-sm text-muted-foreground">
            We'll send a 6-digit code to the email address on your account. Enter it here to turn on
            email codes.
          </p>
          <div class="flex items-center gap-3 flex-wrap">
            <button
              type="button"
              class="btn btn-secondary btn-sm"
              (click)="sendEmail()"
              [disabled]="busy() || countdown.seconds() > 0"
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
          <ng-container *ngTemplateOutlet="codeField" />
          <ng-container *ngTemplateOutlet="feedback" />
          <button
            type="submit"
            class="btn btn-primary btn-full"
            [disabled]="busy() || !emailSent() || !code.trim()"
          >
            Turn on email codes
          </button>
          <ng-container *ngTemplateOutlet="back" />
        </form>
      }

      @case ('totp') {
        <form class="space-y-4" (ngSubmit)="confirmTotp()" novalidate>
          @if (totp(); as setup) {
            <ol class="text-sm text-muted-foreground space-y-1 list-decimal pl-5">
              <li>Open your authenticator app and add an account.</li>
              <li>Scan the QR code, or type the key below.</li>
              <li>Enter the 6-digit code the app shows.</li>
            </ol>
            <div class="flex flex-col items-center gap-3">
              @if (qr()) {
                <img
                  [src]="qr()"
                  width="192"
                  height="192"
                  class="rounded-md border border-border bg-white p-2"
                  alt="QR code for your authenticator app"
                />
              }
              <div class="text-center">
                <p class="text-xs text-muted-foreground mb-1" id="totp-secret-label">Setup key</p>
                <code
                  class="font-mono text-sm text-foreground break-all select-all"
                  aria-labelledby="totp-secret-label"
                  >{{ groupedSecret(setup.secret) }}</code
                >
              </div>
            </div>
            <ng-container *ngTemplateOutlet="codeField" />
            <ng-container *ngTemplateOutlet="feedback" />
            <button
              type="submit"
              class="btn btn-primary btn-full"
              [disabled]="busy() || !code.trim()"
            >
              Turn on authenticator app
            </button>
          } @else {
            <ng-container *ngTemplateOutlet="feedback" />
            @if (busy()) {
              <p class="text-sm text-muted-foreground flex items-center gap-2">
                <span class="spinner spinner-sm" aria-hidden="true"></span> Preparing...
              </p>
            }
          }
          <ng-container *ngTemplateOutlet="back" />
        </form>
      }

      @case ('webauthn') {
        <form class="space-y-4" (ngSubmit)="createPasskey()" novalidate>
          <p class="text-sm text-muted-foreground">
            Your browser will ask you to create a passkey with this device or a security key.
          </p>
          <div>
            <label for="passkey-name" class="block text-sm font-medium text-foreground mb-1.5">
              Name (optional)
            </label>
            <input
              id="passkey-name"
              name="passkeyName"
              class="input"
              maxlength="64"
              placeholder="e.g. Work laptop"
              [(ngModel)]="passkeyName"
            />
          </div>
          <ng-container *ngTemplateOutlet="feedback" />
          <button type="submit" class="btn btn-primary btn-full" [disabled]="busy()">
            @if (busy()) {
              <span class="spinner spinner-sm" aria-hidden="true"></span>
              Waiting for the passkey...
            } @else {
              Create passkey
            }
          </button>
          <ng-container *ngTemplateOutlet="back" />
        </form>
      }
    }

    <ng-template #codeField>
      <div>
        <label for="enroll-code" class="block text-sm font-medium text-foreground mb-1.5"
          >Code</label
        >
        <input
          id="enroll-code"
          name="code"
          class="input font-mono tracking-widest"
          inputmode="numeric"
          maxlength="6"
          placeholder="123456"
          autocomplete="one-time-code"
          [class.input-error]="!!error()"
          [attr.aria-invalid]="!!error()"
          [(ngModel)]="code"
        />
      </div>
    </ng-template>

    <ng-template #feedback>
      @if (error()) {
        <div role="alert" class="note note-error">{{ error() }}</div>
      }
    </ng-template>

    <ng-template #back>
      @if (canGoBack()) {
        <button type="button" class="btn btn-ghost btn-sm" (click)="backToChoice()">
          Choose another method
        </button>
      } @else {
        <button type="button" class="btn btn-ghost btn-sm" (click)="cancelled.emit()">
          Cancel
        </button>
      }
    </ng-template>
  `,
  styles: [
    `
      .enroll-option {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: 0.25rem;
        width: 100%;
        padding: 0.875rem 1rem;
        text-align: left;
        border: 1px solid var(--border);
        border-radius: var(--radius-sm, 0.5rem);
        background: var(--background);
        transition: border-color 0.15s;
      }
      .enroll-option:hover,
      .enroll-option:focus-visible {
        border-color: var(--primary);
      }
      .enroll-option:focus-visible {
        outline: 2px solid var(--primary);
        outline-offset: 2px;
      }
    `,
  ],
})
export class MfaEnrollComponent implements OnInit {
  /** The login's enrollment token; null when the user has a session. */
  readonly enrollmentToken = input<string | null>(null);
  /** Methods to offer on the first screen. */
  readonly offer = input<EnrollMethod[]>(['totp', 'webauthn', 'email']);
  /** Skip the choice and go straight to one method. */
  readonly startWith = input<EnrollMethod | null>(null);

  readonly completed = output<FactorAdded>();
  readonly cancelled = output();

  private readonly mfa = inject(MfaService);
  protected readonly passkeys = inject(PasskeyClient);
  protected readonly countdown = new Countdown();

  readonly step = signal<Step>('choose');
  readonly busy = signal(false);
  readonly error = signal('');
  readonly emailSent = signal(false);
  readonly totp = signal<TotpSetup | null>(null);
  readonly qr = signal('');
  code = '';
  passkeyName = '';

  ngOnInit(): void {
    const start = this.startWith();
    if (start) this.go(start);
  }

  canGoBack(): boolean {
    return !this.startWith();
  }

  go(step: EnrollMethod): void {
    this.step.set(step);
    this.error.set('');
    this.code = '';
    if (step === 'totp') this.startTotp();
  }

  backToChoice(): void {
    this.step.set('choose');
    this.error.set('');
    this.code = '';
  }

  groupedSecret(secret: string): string {
    return secret.replace(/(.{4})/g, '$1 ').trim();
  }

  sendEmail(): void {
    this.busy.set(true);
    this.error.set('');
    this.mfa.sendEmailCode('enroll', this.enrollmentToken()).subscribe({
      next: (res) => {
        this.busy.set(false);
        this.emailSent.set(true);
        this.countdown.start(res.resend_in);
      },
      error: (err: unknown) => this.fail(err, 'Could not send the code.'),
    });
  }

  confirmEmail(): void {
    if (!this.code.trim() || this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    this.mfa.emailEnable(this.code.trim(), this.enrollmentToken()).subscribe({
      next: (res) => this.finish(res),
      error: (err: unknown) => this.fail(err, 'That code is not valid.'),
    });
  }

  confirmTotp(): void {
    if (!this.code.trim() || this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    this.mfa.totpConfirm(this.code.trim(), this.enrollmentToken()).subscribe({
      next: (res) => this.finish(res),
      error: (err: unknown) => this.fail(err, 'That code is not valid.'),
    });
  }

  async createPasskey(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    const name = this.passkeyName.trim();
    let credential;
    try {
      const options = await firstValueFrom(
        this.mfa.passkeyRegisterOptions(name, this.enrollmentToken()),
      );
      credential = await this.passkeys.create(options);
    } catch (err) {
      this.busy.set(false);
      this.error.set(
        isApiError(err)
          ? apiErrorMessage(err, 'Could not start the passkey set-up.', 'error')
          : this.passkeys.errorMessage(err),
      );
      return;
    }
    this.mfa.passkeyRegisterVerify(credential, name, this.enrollmentToken()).subscribe({
      next: (res) => this.finish(res),
      error: (err: unknown) => this.fail(err, 'The passkey could not be registered.'),
    });
  }

  private startTotp(): void {
    this.totp.set(null);
    this.qr.set('');
    this.busy.set(true);
    this.mfa.totpSetup(this.enrollmentToken()).subscribe({
      next: (setup) => {
        this.busy.set(false);
        this.totp.set(setup);
        QRCode.toDataURL(setup.otpauth_uri, { width: 192, margin: 0 }).then(
          (url) => this.qr.set(url),
          () => this.qr.set(''),
        );
      },
      error: (err: unknown) => this.fail(err, 'Could not start the authenticator set-up.'),
    });
  }

  private finish(res: FactorAdded): void {
    this.busy.set(false);
    this.countdown.stop();
    this.completed.emit(res);
  }

  private fail(err: unknown, fallback: string): void {
    this.busy.set(false);
    this.code = '';
    const wait = mfaRetryAfter(err);
    if (wait && mfaErrorCode(err) === 'mfa_email_throttled') this.countdown.start(wait);
    this.error.set(apiErrorMessage(err, fallback, 'error', 'code', 'detail'));
  }
}
