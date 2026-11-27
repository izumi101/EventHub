import {
  Component,
  computed,
  DestroyRef,
  Injector,
  afterNextRender,
  inject,
  signal,
  viewChildren,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, ParamMap, Params, Router, RouterModule } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import {
  Subject,
  catchError,
  debounceTime,
  distinctUntilChanged,
  filter,
  map,
  of,
  switchMap,
} from 'rxjs';
import { ChartNoAxesColumn, LucideAngularModule, Plus, ScanLine } from 'lucide-angular';
import { errorMessage } from '../../api/error-message';
import { LanguageService } from '../../i18n/language.service';
import { AuthService } from '../../services/auth.service';
import { EventService } from '../../services/event.service';
import { ModalService } from '../../services/modal.service';
import {
  DASHBOARD_ORDERINGS,
  DASHBOARD_PAGE_SIZE,
  DASHBOARD_TABS,
  DEFAULT_ORDERING,
  DEFAULT_SALES_RANGE,
  OrganizerDashboardService,
  SALES_RANGES,
  SEARCH_MAX_LENGTH,
  type DashboardOrdering,
  type DashboardSummary,
  type DashboardTab,
  type OrganizerEvent,
  type OrganizerEventPage,
  type SalesRange,
} from '../../services/organizer-dashboard.service';
import { ToastService } from '../../services/toast.service';
import { isAdmin } from '../../utils/roles';
import { DashboardActivityComponent } from './dashboard-activity.component';
import { DashboardEventCardComponent } from './dashboard-event-card.component';
import { DashboardModerationQueueComponent } from './dashboard-moderation-queue.component';
import { DashboardReviewsComponent } from './dashboard-reviews.component';
import { DashboardSalesComponent } from './dashboard-sales.component';
import { DashboardTodayComponent } from './dashboard-today.component';
import { DashboardSummaryComponent, type SectionStatus } from './dashboard-summary.component';
import {
  DASHBOARD_PANEL_ID,
  DashboardToolbarComponent,
  TAB_LABEL,
  dashboardTabId,
} from './dashboard-toolbar.component';

/** The event title column of the backend is 200 characters wide. */
export const EVENT_TITLE_MAX_LENGTH = 200;

/** What the list shows. It lives in the URL, so reload and back navigation restore it. */
export interface ListQuery {
  tab: DashboardTab;
  search: string;
  ordering: DashboardOrdering;
}

interface ListRequest {
  query: ListQuery;
  page: number;
  /** How many pages in a row were asked because the one before brought nothing new. */
  attempt: number;
}

/** Bound on those follow-up requests. */
const MAX_EMPTY_PAGES = 3;

type ListResult =
  { request: ListRequest; page: OrganizerEventPage } | { request: ListRequest; message: string };

const sameQuery = (a: ListQuery, b: ListQuery): boolean =>
  a.tab === b.tab && a.search === b.search && a.ordering === b.ordering;

/** Query params to state; anything missing or unknown falls back to the defaults. */
export function parseQuery(params: ParamMap): ListQuery {
  const tab = DASHBOARD_TABS.find((t) => t === params.get('tab')) ?? 'upcoming';
  const ordering = DASHBOARD_ORDERINGS.find((o) => o === params.get('ordering'));
  return {
    tab,
    search: (params.get('search') ?? '').trim().slice(0, SEARCH_MAX_LENGTH),
    ordering: ordering ?? DEFAULT_ORDERING[tab],
  };
}

/** The sales chart's window from the URL; anything missing or unknown is the default. */
export function parseRange(params: ParamMap): SalesRange {
  return SALES_RANGES.find((r) => r === params.get('range')) ?? DEFAULT_SALES_RANGE;
}

/** The default window is left out of the URL, like the default tab. */
export function rangeQueryParams(range: SalesRange): Params {
  return range === DEFAULT_SALES_RANGE ? {} : { range };
}

/** State to query params; defaults are left out of the URL. */
export function toQueryParams(query: ListQuery): Params {
  const params: Params = {};
  if (query.tab !== 'upcoming') params['tab'] = query.tab;
  if (query.search) params['search'] = query.search;
  if (query.ordering !== DEFAULT_ORDERING[query.tab]) params['ordering'] = query.ordering;
  return params;
}

const EMPTY_KEYS: Record<DashboardTab, { title: string; text: string }> = {
  upcoming: { title: 'dashboard.noUpcomingEvents', text: 'dashboard.createYourFirstEvent' },
  past: { title: 'dashboard.noPastEvents', text: 'dashboard.yourCompletedEventsWill' },
  drafts: { title: 'dashboard.noDrafts', text: 'dashboard.saveEventDraftsBefore' },
  inactive: { title: 'dashboard.noInactiveEvents', text: 'dashboard.inactiveHint' },
};

/**
 * The organizer dashboard: global totals, the organizer's events (one tab at a
 * time, paged, searchable, sortable) and the activity feed. The three sections
 * load and fail independently. A superuser sees the moderation queue instead.
 */
@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    RouterModule,
    LucideAngularModule,
    TranslocoPipe,
    DashboardSummaryComponent,
    DashboardToolbarComponent,
    DashboardEventCardComponent,
    DashboardActivityComponent,
    DashboardModerationQueueComponent,
    DashboardSalesComponent,
    DashboardReviewsComponent,
    DashboardTodayComponent,
  ],
  template: `
    <div class="page-root">
      <div class="container max-w-6xl py-8">
        <header class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div>
            <p class="kicker mb-2">
              {{ (admin ? 'dashboard.admin' : 'dashboard.workspace') | transloco }}
            </p>
            <h1 class="text-3xl font-semibold text-foreground">
              {{ (admin ? 'dashboard.adminPanel' : 'dashboard.organizerDashboard') | transloco }}
            </h1>
            <p class="text-sm text-muted-foreground mt-1.5">
              {{
                (admin ? 'dashboard.reviewAndApproveEvents' : 'dashboard.manageYourEventsAnd')
                  | transloco
              }}
            </p>
          </div>
          @if (!admin) {
            <div class="flex items-center gap-2 flex-shrink-0">
              <a routerLink="/scan" class="btn btn-secondary flex items-center gap-1.5">
                <lucide-icon [img]="icons.ScanLine" class="w-4 h-4" aria-hidden="true" />
                {{ 'dashboard.scan' | transloco }}
              </a>
              <a routerLink="/create-event" class="btn btn-primary flex items-center gap-1.5">
                <lucide-icon [img]="icons.Plus" class="w-4 h-4" aria-hidden="true" />
                {{ 'dashboard.newEvent' | transloco }}
              </a>
            </div>
          }
        </header>

        @if (admin) {
          <app-dashboard-moderation-queue />
        } @else {
          <div class="mb-6">
            <app-dashboard-summary
              [summary]="summary()"
              [status]="summaryStatus()"
              [linkParams]="linkParams()"
              (retry)="loadSummary()"
            />
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
            <div class="lg:col-span-2 min-w-0">
              <app-dashboard-sales [range]="range()" (rangeChange)="setRange($event)" />
            </div>
            <div class="lg:col-span-1 min-w-0">
              <app-dashboard-reviews />
            </div>
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
            <div class="lg:col-span-2 min-w-0 space-y-4">
              <app-dashboard-today [linkParams]="linkParams()" />

              <app-dashboard-toolbar
                [tab]="query().tab"
                [counts]="summary()?.tabs ?? null"
                [searchText]="searchText()"
                [ordering]="query().ordering"
                (tabChange)="setTab($event)"
                (searchInput)="onSearchInput($event)"
                (orderingChange)="setOrdering($event)"
              />

              <div
                [id]="panelId"
                role="tabpanel"
                [attr.aria-labelledby]="tabId(query().tab)"
                [attr.aria-busy]="listStatus() === 'loading'"
                class="space-y-4"
              >
                <h2 class="sr-only">{{ 'dashboard.events' | transloco }}</h2>
                <p class="sr-only" role="status" aria-live="polite" data-testid="live-region">
                  {{ announcement() }}
                </p>

                @switch (listStatus()) {
                  @case ('loading') {
                    <div
                      class="space-y-4"
                      role="status"
                      [attr.aria-label]="'common.loading' | transloco"
                      data-testid="list-loading"
                    >
                      @for (n of placeholders; track n) {
                        <div class="card p-5" aria-hidden="true">
                          <div class="h-5 w-24 rounded bg-muted animate-pulse mb-3"></div>
                          <div class="h-5 w-2/3 rounded bg-muted animate-pulse mb-3"></div>
                          <div class="h-3 w-1/2 rounded bg-muted animate-pulse mb-5"></div>
                          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            <div class="h-10 rounded bg-muted animate-pulse"></div>
                            <div class="h-10 rounded bg-muted animate-pulse"></div>
                            <div class="h-10 rounded bg-muted animate-pulse"></div>
                            <div class="h-10 rounded bg-muted animate-pulse"></div>
                          </div>
                        </div>
                      }
                    </div>
                  }
                  @case ('error') {
                    <div class="note note-error" role="alert" data-testid="list-error">
                      <span class="flex-1">{{ listError() }}</span>
                      <button type="button" class="btn btn-sm btn-secondary" (click)="retryList()">
                        {{ 'common.retry' | transloco }}
                      </button>
                    </div>
                  }
                  @default {
                    @if (events().length === 0) {
                      <div
                        class="card p-12 flex flex-col items-center text-center"
                        data-testid="list-empty"
                      >
                        <div
                          class="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4"
                        >
                          <lucide-icon
                            [img]="icons.ChartNoAxesColumn"
                            class="w-5 h-5 text-muted-foreground"
                            aria-hidden="true"
                          />
                        </div>
                        @if (query().search) {
                          <h3 class="text-base font-semibold text-foreground mb-1">
                            {{ 'dashboard.noSearchResults' | transloco: { query: query().search } }}
                          </h3>
                          <p class="text-sm text-muted-foreground mb-5 max-w-xs">
                            {{ 'dashboard.noSearchResultsHint' | transloco }}
                          </p>
                          <button
                            type="button"
                            class="btn btn-secondary btn-sm"
                            (click)="clearSearch()"
                            data-testid="clear-search"
                          >
                            {{ 'dashboard.clearSearch' | transloco }}
                          </button>
                        } @else {
                          <h3 class="text-base font-semibold text-foreground mb-1">
                            {{ emptyKeys[query().tab].title | transloco }}
                          </h3>
                          <p class="text-sm text-muted-foreground mb-5 max-w-xs">
                            {{ emptyKeys[query().tab].text | transloco }}
                          </p>
                          @if (query().tab === 'drafts') {
                            <a
                              routerLink="/create-event"
                              class="btn btn-primary btn-sm flex items-center gap-1.5"
                              data-testid="empty-create"
                            >
                              <lucide-icon
                                [img]="icons.Plus"
                                class="w-3.5 h-3.5"
                                aria-hidden="true"
                              />
                              {{ 'dashboard.createEvent' | transloco }}
                            </a>
                          }
                        }
                      </div>
                    } @else {
                      <div class="space-y-4" data-testid="event-list">
                        @for (ev of events(); track ev.id) {
                          <app-dashboard-event-card
                            [event]="ev"
                            [menuOpen]="openMenuId() === ev.id"
                            [duplicating]="duplicatingId() === ev.id"
                            (menuOpenChange)="setMenu(ev.id, $event)"
                            (duplicate)="duplicate(ev)"
                            (remove)="remove(ev)"
                          />
                        }
                      </div>
                      <div class="flex flex-col items-center gap-2 pt-1">
                        <p class="text-xs text-muted-foreground" data-testid="list-counter">
                          {{
                            'dashboard.countOfTotal'
                              | transloco: { shown: events().length, total: total() }
                          }}
                        </p>
                        @if (moreError(); as message) {
                          <div class="note note-error w-full" role="alert" data-testid="more-error">
                            {{ message }}
                          </div>
                        }
                        @if (events().length < total()) {
                          <button
                            type="button"
                            class="btn btn-secondary btn-sm flex items-center gap-2"
                            [disabled]="loadingMore()"
                            (click)="showMore()"
                            data-testid="show-more"
                          >
                            @if (loadingMore()) {
                              <span class="spinner spinner-sm" aria-hidden="true"></span>
                            }
                            {{ 'dashboard.showMore' | transloco }}
                          </button>
                        }
                      </div>
                    }
                  }
                }
              </div>
            </div>

            <aside class="lg:col-span-1 min-w-0">
              <app-dashboard-activity [refreshToken]="activityRefresh()" />
            </aside>
          </div>
        }
      </div>
    </div>
  `,
})
export class DashboardComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly service = inject(OrganizerDashboardService);
  private readonly eventService = inject(EventService);
  private readonly modal = inject(ModalService);
  private readonly toast = inject(ToastService);
  private readonly language = inject(LanguageService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly injector = inject(Injector);

  /** A superuser's dashboard is the moderation queue (UX only; the API enforces roles). */
  readonly admin = isAdmin(inject(AuthService).currentUser);

  readonly icons = { Plus, ScanLine, ChartNoAxesColumn };
  readonly panelId = DASHBOARD_PANEL_ID;
  readonly tabId = dashboardTabId;
  readonly emptyKeys = EMPTY_KEYS;
  readonly placeholders = [1, 2, 3];

  /** The sales chart's window. It lives in the URL, next to the list's tab and search. */
  readonly range = signal<SalesRange>(DEFAULT_SALES_RANGE);
  /** Where the links that lead back to the upcoming list point: that tab, and the chart range kept. */
  readonly linkParams = computed<Params>(() => ({
    tab: 'upcoming',
    ...rangeQueryParams(this.range()),
  }));

  // Summary (independent section).
  readonly summary = signal<DashboardSummary | null>(null);
  readonly summaryStatus = signal<SectionStatus>('loading');

  // List state. `query` mirrors the URL.
  readonly query = signal<ListQuery>({
    tab: 'upcoming',
    search: '',
    ordering: DEFAULT_ORDERING.upcoming,
  });
  readonly searchText = signal('');
  readonly events = signal<OrganizerEvent[]>([]);
  readonly total = signal(0);
  readonly listStatus = signal<SectionStatus>('loading');
  readonly listError = signal('');
  readonly loadingMore = signal(false);
  readonly moreError = signal<string | null>(null);
  readonly announcement = signal('');
  readonly openMenuId = signal<number | null>(null);
  readonly duplicatingId = signal<number | null>(null);
  /** Bumped after a delete or a copy: the activity feed reloads. */
  readonly activityRefresh = signal(0);
  private readonly cards = viewChildren(DashboardEventCardComponent);

  /** The search the URL already carries (or is about to), to tell typing from back navigation. */
  private committedSearch = '';
  /** The query this component last navigated to, to tell its own URL changes from back navigation. */
  private expectedQuery: ListQuery | null = null;
  /** Events deleted since this list (tab, search, sort) was opened. */
  private readonly deletedIds = new Set<number>();
  /** The lowest page "Show more" may ask for next (after a page that brought nothing new). */
  private pageFloor = 1;
  private destroyed = false;
  private readonly listRequests$ = new Subject<ListRequest>();
  private readonly summaryRequests$ = new Subject<{ quiet: boolean }>();
  private readonly searchInput$ = new Subject<string>();

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.destroyed = true;
    });
    if (this.admin) return;

    // A newer request cancels the one in flight, so a slow old answer never
    // overwrites a newer one.
    this.listRequests$
      .pipe(
        switchMap((request) =>
          this.service
            .getEvents({
              tab: request.query.tab,
              search: request.query.search,
              // The server's default for the tab is not sent.
              ordering:
                request.query.ordering === DEFAULT_ORDERING[request.query.tab]
                  ? undefined
                  : request.query.ordering,
              page: request.page,
              pageSize: DASHBOARD_PAGE_SIZE,
            })
            .pipe(
              map((page): ListResult => ({ request, page })),
              catchError((err: unknown) =>
                of<ListResult>({
                  request,
                  message: errorMessage(err, this.language, {
                    fallback: this.language.t('dashboard.loadFailed'),
                  }),
                }),
              ),
            ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        this.applyList(result);
      });

    this.summaryRequests$
      .pipe(
        switchMap(({ quiet }) =>
          this.service.getSummary().pipe(
            map((summary) => ({ summary, quiet })),
            catchError(() => of({ summary: null, quiet })),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ summary, quiet }) => {
        if (summary) {
          this.summary.set(summary);
          this.summaryStatus.set('ready');
        } else if (!quiet) {
          this.summaryStatus.set('error');
        }
      });

    this.searchInput$
      .pipe(
        debounceTime(300),
        map((value) => value.trim().slice(0, SEARCH_MAX_LENGTH)),
        filter((value) => value !== this.committedSearch),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((search) => {
        this.committedSearch = search;
        this.navigate({ ...this.query(), search });
      });

    this.route.queryParamMap
      .pipe(map(parseQuery), distinctUntilChanged(sameQuery), takeUntilDestroyed(this.destroyRef))
      .subscribe((query) => {
        const own = this.expectedQuery !== null && sameQuery(query, this.expectedQuery);
        this.expectedQuery = null;
        if (!own) {
          // The URL changed on its own (back/forward navigation, a link): it wins
          // over the search box, even when its search equals the committed one
          // and only the tab or sort differs. A keystroke still waiting for its
          // debounce (the box differs from what is committed) would otherwise
          // override this URL a moment later; replacing it with the URL's own
          // search makes the debounce drop it.
          const typing = this.searchText().trim() !== this.committedSearch;
          this.committedSearch = query.search;
          this.searchText.set(query.search);
          if (typing) this.searchInput$.next(query.search);
        }
        this.query.set(query);
        this.deletedIds.clear();
        this.openMenuId.set(null);
        this.requestList(1);
      });

    this.route.queryParamMap
      .pipe(map(parseRange), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef))
      .subscribe((range) => {
        this.range.set(range);
      });

    this.loadSummary();
  }

  // ── Summary ──

  loadSummary(): void {
    this.summaryStatus.set('loading');
    this.summaryRequests$.next({ quiet: false });
  }

  // ── Sales chart → URL ──

  setRange(range: SalesRange): void {
    if (range === this.range()) return;
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { ...toQueryParams(this.query()), ...rangeQueryParams(range) },
      replaceUrl: true,
    });
  }

  // ── Toolbar → URL ──

  setTab(tab: DashboardTab): void {
    if (tab === this.query().tab) return;
    // Each tab sorts its own way by default, so the sort goes back to it.
    this.navigate({ tab, search: this.query().search, ordering: DEFAULT_ORDERING[tab] });
  }

  setOrdering(ordering: DashboardOrdering): void {
    if (ordering === this.query().ordering) return;
    this.navigate({ ...this.query(), ordering });
  }

  onSearchInput(value: string): void {
    this.searchText.set(value);
    this.searchInput$.next(value);
  }

  clearSearch(): void {
    this.searchText.set('');
    this.committedSearch = '';
    this.navigate({ ...this.query(), search: '' });
  }

  private navigate(query: ListQuery): void {
    this.expectedQuery = query;
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { ...toQueryParams(query), ...rangeQueryParams(this.range()) },
      replaceUrl: true,
    });
  }

  // ── List ──

  /** Page 1 resets the list; later pages append to it. */
  private requestList(page: number, attempt = 0): void {
    if (page === 1) {
      this.events.set([]);
      this.total.set(0);
      this.listStatus.set('loading');
      this.loadingMore.set(false);
      this.pageFloor = 1;
      // Cleared now so the same text, announced again after the reload, is a change.
      this.announcement.set('');
    } else {
      this.loadingMore.set(true);
    }
    this.moreError.set(null);
    this.listRequests$.next({ query: this.query(), page, attempt });
  }

  retryList(): void {
    this.requestList(1);
  }

  /**
   * The next page is derived from what is loaded, not from a counter: after a
   * delete the server's pages shift, and this way no event is skipped. After a
   * page that brought nothing new it moves on instead of asking for it again.
   */
  private nextPage(): number {
    return Math.max(Math.floor(this.events().length / DASHBOARD_PAGE_SIZE) + 1, this.pageFloor);
  }

  showMore(): void {
    if (this.loadingMore() || this.events().length >= this.total()) return;
    this.requestList(this.nextPage());
  }

  private applyList(result: ListResult): void {
    const { request } = result;
    const first = request.page === 1;
    if ('message' in result) {
      if (first) {
        this.listError.set(result.message);
        this.listStatus.set('error');
      } else {
        this.moreError.set(result.message);
        this.loadingMore.set(false);
      }
      return;
    }
    // Events deleted in this session must not come back from a stale page. The
    // server's count still includes them when its answer was computed before the delete.
    const incoming = result.page.results.filter((e) => !this.deletedIds.has(e.id));
    const count = Math.max(0, result.page.count - (result.page.results.length - incoming.length));
    if (first) {
      this.events.set(incoming);
      this.total.set(count);
    } else {
      const seen = new Set(this.events().map((e) => e.id));
      const fresh = incoming.filter((e) => !seen.has(e.id));
      this.events.update((current) => [...current, ...fresh]);
      if (fresh.length) {
        this.pageFloor = 1;
        this.total.set(count);
      } else {
        // Nothing new (the pages shifted under us), though the server counts
        // more: its count stays the truth and the next page is tried, a few
        // times at most, so "Show more" never repeats the same empty page.
        this.pageFloor = request.page + 1;
        if (result.page.next && request.attempt < MAX_EMPTY_PAGES) {
          this.requestList(request.page + 1, request.attempt + 1);
          return;
        }
        // No page left to ask for: only then is the count not believed.
        this.total.set(result.page.next ? count : this.events().length);
      }
    }
    this.loadingMore.set(false);
    this.listStatus.set('ready');
    this.announce();
  }

  /** "Upcoming: showing 20 of 23 events" in the live region. */
  private announce(): void {
    const message = this.language.t('dashboard.tabShowingOfTotal', {
      tab: this.language.t(TAB_LABEL[this.query().tab]),
      shown: this.events().length,
      total: this.total(),
    });
    // The same text is not announced twice: empty the region, and fill it
    // again once that has been rendered.
    this.announcement.set('');
    afterNextRender(
      () => {
        this.announcement.set(message);
      },
      { injector: this.injector },
    );
  }

  // ── Card actions ──

  /** Only one menu is open at a time; a card closing itself must not close another's. */
  setMenu(id: number, open: boolean): void {
    if (open) this.openMenuId.set(id);
    else if (this.openMenuId() === id) this.openMenuId.set(null);
  }

  duplicate(event: OrganizerEvent): void {
    if (this.duplicatingId() !== null) return;
    this.duplicatingId.set(event.id);
    this.eventService
      .cloneEvent(event.id, this.copyTitle(event.title))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (copy) => {
          this.duplicatingId.set(null);
          this.openMenuId.set(null);
          this.activityRefresh.update((n) => n + 1);
          this.toast.success(this.language.t('dashboard.eventDuplicated'));
          void this.router.navigate(['/edit-event', copy.id]);
        },
        error: (err: unknown) => {
          this.duplicatingId.set(null);
          this.toast.error(
            errorMessage(err, this.language, {
              fallback: this.language.t('dashboard.failedToDuplicate'),
              fields: ['error'],
            }),
          );
          // The disabled item had the focus: close the menu and give it back to the button.
          this.openMenuId.set(null);
          this.focusTrigger(event.id);
        },
      });
  }

  /** "<title> (copy)" in the UI language, never longer than the title column. */
  private copyTitle(title: string): string {
    const full = this.language.t('dashboard.copyTitle', { title }).trim();
    if (full.length <= EVENT_TITLE_MAX_LENGTH) return full;
    const frame = this.language.t('dashboard.copyTitle', { title: '' }).length;
    const room = EVENT_TITLE_MAX_LENGTH - frame;
    return this.language
      .t('dashboard.copyTitle', { title: title.slice(0, Math.max(1, room)).trimEnd() })
      .trim();
  }

  async remove(event: OrganizerEvent): Promise<void> {
    this.openMenuId.set(null);
    // The tab the event is counted in, whatever the user does while the dialog is open.
    const tab = this.query().tab;
    const ok = await this.modal.open({
      title: this.language.t('dashboard.deleteEvent'),
      message: this.language.t('dashboard.deleteTitleThisCannot', { title: event.title }),
      confirmText: this.language.t('common.delete'),
      cancelText: this.language.t('common.cancel'),
      isDestructive: true,
    });
    // The page may have been left while the dialog was open.
    if (!ok || this.destroyed) return;
    this.eventService
      .deleteEvent(event.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.applyDeleted(event.id, tab);
        },
        error: (err: unknown) => {
          // 409: the event has sales and must be cancelled instead; the server says so.
          this.toast.error(
            errorMessage(err, this.language, {
              fallback: this.language.t('dashboard.failedToDeleteEvent'),
              fields: ['error', 'detail'],
            }),
          );
          // The menu closed when Delete was chosen and its item is gone: focus
          // would fall to the page, so it goes back to the card's button.
          this.focusTrigger(event.id);
        },
      });
  }

  private applyDeleted(id: number, tab: DashboardTab): void {
    // A page that was requested before the delete may still bring the event
    // back: remember it for as long as this list lives.
    this.deletedIds.add(id);
    this.pageFloor = 1;
    if (this.events().some((e) => e.id === id)) {
      this.events.update((list) => list.filter((e) => e.id !== id));
      this.total.update((n) => Math.max(0, n - 1));
    }
    this.summary.update((s) =>
      s ? { ...s, tabs: { ...s.tabs, [tab]: Math.max(0, s.tabs[tab] - 1) } } : s,
    );
    this.toast.success(this.language.t('dashboard.eventDeleted'));
    this.announce();
    // The server's totals are the truth: sales, revenue and counts all changed.
    this.summaryRequests$.next({ quiet: true });
    this.activityRefresh.update((n) => n + 1);
    if (this.events().length === 0 && this.total() > 0) {
      this.requestList(1);
    } else if (this.loadingMore()) {
      // "Show more" is in flight and was asked before the delete: its page and
      // count are stale. Asking again cancels it (switchMap).
      this.requestList(this.nextPage());
    }
  }

  private focusTrigger(id: number): void {
    this.cards()
      .find((card) => card.event().id === id)
      ?.focusTrigger();
  }
}
