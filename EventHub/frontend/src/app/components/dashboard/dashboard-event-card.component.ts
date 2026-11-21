import {
  Component,
  ElementRef,
  Injector,
  Renderer2,
  afterNextRender,
  computed,
  effect,
  inject,
  input,
  output,
  viewChild,
} from '@angular/core';
import { RouterModule } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import {
  Calendar,
  Copy,
  Ellipsis,
  LucideAngularModule,
  MapPin,
  PenLine,
  Trash2,
  Users,
} from 'lucide-angular';
import { LocalDatePipe, LocalNumberPipe } from '../../i18n/locale.pipes';
import { MoneyPipe } from '../../pipes/money.pipe';
import type { OrganizerEvent } from '../../services/organizer-dashboard.service';
import { EVENT_STATUS_BADGE, EVENT_STATUS_LABEL } from '../../utils/event-status';

const MENU_ITEMS = '[role="menuitem"]:not([disabled])';

/**
 * One event of the organizer dashboard: status, when and where, the sales
 * numbers the server computed, and the actions menu. The page owns which menu
 * is open (only one at a time) and runs duplicate and delete; the card only
 * reports what was chosen.
 */
@Component({
  selector: 'app-dashboard-event-card',
  standalone: true,
  imports: [
    RouterModule,
    LucideAngularModule,
    TranslocoPipe,
    MoneyPipe,
    LocalDatePipe,
    LocalNumberPipe,
  ],
  template: `
    @let ev = event();
    @let s = ev.stats;
    <article
      class="card p-5 hover:border-primary/30 transition-colors"
      [attr.aria-labelledby]="titleId()"
      data-testid="dashboard-event"
    >
      <div class="flex flex-col sm:flex-row sm:items-start gap-4 mb-4">
        <div class="flex-1 min-w-0">
          <div class="flex flex-wrap items-center gap-2 mb-2">
            <span class="badge" [class]="badgeClass()" data-testid="status-badge">{{
              statusKey() | transloco
            }}</span>
            @if (!ev.is_owner) {
              <span class="badge badge-info" data-testid="coorganizer-badge">{{
                'dashboard.coOrganizer' | transloco
              }}</span>
            }
          </div>
          <h3 [id]="titleId()" class="text-base font-semibold text-foreground truncate">
            {{ ev.title }}
          </h3>
          <div
            class="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-xs text-muted-foreground"
          >
            <span class="flex items-center gap-1">
              <lucide-icon [img]="icons.Calendar" class="w-3.5 h-3.5" aria-hidden="true" />
              <time [attr.datetime]="ev.date">{{ ev.date | localDate: 'MMM d, y · h:mm a' }}</time>
            </span>
            <span class="flex items-center gap-1 min-w-0">
              <lucide-icon
                [img]="icons.MapPin"
                class="w-3.5 h-3.5 flex-shrink-0"
                aria-hidden="true"
              />
              <span class="truncate">{{ ev.location }}</span>
            </span>
          </div>
        </div>

        <div class="flex items-start gap-2 flex-shrink-0">
          <a
            [routerLink]="['/organizer/events', ev.id, 'attendees']"
            class="btn btn-sm btn-secondary flex items-center gap-1"
            data-testid="attendees-link"
          >
            <lucide-icon [img]="icons.Users" class="w-3.5 h-3.5" aria-hidden="true" />
            {{ 'nav.attendees' | transloco }}
          </a>
          <div class="relative" #menuRoot>
            <button
              #trigger
              type="button"
              class="btn btn-sm btn-ghost p-2"
              aria-haspopup="menu"
              [attr.aria-expanded]="menuOpen()"
              [attr.aria-controls]="menuOpen() ? menuId() : null"
              [attr.aria-label]="'dashboard.menuFor' | transloco: { title: ev.title }"
              (click)="toggleMenu()"
              data-testid="menu-trigger"
            >
              <lucide-icon [img]="icons.Ellipsis" class="w-4 h-4" aria-hidden="true" />
            </button>
            @if (menuOpen()) {
              <div
                #menu
                role="menu"
                tabindex="-1"
                [id]="menuId()"
                [attr.aria-label]="'dashboard.menuFor' | transloco: { title: ev.title }"
                class="absolute right-0 mt-1 bg-background border border-border rounded-md shadow-lg z-10 min-w-44 py-1 animate-fade-in"
                (keydown)="onMenuKeydown($event)"
              >
                <a
                  role="menuitem"
                  tabindex="-1"
                  [routerLink]="['/edit-event', ev.id]"
                  class="flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted focus:bg-muted outline-none transition-colors"
                  data-testid="menu-edit"
                >
                  <lucide-icon [img]="icons.PenLine" class="w-4 h-4" aria-hidden="true" />
                  {{ 'dashboard.editEvent' | transloco }}
                </a>
                <button
                  type="button"
                  role="menuitem"
                  tabindex="-1"
                  [disabled]="duplicating()"
                  (click)="duplicate.emit()"
                  class="w-full text-left flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted focus:bg-muted outline-none transition-colors disabled:opacity-60"
                  data-testid="menu-duplicate"
                >
                  @if (duplicating()) {
                    <span class="spinner spinner-sm" aria-hidden="true"></span>
                    {{ 'dashboard.duplicating' | transloco }}
                  } @else {
                    <lucide-icon [img]="icons.Copy" class="w-4 h-4" aria-hidden="true" />
                    {{ 'dashboard.duplicate' | transloco }}
                  }
                </button>
                @if (ev.is_owner) {
                  <button
                    type="button"
                    role="menuitem"
                    tabindex="-1"
                    (click)="remove.emit()"
                    class="w-full text-left flex items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-[color:var(--destructive-50)] focus:bg-[color:var(--destructive-50)] outline-none transition-colors"
                    data-testid="menu-delete"
                  >
                    <lucide-icon [img]="icons.Trash2" class="w-4 h-4" aria-hidden="true" />
                    {{ 'common.delete' | transloco }}
                  </button>
                }
              </div>
            }
          </div>
        </div>
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-3 mb-4">
        <div class="col-span-2 sm:col-span-1">
          <div class="flex justify-between text-xs text-muted-foreground mb-1">
            <span>{{ 'dashboard.capacity' | transloco }}</span>
            <span class="font-semibold text-foreground num" data-testid="capacity-count"
              >{{ s.tickets_sold | localNumber }}/{{ s.capacity | localNumber }}</span
            >
          </div>
          <div
            class="h-2 bg-muted rounded-full overflow-hidden"
            role="progressbar"
            aria-valuemin="0"
            aria-valuemax="100"
            [attr.aria-valuenow]="barWidth()"
            [attr.aria-label]="'dashboard.capacity' | transloco"
          >
            <div
              class="h-full rounded-full"
              [class]="overbooked() ? 'bg-destructive' : 'bg-primary'"
              [style.width.%]="barWidth()"
              data-testid="capacity-bar"
            ></div>
          </div>
          <p
            class="text-xs mt-1"
            [class]="overbooked() ? 'text-destructive font-medium' : 'text-muted-foreground'"
            data-testid="capacity-label"
          >
            {{
              (overbooked() ? 'dashboard.overbooked' : 'dashboard.soldThrough')
                | transloco: { pct: (s.sold_through_pct | localNumber: '1.0-1') }
            }}
          </p>
        </div>

        <div>
          <p class="text-xs text-muted-foreground mb-1">
            {{ 'dashboard.ticketsSold' | transloco }}
          </p>
          <p class="text-lg font-bold text-foreground num" data-testid="tickets-sold">
            {{ s.tickets_sold | localNumber }}
          </p>
          <p class="text-xs text-muted-foreground mt-1" data-testid="pending-count">
            {{ 'dashboard.pendingCount' | transloco: { count: s.pending } }}
          </p>
        </div>

        <div>
          <p class="text-xs text-muted-foreground mb-1">
            {{ 'dashboard.checkInRate' | transloco }}
          </p>
          <p class="text-lg font-bold text-foreground num" data-testid="checkin-rate">
            {{ s.checkin_rate_pct | localNumber: '1.0-1' }}%
          </p>
          <p class="text-xs text-muted-foreground mt-1">
            {{ 'dashboard.checkedinCheckedIn' | transloco: { checkedIn: s.checked_in } }}
          </p>
        </div>

        @if (showRevenue()) {
          <div>
            <p class="text-xs text-muted-foreground mb-1">{{ 'dashboard.revenue' | transloco }}</p>
            <p class="text-lg font-bold text-foreground num" data-testid="event-revenue">
              {{ s.net_revenue | money: s.currency }}
            </p>
            <p class="text-xs text-muted-foreground mt-1">
              {{ 'dashboard.netOfRefunds' | transloco }}
            </p>
          </div>
        }
      </div>

      <a
        [routerLink]="['/events', ev.id]"
        class="text-xs text-primary hover:underline inline-flex items-center gap-1"
        data-testid="view-link"
      >
        {{ 'dashboard.viewEvent' | transloco }}
      </a>
    </article>
  `,
})
export class DashboardEventCardComponent {
  readonly event = input.required<OrganizerEvent>();
  readonly menuOpen = input(false);
  /** A copy of this event is being created. */
  readonly duplicating = input(false);

  readonly menuOpenChange = output<boolean>();
  readonly duplicate = output();
  readonly remove = output();

  readonly icons = { Calendar, MapPin, Users, Ellipsis, PenLine, Copy, Trash2 };

  private readonly injector = inject(Injector);
  private readonly renderer = inject(Renderer2);
  private readonly menuRoot = viewChild.required<ElementRef<HTMLElement>>('menuRoot');
  private readonly trigger = viewChild.required<ElementRef<HTMLButtonElement>>('trigger');
  private readonly menu = viewChild<ElementRef<HTMLElement>>('menu');

  readonly titleId = computed(() => `dashboard-event-title-${this.event().id}`);
  readonly menuId = computed(() => `dashboard-menu-${this.event().id}`);
  readonly statusKey = computed(() => EVENT_STATUS_LABEL[this.event().status]);
  readonly badgeClass = computed(() => EVENT_STATUS_BADGE[this.event().status]);

  /** The real figure; it exceeds 100 for an overbooked event. */
  readonly soldThroughPct = computed(() => this.event().stats.sold_through_pct);
  readonly overbooked = computed(() => this.soldThroughPct() > 100);
  /** Bar width only: the label keeps the real number. */
  readonly barWidth = computed(() => Math.min(100, Math.max(0, this.soldThroughPct())));

  /** Free events show revenue only when money actually came in (donations, ticket types). */
  readonly showRevenue = computed(() => {
    const ev = this.event();
    return !ev.is_free || Number(ev.stats.net_revenue) > 0;
  });

  constructor() {
    // Moving focus into the menu once it is rendered.
    effect(() => {
      if (this.menuOpen()) {
        afterNextRender(
          () => {
            this.focusItem(0);
          },
          { injector: this.injector },
        );
      }
    });

    // The page-wide listeners exist only while this card's menu is open, so a
    // list of cards does not register a pair of document listeners each.
    effect((onCleanup) => {
      if (!this.menuOpen()) return;
      const stopClick = this.renderer.listen('document', 'click', (event: MouseEvent) => {
        this.onDocumentClick(event);
      });
      const stopKey = this.renderer.listen('document', 'keydown', (event: KeyboardEvent) => {
        if (event.key === 'Escape') this.onEscape();
      });
      onCleanup(() => {
        stopClick();
        stopKey();
      });
    });
  }

  toggleMenu(): void {
    this.menuOpenChange.emit(!this.menuOpen());
  }

  /** Puts keyboard focus back on the menu button (after the menu closed or an action failed). */
  focusTrigger(): void {
    this.trigger().nativeElement.focus();
  }

  /** A click anywhere outside this card's menu button and menu closes it. */
  private onDocumentClick(event: MouseEvent): void {
    if (event.target instanceof Node && this.menuRoot().nativeElement.contains(event.target)) {
      return;
    }
    this.menuOpenChange.emit(false);
  }

  /** Esc closes the menu and returns focus to its button. */
  private onEscape(): void {
    this.menuOpenChange.emit(false);
    this.focusTrigger();
  }

  onMenuKeydown(event: KeyboardEvent): void {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        this.focusItem(this.focusedIndex() + 1);
        break;
      case 'ArrowUp':
        event.preventDefault();
        this.focusItem(this.focusedIndex() - 1);
        break;
      case 'Home':
        event.preventDefault();
        this.focusItem(0);
        break;
      case 'End':
        event.preventDefault();
        this.focusItem(-1);
        break;
      case 'Tab':
        // Focus leaves the menu: close it and park focus on its button first,
        // so the default Tab moves on from there and never from an item that
        // is about to be removed.
        this.menuOpenChange.emit(false);
        this.focusTrigger();
        break;
    }
  }

  private items(): HTMLElement[] {
    const menu = this.menu()?.nativeElement;
    return menu ? Array.from(menu.querySelectorAll<HTMLElement>(MENU_ITEMS)) : [];
  }

  private focusedIndex(): number {
    return this.items().indexOf(document.activeElement as HTMLElement);
  }

  /** Focuses the item at `index`, wrapping around; -1 is the last one. */
  private focusItem(index: number): void {
    const items = this.items();
    if (!items.length) return;
    const wrapped = ((index % items.length) + items.length) % items.length;
    items[wrapped].focus();
  }
}
