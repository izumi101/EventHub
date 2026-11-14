import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { Observable } from 'rxjs';
import { apiErrorMessage } from '../../api/api-error';
import { isStepUpRequired } from '../../interceptors/step-up.interceptor';
import { FactorAdded, MfaService, MfaStatus, Passkey } from '../../services/mfa.service';
import { ModalService } from '../../services/modal.service';
import { ToastService } from '../../services/toast.service';
import { PasskeyClient } from '../../utils/passkey-client';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from '../../i18n/language.service';
import { LocalDatePipe, PluralPipe } from '../../i18n/locale.pipes';
import { EnrollMethod, MfaEnrollComponent } from '../mfa/mfa-enroll.component';
import { RecoveryCodesComponent } from '../mfa/recovery-codes.component';

/**
 * Profile → Security: second factors of the signed-in user. Removing a
 * factor, regenerating recovery codes and (when a factor exists) adding one
 * are step-up protected by the API; the step-up interceptor asks for a factor
 * and retries, so this page just calls the endpoints.
 */
@Component({
  selector: 'app-security-settings',
  standalone: true,
  imports: [
    FormsModule,
    RouterModule,
    MfaEnrollComponent,
    RecoveryCodesComponent,
    TranslocoPipe,
    LocalDatePipe,
    PluralPipe,
  ],
  template: `
    <div class="page-root">
      <div class="container max-w-2xl py-8">
        <div class="mb-7">
          <a routerLink="/profile" class="text-xs text-primary hover:underline">{{
            'profile.back' | transloco
          }}</a>
          <p class="kicker mt-3 mb-2">{{ 'profile.account' | transloco }}</p>
          <h1 class="text-3xl font-semibold text-foreground">{{ 'security.title' | transloco }}</h1>
          <p class="text-sm text-muted-foreground mt-1.5">
            {{ 'security.intro' | transloco }}
          </p>
        </div>

        @if (loading()) {
          <div class="card p-8 flex items-center justify-center gap-3 text-muted-foreground">
            <span class="spinner" aria-hidden="true"></span>
            <span class="text-sm">{{ 'security.loading' | transloco }}</span>
          </div>
        } @else if (loadError()) {
          <div role="alert" class="note note-error">{{ loadError() }}</div>
        } @else if (status(); as s) {
          <!-- Summary -->
          <section class="card p-5 mb-4 flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h2 class="text-sm font-semibold text-foreground">
                {{ 'security.tfaTitle' | transloco }}
              </h2>
              <p class="text-xs text-muted-foreground mt-0.5">
                @if (s.enabled) {
                  {{ 'security.tfaOn' | transloco }}
                } @else {
                  {{ 'security.tfaOff' | transloco }}
                }
                @if (s.required) {
                  {{ 'security.tfaRequired' | transloco }}
                }
              </p>
            </div>
            <span class="badge" [class]="s.enabled ? 'badge-success' : 'badge-warning'">
              {{ (s.enabled ? 'security.badgeOn' : 'security.badgeOff') | transloco }}
            </span>
          </section>

          @if (recoveryCodes(); as codes) {
            <section class="card p-5 mb-4" aria-labelledby="new-codes-title">
              <h2 id="new-codes-title" class="text-sm font-semibold text-foreground mb-3">
                {{ 'security.newCodesTitle' | transloco }}
              </h2>
              <app-recovery-codes
                [codes]="codes"
                [continueLabel]="'common.done' | transloco"
                (done)="closeCodes()"
              />
            </section>
          }

          @if (adding(); as method) {
            <section class="card p-5 mb-4" aria-labelledby="adding-title">
              <h2 id="adding-title" class="text-sm font-semibold text-foreground mb-3">
                {{ addingTitleKeys[method] | transloco }}
              </h2>
              <app-mfa-enroll
                [startWith]="method"
                (completed)="onAdded($event)"
                (cancelled)="adding.set(null)"
              />
            </section>
          }

          <div class="card divide-y divide-border">
            <!-- Authenticator app -->
            <section class="p-5 flex items-start justify-between gap-4 flex-wrap">
              <div class="min-w-0">
                <h2 class="text-sm font-semibold text-foreground">
                  {{ 'mfa.method.totp' | transloco }}
                </h2>
                <p class="text-xs text-muted-foreground mt-0.5">
                  @if (s.totp_enabled) {
                    {{
                      'security.onSince'
                        | transloco: { date: (s.totp_confirmed_at | localDate: 'mediumDate') }
                    }}
                  } @else {
                    {{ 'security.totpHint' | transloco }}
                  }
                </p>
              </div>
              @if (s.totp_enabled) {
                <button
                  type="button"
                  class="btn btn-sm btn-secondary"
                  [disabled]="busy()"
                  (click)="removeTotp()"
                >
                  {{ 'common.remove' | transloco }}
                </button>
              } @else {
                <button
                  type="button"
                  class="btn btn-sm btn-primary"
                  [disabled]="busy() || !!adding()"
                  (click)="adding.set('totp')"
                >
                  {{ 'security.setUp' | transloco }}
                </button>
              }
            </section>

            <!-- Email codes -->
            <section class="p-5 flex items-start justify-between gap-4 flex-wrap">
              <div class="min-w-0">
                <h2 class="text-sm font-semibold text-foreground">
                  {{ 'security.emailTitle' | transloco }}
                </h2>
                <p class="text-xs text-muted-foreground mt-0.5">
                  @if (s.email_enabled) {
                    {{
                      'security.onSince'
                        | transloco: { date: (s.email_confirmed_at | localDate: 'mediumDate') }
                    }}
                  } @else if (!s.email_allowed) {
                    {{ 'security.emailUnavailable' | transloco }}
                  } @else {
                    {{ 'security.emailHint' | transloco }}
                  }
                </p>
              </div>
              @if (s.email_enabled) {
                <button
                  type="button"
                  class="btn btn-sm btn-secondary"
                  [disabled]="busy()"
                  (click)="disableEmail()"
                >
                  {{ 'security.turnOff' | transloco }}
                </button>
              } @else if (s.email_allowed) {
                <button
                  type="button"
                  class="btn btn-sm btn-primary"
                  [disabled]="busy() || !!adding()"
                  (click)="adding.set('email')"
                >
                  {{ 'security.turnOn' | transloco }}
                </button>
              }
            </section>

            <!-- Passkeys -->
            <section class="p-5">
              <div class="flex items-start justify-between gap-4 flex-wrap">
                <div class="min-w-0">
                  <h2 class="text-sm font-semibold text-foreground">
                    {{ 'security.passkeysTitle' | transloco }}
                  </h2>
                  <p class="text-xs text-muted-foreground mt-0.5">
                    @if (passkeys.supported) {
                      {{ 'security.passkeysHint' | transloco }}
                    } @else {
                      {{ 'security.passkeysUnsupported' | transloco }}
                    }
                  </p>
                </div>
                @if (passkeys.supported) {
                  <button
                    type="button"
                    class="btn btn-sm btn-primary"
                    [disabled]="busy() || !!adding()"
                    (click)="adding.set('webauthn')"
                  >
                    {{ 'security.addPasskeyButton' | transloco }}
                  </button>
                }
              </div>
              @if (s.passkeys.length) {
                <ul class="mt-4 space-y-2">
                  @for (key of s.passkeys; track key.id) {
                    <li
                      class="flex items-center justify-between gap-3 flex-wrap rounded-md border border-border px-3 py-2"
                    >
                      @if (renaming() === key.id) {
                        <form
                          class="flex items-center gap-2 flex-1 min-w-0"
                          (ngSubmit)="saveName(key)"
                          novalidate
                        >
                          <label class="sr-only" [attr.for]="'passkey-name-' + key.id">{{
                            'security.passkeyName' | transloco
                          }}</label>
                          <input
                            [id]="'passkey-name-' + key.id"
                            name="name"
                            class="input h-8 flex-1 min-w-0"
                            maxlength="64"
                            [(ngModel)]="newName"
                          />
                          <button
                            type="submit"
                            class="btn btn-sm btn-primary"
                            [disabled]="busy() || !newName.trim()"
                          >
                            {{ 'common.save' | transloco }}
                          </button>
                          <button
                            type="button"
                            class="btn btn-sm btn-ghost"
                            (click)="renaming.set(null)"
                          >
                            {{ 'common.cancel' | transloco }}
                          </button>
                        </form>
                      } @else {
                        <div class="min-w-0">
                          <p class="text-sm font-medium text-foreground truncate">
                            {{ key.name }}
                            @if (key.backed_up) {
                              <span class="badge badge-info ml-1">{{
                                'security.synced' | transloco
                              }}</span>
                            }
                          </p>
                          <p class="text-xs text-muted-foreground">
                            {{
                              'security.addedOn'
                                | transloco: { date: (key.created_at | localDate: 'mediumDate') }
                            }}
                            @if (key.last_used_at) {
                              {{
                                'security.lastUsed'
                                  | transloco
                                    : { date: (key.last_used_at | localDate: 'mediumDate') }
                              }}
                            }
                          </p>
                        </div>
                        <div class="flex gap-2">
                          <button
                            type="button"
                            class="btn btn-sm btn-ghost"
                            [disabled]="busy()"
                            (click)="startRename(key)"
                            [attr.aria-label]="
                              'security.renameAria' | transloco: { name: key.name }
                            "
                          >
                            {{ 'security.rename' | transloco }}
                          </button>
                          <button
                            type="button"
                            class="btn btn-sm btn-secondary"
                            [disabled]="busy()"
                            (click)="removePasskey(key)"
                            [attr.aria-label]="
                              'security.removeAria' | transloco: { name: key.name }
                            "
                          >
                            {{ 'common.remove' | transloco }}
                          </button>
                        </div>
                      }
                    </li>
                  }
                </ul>
              }
            </section>

            <!-- Recovery codes -->
            <section class="p-5 flex items-start justify-between gap-4 flex-wrap">
              <div class="min-w-0">
                <h2 class="text-sm font-semibold text-foreground">
                  {{ 'mfa.recovery.listLabel' | transloco }}
                </h2>
                <p class="text-xs text-muted-foreground mt-0.5">
                  @if (s.enabled) {
                    {{ 'security.codesLeft' | tPlural: s.recovery_codes_remaining }}
                  } @else {
                    {{ 'security.codesCreatedWhen' | transloco }}
                  }
                </p>
              </div>
              @if (s.enabled) {
                <button
                  type="button"
                  class="btn btn-sm btn-secondary"
                  [disabled]="busy()"
                  (click)="regenerateCodes()"
                >
                  {{ 'security.generateCodes' | transloco }}
                </button>
              }
            </section>
          </div>

          @if (s.enabled && !s.required) {
            <section class="card p-5 mt-4 flex items-start justify-between gap-4 flex-wrap">
              <div class="min-w-0">
                <h2 class="text-sm font-semibold text-foreground">
                  {{ 'security.disableTitle' | transloco }}
                </h2>
                <p class="text-xs text-muted-foreground mt-0.5">
                  {{ 'security.disableHint' | transloco }}
                </p>
              </div>
              <button
                type="button"
                class="btn btn-sm btn-danger"
                [disabled]="busy()"
                (click)="disableAll()"
              >
                {{ 'security.turnOff' | transloco }}
              </button>
            </section>
          }
        }
      </div>
    </div>
  `,
})
export class SecuritySettingsComponent implements OnInit {
  private readonly mfa = inject(MfaService);
  private readonly modal = inject(ModalService);
  private readonly toast = inject(ToastService);
  protected readonly passkeys = inject(PasskeyClient);

  readonly status = signal<MfaStatus | null>(null);
  readonly loading = signal(true);
  readonly loadError = signal('');
  readonly busy = signal(false);
  readonly adding = signal<EnrollMethod | null>(null);
  readonly renaming = signal<number | null>(null);
  readonly recoveryCodes = signal<string[] | null>(null);
  newName = '';

  private readonly lang = inject(LanguageService);

  protected readonly addingTitleKeys: Record<EnrollMethod, string> = {
    totp: 'security.addTotp',
    email: 'security.addEmail',
    webauthn: 'security.addPasskey',
  };

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.mfa.status().subscribe({
      next: (s) => {
        this.status.set(s);
        this.loading.set(false);
      },
      error: (err: unknown) => {
        this.loading.set(false);
        this.loadError.set(apiErrorMessage(err, this.lang.t('security.loadFailed'), 'error'));
      },
    });
  }

  onAdded(res: FactorAdded): void {
    this.adding.set(null);
    this.toast.success(this.lang.t('security.methodAdded'));
    if (res.recovery_codes?.length) this.recoveryCodes.set(res.recovery_codes);
    this.reload();
  }

  closeCodes(): void {
    this.recoveryCodes.set(null);
  }

  async removeTotp(): Promise<void> {
    if (
      !(await this.confirm(
        this.lang.t('security.removeTotpTitle'),
        this.lang.t('security.removeTotpMessage'),
      ))
    )
      return;
    this.act(this.mfa.totpRemove(), this.lang.t('security.totpRemoved'));
  }

  async disableEmail(): Promise<void> {
    if (
      !(await this.confirm(
        this.lang.t('security.disableEmailTitle'),
        this.lang.t('security.disableEmailMessage'),
      ))
    )
      return;
    this.act(this.mfa.emailDisable(), this.lang.t('security.emailOff'));
  }

  async removePasskey(key: Passkey): Promise<void> {
    if (
      !(await this.confirm(
        this.lang.t('security.removePasskeyTitle', { name: key.name }),
        this.lang.t('security.removePasskeyMessage'),
      ))
    )
      return;
    this.act(this.mfa.passkeyRemove(key.id), this.lang.t('security.passkeyRemoved'));
  }

  startRename(key: Passkey): void {
    this.renaming.set(key.id);
    this.newName = key.name;
  }

  saveName(key: Passkey): void {
    const name = this.newName.trim();
    if (!name) return;
    this.act(this.mfa.passkeyRename(key.id, name), this.lang.t('security.passkeyRenamed'), () =>
      this.renaming.set(null),
    );
  }

  async regenerateCodes(): Promise<void> {
    if (
      !(await this.confirm(
        this.lang.t('security.regenTitle'),
        this.lang.t('security.regenMessage'),
        false,
      ))
    )
      return;
    this.busy.set(true);
    this.mfa.regenerateRecoveryCodes().subscribe({
      next: (res) => {
        this.busy.set(false);
        this.recoveryCodes.set(res.recovery_codes);
        this.reload();
      },
      error: (err: unknown) => this.fail(err, this.lang.t('security.regenFailed')),
    });
  }

  async disableAll(): Promise<void> {
    if (
      !(await this.confirm(
        this.lang.t('security.disableAllTitle'),
        this.lang.t('security.disableAllMessage'),
      ))
    )
      return;
    this.act(this.mfa.disableAll(), this.lang.t('security.disabled'));
  }

  private confirm(title: string, message: string, destructive = true): Promise<boolean> {
    return this.modal.open({
      title,
      message,
      confirmText: this.lang.t('common.continue'),
      isDestructive: destructive,
    });
  }

  private act(call: Observable<MfaStatus>, success: string, after?: () => void): void {
    this.busy.set(true);
    call.subscribe({
      next: (s) => {
        this.busy.set(false);
        this.status.set(s);
        this.toast.success(success);
        after?.();
      },
      error: (err: unknown) => this.fail(err, this.lang.t('security.actionFailed')),
    });
  }

  private fail(err: unknown, fallback: string): void {
    this.busy.set(false);
    // A cancelled step-up dialog is the user's choice, not an error to report.
    if (isStepUpRequired(err)) return;
    this.toast.error(apiErrorMessage(err, fallback, 'error', 'detail'));
  }
}
