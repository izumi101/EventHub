import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../services/auth.service';
import { LucideAngularModule, Eye, EyeOff } from 'lucide-angular';

@Component({
  selector: 'app-forgot-password',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, LucideAngularModule],
  template: `
    <div class="min-h-dvh flex bg-background">

      <!-- Left: editorial brand panel -->
      <aside class="auth-brand hidden lg:flex flex-col justify-between w-[44%] xl:w-[46%] p-12 relative overflow-hidden">
        <a routerLink="/" class="flex items-center gap-2.5 relative z-10 focus-ring rounded">
          <span class="ember-mark"></span>
          <span class="font-display font-semibold text-lg text-white">EventHub</span>
        </a>
        <div class="relative z-10 max-w-md">
          <p class="kicker mb-4" style="color:var(--ember-500)">Account recovery</p>
          <h2 class="font-display font-semibold leading-[1.05] text-white" style="font-size:clamp(2rem,3vw,2.75rem)">
            Let's get you back to the night.
          </h2>
          <p class="mt-5 text-[0.95rem] leading-relaxed" style="color:rgba(245,239,230,0.72)">
            Reset your password in a couple of steps and pick up right where you left off.
          </p>
        </div>
        <div class="relative z-10 flex items-center gap-3 text-xs" style="color:rgba(245,239,230,0.55)">
          <span>Secure reset</span><span aria-hidden="true">·</span><span>Takes a minute</span>
        </div>
        <span class="auth-ring" style="right:-120px;bottom:-120px;width:340px;height:340px"></span>
        <span class="auth-ring" style="right:-60px;bottom:-60px;width:200px;height:200px;border-color:rgba(232,85,45,0.10)"></span>
      </aside>

      <!-- Right: form -->
      <main class="flex-1 flex items-center justify-center px-5 py-12">
        <div class="w-full max-w-sm">

          <!-- Mobile brand -->
          <a routerLink="/" class="flex lg:hidden items-center gap-2.5 justify-center mb-7 focus-ring rounded">
            <span class="ember-mark"></span>
            <span class="font-display font-semibold text-foreground text-lg">EventHub</span>
          </a>

        <!-- Progress dots -->
        <div class="flex items-center gap-1.5 justify-center mb-7">
          @for (s of [1,2,3]; track s) {
            <div
              class="h-1.5 rounded-full transition-all duration-300"
              [class]="step >= s ? 'bg-primary w-6' : 'bg-border w-3'"
            ></div>
          }
        </div>

        <!-- Step 1: Enter identifier -->
        @if (step === 1) {
          <h1 class="text-lg font-bold text-foreground mb-1">Reset your password</h1>
          <p class="text-sm text-muted-foreground mb-6">
            Enter your username or email and we'll send you a reset code.
          </p>

          <form (ngSubmit)="requestReset()" novalidate class="space-y-4">
            <div>
              <label for="identifier" class="block text-sm font-medium text-foreground mb-1.5">
                Username or email
              </label>
              <input
                id="identifier"
                type="text"
                [(ngModel)]="identifier"
                name="identifier"
                placeholder="@username or email"
                class="input"
                autocapitalize="none"
                autofocus
              />
            </div>

            @if (error) {
              <div role="alert" class="note note-error">
                {{ error }}
              </div>
            }

            <button type="submit" [disabled]="loading" class="btn btn-primary btn-full btn-lg">
              @if (loading) { <span class="spinner spinner-sm"></span> Sending... }
              @else { Send reset code }
            </button>
          </form>
        }

        <!-- Step 2: Enter code -->
        @if (step === 2) {
          <h1 class="text-lg font-bold text-foreground mb-1">Enter the code</h1>
          <p class="text-sm text-muted-foreground mb-6">
            We sent a 6-digit code to <span class="font-semibold text-foreground">{{ identifier }}</span>.
          </p>

          <form (ngSubmit)="verifyCode()" novalidate class="space-y-4">
            <div>
              <label for="code" class="block text-sm font-medium text-foreground mb-1.5">Reset code</label>
              <input
                id="code"
                type="text"
                [(ngModel)]="code"
                name="code"
                placeholder="000000"
                class="input text-center text-xl tracking-widest font-mono"
                maxlength="6"
                inputmode="numeric"
                autofocus
              />
            </div>

            @if (error) {
              <div role="alert" class="note note-error">
                {{ error }}
              </div>
            }

            <div class="flex gap-2">
              <button type="button" (click)="step = 1" class="btn btn-secondary flex-1">Back</button>
              <button type="submit" [disabled]="loading" class="btn btn-primary flex-1">
                @if (loading) { <span class="spinner spinner-sm"></span> Verifying... }
                @else { Verify }
              </button>
            </div>
          </form>
        }

        <!-- Step 3: New password -->
        @if (step === 3) {
          <h1 class="text-lg font-bold text-foreground mb-1">Set new password</h1>
          <p class="text-sm text-muted-foreground mb-6">Choose a strong password for your account.</p>

          <form (ngSubmit)="confirmReset()" novalidate class="space-y-4">
            <div>
              <label for="newpw" class="block text-sm font-medium text-foreground mb-1.5">New password</label>
              <div class="flex items-center gap-2 border border-border rounded-md px-3 h-10 bg-background focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-shadow">
                <input
                  id="newpw"
                  [type]="showPw ? 'text' : 'password'"
                  [(ngModel)]="newPassword"
                  name="newPassword"
                  placeholder="••••••••"
                  class="flex-1 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
                  autocomplete="new-password"
                  autofocus
                />
                <button
                  type="button"
                  (click)="showPw = !showPw"
                  class="text-muted-foreground hover:text-foreground flex-shrink-0"
                  [attr.aria-label]="showPw ? 'Hide' : 'Show'"
                >
                  <lucide-icon [img]="showPw ? icons.EyeOff : icons.Eye" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                </button>
              </div>
            </div>

            <div>
              <label for="newpw2" class="block text-sm font-medium text-foreground mb-1.5">Confirm password</label>
              <input
                id="newpw2"
                type="password"
                [(ngModel)]="newPassword2"
                name="newPassword2"
                placeholder="••••••••"
                class="input"
                [class.input-error]="newPassword2 && newPassword !== newPassword2"
                autocomplete="new-password"
              />
            </div>

            @if (error) {
              <div role="alert" class="note note-error">
                {{ error }}
              </div>
            }

            @if (success) {
              <div role="status" class="note note-success">
                {{ success }}
              </div>
            }

            <button type="submit" [disabled]="loading" class="btn btn-primary btn-full btn-lg">
              @if (loading) { <span class="spinner spinner-sm"></span> Saving... }
              @else { Save new password }
            </button>
          </form>
        }

          <p class="text-sm text-muted-foreground text-center mt-6">
            Remembered it?
            <a routerLink="/login" class="text-ember font-semibold hover:underline ml-1">Sign in</a>
          </p>
        </div>
      </main>
    </div>
  `,
})
export class ForgotPasswordComponent {
  step = 1;

  identifier = '';
  code = '';
  newPassword = '';
  newPassword2 = '';
  resetToken = '';

  loading = false;
  error = '';
  success = '';
  showPw = false;

  readonly icons = { Eye, EyeOff };

  constructor(private authService: AuthService, private router: Router) {}

  requestReset(): void {
    if (!this.identifier.trim()) { this.error = 'Please enter your username or email.'; return; }
    this.error = ''; this.loading = true;
    this.authService.requestPasswordReset(this.identifier.trim()).subscribe({
      next: () => { this.loading = false; this.step = 2; },
      error: err => { this.loading = false; this.error = err.error?.detail || 'Request failed. Please try again.'; },
    });
  }

  verifyCode(): void {
    if (!this.code || this.code.length !== 6) { this.error = 'Enter the 6-digit code.'; return; }
    this.error = ''; this.loading = true;
    this.authService.verifyResetCode(this.identifier, this.code).subscribe({
      next: res => { this.loading = false; this.resetToken = res.reset_token; this.step = 3; },
      error: err => { this.loading = false; this.error = err.error?.detail || 'Invalid or expired code.'; },
    });
  }

  confirmReset(): void {
    if (!this.newPassword || this.newPassword.length < 8) {
      this.error = 'Password must be at least 8 characters.'; return;
    }
    if (this.newPassword !== this.newPassword2) {
      this.error = 'Passwords do not match.'; return;
    }
    this.error = ''; this.loading = true;
    this.authService.confirmPasswordReset(this.resetToken, this.newPassword, this.newPassword2).subscribe({
      next: () => {
        this.loading = false;
        this.success = 'Password updated! Redirecting to sign in...';
        setTimeout(() => this.router.navigate(['/login']), 1800);
      },
      error: err => { this.loading = false; this.error = err.error?.detail || 'Failed to set new password.'; },
    });
  }
}
