import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from '../../i18n/language.service';
import { NotificationPreferencesService } from '../../services/notification-preferences.service';

type State = 'loading' | 'invalid' | 'ready' | 'saving' | 'done' | 'failed';

/**
 * `/unsubscribe?token=…`: the footer link of optional emails. Public (no
 * sign-in). It shows which email the link switches off and asks for a click:
 * nothing changes on load, so mail scanners that open links are harmless.
 */
@Component({
  selector: 'app-unsubscribe',
  standalone: true,
  imports: [RouterModule, TranslocoPipe],
  template: `
    <div class="page-root">
      <div class="container max-w-lg py-12">
        <p class="kicker mb-2">{{ 'unsubscribe.kicker' | transloco }}</p>
        <h1 class="text-3xl font-semibold text-foreground mb-6">
          {{ 'unsubscribe.title' | transloco }}
        </h1>

        <div class="card p-6" aria-live="polite">
          @switch (state()) {
            @case ('loading') {
              <div class="flex items-center gap-3 text-muted-foreground">
                <span class="spinner"></span>
                <span class="text-sm">{{ 'unsubscribe.loading' | transloco }}</span>
              </div>
            }
            @case ('invalid') {
              <p class="text-sm text-destructive" data-testid="unsubscribe-invalid">
                {{ 'unsubscribe.invalid' | transloco }}
              </p>
              <a routerLink="/profile/notifications" class="btn btn-secondary btn-sm mt-4">
                {{ 'unsubscribe.managePreferences' | transloco }}
              </a>
            }
            @case ('done') {
              <p class="text-sm text-foreground" data-testid="unsubscribe-done">
                {{ 'unsubscribe.done' | transloco: { label: label() } }}
              </p>
              <p class="text-xs text-muted-foreground mt-2">
                {{ 'unsubscribe.doneHint' | transloco }}
              </p>
              <a routerLink="/profile/notifications" class="btn btn-secondary btn-sm mt-4">
                {{ 'unsubscribe.managePreferences' | transloco }}
              </a>
            }
            @default {
              <p class="text-sm text-foreground">
                {{ 'unsubscribe.confirmText' | transloco: { label: label() } }}
              </p>
              <p class="text-xs text-muted-foreground mt-2">
                {{ 'unsubscribe.inAppStays' | transloco }}
              </p>
              @if (state() === 'failed') {
                <p class="text-sm text-destructive mt-3" role="alert">
                  {{ 'unsubscribe.failed' | transloco }}
                </p>
              }
              <div class="flex flex-wrap items-center gap-3 mt-5">
                <button
                  type="button"
                  class="btn btn-primary"
                  [disabled]="state() === 'saving'"
                  (click)="confirm()"
                >
                  {{
                    (state() === 'saving' ? 'unsubscribe.saving' : 'unsubscribe.confirm')
                      | transloco
                  }}
                </button>
                <a routerLink="/profile/notifications" class="btn btn-secondary">
                  {{ 'unsubscribe.managePreferences' | transloco }}
                </a>
              </div>
            }
          }
        </div>
      </div>
    </div>
  `,
})
export class UnsubscribeComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private service = inject(NotificationPreferencesService);
  private language = inject(LanguageService);
  private destroyRef = inject(DestroyRef);

  state = signal<State>('loading');
  /** The email type's label, in the UI language (from the API). */
  label = signal('');
  private token = '';

  ngOnInit(): void {
    this.token = this.route.snapshot.queryParamMap.get('token') ?? '';
    if (!this.token) {
      this.state.set('invalid');
      return;
    }
    this.describe(true);
    // The label comes from the API in the request language: refresh it on a switch.
    this.language.switched$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.describe(false));
  }

  confirm(): void {
    this.state.set('saving');
    this.service.unsubscribe(this.token).subscribe({
      next: (info) => {
        this.label.set(info.label);
        this.state.set('done');
      },
      error: (err: { status?: number }) =>
        this.state.set(err.status === 400 ? 'invalid' : 'failed'),
    });
  }

  private describe(initial: boolean): void {
    this.service.describeUnsubscribe(this.token).subscribe({
      next: (info) => {
        this.label.set(info.label);
        if (initial) this.state.set('ready');
      },
      error: () => {
        if (initial) this.state.set('invalid');
      },
    });
  }
}
