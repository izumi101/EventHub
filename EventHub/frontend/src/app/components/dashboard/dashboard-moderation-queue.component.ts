import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterModule } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { Subject, catchError, map, of, switchMap } from 'rxjs';
import { Clock, LucideAngularModule, Shield } from 'lucide-angular';
import { errorMessage } from '../../api/error-message';
import { LanguageService } from '../../i18n/language.service';
import { LocalDatePipe } from '../../i18n/locale.pipes';
import type { Event } from '../../models/models';
import { EventService } from '../../services/event.service';
import type { SectionStatus } from './dashboard-summary.component';

type QueueResult =
  { page: number; events: Event[]; count: number } | { page: number; message: string };

/**
 * A superuser's dashboard: the moderation queue (events waiting for approval),
 * paged. Approving or rejecting happens on the event page and on the
 * moderation page, which this links to; the queue itself changes nothing.
 */
@Component({
  selector: 'app-dashboard-moderation-queue',
  standalone: true,
  imports: [RouterModule, LucideAngularModule, TranslocoPipe, LocalDatePipe],
  template: `
    <section aria-labelledby="dashboard-queue-title" data-testid="moderation-queue">
      <div class="flex flex-wrap items-center justify-between gap-3 mb-3">
        <h2
          id="dashboard-queue-title"
          class="text-sm font-semibold text-foreground flex items-center gap-2"
        >
          <lucide-icon [img]="icons.Clock" class="w-4 h-4 text-warning" aria-hidden="true" />
          {{
            (status() === 'ready'
              ? 'moderation.awaitingApprovalPendinglength'
              : 'moderation.awaitingApprovalTitle'
            ) | transloco: { pendingLength: total() }
          }}
        </h2>
        <a
          routerLink="/admin/moderation"
          class="btn btn-sm btn-secondary flex items-center gap-1.5"
          data-testid="queue-moderation-link"
        >
          <lucide-icon [img]="icons.Shield" class="w-3.5 h-3.5" aria-hidden="true" />
          {{ 'dashboard.openModeration' | transloco }}
        </a>
      </div>

      @if (status() === 'loading') {
        <div
          class="space-y-3"
          role="status"
          [attr.aria-label]="'common.loading' | transloco"
          data-testid="queue-loading"
        >
          @for (n of placeholders; track n) {
            <div class="card p-4" aria-hidden="true">
              <div class="h-4 w-1/2 rounded bg-muted animate-pulse mb-2"></div>
              <div class="h-3 w-3/4 rounded bg-muted animate-pulse"></div>
            </div>
          }
        </div>
      } @else if (status() === 'error') {
        <div class="note note-error" role="alert" data-testid="queue-error">
          <span class="flex-1">{{ error() }}</span>
          <button type="button" class="btn btn-sm btn-secondary" (click)="reload()">
            {{ 'common.retry' | transloco }}
          </button>
        </div>
      } @else if (events().length === 0) {
        <div class="card p-8 text-center" data-testid="queue-empty">
          <p class="text-sm text-muted-foreground">
            {{ 'moderation.nothingToReviewThe' | transloco }}
          </p>
        </div>
      } @else {
        <ul class="space-y-3">
          @for (ev of events(); track ev.id) {
            <li class="card p-4" data-testid="queue-item">
              <a
                [routerLink]="['/events', ev.id]"
                class="font-semibold text-foreground hover:text-primary transition-colors"
                >{{ ev.title }}</a
              >
              <p class="text-xs text-muted-foreground mt-0.5">
                {{
                  'moderation.byUsernameDateLocation'
                    | transloco
                      : {
                          username: ev.organizer.username,
                          date: (ev.date | localDate: 'MMM d, y · h:mm a'),
                          location: ev.location,
                        }
                }}
              </p>
            </li>
          }
        </ul>
        <div class="mt-4 flex flex-col items-center gap-2">
          <p class="text-xs text-muted-foreground" data-testid="queue-counter">
            {{ 'dashboard.countOfTotal' | transloco: { shown: events().length, total: total() } }}
          </p>
          @if (moreError(); as message) {
            <div class="note note-error w-full" role="alert">{{ message }}</div>
          }
          @if (events().length < total()) {
            <button
              type="button"
              class="btn btn-secondary btn-sm flex items-center gap-2"
              [disabled]="loadingMore()"
              (click)="showMore()"
              data-testid="queue-more"
            >
              @if (loadingMore()) {
                <span class="spinner spinner-sm" aria-hidden="true"></span>
              }
              {{ 'dashboard.showMore' | transloco }}
            </button>
          }
        </div>
      }
    </section>
  `,
})
export class DashboardModerationQueueComponent implements OnInit {
  private readonly eventService = inject(EventService);
  private readonly language = inject(LanguageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly status = signal<SectionStatus>('loading');
  readonly events = signal<Event[]>([]);
  readonly total = signal(0);
  readonly loadingMore = signal(false);
  readonly error = signal('');
  readonly moreError = signal<string | null>(null);
  readonly icons = { Clock, Shield };
  readonly placeholders = [1, 2, 3];

  private page = 1;
  private readonly requests$ = new Subject<number>();

  constructor() {
    this.requests$
      .pipe(
        switchMap((page) =>
          this.eventService.getEvents({ status: 'pending', page }).pipe(
            map((res): QueueResult => ({ page, events: res.results, count: res.count })),
            catchError((err: unknown) =>
              of<QueueResult>({
                page,
                message: errorMessage(err, this.language, {
                  fallback: this.language.t('moderation.failedToLoadThe'),
                }),
              }),
            ),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        if ('message' in result) {
          if (result.page === 1) {
            this.error.set(result.message);
            this.status.set('error');
          } else {
            this.moreError.set(result.message);
            this.loadingMore.set(false);
          }
          return;
        }
        this.page = result.page;
        this.events.update((current) => {
          if (result.page === 1) return result.events;
          const seen = new Set(current.map((e) => e.id));
          return [...current, ...result.events.filter((e) => !seen.has(e.id))];
        });
        this.total.set(result.count);
        this.loadingMore.set(false);
        this.moreError.set(null);
        this.status.set('ready');
      });
  }

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.status.set('loading');
    this.loadingMore.set(false);
    this.moreError.set(null);
    this.requests$.next(1);
  }

  showMore(): void {
    if (this.loadingMore() || this.events().length >= this.total()) return;
    this.loadingMore.set(true);
    this.moreError.set(null);
    this.requests$.next(this.page + 1);
  }
}
