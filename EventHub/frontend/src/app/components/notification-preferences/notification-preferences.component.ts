import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterModule } from '@angular/router';
import {
  NotificationPreferencesService,
  type NotificationTypePreference,
} from '../../services/notification-preferences.service';
import { ToastService } from '../../services/toast.service';
import { apiErrorMessage } from '../../api/api-error';

/** Profile → Notifications: which notifications are also sent by email. */
@Component({
  selector: 'app-notification-preferences',
  standalone: true,
  imports: [RouterModule],
  template: `
    <div class="page-root">
      <div class="container max-w-2xl py-8">
        <div class="mb-7">
          <a routerLink="/profile" class="text-sm text-muted-foreground hover:text-foreground"
            >← Profile</a
          >
          <p class="kicker mb-2 mt-3">Account</p>
          <h1 class="text-3xl font-semibold text-foreground">Notifications</h1>
          <p class="text-sm text-muted-foreground mt-1.5">
            Everything shows up under the bell in the app. Choose what is also sent by email.
          </p>
        </div>

        @if (loading()) {
          <div class="card p-8 flex items-center justify-center gap-3 text-muted-foreground">
            <span class="spinner"></span>
            <span class="text-sm">Loading preferences...</span>
          </div>
        } @else if (loadError()) {
          <div class="card p-5">
            <p class="text-sm text-destructive">{{ loadError() }}</p>
            <button type="button" class="btn btn-secondary btn-sm mt-3" (click)="load()">
              Try again
            </button>
          </div>
        } @else {
          <div class="card p-5 mb-4">
            @if (emailAddress()) {
              <p class="text-sm text-foreground">
                Emails go to <span class="font-semibold">{{ emailAddress() }}</span
                >.
              </p>
            } @else {
              <p class="text-sm text-destructive">
                Your account has no email address, so no emails are sent.
              </p>
            }
            <p class="text-xs text-muted-foreground mt-1">
              Sign-up codes, password resets and other security emails are always sent.
            </p>
          </div>

          <div class="card divide-y divide-border">
            @for (row of types(); track row.type) {
              <div class="p-5 flex items-start justify-between gap-4">
                <div class="min-w-0">
                  <label [for]="'email-' + row.type" class="text-sm font-semibold text-foreground">
                    {{ row.label }}
                  </label>
                  <p class="text-xs text-muted-foreground mt-0.5">{{ row.description }}</p>
                  @if (!row.email_optional) {
                    <p class="text-xs text-muted-foreground mt-1">Always emailed.</p>
                  }
                </div>
                <input
                  type="checkbox"
                  class="toggle mt-0.5"
                  [id]="'email-' + row.type"
                  [checked]="row.email_enabled"
                  [disabled]="!row.email_optional || saving() === row.type"
                  [attr.aria-label]="'Email: ' + row.label"
                  (change)="toggle(row, $event)"
                />
              </div>
            }
          </div>
        }
      </div>
    </div>
  `,
})
export class NotificationPreferencesComponent implements OnInit {
  private service = inject(NotificationPreferencesService);
  private toast = inject(ToastService);

  loading = signal(true);
  loadError = signal('');
  emailAddress = signal('');
  types = signal<NotificationTypePreference[]>([]);
  /** Type whose change is being saved (its toggle is disabled meanwhile). */
  saving = signal<string | null>(null);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set('');
    this.service.get().subscribe({
      next: (prefs) => {
        this.emailAddress.set(prefs.email_address);
        this.types.set(prefs.types);
        this.loading.set(false);
      },
      error: (err) => {
        this.loadError.set(
          apiErrorMessage(err, 'Could not load your notification settings.', 'detail'),
        );
        this.loading.set(false);
      },
    });
  }

  toggle(row: NotificationTypePreference, evt: Event): void {
    const input = evt.target as HTMLInputElement;
    const enabled = input.checked;
    this.saving.set(row.type);
    this.service.setEmail({ [row.type]: enabled }).subscribe({
      next: (prefs) => {
        this.types.set(prefs.types);
        this.saving.set(null);
        this.toast.success(enabled ? `${row.label}: emails on.` : `${row.label}: emails off.`);
      },
      error: (err) => {
        // Put the switch back: the server kept the old setting.
        input.checked = !enabled;
        this.saving.set(null);
        this.toast.error(apiErrorMessage(err, 'Could not save the setting.', 'email', 'detail'));
      },
    });
  }
}
