import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { Observable, Subscription, catchError, forkJoin, map, of, shareReplay } from 'rxjs';
import { LucideAngularModule, ChevronRight, Search } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { apiErrorStatus } from '../../api/api-error';
import { EventService } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { AuthService } from '../../services/auth.service';
import { Event, Category } from '../../models/models';
import { LanguageService } from '../../i18n/language.service';
import { PluralPipe } from '../../i18n/locale.pipes';
import { EventCardComponent } from '../event-card/event-card.component';
import { DiscoverHeroComponent } from './discover-hero.component';
import { FilterBarComponent } from './filter-bar.component';
import { EventRailComponent } from './event-rail.component';
import {
  CITY_STORAGE_KEY,
  DiscoverFilters,
  EMPTY_FILTERS,
  filtersFromParams,
  filtersToApi,
  filtersToParams,
  hasActiveFilters,
} from './discover-filters';

/** Category rails under the fixed ones: the busiest categories. */
const CATEGORY_RAILS = 2;

interface CategoryRail {
  category: Category;
  source: () => Observable<Event[]>;
}

function readStoredCity(): string {
  try {
    return localStorage.getItem(CITY_STORAGE_KEY) ?? '';
  } catch {
    return '';
  }
}

function storeCity(city: string): void {
  try {
    if (city) localStorage.setItem(CITY_STORAGE_KEY, city);
    else localStorage.removeItem(CITY_STORAGE_KEY);
  } catch {
    // Private mode: the city just isn't remembered.
  }
}

/**
 * Discover (Concept A): hero, filter bar, rails and the All events grid.
 * Filters live in the URL; rails show only while nothing narrows the list.
 */
@Component({
  selector: 'app-home',
  standalone: true,
  imports: [
    RouterModule,
    LucideAngularModule,
    TranslocoPipe,
    PluralPipe,
    EventCardComponent,
    DiscoverHeroComponent,
    FilterBarComponent,
    EventRailComponent,
  ],
  template: `
    <div class="discover">
      <app-discover-hero [events]="heroPool()" [loading]="heroLoading()" />

      <div class="container discover-filter-wrap" id="filters">
        <app-filter-bar
          [filters]="filters()"
          [categories]="categories()"
          (filtersChange)="update($event)"
        />
      </div>

      <div class="container discover-body">
        @if (!filtered()) {
          @for (key of [railsKey()]; track key) {
            @if (signedIn()) {
              <app-event-rail
                [title]="'home.recommended' | transloco"
                [source]="recommendedSource"
              />
            }
            @if (filters().city) {
              <app-event-rail
                layout="mosaic"
                [title]="'home.rails.inCity' | transloco: { city: filters().city }"
                [source]="citySource"
                [seeAll]="{}"
              />
            }
            <app-event-rail
              [title]="'home.rails.freeOnline' | transloco"
              [source]="freeOnlineSource"
              [seeAll]="{ free: 1 }"
            />
            @for (rail of categoryRails(); track rail.category.id) {
              <app-event-rail
                [title]="rail.category.name"
                [source]="rail.source"
                [seeAll]="{ category: rail.category.id }"
              />
            }
          }
        }

        <section id="all-events" class="rail" aria-labelledby="all-events-title">
          <div class="rail-head">
            <h2 id="all-events-title" class="rail-title">
              {{ 'home.rails.allEvents' | transloco }}
            </h2>
            @if (!loading() && events().length > 0) {
              <p class="text-sm text-muted-foreground" aria-live="polite">
                {{ 'home.eventsFound' | tPlural: totalCount() }}
              </p>
            }
          </div>

          @if (loading()) {
            <div class="discover-grid" aria-hidden="true">
              @for (i of skeletons; track i) {
                <div class="card-skeleton"></div>
              }
            </div>
          } @else if (events().length === 0) {
            <div class="flex flex-col items-center justify-center py-20 text-center">
              <div class="w-14 h-14 rounded-full bg-muted flex items-center justify-center mb-4">
                <lucide-icon
                  [img]="icons.Search"
                  class="w-6 h-6 text-muted-foreground"
                  aria-hidden="true"
                />
              </div>
              <h3 class="text-base font-semibold text-foreground mb-1">
                {{ 'home.noEvents' | transloco }}
              </h3>
              <p class="text-sm text-muted-foreground mb-5 max-w-xs">
                {{ 'home.noEventsHint' | transloco }}
              </p>
              @if (filtered() || filters().city) {
                <button (click)="resetFilters()" class="btn btn-secondary btn-sm">
                  {{ 'home.clearFilters' | transloco }}
                </button>
              }
            </div>
          } @else {
            <div class="discover-grid">
              @for (event of events(); track event.id) {
                <app-event-card [event]="event" />
              }
            </div>

            @if (hasMore()) {
              <div class="mt-10 flex justify-center">
                <button (click)="loadMore()" [disabled]="loadingMore()" class="btn btn-secondary">
                  @if (loadingMore()) {
                    <span class="spinner spinner-sm"></span>
                    {{ 'common.loading' | transloco }}
                  } @else {
                    {{ 'home.loadMore' | transloco }}
                    <lucide-icon [img]="icons.ChevronRight" class="w-4 h-4" aria-hidden="true" />
                  }
                </button>
              </div>
            }
          }
        </section>
      </div>
    </div>
  `,
})
export class HomeComponent implements OnInit, OnDestroy {
  private eventService = inject(EventService);
  private toastService = inject(ToastService);
  private authService = inject(AuthService);
  private i18n = inject(LanguageService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  readonly filters = signal<DiscoverFilters>(EMPTY_FILTERS);
  readonly filtered = computed(() => hasActiveFilters(this.filters()));
  /** Recreates the rails (and their lazy loads) when the city changes. */
  readonly railsKey = computed(() => `city:${this.filters().city}`);

  readonly categories = signal<Category[]>([]);
  readonly heroPool = signal<Event[]>([]);
  readonly heroLoading = signal(true);
  readonly signedIn = signal(this.authService.isLoggedIn);

  readonly events = signal<Event[]>([]);
  readonly totalCount = signal(0);
  readonly loading = signal(true);
  readonly loadingMore = signal(false);
  readonly hasMore = signal(false);
  private currentPage = 1;
  private listKey = '';

  readonly skeletons = [1, 2, 3, 4, 5, 6, 7, 8];
  readonly icons = { Search, ChevronRight };

  /** Shared by the hero pool and the Recommended rail: one request. */
  private readonly recommended$: Observable<Event[]> = this.authService.isLoggedIn
    ? this.eventService.getRecommendations().pipe(
        map((res) => res.results),
        catchError(() => of([] as Event[])),
        shareReplay(1),
      )
    : of([]);

  readonly recommendedSource = () => this.recommended$.pipe(map((list) => list.slice(0, 10)));

  readonly citySource = () =>
    this.list({ location: this.filters().city }).pipe(map((list) => list.slice(0, 5)));

  /** Free and online are separate API filters: two requests, merged by id. */
  readonly freeOnlineSource = () =>
    forkJoin([this.list({ is_free: true }), this.list({ is_online: true })]).pipe(
      map(([free, online]) => {
        const byId = new Map<number, Event>();
        for (const e of [...free, ...online]) byId.set(e.id, e);
        return [...byId.values()].sort((a, b) => a.date.localeCompare(b.date));
      }),
    );

  readonly categoryRails = computed<CategoryRail[]>(() =>
    [...this.categories()]
      .sort((a, b) => b.event_count - a.event_count)
      .filter((c) => c.event_count > 0)
      .slice(0, CATEGORY_RAILS)
      .map((category) => ({
        category,
        source: () => this.list({ category: category.id }),
      })),
  );

  private subs: Subscription[] = [];

  ngOnInit(): void {
    this.loadCategories();
    this.loadHero();

    this.subs.push(
      this.route.queryParamMap.subscribe((params) => {
        if (params.has('city')) storeCity((params.get('city') ?? '').trim());
        this.filters.set(filtersFromParams(params, readStoredCity()));
        this.applyFilters();
      }),
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }

  /** A filter changed in the bar: write it to the URL (the subscription loads). */
  update(change: Partial<DiscoverFilters>): void {
    const next = { ...this.filters(), ...change };
    if (change.city !== undefined) storeCity(next.city);
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: filtersToParams(next),
      queryParamsHandling: 'merge',
      replaceUrl: true,
      fragment: 'filters',
    });
  }

  resetFilters(): void {
    this.update({ ...EMPTY_FILTERS });
  }

  loadMore(): void {
    if (this.loadingMore() || !this.hasMore()) return;
    this.loadingMore.set(true);
    const page = this.currentPage + 1;
    this.eventService.getEvents(filtersToApi(this.filters(), page)).subscribe({
      next: (res) => {
        this.currentPage = page;
        this.events.set([...this.events(), ...res.results]);
        this.hasMore.set(!!res.next);
        this.loadingMore.set(false);
      },
      error: () => {
        this.toastService.error(this.i18n.t('home.loadMoreError'));
        this.loadingMore.set(false);
      },
    });
  }

  private applyFilters(): void {
    const params = filtersToApi(this.filters(), 1);
    const key = JSON.stringify(params);
    if (key === this.listKey) return;
    this.listKey = key;
    this.loading.set(true);
    this.currentPage = 1;
    this.eventService.getEvents(params).subscribe({
      next: (res) => {
        if (key !== this.listKey) return; // a newer filter won
        this.events.set(res.results);
        this.totalCount.set(res.count);
        this.hasMore.set(!!res.next);
        this.loading.set(false);
      },
      error: (err) => {
        // Status 0 = offline / aborted request: no toast for that.
        if (apiErrorStatus(err) !== 0) this.toastService.error(this.i18n.t('home.loadError'));
        this.loading.set(false);
      },
    });
  }

  private loadCategories(): void {
    this.eventService.getCategories().subscribe({
      next: (cats) => this.categories.set([...cats].sort((a, b) => b.event_count - a.event_count)),
      error: () => {
        // Without categories there are no category chips or rails.
      },
    });
  }

  /** Hero pool: recommendations first, then the soonest upcoming events. */
  private loadHero(): void {
    forkJoin([
      this.recommended$,
      this.eventService.getEvents({ upcoming: true, ordering: 'date', page: 1 }).pipe(
        map((res) => res.results),
        catchError(() => of([] as Event[])),
      ),
    ]).subscribe(([recommended, upcoming]) => {
      this.heroPool.set([...recommended, ...upcoming]);
      this.heroLoading.set(false);
    });
  }

  /** One page of upcoming events for a rail, within the visitor's city. */
  private list(extra: {
    category?: number;
    location?: string;
    is_free?: boolean;
    is_online?: boolean;
  }): Observable<Event[]> {
    const city = this.filters().city;
    return this.eventService
      .getEvents({
        upcoming: true,
        ordering: 'date',
        page: 1,
        ...(city ? { location: city } : {}),
        ...extra,
      })
      .pipe(map((res) => res.results));
  }
}
