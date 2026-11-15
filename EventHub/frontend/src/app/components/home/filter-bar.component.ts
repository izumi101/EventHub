import {
  Component,
  EventEmitter,
  HostListener,
  Input,
  OnChanges,
  Output,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  LucideAngularModule,
  ChevronDown,
  MapPin,
  Search,
  SlidersHorizontal,
  Sparkles,
} from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { Category } from '../../models/models';
import { DiscoverFilters, sheetFilterCount } from './discover-filters';
import { FilterSheetComponent } from './filter-sheet.component';
import { DISCOVER_SEARCH_ID } from '../../layout/top-nav.component';

/** How many category chips fit next to "All" before the "+N more" button. */
export const VISIBLE_CATEGORIES = 4;

/**
 * Discover filter bar: city, format & price (+ sort), categories, search with
 * the AI toggle. One row at ≥1280px, two rows at 768–1279px; below 768px the
 * search stays and the rest moves into a "Filters" sheet, while the category
 * chips scroll sideways.
 */
@Component({
  selector: 'app-filter-bar',
  standalone: true,
  imports: [FormsModule, LucideAngularModule, TranslocoPipe, FilterSheetComponent],
  template: `
    <div class="filter-bar" role="search" [attr.aria-label]="'home.filters.label' | transloco">
      <!-- City -->
      <div class="filter-cell filter-city hidden md:block">
        <label class="filter-label" for="filter-city">{{ 'home.filters.city' | transloco }}</label>
        <div class="filter-field">
          <lucide-icon [img]="icons.MapPin" class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
          <input
            id="filter-city"
            type="text"
            [(ngModel)]="cityDraft"
            (keyup.enter)="emit({ city: cityDraft.trim() })"
            (blur)="cityDraft.trim() !== filters.city && emit({ city: cityDraft.trim() })"
            [placeholder]="'home.filters.cityPlaceholder' | transloco"
            class="filter-input"
          />
        </div>
      </div>

      <!-- Format & price, sort -->
      <div class="filter-cell filter-format hidden md:block">
        <p class="filter-label" id="filter-format-label">
          {{ 'home.filters.formatPrice' | transloco }}
        </p>
        <div class="flex items-center gap-1.5" role="group" aria-labelledby="filter-format-label">
          <button
            type="button"
            class="chip"
            [class.chip-active]="filters.free"
            [attr.aria-pressed]="filters.free"
            [attr.aria-label]="'home.freeOnlyLabel' | transloco"
            (click)="emit({ free: !filters.free })"
          >
            {{ 'home.freeOnly' | transloco }}
          </button>
          <button
            type="button"
            class="chip"
            [class.chip-active]="filters.online"
            [attr.aria-pressed]="filters.online"
            [attr.aria-label]="'home.onlineOnlyLabel' | transloco"
            (click)="emit({ online: !filters.online })"
          >
            {{ 'home.online' | transloco }}
          </button>
          <select
            class="chip filter-sort"
            [ngModel]="filters.sort"
            (ngModelChange)="emit({ sort: $event })"
            [attr.aria-label]="'home.sortEvents' | transloco"
          >
            <option value="date">{{ 'home.sort.dateAsc' | transloco }}</option>
            <option value="-date">{{ 'home.sort.dateDesc' | transloco }}</option>
            <option value="-created_at">{{ 'home.sort.newest' | transloco }}</option>
            <option value="price">{{ 'home.sort.priceAsc' | transloco }}</option>
            <option value="-price">{{ 'home.sort.priceDesc' | transloco }}</option>
          </select>
        </div>
      </div>

      <!-- Categories -->
      <div class="filter-cell filter-categories">
        <p class="filter-label hidden md:block" id="filter-category-label">
          {{ 'home.filters.category' | transloco }}
        </p>
        <div
          class="filter-chips"
          role="group"
          [attr.aria-label]="'home.filters.category' | transloco"
        >
          <button
            type="button"
            class="chip flex-shrink-0"
            [class.chip-active]="filters.category === null"
            [attr.aria-pressed]="filters.category === null"
            (click)="emit({ category: null })"
          >
            {{ 'home.all' | transloco }}
          </button>
          @for (cat of categories; track cat.id) {
            <button
              type="button"
              class="chip flex-shrink-0"
              [class.filter-chip-extra]="$index >= visibleCategories && cat.id !== filters.category"
              [class.chip-active]="filters.category === cat.id"
              [attr.aria-pressed]="filters.category === cat.id"
              (click)="emit({ category: cat.id })"
            >
              {{ cat.name }}
            </button>
          }
          @if (hiddenCount() > 0) {
            <div class="relative hidden md:block">
              <button
                type="button"
                class="chip flex-shrink-0"
                [attr.aria-expanded]="moreOpen()"
                (click)="toggleMore($event)"
              >
                {{ 'home.filters.more' | transloco: { count: hiddenCount() } }}
                <lucide-icon [img]="icons.ChevronDown" class="w-3.5 h-3.5" aria-hidden="true" />
              </button>
              @if (moreOpen()) {
                <div class="filter-more" role="presentation" (click)="$event.stopPropagation()">
                  @for (cat of categories.slice(visibleCategories); track cat.id) {
                    <button
                      type="button"
                      class="chip"
                      [class.chip-active]="filters.category === cat.id"
                      [attr.aria-pressed]="filters.category === cat.id"
                      (click)="emit({ category: cat.id }); moreOpen.set(false)"
                    >
                      {{ cat.name }}
                    </button>
                  }
                </div>
              }
            </div>
          }
        </div>
      </div>

      <!-- Search -->
      <div class="filter-cell filter-search">
        <label class="filter-label hidden md:block" [for]="searchId">{{
          'home.filters.search' | transloco
        }}</label>
        <div class="filter-field" [class.filter-field-ai]="filters.ai">
          <lucide-icon
            [img]="filters.ai ? icons.Sparkles : icons.Search"
            class="w-4 h-4 flex-shrink-0"
            aria-hidden="true"
          />
          <input
            [id]="searchId"
            type="search"
            [(ngModel)]="queryDraft"
            (keyup.enter)="emit({ q: queryDraft.trim() })"
            [placeholder]="
              (filters.ai ? 'home.searchPlaceholderAi' : 'home.searchPlaceholder') | transloco
            "
            [attr.aria-label]="'home.searchEvents' | transloco"
            class="filter-input"
          />
          <button
            type="button"
            class="filter-ai focus-ring"
            [class.filter-ai-on]="filters.ai"
            [attr.aria-pressed]="filters.ai"
            [title]="'home.toggleAi' | transloco"
            [attr.aria-label]="'home.toggleAi' | transloco"
            (click)="emit({ ai: !filters.ai, q: queryDraft.trim() })"
          >
            AI
          </button>
        </div>
      </div>

      <button
        type="button"
        class="filter-submit focus-ring hidden md:inline-flex"
        [attr.aria-label]="'home.search' | transloco"
        (click)="submitAll()"
      >
        <lucide-icon [img]="icons.Search" class="w-5 h-5" aria-hidden="true" />
      </button>

      <!-- Mobile: filters sheet -->
      <button
        type="button"
        class="filter-open md:hidden focus-ring"
        [attr.aria-label]="'home.filters.openWithCount' | transloco: { count: sheetCount() }"
        (click)="sheetOpen.set(true)"
      >
        <lucide-icon [img]="icons.SlidersHorizontal" class="w-4 h-4" aria-hidden="true" />
        {{ 'home.filters.open' | transloco }}
        @if (sheetCount() > 0) {
          <span class="filter-count" aria-hidden="true">{{ sheetCount() }}</span>
        }
      </button>
    </div>

    @defer (when sheetOpen()) {
      @if (sheetOpen()) {
        <app-filter-sheet
          [filters]="filters"
          (applied)="emit($event); sheetOpen.set(false)"
          (closed)="sheetOpen.set(false)"
        />
      }
    }
  `,
  styles: [
    `
      :host {
        display: block;
      }
    `,
  ],
})
export class FilterBarComponent implements OnChanges {
  @Input({ required: true }) filters!: DiscoverFilters;
  @Input() categories: Category[] = [];
  @Output() readonly filtersChange = new EventEmitter<Partial<DiscoverFilters>>();

  readonly searchId = DISCOVER_SEARCH_ID;
  readonly visibleCategories = VISIBLE_CATEGORIES;
  readonly icons = { ChevronDown, MapPin, Search, SlidersHorizontal, Sparkles };

  queryDraft = '';
  cityDraft = '';
  readonly moreOpen = signal(false);
  readonly sheetOpen = signal(false);
  readonly sheetCount = signal(0);
  readonly hiddenCount = signal(0);

  ngOnChanges(): void {
    this.queryDraft = this.filters.q;
    this.cityDraft = this.filters.city;
    this.sheetCount.set(sheetFilterCount(this.filters));
    this.hiddenCount.set(Math.max(0, this.categories.length - this.visibleCategories));
  }

  @HostListener('document:click')
  onDocumentClick(): void {
    this.moreOpen.set(false);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.moreOpen.set(false);
  }

  toggleMore(event: MouseEvent): void {
    event.stopPropagation();
    this.moreOpen.set(!this.moreOpen());
  }

  emit(change: Partial<DiscoverFilters>): void {
    this.filtersChange.emit(change);
  }

  /** The round search button applies the typed search and city together. */
  submitAll(): void {
    this.emit({ q: this.queryDraft.trim(), city: this.cityDraft.trim() });
  }
}
