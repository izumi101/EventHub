import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../services/auth.service';
import { ToastService } from '../../services/toast.service';
import { User } from '../../models/models';
import { apiErrorMessage } from '../../api/api-error';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from '../../i18n/language.service';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, TranslocoPipe],
  template: `
    <div class="page-root">
      <div class="container max-w-2xl py-8">
        <!-- Header -->
        <div class="mb-7">
          <p class="kicker mb-2">{{ 'profile.account' | transloco }}</p>
          <h1 class="text-3xl font-semibold text-foreground">{{ 'profile.title' | transloco }}</h1>
          <p class="text-sm text-muted-foreground mt-1.5">{{ 'profile.intro' | transloco }}</p>
        </div>

        @if (loading) {
          <div class="card p-8 flex items-center justify-center gap-3 text-muted-foreground">
            <span class="spinner"></span>
            <span class="text-sm">{{ 'profile.loading' | transloco }}</span>
          </div>
        }

        @if (!loading && user) {
          <!-- Avatar + username row -->
          <div class="card p-5 mb-4 flex items-center gap-4 flex-wrap">
            @if (user.profile.avatar) {
              <img
                [src]="user.profile.avatar"
                [alt]="'profile.avatarAlt' | transloco"
                class="w-14 h-14 rounded-full object-cover ring-1 ring-border flex-shrink-0"
              />
            } @else {
              <div
                class="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center text-xl font-bold text-primary flex-shrink-0"
              >
                {{ user.username.charAt(0).toUpperCase() }}
              </div>
            }
            <div class="flex-1 min-w-0">
              <p class="font-semibold text-foreground">{{ user.username }}</p>
              <p class="text-sm text-muted-foreground">{{ user.email }}</p>
              @if (user.is_superuser) {
                <span class="badge badge-completed mt-1">{{
                  'profile.roleAdmin' | transloco
                }}</span>
              } @else if (user.is_staff) {
                <span class="badge badge-pending mt-1">{{ 'profile.roleStaff' | transloco }}</span>
              } @else if (user.profile.role === 'organizer') {
                <span class="badge badge-published mt-1">{{
                  'profile.roleOrganizer' | transloco
                }}</span>
              } @else {
                <span class="badge badge-pending mt-1">{{
                  'profile.roleAttendee' | transloco
                }}</span>
              }
            </div>
            <div class="flex items-center gap-2">
              <label class="btn btn-sm btn-secondary cursor-pointer">
                {{
                  uploadingAvatar
                    ? ('profile.uploading' | transloco)
                    : user.profile.avatar
                      ? ('profile.changePhoto' | transloco)
                      : ('profile.uploadPhoto' | transloco)
                }}
                <input
                  type="file"
                  accept="image/*"
                  class="hidden"
                  (change)="onAvatarSelected($event)"
                  [disabled]="uploadingAvatar"
                />
              </label>
              @if (user.profile.avatar) {
                <button
                  type="button"
                  (click)="removeAvatar()"
                  class="btn btn-sm btn-ghost text-muted-foreground"
                >
                  {{ 'common.remove' | transloco }}
                </button>
              }
            </div>
          </div>

          <!-- Role (read-only — organizer accounts are created by administrators) -->
          @if (!user.is_staff && !user.is_superuser) {
            <div class="card p-5 mb-4 flex items-center justify-between gap-4 flex-wrap">
              <div>
                <p class="text-sm font-semibold text-foreground">
                  {{
                    (user.profile.role === 'organizer'
                      ? 'profile.organizerAccount'
                      : 'profile.attendeeAccount'
                    ) | transloco
                  }}
                </p>
                <p class="text-xs text-muted-foreground mt-0.5">
                  {{
                    user.profile.role === 'organizer'
                      ? ('profile.organizerHint' | transloco)
                      : ('profile.attendeeHint' | transloco)
                  }}
                </p>
              </div>
            </div>
          }

          <!-- Security (2FA) -->
          <div class="card p-5 mb-4 flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h2 class="text-sm font-semibold text-foreground">
                {{ 'profile.securityTitle' | transloco }}
              </h2>
              <p class="text-xs text-muted-foreground mt-0.5">
                {{ 'profile.securityHint' | transloco }}
              </p>
            </div>
            <a routerLink="/profile/security" class="btn btn-sm btn-secondary">{{
              'profile.manage' | transloco
            }}</a>
          </div>

          <!-- Notifications -->
          <div class="card p-5 mb-4 flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h2 class="text-sm font-semibold text-foreground">
                {{ 'profile.notificationsTitle' | transloco }}
              </h2>
              <p class="text-xs text-muted-foreground mt-0.5">
                {{ 'profile.notificationsHint' | transloco }}
              </p>
            </div>
            <a routerLink="/profile/notifications" class="btn btn-sm btn-secondary">{{
              'profile.manage' | transloco
            }}</a>
          </div>

          <!-- Form -->
          <form (ngSubmit)="onSubmit()" novalidate>
            <div class="card divide-y divide-border">
              <!-- Personal details -->
              <div class="p-5">
                <h2 class="text-sm font-semibold text-foreground mb-4">
                  {{ 'profile.personalDetails' | transloco }}
                </h2>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label
                      for="first_name"
                      class="block text-sm font-medium text-foreground mb-1.5"
                      >{{ 'profile.firstName' | transloco }}</label
                    >
                    <input
                      id="first_name"
                      type="text"
                      [(ngModel)]="formData.first_name"
                      name="first_name"
                      [placeholder]="'profile.firstName' | transloco"
                      class="input"
                      autocomplete="given-name"
                    />
                  </div>
                  <div>
                    <label
                      for="last_name"
                      class="block text-sm font-medium text-foreground mb-1.5"
                      >{{ 'profile.lastName' | transloco }}</label
                    >
                    <input
                      id="last_name"
                      type="text"
                      [(ngModel)]="formData.last_name"
                      name="last_name"
                      [placeholder]="'profile.lastName' | transloco"
                      class="input"
                      autocomplete="family-name"
                    />
                  </div>
                  <div class="sm:col-span-2">
                    <label for="bio" class="block text-sm font-medium text-foreground mb-1.5">{{
                      'profile.bio' | transloco
                    }}</label>
                    <textarea
                      id="bio"
                      [(ngModel)]="formData.profile.bio"
                      name="bio"
                      [placeholder]="'profile.bioPlaceholder' | transloco"
                      rows="3"
                      class="input resize-none"
                    ></textarea>
                  </div>
                </div>
              </div>

              <!-- Contact -->
              <div class="p-5">
                <h2 class="text-sm font-semibold text-foreground mb-4">
                  {{ 'profile.contact' | transloco }}
                </h2>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label for="phone" class="block text-sm font-medium text-foreground mb-1.5">{{
                      'common.phone' | transloco
                    }}</label>
                    <input
                      id="phone"
                      type="tel"
                      [(ngModel)]="formData.profile.phone"
                      name="phone"
                      placeholder="+1 234 567 890"
                      class="input"
                      autocomplete="tel"
                    />
                  </div>
                  <div>
                    <label
                      for="location"
                      class="block text-sm font-medium text-foreground mb-1.5"
                      >{{ 'profile.location' | transloco }}</label
                    >
                    <input
                      id="location"
                      type="text"
                      [(ngModel)]="formData.profile.location"
                      name="location"
                      [placeholder]="'profile.locationPlaceholder' | transloco"
                      class="input"
                    />
                  </div>
                  <div class="sm:col-span-2">
                    <label for="website" class="block text-sm font-medium text-foreground mb-1.5">{{
                      'profile.website' | transloco
                    }}</label>
                    <input
                      id="website"
                      type="url"
                      [(ngModel)]="formData.profile.website"
                      name="website"
                      placeholder="https://yoursite.com"
                      class="input"
                      autocomplete="url"
                    />
                  </div>
                </div>
              </div>

              <!-- Actions -->
              <div class="p-5 flex items-center justify-between gap-3">
                <div>
                  @if (error) {
                    <p class="text-sm text-destructive">{{ error }}</p>
                  }
                  @if (success) {
                    <p class="text-sm text-[color:var(--pine-600)]">{{ success }}</p>
                  }
                </div>
                <button type="submit" [disabled]="submitting" class="btn btn-primary">
                  @if (submitting) {
                    <span class="spinner spinner-sm"></span>
                    {{ 'common.saving' | transloco }}
                  } @else {
                    {{ 'profile.saveChanges' | transloco }}
                  }
                </button>
              </div>
            </div>
          </form>

          <!-- Change password -->
          <div class="card divide-y divide-border mt-4">
            <div class="p-5">
              <h2 class="text-sm font-semibold text-foreground mb-4">
                {{ 'profile.changePassword' | transloco }}
              </h2>
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label for="old_pw" class="block text-sm font-medium text-foreground mb-1.5">{{
                    'profile.currentPassword' | transloco
                  }}</label>
                  <input
                    id="old_pw"
                    type="password"
                    [(ngModel)]="pw.old"
                    name="old_pw"
                    class="input"
                    autocomplete="current-password"
                  />
                </div>
                <div>
                  <label for="new_pw" class="block text-sm font-medium text-foreground mb-1.5">{{
                    'profile.newPassword' | transloco
                  }}</label>
                  <input
                    id="new_pw"
                    type="password"
                    [(ngModel)]="pw.new1"
                    name="new_pw"
                    class="input"
                    autocomplete="new-password"
                  />
                </div>
                <div>
                  <label for="new_pw2" class="block text-sm font-medium text-foreground mb-1.5">{{
                    'profile.repeatNewPassword' | transloco
                  }}</label>
                  <input
                    id="new_pw2"
                    type="password"
                    [(ngModel)]="pw.new2"
                    name="new_pw2"
                    class="input"
                    autocomplete="new-password"
                  />
                </div>
              </div>
            </div>
            <div class="p-5 flex items-center justify-between gap-3">
              <div>
                @if (pwError) {
                  <p class="text-sm text-destructive">{{ pwError }}</p>
                }
                @if (pwSuccess) {
                  <p class="text-sm text-[color:var(--pine-600)]">{{ pwSuccess }}</p>
                }
              </div>
              <button
                type="button"
                (click)="changePassword()"
                [disabled]="changingPw || !pw.old || !pw.new1 || !pw.new2"
                class="btn btn-secondary"
              >
                {{ (changingPw ? 'profile.updating' : 'profile.updatePassword') | transloco }}
              </button>
            </div>
          </div>
        }
      </div>
    </div>
  `,
})
export class ProfileComponent implements OnInit {
  private authService = inject(AuthService);
  private toastService = inject(ToastService);
  private lang = inject(LanguageService);

  user: User | null = null;
  loading = false;
  submitting = false;
  error = '';
  success = '';

  // NOTE: avatar is intentionally NOT part of this payload — it's an
  // ImageField and uploads go through the dedicated avatar endpoint.
  formData = {
    first_name: '',
    last_name: '',
    profile: { bio: '', phone: '', location: '', website: '' },
  };

  uploadingAvatar = false;

  pw = { old: '', new1: '', new2: '' };
  changingPw = false;
  pwError = '';
  pwSuccess = '';

  ngOnInit(): void {
    this.loading = true;
    this.authService.getProfile().subscribe({
      next: (user) => {
        this.user = user;
        this.formData = {
          first_name: user.first_name,
          last_name: user.last_name,
          profile: {
            bio: user.profile.bio,
            phone: user.profile.phone,
            location: user.profile.location,
            website: user.profile.website,
          },
        };
        this.loading = false;
      },
      error: () => {
        this.error = this.lang.t('profile.loadFailed');
        this.loading = false;
      },
    });
  }

  onSubmit(): void {
    this.error = '';
    this.success = '';
    this.submitting = true;
    this.authService.updateProfile(this.formData).subscribe({
      next: (user) => {
        this.user = user;
        this.success = this.lang.t('profile.updated');
        this.submitting = false;
        setTimeout(() => {
          this.success = '';
        }, 3000);
      },
      error: (err) => {
        this.error = apiErrorMessage(err, this.lang.t('profile.updateFailed'), 'detail');
        this.submitting = false;
      },
    });
  }

  onAvatarSelected(evt: Event): void {
    const input = evt.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      this.toastService.error(this.lang.t('profile.avatarTooBig'));
      input.value = '';
      return;
    }
    this.uploadingAvatar = true;
    this.authService.uploadAvatar(file).subscribe({
      next: (user) => {
        this.user = user;
        this.uploadingAvatar = false;
        this.toastService.success(this.lang.t('profile.avatarUpdated'));
      },
      error: (err) => {
        this.uploadingAvatar = false;
        this.toastService.error(
          apiErrorMessage(err, this.lang.t('profile.avatarUploadFailed'), 'error'),
        );
      },
    });
    input.value = '';
  }

  removeAvatar(): void {
    this.authService.deleteAvatar().subscribe({
      next: (user) => {
        this.user = user;
        this.toastService.success(this.lang.t('profile.avatarRemoved'));
      },
      error: () => this.toastService.error(this.lang.t('profile.avatarRemoveFailed')),
    });
  }

  changePassword(): void {
    this.pwError = '';
    this.pwSuccess = '';
    if (this.pw.new1 !== this.pw.new2) {
      this.pwError = this.lang.t('profile.passwordsMismatch');
      return;
    }
    if (this.pw.new1.length < 8) {
      this.pwError = this.lang.t('profile.passwordTooShort');
      return;
    }
    this.changingPw = true;
    this.authService.changePassword(this.pw.old, this.pw.new1, this.pw.new2).subscribe({
      next: () => {
        this.changingPw = false;
        this.pw = { old: '', new1: '', new2: '' };
        this.pwSuccess = this.lang.t('profile.passwordChanged');
        setTimeout(() => {
          this.pwSuccess = '';
        }, 3000);
      },
      error: (err) => {
        this.changingPw = false;
        this.pwError = apiErrorMessage(err, this.lang.t('profile.passwordChangeFailed'), 'error');
      },
    });
  }
}
