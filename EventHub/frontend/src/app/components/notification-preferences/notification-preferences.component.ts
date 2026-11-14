import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterModule } from '@angular/router';
import {
  NotificationPreferencesService,
  type NotificationTypePreference,
} from '../../services/notification-preferences.service';
import { ToastService } from '../../services/toast.service';
import { apiErrorMessage } from '../../api/api-error';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from '../../i18n/language.service';

/** Profile → Notifications: which notifications are also sent by email. */
@Component({
  selector: 'app-notification-preferences',
  standalone: true,
  imports: [RouterModule, TranslocoPipe],
  template: `
    <div class="page-root">
      <div class="container max-w-2xl py-8">
        <div class="mb-7">
          <a routerLink="/profile" class="text-sm text-muted-foreground hover:text-foreground">{{
            'profile.back' | transloco
          }}</a>
          <p class="kicker mb-2 mt-3">{{ 'profile.account' | transloco }}</p>
          <h1 class="text-3xl font-semibold text-foreground">
            {{ 'notificationPrefs.title' | transloco }}
          </h1>
          <p class="text-sm text-muted-foreground mt-1.5">
            {{ 'notificationPrefs.intro' | transloco }}
          </p>
        </div>

        @if (loading()) {
          <div class="card p-8 flex items-center justify-center gap-3 text-muted-foreground">
            <span class="spinner"></span>
            <span class="text-sm">{{ 'notificationPrefs.loading' | transloco }}</span>
          </div>
        } @else if (loadError()) {
          <div class="card p-5">
            <p class="text-sm text-destructive">{{ loadError() }}</p>
            <button type="button" class="btn btn-secondary btn-sm mt-3" (click)="load()">
              {{ 'notificationPrefs.tryAgain' | transloco }}
            </button>
          </div>
        } @else {
          <div class="card p-5 mb-4">
            @if (emailAddress()) {
              <p class="text-sm text-foreground">
                {{ 'notificationPrefs.emailsGoTo' | transloco: { email: emailAddress() } }}
              </p>
            } @else {
              <p class="text-sm text-destructive">
                {{ 'notificationPrefs.noEmail' | transloco }}
              </p>
            }
            <p class="text-xs text-muted-foreground mt-1">
              {{ 'notificationPrefs.alwaysSent' | transloco }}
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
                    <p class="text-xs text-muted-foreground mt-1">
                      {{ 'notificationPrefs.alwaysEmailed' | transloco }}
                    </p>
                  }
                </div>
                <input
                  type="checkbox"
                  class="toggle mt-0.5"
                  [id]="'email-' + row.type"
                  [checked]="row.email_enabled"
                  [disabled]="!row.email_optional || saving() === row.type"
                  [attr.aria-label]="
                    'notificationPrefs.emailAria' | transloco: { label: row.label }
                  "
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
  private lang = inject(LanguageService);

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
          apiErrorMessage(err, this.lang.t('notificationPrefs.loadFailed'), 'detail'),
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
        this.toast.success(
          this.lang.t(enabled ? 'notificationPrefs.emailsOn' : 'notificationPrefs.emailsOff', {
            label: row.label,
          }),
        );
      },
      error: (err) => {
        // Put the switch back: the server kept the old setting.
        input.checked = !enabled;
        this.saving.set(null);
        this.toast.error(
          apiErrorMessage(err, this.lang.t('notificationPrefs.saveFailed'), 'email', 'detail'),
        );
      },
    });
  }
}
