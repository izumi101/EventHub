import {
  Component,
  DestroyRef,
  NgZone,
  OnInit,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterModule } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { Subject, catchError, map, of, switchMap } from 'rxjs';
import {
  CircleCheckBig,
  LucideAngularModule,
  RotateCcw,
  UserPlus,
  Users,
  type LucideIconData,
} from 'lucide-angular';
import { errorMessage } from '../../api/error-message';
import { LanguageService } from '../../i18n/language.service';
import { LocalDatePipe, PluralPipe } from '../../i18n/locale.pipes';
import { MoneyPipe } from '../../pipes/money.pipe';
import {
  OrganizerDashboardService,
  type ActivityFeed,
  type ActivityItem,
  type ActivityType,
} from '../../services/organizer-dashboard.service';
import { relativeTime } from '../../utils/relative-time';
import type { SectionStatus } from './dashboard-summary.component';

export const ACTIVITY_PAGE_SIZE = 10;
/** How often "5 min. ago" is recomputed. */
export const RELATIVE_TIME_TICK_MS = 60_000;

interface ActivityRequest {
  cursor: string | null;
  /** A background refresh: no skeleton, and a failure leaves the list alone. */
  quiet: boolean;
}

type ActivityResult =
  { request: ActivityRequest; feed: ActivityFeed } | { request: ActivityRequest; message: string };

/**
 * The real activity of the last 30 days on the organizer's events (new
 * registrations, group bookings, check-ins, refunds), newest first, paged with
 * the server's cursor. It loads and fails on its own: the rest of the page
 * does not depend on it.
 */
@Component({
  selector: 'app-dashboard-activity',
  standalone: true,
  imports: [RouterModule, LucideAngularModule, TranslocoPipe, MoneyPipe, LocalDatePipe, PluralPipe],
  template: `
    <section class="card p-5" aria-labelledby="dashboard-activity-title" data-testid="activity">
      <h2 id="dashboard-activity-title" class="text-sm font-semibold text-foreground mb-4">
        {{ 'dashboard.recentActivity' | transloco }}
      </h2>

      @if (status() === 'loading') {
        <div
          class="space-y-4"
          role="status"
          [attr.aria-label]="'common.loading' | transloco"
          data-testid="activity-loading"
        >
          @for (n of placeholders; track n) {
            <div class="flex gap-3" aria-hidden="true">
              <div class="w-8 h-8 rounded-full bg-muted animate-pulse flex-shrink-0"></div>
              <div class="flex-1 space-y-2">
                <div class="h-3 w-3/4 rounded bg-muted animate-pulse"></div>
                <div class="h-3 w-1/2 rounded bg-muted animate-pulse"></div>
              </div>
            </div>
          }
        </div>
      } @else if (status() === 'error') {
        <div class="note note-error" role="alert" data-testid="activity-error">
          <span class="flex-1">{{ error() }}</span>
          <button type="button" class="btn btn-sm btn-secondary" (click)="reload()">
            {{ 'common.retry' | transloco }}
          </button>
        </div>
      } @else if (items().length === 0) {
        <p class="text-sm text-muted-foreground" data-testid="activity-empty">
          {{ 'dashboard.noActivity' | transloco }}
        </p>
      } @else {
        <ul class="space-y-4" data-testid="activity-list">
          @for (item of items(); track item.id) {
            <li class="flex gap-3" [attr.data-type]="item.type" data-testid="activity-item">
              <span
                class="w-8 h-8 rounded-full bg-muted flex items-center justify-center flex-shrink-0"
              >
                <lucide-icon
                  [img]="icons[item.type]"
                  class="w-4 h-4 text-muted-foreground"
                  aria-hidden="true"
                />
              </span>
              <div class="min-w-0 flex-1">
                <p class="text-sm text-foreground" data-testid="activity-text">
                  @switch (item.type) {
                    @case ('registration') {
                      {{
                        'dashboard.activityRegistration' | transloco: { name: item.attendee_name }
                      }}
                    }
                    @case ('group_booking') {
                      {{
                        'dashboard.activityGroupBooking'
                          | tPlural: item.quantity : { name: item.attendee_name }
                      }}
                    }
                    @case ('check_in') {
                      {{ 'dashboard.activityCheckIn' | transloco: { name: item.attendee_name } }}
                    }
                    @case ('refund') {
                      {{
                        'dashboard.activityRefund'
                          | transloco
                            : {
                                name: item.attendee_name,
                                amount: item.currency
                                  ? (item.amount | money: item.currency)
                                  : item.amount,
                              }
                      }}
                    }
                  }
                </p>
                <p class="text-xs text-muted-foreground flex flex-wrap items-center gap-x-2">
                  <a
                    [routerLink]="['/organizer/events', item.event_id, 'attendees']"
                    class="text-primary hover:underline truncate max-w-full"
                    data-testid="activity-event-link"
                    >{{ item.event_title }}</a
                  >
                  <span aria-hidden="true">·</span>
                  <time
                    [attr.datetime]="item.occurred_at"
                    [title]="item.occurred_at | localDate: 'MMM d, y · h:mm a'"
                    data-testid="activity-time"
                    >{{ relative(item) }}</time
                  >
                </p>
              </div>
            </li>
          }
        </ul>

        @if (moreError(); as message) {
          <div class="note note-error mt-4" role="alert" data-testid="activity-more-error">
            {{ message }}
          </div>
        }
        @if (nextCursor()) {
          <button
            type="button"
            class="btn btn-sm btn-secondary mt-4 w-full flex items-center justify-center gap-2"
            [disabled]="loadingMore()"
            (click)="showMore()"
            data-testid="activity-more"
          >
            @if (loadingMore()) {
              <span class="spinner spinner-sm" aria-hidden="true"></span>
            }
            {{ (moreError() ? 'common.retry' : 'dashboard.showMore') | transloco }}
          </button>
        }
      }
    </section>
  `,
})
export class DashboardActivityComponent implements OnInit {
  private readonly service = inject(OrganizerDashboardService);
  private readonly language = inject(LanguageService);
  private readonly destroyRef = inject(DestroyRef);

  /**
   * Bump it to refresh the feed (the page does after it deleted or copied an
   * event). The list stays on screen while the new one loads.
   */
  readonly refreshToken = input(0);

  readonly status = signal<SectionStatus>('loading');
  readonly items = signal<ActivityItem[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly loadingMore = signal(false);
  readonly error = signal('');
  readonly moreError = signal<string | null>(null);

  /** "5 min. ago" is recomputed against this clock, which ticks without any request. */
  private readonly now = signal(Date.now());

  readonly icons: Record<ActivityType, LucideIconData> = {
    registration: UserPlus,
    group_booking: Users,
    check_in: CircleCheckBig,
    refund: RotateCcw,
  };
  readonly placeholders = [1, 2, 3];

  /** First page and "show more" share one stream, so a newer request cancels an older one. */
  private readonly requests$ = new Subject<ActivityRequest>();

  constructor() {
    this.requests$
      .pipe(
        switchMap((request) =>
          this.service.getActivity({ limit: ACTIVITY_PAGE_SIZE, cursor: request.cursor }).pipe(
            map((feed): ActivityResult => ({ request, feed })),
            catchError((err: unknown) =>
              of<ActivityResult>({
                request,
                message: errorMessage(err, this.language, {
                  fallback: this.language.t('dashboard.activityFailed'),
                }),
              }),
            ),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        const { cursor, quiet } = result.request;
        if ('message' in result) {
          if (quiet) {
            // A failed background refresh keeps what is on screen.
            this.loadingMore.set(false);
          } else if (cursor === null) {
            this.error.set(result.message);
            this.status.set('error');
          } else {
            this.moreError.set(result.message);
            this.loadingMore.set(false);
          }
          return;
        }
        const { feed } = result;
        this.items.update((current) => {
          if (cursor === null) return feed.results;
          const seen = new Set(current.map((i) => i.id));
          return [...current, ...feed.results.filter((i) => !seen.has(i.id))];
        });
        this.nextCursor.set(feed.next_cursor);
        this.loadingMore.set(false);
        this.moreError.set(null);
        this.status.set('ready');
      });

    // The relative times move on every minute. The timer lives outside the
    // zone (it must not keep the app "unstable") and asks the server nothing.
    const zone = inject(NgZone);
    const timer = zone.runOutsideAngular(() =>
      setInterval(() => {
        this.now.set(Date.now());
      }, RELATIVE_TIME_TICK_MS),
    );
    this.destroyRef.onDestroy(() => {
      clearInterval(timer);
    });

    effect(() => {
      if (this.refreshToken() > 0) untracked(() => this.refreshQuietly());
    });
  }

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.status.set('loading');
    this.loadingMore.set(false);
    this.moreError.set(null);
    this.requests$.next({ cursor: null, quiet: false });
  }

  private refreshQuietly(): void {
    this.loadingMore.set(false);
    this.moreError.set(null);
    this.requests$.next({ cursor: null, quiet: true });
  }

  showMore(): void {
    const cursor = this.nextCursor();
    if (!cursor || this.loadingMore()) return;
    this.loadingMore.set(true);
    this.moreError.set(null);
    this.requests$.next({ cursor, quiet: false });
  }

  relative(item: ActivityItem): string {
    return relativeTime(item.occurred_at, this.language.locale(), this.now());
  }
}
