import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { Observable } from 'rxjs';
import { apiErrorMessage } from '../../api/api-error';
import { isStepUpRequired } from '../../interceptors/step-up.interceptor';
import { FactorAdded, MfaService, MfaStatus, Passkey } from '../../services/mfa.service';
import { ModalService } from '../../services/modal.service';
import { ToastService } from '../../services/toast.service';
import { PasskeyClient } from '../../utils/passkey-client';
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
  imports: [DatePipe, FormsModule, RouterModule, MfaEnrollComponent, RecoveryCodesComponent],
  template: `
    <div class="page-root">
      <div class="container max-w-2xl py-8">
        <div class="mb-7">
          <a routerLink="/profile" class="text-xs text-primary hover:underline">← Profile</a>
          <p class="kicker mt-3 mb-2">Account</p>
          <h1 class="text-3xl font-semibold text-foreground">Security</h1>
          <p class="text-sm text-muted-foreground mt-1.5">
            Two-factor authentication protects your account even if your password leaks.
          </p>
        </div>

        @if (loading()) {
          <div class="card p-8 flex items-center justify-center gap-3 text-muted-foreground">
            <span class="spinner" aria-hidden="true"></span>
            <span class="text-sm">Loading security settings...</span>
          </div>
        } @else if (loadError()) {
          <div role="alert" class="note note-error">{{ loadError() }}</div>
        } @else if (status(); as s) {
          <!-- Summary -->
          <section class="card p-5 mb-4 flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h2 class="text-sm font-semibold text-foreground">Two-factor authentication</h2>
              <p class="text-xs text-muted-foreground mt-0.5">
                @if (s.enabled) {
                  On. Signing in asks for a second factor.
                } @else {
                  Off. Turn on at least one method below.
                }
                @if (s.required) {
                  Required for your account.
                }
              </p>
            </div>
            <span class="badge" [class]="s.enabled ? 'badge-success' : 'badge-warning'">
              {{ s.enabled ? 'On' : 'Off' }}
            </span>
          </section>

          @if (recoveryCodes(); as codes) {
            <section class="card p-5 mb-4" aria-labelledby="new-codes-title">
              <h2 id="new-codes-title" class="text-sm font-semibold text-foreground mb-3">
                Your new recovery codes
              </h2>
              <app-recovery-codes [codes]="codes" continueLabel="Done" (done)="closeCodes()" />
            </section>
          }

          @if (adding(); as method) {
            <section class="card p-5 mb-4" aria-labelledby="adding-title">
              <h2 id="adding-title" class="text-sm font-semibold text-foreground mb-3">
                {{ addingTitle[method] }}
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
                <h2 class="text-sm font-semibold text-foreground">Authenticator app</h2>
                <p class="text-xs text-muted-foreground mt-0.5">
                  @if (s.totp_enabled) {
                    On since {{ s.totp_confirmed_at | date: 'mediumDate' }}.
                  } @else {
                    6-digit codes from an app such as Google Authenticator or 1Password.
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
                  Remove
                </button>
              } @else {
                <button
                  type="button"
                  class="btn btn-sm btn-primary"
                  [disabled]="busy() || !!adding()"
                  (click)="adding.set('totp')"
                >
                  Set up
                </button>
              }
            </section>

            <!-- Email codes -->
            <section class="p-5 flex items-start justify-between gap-4 flex-wrap">
              <div class="min-w-0">
                <h2 class="text-sm font-semibold text-foreground">Email codes</h2>
                <p class="text-xs text-muted-foreground mt-0.5">
                  @if (s.email_enabled) {
                    On since {{ s.email_confirmed_at | date: 'mediumDate' }}.
                  } @else if (!s.email_allowed) {
                    Not available for your account: use an authenticator app or a passkey.
                  } @else {
                    A code sent to your account email. Simpler, but only as safe as your mailbox.
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
                  Turn off
                </button>
              } @else if (s.email_allowed) {
                <button
                  type="button"
                  class="btn btn-sm btn-primary"
                  [disabled]="busy() || !!adding()"
                  (click)="adding.set('email')"
                >
                  Turn on
                </button>
              }
            </section>

            <!-- Passkeys -->
            <section class="p-5">
              <div class="flex items-start justify-between gap-4 flex-wrap">
                <div class="min-w-0">
                  <h2 class="text-sm font-semibold text-foreground">Passkeys</h2>
                  <p class="text-xs text-muted-foreground mt-0.5">
                    @if (passkeys.supported) {
                      Face ID, Touch ID, Windows Hello or a security key.
                    } @else {
                      This browser or connection can't create passkeys (they need https or
                      localhost).
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
                    Add passkey
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
                          <label class="sr-only" [attr.for]="'passkey-name-' + key.id"
                            >Passkey name</label
                          >
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
                            Save
                          </button>
                          <button
                            type="button"
                            class="btn btn-sm btn-ghost"
                            (click)="renaming.set(null)"
                          >
                            Cancel
                          </button>
                        </form>
                      } @else {
                        <div class="min-w-0">
                          <p class="text-sm font-medium text-foreground truncate">
                            {{ key.name }}
                            @if (key.backed_up) {
                              <span class="badge badge-info ml-1">Synced</span>
                            }
                          </p>
                          <p class="text-xs text-muted-foreground">
                            Added {{ key.created_at | date: 'mediumDate' }}
                            @if (key.last_used_at) {
                              · last used {{ key.last_used_at | date: 'mediumDate' }}
                            }
                          </p>
                        </div>
                        <div class="flex gap-2">
                          <button
                            type="button"
                            class="btn btn-sm btn-ghost"
                            [disabled]="busy()"
                            (click)="startRename(key)"
                            [attr.aria-label]="'Rename passkey ' + key.name"
                          >
                            Rename
                          </button>
                          <button
                            type="button"
                            class="btn btn-sm btn-secondary"
                            [disabled]="busy()"
                            (click)="removePasskey(key)"
                            [attr.aria-label]="'Remove passkey ' + key.name"
                          >
                            Remove
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
                <h2 class="text-sm font-semibold text-foreground">Recovery codes</h2>
                <p class="text-xs text-muted-foreground mt-0.5">
                  @if (s.enabled) {
                    {{ s.recovery_codes_remaining }} unused
                    {{ s.recovery_codes_remaining === 1 ? 'code' : 'codes' }} left.
                  } @else {
                    Created when you turn on two-factor authentication.
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
                  Generate new codes
                </button>
              }
            </section>
          </div>

          @if (s.enabled && !s.required) {
            <section class="card p-5 mt-4 flex items-start justify-between gap-4 flex-wrap">
              <div class="min-w-0">
                <h2 class="text-sm font-semibold text-foreground">
                  Turn off two-factor authentication
                </h2>
                <p class="text-xs text-muted-foreground mt-0.5">
                  Removes every method and recovery code. Not recommended.
                </p>
              </div>
              <button
                type="button"
                class="btn btn-sm btn-danger"
                [disabled]="busy()"
                (click)="disableAll()"
              >
                Turn off
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

  protected readonly addingTitle: Record<EnrollMethod, string> = {
    totp: 'Set up an authenticator app',
    email: 'Turn on email codes',
    webauthn: 'Add a passkey',
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
        this.loadError.set(apiErrorMessage(err, 'Could not load your security settings.', 'error'));
      },
    });
  }

  onAdded(res: FactorAdded): void {
    this.adding.set(null);
    this.toast.success('Sign-in method added.');
    if (res.recovery_codes?.length) this.recoveryCodes.set(res.recovery_codes);
    this.reload();
  }

  closeCodes(): void {
    this.recoveryCodes.set(null);
  }

  async removeTotp(): Promise<void> {
    if (
      !(await this.confirm(
        'Remove the authenticator app?',
        'Codes from the app will stop working for this account.',
      ))
    )
      return;
    this.act(this.mfa.totpRemove(), 'Authenticator app removed.');
  }

  async disableEmail(): Promise<void> {
    if (
      !(await this.confirm(
        'Turn off email codes?',
        'Codes sent by email will no longer confirm your sign-ins.',
      ))
    )
      return;
    this.act(this.mfa.emailDisable(), 'Email codes turned off.');
  }

  async removePasskey(key: Passkey): Promise<void> {
    if (
      !(await this.confirm(
        `Remove the passkey "${key.name}"?`,
        'You will not be able to sign in with it any more.',
      ))
    )
      return;
    this.act(this.mfa.passkeyRemove(key.id), 'Passkey removed.');
  }

  startRename(key: Passkey): void {
    this.renaming.set(key.id);
    this.newName = key.name;
  }

  saveName(key: Passkey): void {
    const name = this.newName.trim();
    if (!name) return;
    this.act(this.mfa.passkeyRename(key.id, name), 'Passkey renamed.', () =>
      this.renaming.set(null),
    );
  }

  async regenerateCodes(): Promise<void> {
    if (
      !(await this.confirm(
        'Generate new recovery codes?',
        'Your current recovery codes will stop working.',
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
      error: (err: unknown) => this.fail(err, 'Could not generate new codes.'),
    });
  }

  async disableAll(): Promise<void> {
    if (
      !(await this.confirm(
        'Turn off two-factor authentication?',
        'Every sign-in method and recovery code will be removed. Your password alone will protect the account.',
      ))
    )
      return;
    this.act(this.mfa.disableAll(), 'Two-factor authentication turned off.');
  }

  private confirm(title: string, message: string, destructive = true): Promise<boolean> {
    return this.modal.open({
      title,
      message,
      confirmText: 'Continue',
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
      error: (err: unknown) => this.fail(err, 'That did not work. Try again.'),
    });
  }

  private fail(err: unknown, fallback: string): void {
    this.busy.set(false);
    // A cancelled step-up dialog is the user's choice, not an error to report.
    if (isStepUpRequired(err)) return;
    this.toast.error(apiErrorMessage(err, fallback, 'error', 'detail'));
  }
}
