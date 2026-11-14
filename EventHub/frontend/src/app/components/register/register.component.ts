import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../services/auth.service';
import { LucideAngularModule, Eye, EyeOff } from 'lucide-angular';
import { apiErrorBody, apiErrorMessage } from '../../api/api-error';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from '../../i18n/language.service';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, LucideAngularModule, TranslocoPipe],
  template: `
    <!-- Each step of this multi-step form shows the one field to fill next, which
         takes focus on purpose: a deliberate exception to no-autofocus. -->
    <!-- eslint-disable @angular-eslint/template/no-autofocus -->
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
          <p class="kicker mb-4" style="color:var(--ember-500)">
            {{ 'register.joinEventhub' | transloco }}
          </p>
          <h2
            class="font-display font-semibold leading-[1.05] text-white"
            style="font-size:clamp(2rem,3vw,2.75rem)"
          >
            {{ 'register.yourSeatAtThe' | transloco }}
          </h2>
          <p class="mt-5 text-[0.95rem] leading-relaxed" style="color:rgba(245,239,230,0.72)">
            {{ 'register.createAnAccountTo' | transloco }}
          </p>
        </div>
        <div
          class="relative z-10 flex items-center gap-3 text-xs"
          style="color:rgba(245,239,230,0.55)"
        >
          <span>{{ 'register.freeToJoin' | transloco }}</span
          ><span aria-hidden="true">·</span><span>{{ 'register.cancelAnytime' | transloco }}</span>
        </div>
        <span class="auth-ring" style="right:-120px;bottom:-120px;width:340px;height:340px"></span>
        <span
          class="auth-ring"
          style="right:-60px;bottom:-60px;width:200px;height:200px;border-color:rgba(232,85,45,0.10)"
        ></span>
      </aside>

      <!-- Right: form -->
      <main class="flex-1 flex items-center justify-center px-5 py-12">
        <div class="w-full max-w-md">
          <!-- Mobile brand -->
          <a
            routerLink="/"
            class="flex lg:hidden items-center gap-2.5 justify-center mb-7 focus-ring rounded"
          >
            <span class="ember-mark"></span>
            <span class="font-display font-semibold text-foreground text-lg">EventHub</span>
          </a>

          <!-- Progress -->
          <div class="flex items-center gap-1 mb-7">
            @for (s of steps; track s) {
              <div
                class="h-1 flex-1 rounded-full transition-all duration-300"
                [class]="currentStep >= s ? 'bg-primary' : 'bg-border'"
              ></div>
            }
          </div>

          <h1 class="text-lg font-bold text-foreground mb-0.5">{{ stepTitle }}</h1>
          <p class="text-sm text-muted-foreground mb-6">
            {{
              'register.stepCurrentstepOfStepslength'
                | transloco: { currentStep: currentStep, stepsLength: steps.length }
            }}
          </p>

          <form (ngSubmit)="onSubmit()" novalidate class="space-y-4">
            <!-- Step 1: Email + Username -->
            @if (currentStep === 1) {
              <div>
                <label for="email" class="block text-sm font-medium text-foreground mb-1.5">{{
                  'common.email' | transloco
                }}</label>
                <input
                  id="email"
                  type="email"
                  [(ngModel)]="email"
                  name="email"
                  [placeholder]="'register.yourEmailCom' | transloco"
                  class="input"
                  autocomplete="email"
                  autofocus
                />
              </div>
              <div>
                <label for="username" class="block text-sm font-medium text-foreground mb-1.5">{{
                  'eventSettings.username' | transloco
                }}</label>
                <input
                  id="username"
                  type="text"
                  [(ngModel)]="username"
                  name="username"
                  [placeholder]="'register.chooseUsername' | transloco"
                  class="input"
                  autocapitalize="none"
                  autocomplete="username"
                />
              </div>
            }

            <!-- Step 2: Verification code -->
            @if (currentStep === 2) {
              <div class="text-center mb-4">
                <p class="text-sm text-muted-foreground">
                  {{ 'forgotPassword.weSentADigit' | transloco }}
                  <span class="font-semibold text-foreground">{{ email }}</span
                  >.
                </p>
              </div>
              @if (devCode) {
                <div class="note note-info">
                  {{ 'register.emailIsNotConfigured' | transloco }}
                  <span class="font-mono font-bold">{{ devCode }}</span
                  >.
                </div>
              }
              <div>
                <label for="code" class="block text-sm font-medium text-foreground mb-1.5">{{
                  'register.verificationCode' | transloco
                }}</label>
                <input
                  id="code"
                  type="text"
                  [(ngModel)]="verification_code"
                  name="verification_code"
                  placeholder="000000"
                  class="input text-center text-xl tracking-widest font-mono"
                  maxlength="6"
                  inputmode="numeric"
                  autofocus
                />
              </div>
            }

            <!-- Step 3: Personal details -->
            @if (currentStep === 3) {
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label
                    for="first_name"
                    class="block text-sm font-medium text-foreground mb-1.5"
                    >{{ 'moderation.firstName' | transloco }}</label
                  >
                  <input
                    id="first_name"
                    type="text"
                    [(ngModel)]="first_name"
                    name="first_name"
                    [placeholder]="'register.john' | transloco"
                    class="input"
                    autocomplete="given-name"
                    autofocus
                  />
                </div>
                <div>
                  <label for="last_name" class="block text-sm font-medium text-foreground mb-1.5">{{
                    'moderation.lastName' | transloco
                  }}</label>
                  <input
                    id="last_name"
                    type="text"
                    [(ngModel)]="last_name"
                    name="last_name"
                    [placeholder]="'register.doe' | transloco"
                    class="input"
                    autocomplete="family-name"
                  />
                </div>
              </div>
              <div>
                <label for="phone" class="block text-sm font-medium text-foreground mb-1.5">
                  {{ 'common.phone' | transloco }}
                  <span class="text-muted-foreground font-normal">{{
                    'checkout.optional' | transloco
                  }}</span>
                </label>
                <input
                  id="phone"
                  type="tel"
                  [(ngModel)]="phone"
                  name="phone"
                  placeholder="+1 234 567 890"
                  class="input"
                  autocomplete="tel"
                />
              </div>
            }

            <!-- Step 4: Password -->
            @if (currentStep === 4) {
              <div>
                <label for="password" class="block text-sm font-medium text-foreground mb-1.5">{{
                  'register.password' | transloco
                }}</label>
                <div
                  class="flex items-center gap-2 border border-border rounded-md px-3 h-10 bg-background focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-shadow"
                >
                  <input
                    id="password"
                    [type]="showPassword ? 'text' : 'password'"
                    [(ngModel)]="password"
                    name="password"
                    placeholder="••••••••"
                    class="flex-1 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
                    autocomplete="new-password"
                    autofocus
                  />
                  <button
                    type="button"
                    (click)="showPassword = !showPassword"
                    class="text-muted-foreground hover:text-foreground flex-shrink-0"
                    [attr.aria-label]="
                      (showPassword ? 'register.hidePassword' : 'register.showPassword') | transloco
                    "
                  >
                    <lucide-icon
                      [img]="showPassword ? icons.EyeOff : icons.Eye"
                      class="w-4 h-4"
                      aria-hidden="true"
                    />
                  </button>
                </div>
                @if (password) {
                  <ul class="mt-2 space-y-1 text-xs">
                    <li
                      class="flex items-center gap-1.5"
                      [class.text-[color:var(--pine-600)]]="password.length >= 8"
                      [class.text-muted-foreground]="password.length < 8"
                    >
                      <span>{{ password.length >= 8 ? '✓' : '○' }}</span>
                      {{ 'register.atLeastCharacters' | transloco }}
                    </li>
                    <li
                      class="flex items-center gap-1.5"
                      [class.text-[color:var(--pine-600)]]="hasDigit(password)"
                      [class.text-muted-foreground]="!hasDigit(password)"
                    >
                      <span>{{ hasDigit(password) ? '✓' : '○' }}</span>
                      {{ 'register.containsANumber' | transloco }}
                    </li>
                  </ul>
                }
              </div>
              <div>
                <label for="password2" class="block text-sm font-medium text-foreground mb-1.5">{{
                  'forgotPassword.confirmPassword' | transloco
                }}</label>
                <input
                  id="password2"
                  type="password"
                  [(ngModel)]="password2"
                  name="password2"
                  placeholder="••••••••"
                  class="input"
                  [class.input-error]="password2 && password !== password2"
                  autocomplete="new-password"
                />
                @if (password2 && password !== password2) {
                  <p class="text-xs text-destructive mt-1">
                    {{ 'forgotPassword.passwordsDoNotMatch' | transloco }}
                  </p>
                }
              </div>
            }

            <!-- Errors -->
            @if (errors.length > 0) {
              <div role="alert" class="note note-error">
                <ul
                  class="text-sm text-[color:var(--destructive)] space-y-0.5 list-disc list-inside"
                >
                  @for (e of errors; track e) {
                    <li>{{ e }}</li>
                  }
                </ul>
              </div>
            }

            <!-- Buttons -->
            <div class="flex gap-2 pt-1">
              @if (currentStep > 1) {
                <button type="button" (click)="prevStep()" class="btn btn-secondary flex-1">
                  {{ 'common.back' | transloco }}
                </button>
              }

              @if (currentStep < steps.length) {
                <button
                  type="button"
                  (click)="nextStep()"
                  [disabled]="submitting"
                  class="btn btn-primary flex-1"
                >
                  @if (submitting) {
                    <span class="spinner spinner-sm"></span>
                    {{
                      (currentStep === 1 ? 'register.sendingCode' : 'forgotPassword.verifying')
                        | transloco
                    }}
                  } @else {
                    {{ 'register.continue' | transloco }}
                  }
                </button>
              } @else {
                <button type="submit" [disabled]="submitting" class="btn btn-primary flex-1">
                  @if (submitting) {
                    <span class="spinner spinner-sm"></span>
                    {{ 'register.creatingAccount' | transloco }}
                  } @else {
                    {{ 'register.createAccount' | transloco }}
                  }
                </button>
              }
            </div>
          </form>

          <p class="text-sm text-muted-foreground text-center mt-6">
            {{ 'register.alreadyHaveAnAccount' | transloco }}
            <a routerLink="/login" class="text-ember font-semibold hover:underline ml-1">{{
              'bookingClaim.signIn' | transloco
            }}</a>
          </p>
        </div>
      </main>
    </div>
  `,
})
export class RegisterComponent {
  private i18n = inject(LanguageService);
  private authService = inject(AuthService);
  private router = inject(Router);

  readonly steps = [1, 2, 3, 4];

  currentStep = 1;
  username = '';
  email = '';
  password = '';
  password2 = '';
  first_name = '';
  last_name = '';
  phone = '';
  verification_code = '';
  devCode = '';

  errors: string[] = [];
  submitting = false;
  showPassword = false;

  readonly icons = { Eye, EyeOff };

  get stepTitle(): string {
    const titles: Record<number, string> = {
      1: this.i18n.t('register.createYourAccount'),
      2: this.i18n.t('register.verifyYourEmail'),
      3: this.i18n.t('register.personalDetails'),
      4: this.i18n.t('register.setAPassword'),
    };
    return titles[this.currentStep] ?? '';
  }

  nextStep(): void {
    this.errors = [];

    if (this.currentStep === 1) {
      if (!this.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.email)) {
        this.errors.push(this.i18n.t('register.enterAValidEmail'));
        return;
      }
      if (!this.username || this.username.length < 3) {
        this.errors.push(this.i18n.t('register.usernameMustBeAt'));
        return;
      }
      this.submitting = true;
      this.authService.sendRegistrationCode(this.email).subscribe({
        next: (res) => {
          this.submitting = false;
          this.devCode = res.dev_code ?? '';
          this.currentStep++;
        },
        error: (err) => {
          this.submitting = false;
          this.errors.push(
            apiErrorMessage(err, this.i18n.t('register.failedToSendVerification'), 'error'),
          );
        },
      });
      return;
    }

    if (this.currentStep === 2) {
      if (this.verification_code.length !== 6) {
        this.errors.push(this.i18n.t('register.enterTheDigitCode'));
        return;
      }
      this.submitting = true;
      this.authService.verifyRegistrationCode(this.email, this.verification_code).subscribe({
        next: () => {
          this.submitting = false;
          this.currentStep++;
        },
        error: (err) => {
          this.submitting = false;
          this.errors.push(
            apiErrorMessage(err, this.i18n.t('forgotPassword.invalidOrExpiredCode'), 'error'),
          );
        },
      });
      return;
    }

    if (this.currentStep < this.steps.length) this.currentStep++;
  }

  prevStep(): void {
    if (this.currentStep > 1) this.currentStep--;
  }

  onSubmit(): void {
    if (this.currentStep < this.steps.length) {
      this.nextStep();
      return;
    }

    this.errors = [];

    if (!this.password || this.password.length < 8 || !this.hasDigit(this.password)) {
      this.errors.push(this.i18n.t('register.passwordMustBeAt'));
      return;
    }
    if (this.password !== this.password2) {
      this.errors.push(this.i18n.t('register.passwordsDoNotMatch'));
      return;
    }

    this.submitting = true;
    this.authService
      .register(
        this.username,
        this.email,
        this.password,
        this.password2,
        this.verification_code,
        this.first_name,
        this.last_name,
        this.phone,
      )
      .subscribe({
        next: () => {
          this.submitting = false;
          void this.router.navigate(['/']);
        },
        error: (err) => {
          this.submitting = false;
          const body = apiErrorBody(err);
          if (body) {
            // DRF validation errors: one entry per field, each a list of messages.
            for (const messages of Object.values(body)) {
              this.errors.push(String(messages));
            }
          } else {
            this.errors.push(this.i18n.t('register.registrationFailedPleaseTry'));
          }
        },
      });
  }

  hasDigit(v: string): boolean {
    return /\d/.test(v);
  }
}
