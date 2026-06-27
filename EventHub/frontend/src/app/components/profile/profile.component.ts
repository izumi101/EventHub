import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../services/auth.service';
import { ToastService } from '../../services/toast.service';
import { User } from '../../models/models';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule],
  template: `
    <div class="page-root">
      <div class="container max-w-2xl py-8">

        <!-- Header -->
        <div class="mb-7">
          <p class="kicker mb-2">Account</p>
          <h1 class="text-3xl font-semibold text-foreground">Profile</h1>
          <p class="text-sm text-muted-foreground mt-1.5">Manage your account information</p>
        </div>

        @if (loading) {
          <div class="card p-8 flex items-center justify-center gap-3 text-muted-foreground">
            <span class="spinner"></span>
            <span class="text-sm">Loading profile...</span>
          </div>
        }

        @if (!loading && user) {
          <!-- Avatar + username row -->
          <div class="card p-5 mb-4 flex items-center gap-4 flex-wrap">
            @if (user.profile.avatar) {
              <img [src]="user.profile.avatar" alt="Avatar"
                class="w-14 h-14 rounded-full object-cover ring-1 ring-border flex-shrink-0" />
            } @else {
              <div class="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center text-xl font-bold text-primary flex-shrink-0">
                {{ user.username.charAt(0).toUpperCase() }}
              </div>
            }
            <div class="flex-1 min-w-0">
              <p class="font-semibold text-foreground">{{ user.username }}</p>
              <p class="text-sm text-muted-foreground">{{ user.email }}</p>
              @if (user.is_superuser) {
                <span class="badge badge-completed mt-1">Admin</span>
              } @else if (user.is_staff) {
                <span class="badge badge-pending mt-1">Staff</span>
              } @else if (user.profile.role === 'organizer') {
                <span class="badge badge-published mt-1">Organizer</span>
              } @else {
                <span class="badge badge-pending mt-1">Attendee</span>
              }
            </div>
            <div class="flex items-center gap-2">
              <label class="btn btn-sm btn-secondary cursor-pointer">
                {{ uploadingAvatar ? 'Uploading…' : (user.profile.avatar ? 'Change photo' : 'Upload photo') }}
                <input type="file" accept="image/*" class="hidden" (change)="onAvatarSelected($event)" [disabled]="uploadingAvatar" />
              </label>
              @if (user.profile.avatar) {
                <button type="button" (click)="removeAvatar()" class="btn btn-sm btn-ghost text-muted-foreground">Remove</button>
              }
            </div>
          </div>

          <!-- Role (read-only — organizer accounts are created by administrators) -->
          @if (!user.is_staff && !user.is_superuser) {
            <div class="card p-5 mb-4 flex items-center justify-between gap-4 flex-wrap">
              <div>
                <p class="text-sm font-semibold text-foreground">
                  {{ user.profile.role === 'organizer' ? 'Organizer account' : 'Attendee account' }}
                </p>
                <p class="text-xs text-muted-foreground mt-0.5">
                  {{ user.profile.role === 'organizer'
                    ? 'You can create and manage events.'
                    : 'Organizer accounts are created by administrators. Contact support if you need one.' }}
                </p>
              </div>
            </div>
          }

          <!-- Form -->
          <form (ngSubmit)="onSubmit()" novalidate>
            <div class="card divide-y divide-border">

              <!-- Personal details -->
              <div class="p-5">
                <h2 class="text-sm font-semibold text-foreground mb-4">Personal details</h2>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label for="first_name" class="block text-sm font-medium text-foreground mb-1.5">First name</label>
                    <input
                      id="first_name"
                      type="text"
                      [(ngModel)]="formData.first_name"
                      name="first_name"
                      placeholder="First name"
                      class="input"
                      autocomplete="given-name"
                    />
                  </div>
                  <div>
                    <label for="last_name" class="block text-sm font-medium text-foreground mb-1.5">Last name</label>
                    <input
                      id="last_name"
                      type="text"
                      [(ngModel)]="formData.last_name"
                      name="last_name"
                      placeholder="Last name"
                      class="input"
                      autocomplete="family-name"
                    />
                  </div>
                  <div class="sm:col-span-2">
                    <label for="bio" class="block text-sm font-medium text-foreground mb-1.5">Bio</label>
                    <textarea
                      id="bio"
                      [(ngModel)]="formData.profile.bio"
                      name="bio"
                      placeholder="Tell us a bit about yourself..."
                      rows="3"
                      class="input resize-none"
                    ></textarea>
                  </div>
                </div>
              </div>

              <!-- Contact -->
              <div class="p-5">
                <h2 class="text-sm font-semibold text-foreground mb-4">Contact & location</h2>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label for="phone" class="block text-sm font-medium text-foreground mb-1.5">Phone</label>
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
                    <label for="location" class="block text-sm font-medium text-foreground mb-1.5">Location</label>
                    <input
                      id="location"
                      type="text"
                      [(ngModel)]="formData.profile.location"
                      name="location"
                      placeholder="City, Country"
                      class="input"
                    />
                  </div>
                  <div class="sm:col-span-2">
                    <label for="website" class="block text-sm font-medium text-foreground mb-1.5">Website</label>
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
                <button
                  type="submit"
                  [disabled]="submitting"
                  class="btn btn-primary"
                >
                  @if (submitting) {
                    <span class="spinner spinner-sm"></span>
                    Saving...
                  } @else {
                    Save changes
                  }
                </button>
              </div>
            </div>
          </form>

          <!-- Change password -->
          <div class="card divide-y divide-border mt-4">
            <div class="p-5">
              <h2 class="text-sm font-semibold text-foreground mb-4">Change password</h2>
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label for="old_pw" class="block text-sm font-medium text-foreground mb-1.5">Current password</label>
                  <input id="old_pw" type="password" [(ngModel)]="pw.old" name="old_pw" class="input" autocomplete="current-password" />
                </div>
                <div>
                  <label for="new_pw" class="block text-sm font-medium text-foreground mb-1.5">New password</label>
                  <input id="new_pw" type="password" [(ngModel)]="pw.new1" name="new_pw" class="input" autocomplete="new-password" />
                </div>
                <div>
                  <label for="new_pw2" class="block text-sm font-medium text-foreground mb-1.5">Repeat new password</label>
                  <input id="new_pw2" type="password" [(ngModel)]="pw.new2" name="new_pw2" class="input" autocomplete="new-password" />
                </div>
              </div>
            </div>
            <div class="p-5 flex items-center justify-between gap-3">
              <div>
                @if (pwError) { <p class="text-sm text-destructive">{{ pwError }}</p> }
                @if (pwSuccess) { <p class="text-sm text-[color:var(--pine-600)]">{{ pwSuccess }}</p> }
              </div>
              <button type="button" (click)="changePassword()"
                [disabled]="changingPw || !pw.old || !pw.new1 || !pw.new2"
                class="btn btn-secondary">
                {{ changingPw ? 'Updating…' : 'Update password' }}
              </button>
            </div>
          </div>
        }
      </div>
    </div>
  `,
})
export class ProfileComponent implements OnInit {
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

  constructor(private authService: AuthService, private toastService: ToastService) {}

  ngOnInit(): void {
    this.loading = true;
    this.authService.getProfile().subscribe({
      next: user => {
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
        this.error = 'Failed to load profile.';
        this.loading = false;
      },
    });
  }

  onSubmit(): void {
    this.error = ''; this.success = ''; this.submitting = true;
    this.authService.updateProfile(this.formData as any).subscribe({
      next: user => {
        this.user = user;
        this.success = 'Profile updated.';
        this.submitting = false;
        setTimeout(() => { this.success = ''; }, 3000);
      },
      error: err => {
        this.error = err.error?.detail || 'Failed to update profile.';
        this.submitting = false;
      },
    });
  }

  onAvatarSelected(evt: Event): void {
    const input = evt.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      this.toastService.error('Avatar must be under 5 MB.');
      input.value = '';
      return;
    }
    this.uploadingAvatar = true;
    this.authService.uploadAvatar(file).subscribe({
      next: user => {
        this.user = user;
        this.uploadingAvatar = false;
        this.toastService.success('Avatar updated.');
      },
      error: err => {
        this.uploadingAvatar = false;
        this.toastService.error(err.error?.error || 'Could not upload the avatar.');
      },
    });
    input.value = '';
  }

  removeAvatar(): void {
    this.authService.deleteAvatar().subscribe({
      next: user => { this.user = user; this.toastService.success('Avatar removed.'); },
      error: () => this.toastService.error('Could not remove the avatar.'),
    });
  }

  changePassword(): void {
    this.pwError = ''; this.pwSuccess = '';
    if (this.pw.new1 !== this.pw.new2) { this.pwError = 'Passwords do not match.'; return; }
    if (this.pw.new1.length < 8) { this.pwError = 'Password must be at least 8 characters.'; return; }
    this.changingPw = true;
    this.authService.changePassword(this.pw.old, this.pw.new1, this.pw.new2).subscribe({
      next: () => {
        this.changingPw = false;
        this.pw = { old: '', new1: '', new2: '' };
        this.pwSuccess = 'Password changed.';
        setTimeout(() => { this.pwSuccess = ''; }, 3000);
      },
      error: err => {
        this.changingPw = false;
        this.pwError = err.error?.error || 'Could not change the password.';
      },
    });
  }
}
