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
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from '../../i18n/language.service';

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
  imports: [FormsModule, NgTemplateOutlet, TranslocoPipe],
  template: `
    @switch (step()) {
      @case ('choose') {
        <div
          class="space-y-3"
          role="group"
          [attr.aria-label]="'mfa.enroll.chooseGroup' | transloco"
        >
          @if (offer().includes('totp')) {
            <button type="button" class="enroll-option" (click)="go('totp')">
              <span class="font-semibold text-foreground">{{ 'mfa.method.totp' | transloco }}</span>
              <span class="text-xs text-muted-foreground">
                {{ 'mfa.enroll.totpDesc' | transloco }}
              </span>
            </button>
          }
          @if (offer().includes('webauthn') && passkeys.supported) {
            <button type="button" class="enroll-option" (click)="go('webauthn')">
              <span class="font-semibold text-foreground">{{
                'mfa.method.webauthn' | transloco
              }}</span>
              <span class="text-xs text-muted-foreground">
                {{ 'mfa.enroll.passkeyDesc' | transloco }}
              </span>
            </button>
          }
          @if (offer().includes('email')) {
            <button type="button" class="enroll-option" (click)="go('email')">
              <span class="font-semibold text-foreground">{{
                'mfa.method.email' | transloco
              }}</span>
              <span class="text-xs text-muted-foreground">
                {{ 'mfa.enroll.emailDesc' | transloco }}
              </span>
            </button>
          }
        </div>
      }

      @case ('email') {
        <form class="space-y-4" (ngSubmit)="confirmEmail()" novalidate>
          <p class="text-sm text-muted-foreground">
            {{ 'mfa.enroll.emailIntro' | transloco }}
          </p>
          <div class="flex items-center gap-3 flex-wrap">
            <button
              type="button"
              class="btn btn-secondary btn-sm"
              (click)="sendEmail()"
              [disabled]="busy() || countdown.seconds() > 0"
            >
              {{ (emailSent() ? 'mfa.resendCode' : 'mfa.sendCode') | transloco }}
            </button>
            <span class="text-xs text-muted-foreground" aria-live="polite">
              @if (countdown.seconds() > 0) {
                {{ 'mfa.resendIn' | transloco: { seconds: countdown.seconds() } }}
              } @else if (emailSent()) {
                {{ 'mfa.codeSent' | transloco }}
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
            {{ 'mfa.enroll.turnOnEmail' | transloco }}
          </button>
          <ng-container *ngTemplateOutlet="back" />
        </form>
      }

      @case ('totp') {
        <form class="space-y-4" (ngSubmit)="confirmTotp()" novalidate>
          @if (totp(); as setup) {
            <ol class="text-sm text-muted-foreground space-y-1 list-decimal pl-5">
              <li>{{ 'mfa.enroll.totpStep1' | transloco }}</li>
              <li>{{ 'mfa.enroll.totpStep2' | transloco }}</li>
              <li>{{ 'mfa.enroll.totpStep3' | transloco }}</li>
            </ol>
            <div class="flex flex-col items-center gap-3">
              @if (qr()) {
                <img
                  [src]="qr()"
                  width="192"
                  height="192"
                  class="rounded-md border border-border bg-white p-2"
                  [alt]="'mfa.enroll.qrAlt' | transloco"
                />
              }
              <div class="text-center">
                <p class="text-xs text-muted-foreground mb-1" id="totp-secret-label">
                  {{ 'mfa.enroll.setupKey' | transloco }}
                </p>
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
              {{ 'mfa.enroll.turnOnTotp' | transloco }}
            </button>
          } @else {
            <ng-container *ngTemplateOutlet="feedback" />
            @if (busy()) {
              <p class="text-sm text-muted-foreground flex items-center gap-2">
                <span class="spinner spinner-sm" aria-hidden="true"></span>
                {{ 'mfa.enroll.preparing' | transloco }}
              </p>
            }
          }
          <ng-container *ngTemplateOutlet="back" />
        </form>
      }

      @case ('webauthn') {
        <form class="space-y-4" (ngSubmit)="createPasskey()" novalidate>
          <p class="text-sm text-muted-foreground">
            {{ 'mfa.enroll.passkeyIntro' | transloco }}
          </p>
          <div>
            <label for="passkey-name" class="block text-sm font-medium text-foreground mb-1.5">
              {{ 'mfa.enroll.nameOptional' | transloco }}
            </label>
            <input
              id="passkey-name"
              name="passkeyName"
              class="input"
              maxlength="64"
              [placeholder]="'mfa.enroll.namePlaceholder' | transloco"
              [(ngModel)]="passkeyName"
            />
          </div>
          <ng-container *ngTemplateOutlet="feedback" />
          <button type="submit" class="btn btn-primary btn-full" [disabled]="busy()">
            @if (busy()) {
              <span class="spinner spinner-sm" aria-hidden="true"></span>
              {{ 'mfa.verifyForm.waitingForPasskey' | transloco }}
            } @else {
              {{ 'mfa.enroll.createPasskey' | transloco }}
            }
          </button>
          <ng-container *ngTemplateOutlet="back" />
        </form>
      }
    }

    <ng-template #codeField>
      <div>
        <label for="enroll-code" class="block text-sm font-medium text-foreground mb-1.5">{{
          'mfa.code' | transloco
        }}</label>
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
          {{ 'mfa.enroll.chooseAnother' | transloco }}
        </button>
      } @else {
        <button type="button" class="btn btn-ghost btn-sm" (click)="cancelled.emit()">
          {{ 'common.cancel' | transloco }}
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
  private readonly lang = inject(LanguageService);
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
      error: (err: unknown) => this.fail(err, this.lang.t('mfa.enroll.sendFailed')),
    });
  }

  confirmEmail(): void {
    if (!this.code.trim() || this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    this.mfa.emailEnable(this.code.trim(), this.enrollmentToken()).subscribe({
      next: (res) => this.finish(res),
      error: (err: unknown) => this.fail(err, this.lang.t('mfa.enroll.invalidCode')),
    });
  }

  confirmTotp(): void {
    if (!this.code.trim() || this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    this.mfa.totpConfirm(this.code.trim(), this.enrollmentToken()).subscribe({
      next: (res) => this.finish(res),
      error: (err: unknown) => this.fail(err, this.lang.t('mfa.enroll.invalidCode')),
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
          ? apiErrorMessage(err, this.lang.t('mfa.enroll.passkeyStartFailed'), 'error')
          : this.passkeys.errorMessage(err),
      );
      return;
    }
    this.mfa.passkeyRegisterVerify(credential, name, this.enrollmentToken()).subscribe({
      next: (res) => this.finish(res),
      error: (err: unknown) => this.fail(err, this.lang.t('mfa.enroll.passkeyRegisterFailed')),
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
      error: (err: unknown) => this.fail(err, this.lang.t('mfa.enroll.totpStartFailed')),
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
