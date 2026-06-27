import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { EventService } from '../../services/event.service';
import { SearchService } from '../../services/search.service';
import { ToastService } from '../../services/toast.service';
import { AuthService } from '../../services/auth.service';
import { EventCardComponent } from '../event-card/event-card.component';
import { Event, Category } from '../../models/models';
import { Subscription, distinctUntilChanged } from 'rxjs';
import { LucideAngularModule, Search, MapPin, SlidersHorizontal, ChevronRight, X } from 'lucide-angular';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, EventCardComponent, LucideAngularModule],
  template: `
    <div class="page-root-white">

      <!-- ─── Discovery header ─── -->
      <section class="border-b border-border bg-background">
        <div class="container py-7">

          <!-- Editorial hero -->
          <div class="mb-6 max-w-2xl">
            <p class="kicker mb-3">What's on · This week</p>
            <h1 class="font-display font-semibold tracking-tight leading-[1.02] text-foreground"
                style="font-size:clamp(2.25rem,4.6vw,3.4rem)">
              Find your next<br><span class="text-ember">night out.</span>
            </h1>
            <p class="text-muted-foreground mt-4 text-[0.975rem] leading-relaxed max-w-xl">
              From sold-out gigs to quiet gallery openings — every event worth your evening, in one place.
            </p>
          </div>

          <!-- Search bar -->
          <div class="flex flex-col sm:flex-row gap-2 max-w-2xl">

            <!-- Search field — flex wrapper, icon + input side by side -->
            <label
              class="flex items-center gap-2 flex-1 border rounded-md px-3 h-10 bg-background transition-shadow cursor-text"
              [class]="semanticMode
                ? 'border-ember ring-2 ring-ember/20 focus-within:border-ember'
                : 'border-border focus-within:border-ember focus-within:ring-2 focus-within:ring-ember/15'"
            >
              <lucide-icon [img]="icons.Search" class="w-4 h-4 flex-shrink-0" [class]="semanticMode ? 'text-ember' : 'text-muted-foreground'" aria-hidden="true"></lucide-icon>
              <input
                type="search"
                [(ngModel)]="searchQuery"
                (keyup.enter)="applyFilters()"
                [placeholder]="semanticMode ? 'Describe what you are looking for...' : 'Search events...'"
                class="flex-1 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
                aria-label="Search events"
              />
              <!-- AI toggle button -->
              <button
                type="button"
                (click)="semanticMode = !semanticMode; applyFilters()"
                [class]="semanticMode
                  ? 'flex-shrink-0 font-mono-ui text-[10px] font-medium tracking-wide px-1.5 py-0.5 rounded bg-ember text-white'
                  : 'flex-shrink-0 font-mono-ui text-[10px] font-medium tracking-wide px-1.5 py-0.5 rounded bg-muted text-muted-foreground hover:bg-ember/10 hover:text-ember transition-colors'"
                title="Toggle AI semantic search"
              >AI</button>
            </label>

            <!-- Location field -->
            <label class="flex items-center gap-2 sm:w-44 border border-border rounded-md px-3 h-10 bg-background focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-shadow cursor-text">
              <lucide-icon [img]="icons.MapPin" class="w-4 h-4 text-muted-foreground flex-shrink-0" aria-hidden="true"></lucide-icon>
              <input
                type="text"
                [(ngModel)]="searchLocation"
                (keyup.enter)="applyFilters()"
                placeholder="Location"
                class="flex-1 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground w-full"
                aria-label="Filter by location"
              />
            </label>

            <button (click)="applyFilters()" class="btn btn-primary h-10 px-5">
              Search
            </button>

            @if (hasActiveFilters) {
              <button
                (click)="resetFilters()"
                class="btn btn-ghost btn-sm h-10 flex items-center gap-1.5 text-muted-foreground"
                aria-label="Clear all filters"
              >
                <lucide-icon [img]="icons.X" class="w-3.5 h-3.5" aria-hidden="true"></lucide-icon>
                Clear
              </button>
            }
          </div>

          <!-- Filter row -->
          <div class="flex flex-wrap items-center gap-2 mt-4">

            <!-- Sort -->
            <div class="flex items-center gap-1.5 border border-border rounded-md px-2.5 h-8 bg-background">
              <lucide-icon [img]="icons.SlidersHorizontal" class="w-3.5 h-3.5 text-muted-foreground" aria-hidden="true"></lucide-icon>
              <select
                [(ngModel)]="ordering"
                (change)="applyFilters()"
                class="bg-transparent text-sm text-foreground outline-none cursor-pointer h-full"
                aria-label="Sort events"
              >
                <option value="date">Date: soonest first</option>
                <option value="-date">Date: latest first</option>
                <option value="-created_at">Newest added</option>
                <option value="price">Price: low to high</option>
                <option value="-price">Price: high to low</option>
              </select>
            </div>

            <!-- Free toggle -->
            <button
              (click)="toggleFree()"
              class="chip"
              [class.chip-active]="isFree"
              aria-label="Show free events only"
              [attr.aria-pressed]="isFree"
            >
              Free only
            </button>

            <!-- Online toggle -->
            <button
              (click)="toggleOnline()"
              class="chip"
              [class.chip-active]="isOnline"
              aria-label="Show online events only"
              [attr.aria-pressed]="isOnline"
            >
              Online
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
              All
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
            <p class="kicker mb-3">Recommended for you</p>
            <div class="flex gap-5 overflow-x-auto pb-2 no-scrollbar">
              @for (event of recommended; track event.id) {
                <div class="w-72 flex-shrink-0">
                  <app-event-card [event]="event"></app-event-card>
                </div>
              }
            </div>
          </section>
        }

        <!-- Results meta -->
        @if (!loading && events.length > 0) {
          <p class="text-sm text-muted-foreground mb-5">
            {{ totalCount }} event{{ totalCount !== 1 ? 's' : '' }} found
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
              <lucide-icon [img]="icons.Search" class="w-6 h-6 text-muted-foreground" aria-hidden="true"></lucide-icon>
            </div>
            <h3 class="text-base font-semibold text-foreground mb-1">No events found</h3>
            <p class="text-sm text-muted-foreground mb-5 max-w-xs">
              Try adjusting your search or filters to find what you're looking for.
            </p>
            <button (click)="resetFilters()" class="btn btn-secondary btn-sm">
              Clear filters
            </button>
          </div>

        <!-- Grid -->
        } @else {
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            @for (event of events; track event.id; let i = $index) {
              <app-event-card
                [event]="event"
                [featured]="i === 0"
                [class.sm:col-span-2]="i === 0"
                [class.lg:col-span-2]="i === 0"
              ></app-event-card>
            }
          </div>

          <!-- Load more -->
          @if (hasMore) {
            <div class="mt-10 flex justify-center">
              <button
                (click)="loadMore()"
                [disabled]="loadingMore"
                class="btn btn-secondary"
              >
                @if (loadingMore) {
                  <span class="spinner spinner-sm"></span>
                  Loading...
                } @else {
                  Load more events
                  <lucide-icon [img]="icons.ChevronRight" class="w-4 h-4" aria-hidden="true"></lucide-icon>
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
  semanticMode = false;   // toggle: semantic AI search vs keyword

  loading = false;
  loadingMore = false;
  hasMore = false;
  currentPage = 1;

  readonly skeletons = [1, 2, 3, 4, 5, 6];
  readonly icons = { Search, MapPin, SlidersHorizontal, ChevronRight, X };

  private searchSub?: Subscription;

  constructor(
    private eventService: EventService,
    private searchService: SearchService,
    private toastService: ToastService,
    private authService: AuthService,
  ) {}

  ngOnInit(): void {
    this.loadCategories();
    this.applyFilters();
    this.loadRecommendations();

    this.searchSub = this.searchService.searchQuery$.pipe(
      distinctUntilChanged()
    ).subscribe(query => {
      if (query !== this.searchQuery) {
        this.searchQuery = query;
        this.applyFilters();
      }
    });

    this.searchService.searchLocation$.pipe(
      distinctUntilChanged()
    ).subscribe(loc => {
      this.searchLocation = loc;
    });
  }

  ngOnDestroy(): void {
    this.searchSub?.unsubscribe();
  }

  get hasActiveFilters(): boolean {
    return !!(this.searchQuery || this.searchLocation || this.selectedCategory || this.isFree || this.isOnline || this.ordering !== 'date');
  }

  loadCategories(): void {
    this.eventService.getCategories().subscribe({
      next: cats => { this.categories = cats; },
      error: () => {},
    });
  }

  loadRecommendations(): void {
    if (!this.authService.isLoggedIn) return;
    this.eventService.getRecommendations().subscribe({
      next: res => { this.recommended = (res.results ?? []).slice(0, 8); },
      error: () => {},
    });
  }

  applyFilters(): void {
    this.searchService.setSearchQuery(this.searchQuery);
    this.searchService.setSearchLocation(this.searchLocation);

    this.loading = true;
    this.currentPage = 1;

    this.eventService.getEvents(this.buildParams(1)).subscribe({
      next: res => {
        this.events = res.results;
        this.totalCount = res.count;
        this.hasMore = !!res.next;
        this.loading = false;
      },
      error: err => {
        if (err.status !== 0) {
          this.toastService.error('Failed to load events. Please try again.');
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
      next: res => {
        this.events = [...this.events, ...res.results];
        this.hasMore = !!res.next;
        this.loadingMore = false;
      },
      error: () => {
        this.currentPage--;
        this.toastService.error('Failed to load more events.');
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
      ...(useSemanticSearch ? { q: this.searchQuery } : (this.searchQuery && { search: this.searchQuery })),
      ...(this.searchLocation && { location: this.searchLocation }),
      ...(this.selectedCategory !== null && { category: this.selectedCategory }),
      ...(this.ordering       && { ordering: this.ordering }),
      ...(this.isFree         && { is_free: true }),
      ...(this.isOnline       && { is_online: true }),
    };
  }
}
