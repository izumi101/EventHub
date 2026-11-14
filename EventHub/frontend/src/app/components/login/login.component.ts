import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import {
  AuthService,
  MfaChallenge,
  isMfaChallenge,
  isMfaEnrollmentRequired,
} from '../../services/auth.service';
import { FactorAdded, MfaService } from '../../services/mfa.service';
import { LucideAngularModule, Eye, EyeOff } from 'lucide-angular';
import { apiErrorMessage } from '../../api/api-error';
import { MfaVerifier, MfaVerifyComponent } from '../mfa/mfa-verify.component';
import { MfaEnrollComponent } from '../mfa/mfa-enroll.component';
import { RecoveryCodesComponent } from '../mfa/recovery-codes.component';

/**
 * Sign-in as a small state machine:
 *   password → (session)                       → returnUrl
 *   password → mfa (challenge)                 → returnUrl
 *   password → enroll (role must use 2FA)      → recovery codes → returnUrl
 */
export type LoginStep = 'password' | 'mfa' | 'enroll' | 'recovery';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    FormsModule,
    LucideAngularModule,
    MfaVerifyComponent,
    MfaEnrollComponent,
    RecoveryCodesComponent,
  ],
  template: `
    <div class="min-h-dvh flex bg-background">
      <!-- Left: editorial brand panel -->
      <aside
        class="auth-brand hidden lg:flex flex-col justify-between w-[44%] xl:w-[46%] p-12 relative overflow-hidden"
      >
        <a routerLink="/" class="flex items-center gap-2.5 relative z-10 focus-ring rounded">
          <span class="ember-mark"></span>
          <span class="font-display font-semibold text-lg text-white">EventHub</span>
        </a>
        <div class="relative z-10 max-w-md">
          <p class="kicker mb-4" style="color:var(--ember-500)">What's on · Tonight</p>
          <h2
            class="font-display font-semibold leading-[1.05] text-white"
            style="font-size:clamp(2rem,3vw,2.75rem)"
          >
            Every great night starts with a ticket.
          </h2>
          <p class="mt-5 text-[0.95rem] leading-relaxed" style="color:rgba(245,239,230,0.72)">
            Discover concerts, gallery nights and conferences — and keep every ticket in one place.
          </p>
        </div>
        <div
          class="relative z-10 flex items-center gap-3 text-xs"
          style="color:rgba(245,239,230,0.55)"
        >
          <span>Secure checkout</span><span aria-hidden="true">·</span
          ><span>Trusted by organizers</span>
        </div>
        <span class="auth-ring" style="right:-120px;bottom:-120px;width:340px;height:340px"></span>
        <span
          class="auth-ring"
          style="right:-60px;bottom:-60px;width:200px;height:200px;border-color:rgba(232,85,45,0.10)"
        ></span>
      </aside>

      <!-- Right: form -->
      <main class="flex-1 flex items-center justify-center px-5 py-12">
        <div class="w-full max-w-sm">
          <!-- Mobile brand -->
          <a
            routerLink="/"
            class="flex lg:hidden items-center gap-2.5 justify-center mb-8 focus-ring rounded"
          >
            <span class="ember-mark"></span>
            <span class="font-display font-semibold text-foreground text-lg">EventHub</span>
          </a>

          @switch (step()) {
            @case ('mfa') {
              <p class="kicker mb-2">Two-step sign-in</p>
              <h1 class="font-display text-3xl font-semibold text-foreground mb-1.5">
                Confirm it's you
              </h1>
              <p class="text-sm text-muted-foreground mb-7">
                Your account is protected with two-factor authentication.
              </p>
              <app-mfa-verify
                [methods]="challenge()?.methods ?? []"
                [verifier]="loginVerifier"
                submitLabel="Sign in"
                (verified)="finish()"
              />
              <button type="button" class="btn btn-ghost btn-sm mt-4" (click)="startOver()">
                Back to sign in
              </button>
            }
            @case ('enroll') {
              <p class="kicker mb-2">One more step</p>
              <h1 class="font-display text-3xl font-semibold text-foreground mb-1.5">
                Set up two-factor authentication
              </h1>
              <p class="text-sm text-muted-foreground mb-7">
                Organizer and admin accounts must use a second factor. Choose how you want to
                confirm your sign-ins.
              </p>
              <app-mfa-enroll
                [enrollmentToken]="enrollmentToken()"
                (completed)="onEnrolled($event)"
                (cancelled)="startOver()"
              />
              <button type="button" class="btn btn-ghost btn-sm mt-4" (click)="startOver()">
                Back to sign in
              </button>
            }
            @case ('recovery') {
              <p class="kicker mb-2">Two-factor authentication is on</p>
              <h1 class="font-display text-3xl font-semibold text-foreground mb-1.5">
                Save your recovery codes
              </h1>
              <p class="text-sm text-muted-foreground mb-7">
                Use one if you can't get a code from your app or email.
              </p>
              <app-recovery-codes
                [codes]="recoveryCodes()"
                continueLabel="Continue to EventHub"
                (done)="finish()"
              />
            }
            @default {
              <p class="kicker mb-2">Welcome back</p>
              <h1 class="font-display text-3xl font-semibold text-foreground mb-1.5">Sign in</h1>
              <p class="text-sm text-muted-foreground mb-7">Continue to your tickets and events.</p>

              <form (ngSubmit)="onSubmit()" class="space-y-4" novalidate>
                <div>
                  <label for="username" class="block text-sm font-medium text-foreground mb-1.5">
                    Username or email
                  </label>
                  <input
                    id="username"
                    type="text"
                    [(ngModel)]="username"
                    name="username"
                    placeholder="@username or email"
                    class="input"
                    [class.input-error]="error && !username"
                    autocapitalize="none"
                    autocorrect="off"
                    autocomplete="username"
                    required
                  />
                </div>

                <div>
                  <div class="flex items-center justify-between mb-1.5">
                    <label for="password" class="text-sm font-medium text-foreground"
                      >Password</label
                    >
                    <a routerLink="/forgot-password" class="text-xs text-primary hover:underline">
                      Forgot password?
                    </a>
                  </div>
                  <div
                    class="flex items-center gap-2 border rounded-md px-3 h-10 bg-background transition-shadow"
                    [class]="
                      error && !password
                        ? 'border-destructive'
                        : 'border-border focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20'
                    "
                  >
                    <input
                      id="password"
                      [type]="showPassword ? 'text' : 'password'"
                      [(ngModel)]="password"
                      name="password"
                      placeholder="••••••••"
                      class="flex-1 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
                      autocomplete="current-password"
                      required
                    />
                    <button
                      type="button"
                      (click)="showPassword = !showPassword"
                      class="text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
                      [attr.aria-label]="showPassword ? 'Hide password' : 'Show password'"
                    >
                      <lucide-icon
                        [img]="showPassword ? icons.EyeOff : icons.Eye"
                        class="w-4 h-4"
                        aria-hidden="true"
                      />
                    </button>
                  </div>
                </div>

                @if (error) {
                  <div role="alert" class="note note-error">{{ error }}</div>
                }

                <button
                  type="submit"
                  class="btn btn-primary btn-full btn-lg mt-1"
                  [disabled]="submitting"
                >
                  @if (submitting) {
                    <span class="spinner spinner-sm"></span>
                    Signing in...
                  } @else {
                    Sign in
                  }
                </button>
              </form>

              <p class="text-sm text-muted-foreground text-center mt-6">
                Don't have an account?
                <a routerLink="/register" class="text-ember font-semibold hover:underline ml-1"
                  >Create one</a
                >
              </p>
            }
          }
        </div>
      </main>
    </div>
  `,
})
export class LoginComponent {
  private authService = inject(AuthService);
  private mfa = inject(MfaService);
  private router = inject(Router);

  readonly step = signal<LoginStep>('password');
  readonly challenge = signal<MfaChallenge | null>(null);
  readonly enrollmentToken = signal<string | null>(null);
  readonly recoveryCodes = signal<string[]>([]);

  /** The second step of sign-in, bound to the current challenge token. */
  readonly loginVerifier: MfaVerifier = {
    sendEmailCode: () => this.mfa.loginSendEmailCode(this.challengeToken()),
    passkeyOptions: () => this.mfa.loginPasskeyOptions(this.challengeToken()),
    verify: (proof) => this.mfa.loginVerify(this.challengeToken(), proof),
  };

  username = '';
  password = '';
  error = '';
  submitting = false;
  showPassword = false;

  readonly icons = { Eye, EyeOff };
  private returnUrl = '/';

  constructor() {
    const route = inject(ActivatedRoute);

    this.returnUrl = route.snapshot.queryParamMap.get('returnUrl') || '/';
  }

  onSubmit(): void {
    if (!this.username.trim() || !this.password.trim()) {
      this.error = 'Please fill in all fields.';
      return;
    }
    this.error = '';
    this.submitting = true;

    this.authService.login(this.username.trim(), this.password).subscribe({
      next: (res) => {
        this.submitting = false;
        this.password = '';
        if (isMfaChallenge(res)) {
          this.challenge.set(res);
          this.step.set('mfa');
        } else if (isMfaEnrollmentRequired(res)) {
          this.enrollmentToken.set(res.enrollment_token);
          this.step.set('enroll');
        } else {
          this.finish();
        }
      },
      error: (err) => {
        this.error = apiErrorMessage(err, 'Invalid username or password.', 'detail');
        this.submitting = false;
      },
    });
  }

  /** Enrollment at sign-in: the first factor came with a session; show the codes once. */
  onEnrolled(res: FactorAdded): void {
    this.enrollmentToken.set(null);
    if (res.recovery_codes?.length) {
      this.recoveryCodes.set(res.recovery_codes);
      this.step.set('recovery');
    } else {
      this.finish();
    }
  }

  startOver(): void {
    this.challenge.set(null);
    this.enrollmentToken.set(null);
    this.recoveryCodes.set([]);
    this.error = '';
    this.step.set('password');
  }

  finish(): void {
    void this.router.navigateByUrl(this.returnUrl);
  }

  private challengeToken(): string {
    return this.challenge()?.challenge_token ?? '';
  }
}
