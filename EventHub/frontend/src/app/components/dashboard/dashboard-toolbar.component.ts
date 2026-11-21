import { Component, ElementRef, input, output, viewChildren } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';
import { LucideAngularModule, Search } from 'lucide-angular';
import { LocalNumberPipe } from '../../i18n/locale.pipes';
import {
  DASHBOARD_ORDERINGS,
  DASHBOARD_TABS,
  SEARCH_MAX_LENGTH,
  type DashboardOrdering,
  type DashboardTab,
  type DashboardTabs,
} from '../../services/organizer-dashboard.service';

/** Id of the tab panel the tabs control (the list section of the page). */
export const DASHBOARD_PANEL_ID = 'dashboard-events';
export const dashboardTabId = (tab: DashboardTab): string => `dashboard-tab-${tab}`;

export const TAB_LABEL: Record<DashboardTab, string> = {
  upcoming: 'dashboard.tabUpcoming',
  past: 'dashboard.tabPast',
  drafts: 'dashboard.tabDrafts',
  inactive: 'dashboard.tabInactive',
};

const ORDERING_LABEL: Record<DashboardOrdering, string> = {
  date: 'dashboard.sortDateSoonest',
  '-date': 'dashboard.sortDateLatest',
  '-tickets_sold': 'dashboard.sortMostTickets',
  '-checkin_rate': 'dashboard.sortCheckIn',
  '-sold_through': 'dashboard.sortSellThrough',
};

/**
 * Tabs (with the server's counts), debounced search and sort of the event
 * list. It only reports what the user did; the page keeps the state in the URL.
 */
@Component({
  selector: 'app-dashboard-toolbar',
  standalone: true,
  imports: [LucideAngularModule, TranslocoPipe, LocalNumberPipe],
  template: `
    <div class="space-y-3">
      <div class="flex flex-col sm:flex-row gap-3">
        <label
          class="flex items-center gap-2 flex-1 border border-border rounded-md px-3 h-10 bg-background focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-shadow"
        >
          <lucide-icon
            [img]="icons.Search"
            class="w-4 h-4 text-muted-foreground flex-shrink-0"
            aria-hidden="true"
          />
          <input
            type="search"
            [value]="searchText()"
            (input)="onSearch($event)"
            [maxLength]="searchMax"
            [placeholder]="'dashboard.searchEvents' | transloco"
            class="flex-1 min-w-0 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
            [attr.aria-label]="'dashboard.searchLabel' | transloco"
            data-testid="dashboard-search"
          />
        </label>
        <select
          class="input h-10 sm:w-52"
          [attr.aria-label]="'dashboard.sortEvents' | transloco"
          (change)="onOrdering($event)"
          data-testid="dashboard-sort"
        >
          @for (o of orderings; track o) {
            <option [value]="o" [selected]="o === ordering()">
              {{ orderingLabel[o] | transloco }}
            </option>
          }
        </select>
      </div>

      <div
        class="flex items-center gap-1 border-b border-border overflow-x-auto"
        role="tablist"
        [attr.aria-label]="'dashboard.tabsLabel' | transloco"
      >
        @for (t of tabs; track t) {
          <button
            #tabButton
            type="button"
            role="tab"
            [id]="tabId(t)"
            [attr.aria-selected]="t === tab()"
            [attr.aria-controls]="panelId"
            [attr.tabindex]="t === tab() ? 0 : -1"
            (click)="tabChange.emit(t)"
            (keydown)="onTabKeydown($event)"
            class="px-4 py-2 text-sm font-medium whitespace-nowrap -mb-px flex items-center gap-1.5"
            [class]="
              t === tab()
                ? 'text-primary border-b-2 border-primary'
                : 'text-muted-foreground hover:text-foreground'
            "
          >
            {{ tabLabel[t] | transloco }}
            @if (counts(); as c) {
              <span class="num text-xs text-muted-foreground" [attr.data-testid]="'count-' + t">{{
                c[t] | localNumber
              }}</span>
            }
          </button>
        }
      </div>
    </div>
  `,
})
export class DashboardToolbarComponent {
  readonly tab = input.required<DashboardTab>();
  /** Per-tab totals from the summary; null while unknown (then no counts are shown). */
  readonly counts = input<DashboardTabs | null>(null);
  readonly searchText = input('');
  readonly ordering = input.required<DashboardOrdering>();

  readonly tabChange = output<DashboardTab>();
  /** Every keystroke; the page debounces it. */
  readonly searchInput = output<string>();
  readonly orderingChange = output<DashboardOrdering>();

  readonly icons = { Search };
  readonly tabs = DASHBOARD_TABS;
  readonly orderings = DASHBOARD_ORDERINGS;
  readonly tabLabel = TAB_LABEL;
  readonly orderingLabel = ORDERING_LABEL;
  readonly searchMax = SEARCH_MAX_LENGTH;
  readonly panelId = DASHBOARD_PANEL_ID;
  readonly tabId = dashboardTabId;

  private readonly tabButtons = viewChildren<ElementRef<HTMLButtonElement>>('tabButton');

  onSearch(event: Event): void {
    this.searchInput.emit((event.target as HTMLInputElement).value);
  }

  onOrdering(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    const ordering = this.orderings.find((o) => o === value);
    if (ordering) this.orderingChange.emit(ordering);
  }

  /** Arrow keys, Home and End move between tabs and select the focused one. */
  onTabKeydown(event: KeyboardEvent): void {
    // The focused tab counts, not the selected one: the page applies a choice a moment later.
    const focused = this.tabButtons().findIndex((b) => b.nativeElement === event.target);
    const current = focused >= 0 ? focused : this.tabs.indexOf(this.tab());
    const last = this.tabs.length - 1;
    let next: number;
    switch (event.key) {
      case 'ArrowRight':
        next = current === last ? 0 : current + 1;
        break;
      case 'ArrowLeft':
        next = current === 0 ? last : current - 1;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = last;
        break;
      default:
        return;
    }
    event.preventDefault();
    this.tabChange.emit(this.tabs[next]);
    this.tabButtons()[next]?.nativeElement.focus();
  }
}
