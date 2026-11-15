import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { LucideAngularModule, MapPin, X } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { DialogDirective } from '../../directives/dialog.directive';
import { DEFAULT_SORT, DiscoverFilters } from './discover-filters';

/** Mobile filters (<768px): city, format and price, sort. Loaded on first open. */
@Component({
  selector: 'app-filter-sheet',
  standalone: true,
  imports: [FormsModule, LucideAngularModule, TranslocoPipe, DialogDirective],
  template: `
    <div class="fixed inset-0 z-50 bg-black/50 animate-fade-in">
      <div class="filter-sheet" appDialog dismissOnBackdrop (dismiss)="closed.emit()">
        <div class="flex items-center justify-between mb-5">
          <h2 class="text-lg font-semibold text-foreground">
            {{ 'home.filters.open' | transloco }}
          </h2>
          <button
            type="button"
            class="nav-icon-btn focus-ring"
            [attr.aria-label]="'common.close' | transloco"
            (click)="closed.emit()"
          >
            <lucide-icon [img]="icons.X" class="w-5 h-5" aria-hidden="true" />
          </button>
        </div>

        <label class="filter-label" for="sheet-city">{{ 'home.filters.city' | transloco }}</label>
        <div class="filter-field mb-5">
          <lucide-icon [img]="icons.MapPin" class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
          <input
            id="sheet-city"
            type="text"
            [(ngModel)]="draft.city"
            [placeholder]="'home.filters.cityPlaceholder' | transloco"
            class="filter-input"
          />
        </div>

        <p class="filter-label">{{ 'home.filters.formatPrice' | transloco }}</p>
        <div class="flex flex-wrap gap-2 mb-5">
          <button
            type="button"
            class="chip"
            [class.chip-active]="draft.free"
            [attr.aria-pressed]="draft.free"
            (click)="draft.free = !draft.free"
          >
            {{ 'home.freeOnly' | transloco }}
          </button>
          <button
            type="button"
            class="chip"
            [class.chip-active]="draft.online"
            [attr.aria-pressed]="draft.online"
            (click)="draft.online = !draft.online"
          >
            {{ 'home.online' | transloco }}
          </button>
        </div>

        <label class="filter-label" for="sheet-sort">{{ 'home.sortEvents' | transloco }}</label>
        <select id="sheet-sort" [(ngModel)]="draft.sort" class="input mb-6">
          <option value="date">{{ 'home.sort.dateAsc' | transloco }}</option>
          <option value="-date">{{ 'home.sort.dateDesc' | transloco }}</option>
          <option value="-created_at">{{ 'home.sort.newest' | transloco }}</option>
          <option value="price">{{ 'home.sort.priceAsc' | transloco }}</option>
          <option value="-price">{{ 'home.sort.priceDesc' | transloco }}</option>
        </select>

        <div class="flex gap-2">
          <button type="button" class="btn btn-secondary flex-1" (click)="clear()">
            {{ 'home.clear' | transloco }}
          </button>
          <button type="button" class="btn btn-primary flex-1" (click)="apply()">
            {{ 'home.filters.apply' | transloco }}
          </button>
        </div>
      </div>
    </div>
  `,
})
export class FilterSheetComponent implements OnInit {
  @Input({ required: true }) filters!: DiscoverFilters;
  @Output() readonly applied = new EventEmitter<Partial<DiscoverFilters>>();
  @Output() readonly closed = new EventEmitter<void>();

  draft = { city: '', free: false, online: false, sort: DEFAULT_SORT };
  readonly icons = { MapPin, X };

  ngOnInit(): void {
    const { city, free, online, sort } = this.filters;
    this.draft = { city, free, online, sort };
  }

  clear(): void {
    this.draft = { city: '', free: false, online: false, sort: DEFAULT_SORT };
  }

  apply(): void {
    this.applied.emit({ ...this.draft, city: this.draft.city.trim() });
  }
}
