import { Component, computed, input, output } from '@angular/core';
import { Params, RouterModule } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import {
  ArrowDown,
  ArrowUp,
  CalendarClock,
  ClipboardCheck,
  LucideAngularModule,
} from 'lucide-angular';
import { LocalNumberPipe, PluralPipe } from '../../i18n/locale.pipes';
import { MoneyPipe } from '../../pipes/money.pipe';
import type { DashboardSummary } from '../../services/organizer-dashboard.service';

export type SectionStatus = 'loading' | 'ready' | 'error';

export interface SalesTrend {
  direction: 'up' | 'down' | 'flat';
  /** Last 7 days minus the 7 days before (signed). */
  delta: number;
  /** Absolute change in percent of the previous week; null when it has no base or no change. */
  percent: number | null;
}

/**
 * Sales of the last 7 days against the 7 days before. Null when both are 0:
 * nothing happened, so there is nothing to compare (and no made-up trend).
 */
export function salesTrend(last: number, previous: number): SalesTrend | null {
  if (last === 0 && previous === 0) return null;
  const delta = last - previous;
  const direction = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat';
  const percent =
    previous > 0 && delta !== 0 ? Math.round((Math.abs(delta) / previous) * 100) : null;
  return { direction, delta, percent };
}

/**
 * The KPI row of the organizer dashboard: global numbers over every managed
 * event (never the current tab), plus links to what needs attention.
 */
@Component({
  selector: 'app-dashboard-summary',
  standalone: true,
  imports: [
    RouterModule,
    LucideAngularModule,
    TranslocoPipe,
    MoneyPipe,
    LocalNumberPipe,
    PluralPipe,
  ],
  template: `
    @if (status() === 'loading') {
      <div
        class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3"
        role="status"
        [attr.aria-label]="'dashboard.loadingDashboard' | transloco"
      >
        @for (n of placeholders; track n) {
          <div class="card p-4" aria-hidden="true">
            <div class="h-3 w-16 rounded bg-muted animate-pulse mb-3"></div>
            <div class="h-7 w-20 rounded bg-muted animate-pulse"></div>
          </div>
        }
      </div>
    } @else if (status() === 'error' || !summary()) {
      <div class="note note-error" role="alert" data-testid="summary-error">
        <span class="flex-1">{{ 'dashboard.summaryFailed' | transloco }}</span>
        <button type="button" class="btn btn-sm btn-secondary" (click)="retry.emit()">
          {{ 'common.retry' | transloco }}
        </button>
      </div>
    } @else {
      @let s = summary()!;
      <dl class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3" data-testid="summary-kpis">
        <div class="card p-4">
          <dt class="text-xs text-muted-foreground font-medium mb-1">
            {{ 'dashboard.events' | transloco }}
          </dt>
          <dd class="text-2xl font-bold text-foreground num" data-testid="kpi-events">
            {{ eventsTotal() | localNumber }}
          </dd>
        </div>
        <div class="card p-4">
          <dt class="text-xs text-muted-foreground font-medium mb-1">
            {{ 'dashboard.ticketsSold' | transloco }}
          </dt>
          <dd class="text-2xl font-bold text-foreground num" data-testid="kpi-tickets">
            {{ s.tickets_sold | localNumber }}
          </dd>
        </div>
        <div class="card p-4">
          <dt class="text-xs text-muted-foreground font-medium mb-1">
            {{ 'dashboard.checkInRate' | transloco }}
          </dt>
          <dd class="text-2xl font-bold text-foreground num" data-testid="kpi-checkin">
            {{ s.checkin_rate_pct | localNumber: '1.0-1' }}%
          </dd>
          <dd class="text-xs text-muted-foreground mt-0.5">
            {{
              'dashboard.checkedInOfSold'
                | transloco: { checkedIn: s.checked_in, sold: s.tickets_sold }
            }}
          </dd>
        </div>
        <div class="card p-4">
          <dt class="text-xs text-muted-foreground font-medium mb-1">
            {{ 'dashboard.revenue' | transloco }}
          </dt>
          <!-- One line per currency: amounts in different currencies never add up. -->
          @for (r of s.revenue; track r.currency) {
            <dd
              class="text-2xl font-bold text-foreground num leading-tight"
              data-testid="kpi-revenue"
            >
              {{ r.net_revenue | money: r.currency }}
            </dd>
          } @empty {
            <dd class="text-2xl font-bold text-foreground num" data-testid="kpi-revenue">—</dd>
          }
        </div>
        <div class="card p-4 col-span-2 sm:col-span-1">
          <dt class="text-xs text-muted-foreground font-medium mb-1">
            {{ 'dashboard.salesLast7Days' | transloco }}
          </dt>
          <dd class="flex items-baseline gap-2 flex-wrap">
            <span class="text-2xl font-bold text-foreground num" data-testid="kpi-sales">
              {{ s.sales_last_7_days | localNumber }}
            </span>
            @if (trend(); as t) {
              <span
                class="text-xs font-medium flex items-center gap-0.5"
                [class]="trendClass[t.direction]"
                data-testid="sales-trend"
                [attr.data-direction]="t.direction"
              >
                @if (t.direction === 'up') {
                  <lucide-icon [img]="icons.ArrowUp" class="w-3 h-3" aria-hidden="true" />
                  <span aria-hidden="true">+{{ t.delta | localNumber }}</span>
                } @else if (t.direction === 'down') {
                  <lucide-icon [img]="icons.ArrowDown" class="w-3 h-3" aria-hidden="true" />
                  <span aria-hidden="true">−{{ -t.delta | localNumber }}</span>
                } @else {
                  <span aria-hidden="true">0</span>
                }
                @if (t.percent !== null) {
                  <span aria-hidden="true"
                    >({{ t.direction === 'up' ? '+' : '−' }}{{ t.percent }}%)</span
                  >
                }
                <span class="sr-only">{{
                  'dashboard.trend_' + t.direction
                    | transloco
                      : { count: t.delta < 0 ? -t.delta : t.delta, percent: t.percent ?? 0 }
                }}</span>
              </span>
            }
          </dd>
          @if (trend()) {
            <dd class="text-2xs text-muted-foreground mt-0.5">
              {{ 'dashboard.vsPreviousWeek' | transloco }}
            </dd>
          }
        </div>
      </dl>

      @if (s.upcoming_next_7_days > 0 || s.pending_approval > 0) {
        <nav
          class="flex flex-wrap gap-2 mt-3"
          [attr.aria-label]="'dashboard.needsAttention' | transloco"
          data-testid="callouts"
        >
          @if (s.upcoming_next_7_days > 0) {
            <a
              [routerLink]="[]"
              [queryParams]="linkParams()"
              fragment="dashboard-events"
              [replaceUrl]="true"
              class="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-sm text-foreground hover:border-primary/40 transition-colors"
              data-testid="callout-soon"
            >
              <lucide-icon
                [img]="icons.CalendarClock"
                class="w-4 h-4 text-primary"
                aria-hidden="true"
              />
              {{ 'dashboard.upcomingSoon' | tPlural: s.upcoming_next_7_days }}
            </a>
          }
          @if (s.pending_approval > 0) {
            <a
              [routerLink]="[]"
              [queryParams]="linkParams()"
              fragment="dashboard-events"
              [replaceUrl]="true"
              class="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-sm text-foreground hover:border-primary/40 transition-colors"
              data-testid="callout-approval"
            >
              <lucide-icon
                [img]="icons.ClipboardCheck"
                class="w-4 h-4 text-warning"
                aria-hidden="true"
              />
              {{ 'dashboard.awaitingApproval' | tPlural: s.pending_approval }}
            </a>
          }
        </nav>
      }
    }
  `,
})
export class DashboardSummaryComponent {
  readonly summary = input<DashboardSummary | null>(null);
  readonly status = input<SectionStatus>('loading');
  /**
   * Query params of the callouts (the Upcoming tab, plus whatever else the page
   * keeps in its URL), so following one loses nothing.
   */
  readonly linkParams = input<Params>({ tab: 'upcoming' });
  readonly retry = output();

  readonly icons = { ArrowUp, ArrowDown, CalendarClock, ClipboardCheck };
  readonly placeholders = [1, 2, 3, 4, 5];
  readonly trendClass: Record<SalesTrend['direction'], string> = {
    up: 'text-[color:var(--pine-600)]',
    down: 'text-destructive',
    flat: 'text-muted-foreground',
  };

  /** All managed events: the sum of the tab counts (every event is in exactly one tab). */
  readonly eventsTotal = computed(() => {
    const tabs = this.summary()?.tabs;
    return tabs ? tabs.upcoming + tabs.past + tabs.drafts + tabs.inactive : 0;
  });

  readonly trend = computed(() => {
    const s = this.summary();
    return s ? salesTrend(s.sales_last_7_days, s.sales_previous_7_days) : null;
  });
}
