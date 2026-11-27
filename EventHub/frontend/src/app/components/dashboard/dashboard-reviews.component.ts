import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterModule } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { Subject, catchError, map, of, switchMap } from 'rxjs';
import { errorMessage } from '../../api/error-message';
import { LanguageService } from '../../i18n/language.service';
import { LocalDatePipe, LocalNumberPipe, PluralPipe } from '../../i18n/locale.pipes';
import {
  OrganizerDashboardService,
  type RecentReview,
  type ReviewsSummary,
} from '../../services/organizer-dashboard.service';
import { relativeTime } from '../../utils/relative-time';
import { DashboardStarsComponent } from './dashboard-stars.component';
import type { SectionStatus } from './dashboard-summary.component';
import { LucideAngularModule, Star } from 'lucide-angular';

/** Longer than this, a comment is likely to need more than 3 lines: "More" is offered. */
export const COMMENT_PREVIEW_CHARS = 140;
const COMMENT_PREVIEW_LINES = 3;

/** Rows of the distribution, best rating first. */
const STARS = [5, 4, 3, 2, 1] as const;

/**
 * How attendees rated the organizer's events: the average, how the ratings
 * spread, and the latest reviews. It loads and fails on its own.
 */
@Component({
  selector: 'app-dashboard-reviews',
  standalone: true,
  imports: [
    RouterModule,
    LucideAngularModule,
    TranslocoPipe,
    LocalDatePipe,
    LocalNumberPipe,
    PluralPipe,
    DashboardStarsComponent,
  ],
  template: `
    <section
      class="card p-5 min-w-0 h-full"
      aria-labelledby="dashboard-reviews-title"
      data-testid="reviews"
    >
      <h2 id="dashboard-reviews-title" class="text-sm font-semibold text-foreground mb-4">
        {{ 'dashboard.reviews.title' | transloco }}
      </h2>

      @if (status() === 'loading') {
        <div
          class="space-y-3"
          role="status"
          [attr.aria-label]="'common.loading' | transloco"
          data-testid="reviews-loading"
        >
          <div class="h-9 w-32 rounded bg-muted animate-pulse motion-reduce:animate-none"></div>
          @for (n of placeholders; track n) {
            <div
              class="h-3 rounded bg-muted animate-pulse motion-reduce:animate-none"
              aria-hidden="true"
            ></div>
          }
        </div>
      } @else if (status() === 'error') {
        <div class="note note-error" role="alert" data-testid="reviews-error">
          <span class="flex-1">{{ error() }}</span>
          <button type="button" class="btn btn-sm btn-secondary" (click)="reload()">
            {{ 'common.retry' | transloco }}
          </button>
        </div>
      } @else if (data(); as r) {
        @if (r.count === 0 || r.average === null) {
          <div data-testid="reviews-empty">
            <p class="text-sm font-medium text-foreground">
              {{ 'dashboard.reviews.empty' | transloco }}
            </p>
            <p class="text-xs text-muted-foreground mt-1">
              {{ 'dashboard.reviews.emptyHint' | transloco }}
            </p>
          </div>
        } @else {
          <div class="flex items-center gap-4 mb-4">
            <p class="text-3xl font-bold text-foreground num" data-testid="reviews-average">
              {{ r.average | localNumber: '1.1-1' }}
            </p>
            <div>
              <app-dashboard-stars [rating]="r.average" [decimals]="1" size="md" />
              <p class="text-xs text-muted-foreground mt-0.5" data-testid="reviews-count">
                {{ 'dashboard.reviews.count' | tPlural: r.count }}
              </p>
            </div>
          </div>

          <ul
            class="space-y-1.5 mb-5"
            [attr.aria-label]="'dashboard.reviews.distribution' | transloco"
            data-testid="reviews-distribution"
          >
            @for (row of rows(); track row.stars) {
              <li class="flex items-center gap-2 text-xs" data-testid="reviews-row">
                <span class="sr-only">{{
                  'dashboard.reviews.rowLabel' | transloco: { stars: row.stars, count: row.count }
                }}</span>
                <span
                  class="w-6 flex items-center gap-0.5 text-muted-foreground"
                  aria-hidden="true"
                >
                  <span class="num">{{ row.stars }}</span>
                  <lucide-icon [img]="icons.Star" class="w-3 h-3 fill-current text-warning" />
                </span>
                <span class="flex-1 h-2 rounded-full bg-muted overflow-hidden" aria-hidden="true">
                  <span
                    class="block h-full rounded-full bg-ember"
                    [style.width.%]="row.percent"
                    data-testid="reviews-bar"
                  ></span>
                </span>
                <span
                  class="w-8 text-right num text-foreground"
                  aria-hidden="true"
                  data-testid="reviews-row-count"
                  >{{ row.count | localNumber }}</span
                >
              </li>
            }
          </ul>

          <h3 class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            {{ 'dashboard.reviews.recent' | transloco }}
          </h3>
          <ul class="divide-y divide-border/60" data-testid="reviews-recent">
            @for (review of r.recent; track $index) {
              <li class="py-3 first:pt-0 last:pb-0" data-testid="review">
                <div class="flex items-center justify-between gap-2">
                  <span
                    class="text-sm font-medium text-foreground truncate"
                    data-testid="review-author"
                    >{{ author(review) }}</span
                  >
                  <app-dashboard-stars [rating]="review.rating" />
                </div>
                <a
                  [routerLink]="['/events', review.event_id]"
                  class="text-xs text-primary hover:underline block truncate"
                  data-testid="review-event"
                  >{{ review.event_title }}</a
                >
                @if (review.comment) {
                  <p
                    [id]="commentId($index)"
                    class="text-sm text-foreground mt-1 break-words whitespace-pre-line"
                    [class.line-clamp-3]="!isExpanded($index)"
                    data-testid="review-comment"
                  >
                    {{ review.comment }}
                  </p>
                  @if (isLong(review)) {
                    <button
                      type="button"
                      class="text-xs text-primary hover:underline"
                      [attr.aria-expanded]="isExpanded($index)"
                      [attr.aria-controls]="commentId($index)"
                      (click)="toggle($index)"
                      data-testid="review-toggle"
                    >
                      {{
                        (isExpanded($index) ? 'dashboard.reviews.less' : 'dashboard.reviews.more')
                          | transloco
                      }}
                    </button>
                  }
                }
                <p class="text-2xs text-muted-foreground mt-1">
                  <time
                    [attr.datetime]="review.created_at"
                    [title]="review.created_at | localDate: 'MMM d, y · h:mm a'"
                    data-testid="review-time"
                    >{{ relative(review) }}</time
                  >
                </p>
              </li>
            }
          </ul>
        }
      }
    </section>
  `,
})
export class DashboardReviewsComponent implements OnInit {
  private readonly service = inject(OrganizerDashboardService);
  private readonly language = inject(LanguageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly status = signal<SectionStatus>('loading');
  readonly data = signal<ReviewsSummary | null>(null);
  readonly error = signal('');
  /** Indexes (in the recent list) of the comments shown in full. */
  private readonly expanded = signal<ReadonlySet<number>>(new Set());

  readonly icons = { Star };
  readonly placeholders = [1, 2, 3, 4, 5];

  private readonly requests$ = new Subject<void>();

  /** One row per rating, 5 to 1; the bar is the share of all reviews. */
  readonly rows = computed(() => {
    const data = this.data();
    if (!data) return [];
    return STARS.map((stars) => {
      const count = data.distribution[stars];
      return { stars, count, percent: data.count > 0 ? (count / data.count) * 100 : 0 };
    });
  });

  constructor() {
    this.requests$
      .pipe(
        switchMap(() =>
          this.service.getReviews().pipe(
            map((data) => ({ data })),
            catchError((err: unknown) =>
              of({
                message: errorMessage(err, this.language, {
                  fallback: this.language.t('dashboard.reviews.loadFailed'),
                }),
              }),
            ),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        if ('data' in result) {
          this.data.set(result.data);
          this.expanded.set(new Set());
          this.status.set('ready');
        } else {
          this.error.set(result.message);
          this.status.set('error');
        }
      });
  }

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.status.set('loading');
    this.requests$.next();
  }

  /** The server never sends an email; if one ever slipped through, it is not shown. */
  author(review: RecentReview): string {
    const name = review.author.trim();
    return !name || name.includes('@') ? this.language.t('dashboard.reviews.anonymous') : name;
  }

  commentId(index: number): string {
    return `dashboard-review-comment-${index}`;
  }

  isLong(review: RecentReview): boolean {
    const lines = review.comment.split('\n').length;
    return review.comment.length > COMMENT_PREVIEW_CHARS || lines > COMMENT_PREVIEW_LINES;
  }

  isExpanded(index: number): boolean {
    return this.expanded().has(index);
  }

  toggle(index: number): void {
    this.expanded.update((set) => {
      const next = new Set(set);
      if (!next.delete(index)) next.add(index);
      return next;
    });
  }

  relative(review: RecentReview): string {
    return relativeTime(review.created_at, this.language.locale());
  }
}
