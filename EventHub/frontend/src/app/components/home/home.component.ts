import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { apiErrorStatus } from '../../api/api-error';
import { FormsModule } from '@angular/forms';
import { EventService } from '../../services/event.service';
import { SearchService } from '../../services/search.service';
import { ToastService } from '../../services/toast.service';
import { AuthService } from '../../services/auth.service';
import { EventCardComponent } from '../event-card/event-card.component';
import { Event, Category } from '../../models/models';
import { Subscription, distinctUntilChanged } from 'rxjs';
import {
  LucideAngularModule,
  Search,
  MapPin,
  SlidersHorizontal,
  ChevronRight,
  X,
} from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from '../../i18n/language.service';
import { PluralPipe } from '../../i18n/locale.pipes';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    FormsModule,
    EventCardComponent,
    LucideAngularModule,
    TranslocoPipe,
    PluralPipe,
  ],
  template: `
    <div class="page-root-white">
      <!-- ─── Discovery header ─── -->
      <section class="border-b border-border bg-background">
        <div class="container py-7">
          <!-- Editorial hero -->
          <div class="mb-6 max-w-2xl">
            <p class="kicker mb-3">{{ 'home.kicker' | transloco }}</p>
            <h1
              class="font-display font-semibold tracking-tight leading-[1.02] text-foreground"
              style="font-size:clamp(2.25rem,4.6vw,3.4rem)"
            >
              {{ 'home.titleLine1' | transloco }}<br /><span class="text-ember">{{
                'home.titleLine2' | transloco
              }}</span>
            </h1>
            <p class="text-muted-foreground mt-4 text-[0.975rem] leading-relaxed max-w-xl">
              {{ 'home.subtitle' | transloco }}
            </p>
          </div>

          <!-- Search bar -->
          <div class="flex flex-col sm:flex-row gap-2 max-w-2xl">
            <!-- Search field — flex wrapper, icon + input side by side -->
            <label
              class="flex items-center gap-2 flex-1 border rounded-md px-3 h-10 bg-background transition-shadow cursor-text"
              [class]="
                semanticMode
                  ? 'border-ember ring-2 ring-ember/20 focus-within:border-ember'
                  : 'border-border focus-within:border-ember focus-within:ring-2 focus-within:ring-ember/15'
              "
            >
              <lucide-icon
                [img]="icons.Search"
                class="w-4 h-4 flex-shrink-0"
                [class]="semanticMode ? 'text-ember' : 'text-muted-foreground'"
                aria-hidden="true"
              />
              <input
                type="search"
                [(ngModel)]="searchQuery"
                (keyup.enter)="applyFilters()"
                [placeholder]="
                  (semanticMode ? 'home.searchPlaceholderAi' : 'home.searchPlaceholder') | transloco
                "
                class="flex-1 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
                [attr.aria-label]="'home.searchEvents' | transloco"
              />
              <!-- AI toggle button -->
              <button
                type="button"
                (click)="semanticMode = !semanticMode; applyFilters()"
                [class]="
                  semanticMode
                    ? 'flex-shrink-0 font-mono-ui text-[10px] font-medium tracking-wide px-1.5 py-0.5 rounded bg-ember text-white'
                    : 'flex-shrink-0 font-mono-ui text-[10px] font-medium tracking-wide px-1.5 py-0.5 rounded bg-muted text-muted-foreground hover:bg-ember/10 hover:text-ember transition-colors'
                "
                [title]="'home.toggleAi' | transloco"
              >
                AI
              </button>
            </label>

            <!-- Location field -->
            <label
              class="flex items-center gap-2 sm:w-44 border border-border rounded-md px-3 h-10 bg-background focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-shadow cursor-text"
            >
              <lucide-icon
                [img]="icons.MapPin"
                class="w-4 h-4 text-muted-foreground flex-shrink-0"
                aria-hidden="true"
              />
              <input
                type="text"
                [(ngModel)]="searchLocation"
                (keyup.enter)="applyFilters()"
                [placeholder]="'home.location' | transloco"
                class="flex-1 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground w-full"
                [attr.aria-label]="'home.filterLocation' | transloco"
              />
            </label>

            <button (click)="applyFilters()" class="btn btn-primary h-10 px-5">
              {{ 'home.search' | transloco }}
            </button>

            @if (hasActiveFilters) {
              <button
                (click)="resetFilters()"
                class="btn btn-ghost btn-sm h-10 flex items-center gap-1.5 text-muted-foreground"
                [attr.aria-label]="'home.clearAll' | transloco"
              >
                <lucide-icon [img]="icons.X" class="w-3.5 h-3.5" aria-hidden="true" />
                {{ 'home.clear' | transloco }}
              </button>
            }
          </div>

          <!-- Filter row -->
          <div class="flex flex-wrap items-center gap-2 mt-4">
            <!-- Sort -->
            <div
              class="flex items-center gap-1.5 border border-border rounded-md px-2.5 h-8 bg-background"
            >
              <lucide-icon
                [img]="icons.SlidersHorizontal"
                class="w-3.5 h-3.5 text-muted-foreground"
                aria-hidden="true"
              />
              <select
                [(ngModel)]="ordering"
                (change)="applyFilters()"
                class="bg-transparent text-sm text-foreground outline-none cursor-pointer h-full"
                [attr.aria-label]="'home.sortEvents' | transloco"
              >
                <option value="date">{{ 'home.sort.dateAsc' | transloco }}</option>
                <option value="-date">{{ 'home.sort.dateDesc' | transloco }}</option>
                <option value="-created_at">{{ 'home.sort.newest' | transloco }}</option>
                <option value="price">{{ 'home.sort.priceAsc' | transloco }}</option>
                <option value="-price">{{ 'home.sort.priceDesc' | transloco }}</option>
              </select>
            </div>

            <!-- Free toggle -->
            <button
              (click)="toggleFree()"
              class="chip"
              [class.chip-active]="isFree"
              [attr.aria-label]="'home.freeOnlyLabel' | transloco"
              [attr.aria-pressed]="isFree"
            >
              {{ 'home.freeOnly' | transloco }}
            </button>

            <!-- Online toggle -->
            <button
              (click)="toggleOnline()"
              class="chip"
              [class.chip-active]="isOnline"
              [attr.aria-label]="'home.onlineOnlyLabel' | transloco"
              [attr.aria-pressed]="isOnline"
            >
              {{ 'home.online' | transloco }}
            </button>
          </div>
        </div>
      </section>

      <!-- ─── Category rail ─── -->
      <!-- z-10: must stay below the topbar (z-20) so the notifications
           dropdown isn't covered by this sticky rail -->
      <section class="border-b border-border bg-background sticky top-16 z-10">
        <div class="container">
          <div class="flex gap-1.5 overflow-x-auto py-3 no-scrollbar">
            <button
              (click)="filterByCategory(null)"
              class="chip flex-shrink-0"
              [class.chip-active]="selectedCategory === null"
            >
              {{ 'home.all' | transloco }}
            </button>
            @for (cat of categories; track cat.id) {
              <button
                (click)="filterByCategory(cat.id)"
                class="chip flex-shrink-0"
                [class.chip-active]="selectedCategory === cat.id"
              >
                {{ cat.name }}
              </button>
            }
          </div>
        </div>
      </section>

      <!-- ─── Events grid ─── -->
      <main class="container py-8">
        <!-- Recommended for you (personalised, signed-in only) -->
        @if (recommended.length > 0 && !hasActiveFilters) {
          <section class="mb-10">
            <p class="kicker mb-3">{{ 'home.recommended' | transloco }}</p>
            <div class="flex gap-5 overflow-x-auto pb-2 no-scrollbar">
              @for (event of recommended; track event.id) {
                <div class="w-72 flex-shrink-0">
                  <app-event-card [event]="event" />
                </div>
              }
            </div>
          </section>
        }

        <!-- Results meta -->
        @if (!loading && events.length > 0) {
          <p class="text-sm text-muted-foreground mb-5">
            {{ 'home.eventsFound' | tPlural: totalCount }}
          </p>
        }

        <!-- Loading skeletons -->
        @if (loading) {
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            @for (i of skeletons; track i) {
              <div class="card animate-pulse overflow-hidden">
                <div class="bg-muted aspect-video"></div>
                <div class="p-4 space-y-3">
                  <div class="h-3 bg-muted rounded-full w-1/4"></div>
                  <div class="h-4 bg-muted rounded-full w-3/4"></div>
                  <div class="h-3 bg-muted rounded-full w-1/2"></div>
                  <div class="h-3 bg-muted rounded-full w-2/5"></div>
                  <div class="flex justify-between pt-1">
                    <div class="h-4 bg-muted rounded-full w-1/5"></div>
                    <div class="h-4 bg-muted rounded-full w-1/4"></div>
                  </div>
                </div>
              </div>
            }
          </div>

          <!-- Empty state -->
        } @else if (events.length === 0) {
          <div class="flex flex-col items-center justify-center py-24 text-center">
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
            <button (click)="resetFilters()" class="btn btn-secondary btn-sm">
              {{ 'home.clearFilters' | transloco }}
            </button>
          </div>

          <!-- Grid -->
        } @else {
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            @for (event of events; track event.id) {
              <app-event-card
                [event]="event"
                [featured]="$first"
                [class.sm:col-span-2]="$first"
                [class.lg:col-span-2]="$first"
              />
            }
          </div>

          <!-- Load more -->
          @if (hasMore) {
            <div class="mt-10 flex justify-center">
              <button (click)="loadMore()" [disabled]="loadingMore" class="btn btn-secondary">
                @if (loadingMore) {
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
      </main>
    </div>
  `,
})
export class HomeComponent implements OnInit, OnDestroy {
  private eventService = inject(EventService);
  private searchService = inject(SearchService);
  private toastService = inject(ToastService);
  private authService = inject(AuthService);
  private i18n = inject(LanguageService);

  events: Event[] = [];
  categories: Category[] = [];
  recommended: Event[] = [];
  totalCount = 0;

  searchQuery = '';
  searchLocation = '';
  selectedCategory: number | null = null;
  ordering = 'date';
  isFree = false;
  isOnline = false;
  semanticMode = false; // toggle: semantic AI search vs keyword

  loading = false;
  loadingMore = false;
  hasMore = false;
  currentPage = 1;

  readonly skeletons = [1, 2, 3, 4, 5, 6];
  readonly icons = { Search, MapPin, SlidersHorizontal, ChevronRight, X };

  private searchSub?: Subscription;
  private locationSub?: Subscription;

  ngOnInit(): void {
    this.loadCategories();
    this.applyFilters();
    this.loadRecommendations();

    this.searchSub = this.searchService.searchQuery$
      .pipe(distinctUntilChanged())
      .subscribe((query) => {
        if (query !== this.searchQuery) {
          this.searchQuery = query;
          this.applyFilters();
        }
      });

    // Kept in its own subscription so it is released with the component —
    // the root SearchService outlives every visit to the home page.
    this.locationSub = this.searchService.searchLocation$
      .pipe(distinctUntilChanged())
      .subscribe((loc) => {
        this.searchLocation = loc;
      });
  }

  ngOnDestroy(): void {
    this.searchSub?.unsubscribe();
    this.locationSub?.unsubscribe();
  }

  get hasActiveFilters(): boolean {
    return !!(
      this.searchQuery ||
      this.searchLocation ||
      this.selectedCategory ||
      this.isFree ||
      this.isOnline ||
      this.ordering !== 'date'
    );
  }

  loadCategories(): void {
    this.eventService.getCategories().subscribe({
      next: (cats) => {
        this.categories = cats;
      },
      error: () => {
        // Without categories the filter chips are just not shown.
      },
    });
  }

  loadRecommendations(): void {
    if (!this.authService.isLoggedIn) return;
    this.eventService.getRecommendations().subscribe({
      next: (res) => {
        this.recommended = res.results.slice(0, 8);
      },
      error: () => {
        // The "For you" row is optional; the main listing is unaffected.
      },
    });
  }

  applyFilters(): void {
    this.searchService.setSearchQuery(this.searchQuery);
    this.searchService.setSearchLocation(this.searchLocation);

    this.loading = true;
    this.currentPage = 1;

    this.eventService.getEvents(this.buildParams(1)).subscribe({
      next: (res) => {
        this.events = res.results;
        this.totalCount = res.count;
        this.hasMore = !!res.next;
        this.loading = false;
      },
      error: (err) => {
        // Status 0 = offline / aborted request: no toast for that.
        if (apiErrorStatus(err) !== 0) {
          this.toastService.error(this.i18n.t('home.loadError'));
        }
        this.loading = false;
      },
    });
  }

  loadMore(): void {
    if (this.loadingMore || !this.hasMore) return;
    this.loadingMore = true;
    this.currentPage++;

    this.eventService.getEvents(this.buildParams(this.currentPage)).subscribe({
      next: (res) => {
        this.events = [...this.events, ...res.results];
        this.hasMore = !!res.next;
        this.loadingMore = false;
      },
      error: () => {
        this.currentPage--;
        this.toastService.error(this.i18n.t('home.loadMoreError'));
        this.loadingMore = false;
      },
    });
  }

  filterByCategory(id: number | null): void {
    this.selectedCategory = id;
    this.applyFilters();
  }

  toggleFree(): void {
    this.isFree = !this.isFree;
    this.applyFilters();
  }

  toggleOnline(): void {
    this.isOnline = !this.isOnline;
    this.applyFilters();
  }

  resetFilters(): void {
    this.searchQuery = '';
    this.searchLocation = '';
    this.selectedCategory = null;
    this.ordering = 'date';
    this.isFree = false;
    this.isOnline = false;
    this.applyFilters();
  }

  private buildParams(page: number) {
    const useSemanticSearch = this.semanticMode && !!this.searchQuery;
    return {
      page,
      upcoming: true, // discovery never shows events that already happened
      // In semantic mode send ?q= instead of ?search= to hit the vector path
      ...(useSemanticSearch
        ? { q: this.searchQuery }
        : this.searchQuery && { search: this.searchQuery }),
      ...(this.searchLocation && { location: this.searchLocation }),
      ...(this.selectedCategory !== null && { category: this.selectedCategory }),
      ...(this.ordering && { ordering: this.ordering }),
      ...(this.isFree && { is_free: true }),
      ...(this.isOnline && { is_online: true }),
    };
  }
}
