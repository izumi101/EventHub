import { formatDate, formatNumber } from '@angular/common';
import {
  Component,
  DestroyRef,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslocoPipe } from '@jsverse/transloco';
import { Subject, catchError, map, of, switchMap } from 'rxjs';
import { errorMessage } from '../../api/error-message';
import { LanguageService } from '../../i18n/language.service';
import { LocalDatePipe, LocalNumberPipe, PluralPipe } from '../../i18n/locale.pipes';
import { MoneyPipe } from '../../pipes/money.pipe';
import {
  DEFAULT_SALES_RANGE,
  OrganizerDashboardService,
  SALES_RANGES,
  type SalesChart,
  type SalesRange,
} from '../../services/organizer-dashboard.service';
import { DashboardSegmentedComponent, type SegmentedOption } from './dashboard-segmented.component';
import type { SectionStatus } from './dashboard-summary.component';
import {
  CHART_LEFT,
  CHART_RIGHT,
  TICKETS_TOP,
  buildChartModel,
  isEmptySales,
  revenueTotals,
  totalTickets,
} from './sales-chart';

const RANGE_LABEL: Record<SalesRange, string> = {
  '7d': 'dashboard.sales.range7d',
  '30d': 'dashboard.sales.range30d',
  '90d': 'dashboard.sales.range90d',
};

/** "30d" → 30. */
const rangeDays = (range: SalesRange): number => Number.parseInt(range, 10);

/**
 * Sales of every managed event over 7, 30 or 90 days: tickets per day and net
 * revenue per day in one currency at a time, the range totals, and the events
 * published in the range. The chart is an inline SVG. It loads and fails on
 * its own, and the range lives in the URL (the page owns it).
 *
 * Keyboard: the chart is one tab stop; the arrow keys, Home and End move from
 * day to day and the day's figures are read out (and announced). The same
 * numbers are available as a table.
 */
@Component({
  selector: 'app-dashboard-sales',
  standalone: true,
  imports: [
    TranslocoPipe,
    MoneyPipe,
    LocalDatePipe,
    LocalNumberPipe,
    PluralPipe,
    DashboardSegmentedComponent,
  ],
  styles: [
    `
      /* A total fills its cell: scales with the cell's width (cqi), between 15 and 20 px, so a
         long amount in a narrow cell never wraps or overflows. */
      .sales-total {
        font-size: clamp(0.95rem, 9cqi, 1.25rem);
        line-height: 1.3;
      }
    `,
  ],
  template: `
    <section
      class="card p-5 min-w-0 h-full"
      aria-labelledby="dashboard-sales-title"
      data-testid="sales-section"
    >
      <header class="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div class="min-w-0">
          <h2 id="dashboard-sales-title" class="text-sm font-semibold text-foreground">
            {{ 'dashboard.sales.title' | transloco }}
          </h2>
          @if (sales(); as s) {
            <p class="text-xs text-muted-foreground mt-0.5" data-testid="chart-period">
              <time [attr.datetime]="s.start">{{ s.start | localDate: 'MMM d' }}</time>
              –
              <time [attr.datetime]="s.end">{{ s.end | localDate: 'MMM d' }}</time>
            </p>
          }
        </div>
        <app-dashboard-segmented
          [options]="rangeOptions()"
          [value]="range()"
          [label]="'dashboard.sales.rangeLabel' | transloco"
          (valueChange)="chooseRange($event)"
          data-testid="chart-range"
        />
      </header>

      @if (status() === 'loading') {
        <div
          role="status"
          [attr.aria-label]="'common.loading' | transloco"
          data-testid="chart-loading"
        >
          <div class="grid grid-cols-2 gap-3 mb-4" aria-hidden="true">
            <div class="h-10 rounded bg-muted animate-pulse motion-reduce:animate-none"></div>
            <div class="h-10 rounded bg-muted animate-pulse motion-reduce:animate-none"></div>
          </div>
          <div
            class="h-56 rounded bg-muted animate-pulse motion-reduce:animate-none"
            aria-hidden="true"
          ></div>
        </div>
      } @else if (status() === 'error') {
        <div class="note note-error" role="alert" data-testid="chart-error">
          <span class="flex-1">{{ error() }}</span>
          <button type="button" class="btn btn-sm btn-secondary" (click)="retry()">
            {{ 'common.retry' | transloco }}
          </button>
        </div>
      } @else if (empty()) {
        <p class="text-sm text-muted-foreground py-10 text-center" data-testid="chart-empty">
          {{ 'dashboard.sales.emptyRange' | tPlural: days() }}
        </p>
      } @else {
        @let m = model()!;
        <div class="grid grid-cols-2 gap-3 mb-4" data-testid="chart-totals">
          <div class="min-w-0 [container-type:inline-size]">
            <p class="text-xs text-muted-foreground mb-0.5">
              {{ 'dashboard.sales.ticketsTotal' | transloco }}
            </p>
            <p
              class="sales-total num font-bold text-foreground whitespace-nowrap"
              data-testid="chart-total-tickets"
            >
              {{ tickets() | localNumber }}
            </p>
          </div>
          <div class="min-w-0 [container-type:inline-size]">
            <p class="text-xs text-muted-foreground mb-0.5">
              {{ 'dashboard.sales.revenueTotal' | transloco }}
            </p>
            <!-- One line per currency: amounts in different currencies never add up. -->
            @for (r of totals(); track r.currency) {
              <p
                class="sales-total num font-bold text-foreground whitespace-nowrap"
                data-testid="chart-total-revenue"
              >
                {{ r.total | money: r.currency }}
              </p>
            } @empty {
              <p
                class="sales-total num font-bold text-foreground"
                data-testid="chart-total-revenue"
              >
                —
              </p>
            }
          </div>
        </div>

        @if (currencies().length > 1) {
          <div class="flex flex-wrap items-center gap-2 mb-3">
            <span class="text-xs text-muted-foreground">{{
              'dashboard.sales.currencyLabel' | transloco
            }}</span>
            <app-dashboard-segmented
              [options]="currencyOptions()"
              [value]="currency() ?? ''"
              [label]="'dashboard.sales.currencyLabel' | transloco"
              (valueChange)="currencyChoice.set($event)"
              data-testid="chart-currency"
            />
          </div>
        }

        <p
          class="text-xs text-muted-foreground min-h-[2.5rem] mb-1"
          [attr.aria-live]="focused() ? 'polite' : 'off'"
          data-testid="chart-readout"
        >
          @if (activeColumn(); as c) {
            <span class="font-semibold text-foreground">{{
              c.date | localDate: 'EEE, MMM d'
            }}</span>
            · {{ 'dashboard.sales.readoutTickets' | tPlural: c.tickets }}
            @if (c.revenue !== null) {
              ·
              {{
                'dashboard.sales.readoutRevenue'
                  | transloco: { amount: (c.revenue | money: currency()) }
              }}
            }
            @for (marker of c.markers; track marker.event_id) {
              <br />
              <span class="text-primary" data-testid="chart-readout-marker">{{
                'dashboard.sales.readoutPublished' | transloco: { title: marker.title }
              }}</span>
            }
          } @else {
            {{ 'dashboard.sales.readoutHint' | transloco }}
          }
        </p>

        <p id="dashboard-sales-hint" class="sr-only">
          {{ 'dashboard.sales.chartHint' | transloco }}
        </p>
        <!-- The scroll container is the one tab stop of the chart. A narrow screen scrolls
             here, never the page. -->
        <div
          #scroller
          class="overflow-x-auto rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring"
          tabindex="0"
          role="group"
          [attr.aria-label]="'dashboard.sales.chartLabel' | transloco"
          aria-describedby="dashboard-sales-hint"
          (keydown)="onKeydown($event)"
          (focus)="onFocus()"
          (blur)="onBlur()"
          data-testid="chart-scroll"
        >
          <svg
            role="img"
            [attr.viewBox]="'0 0 ' + m.width + ' ' + m.height"
            [attr.aria-label]="summaryLabel()"
            class="block w-full h-auto select-none"
            [style.min-width.px]="m.width"
            (mouseleave)="onLeave()"
            data-testid="chart"
          >
            <!-- Panel titles -->
            <text x="0" y="12" font-size="10" class="fill-muted-foreground">
              {{ 'dashboard.sales.ticketsPerDay' | transloco }}
            </text>
            @if (m.hasRevenue) {
              <text x="0" [attr.y]="m.revenueTitleY" font-size="10" class="fill-muted-foreground">
                {{ 'dashboard.sales.revenuePerDay' | transloco: { currency: currency() } }}
              </text>
            }

            <!-- The highlighted day sits behind the bars -->
            @if (activeColumn(); as c) {
              <rect
                [attr.x]="c.x"
                [attr.y]="top"
                [attr.width]="m.step"
                [attr.height]="m.axisY - top - 6"
                class="fill-foreground/10"
                data-testid="chart-active"
              />
            }

            <!-- Tickets axis and bars -->
            @for (t of ticketTicks(); track t.y) {
              <line
                [attr.x1]="left"
                [attr.x2]="m.width - right"
                [attr.y1]="t.y"
                [attr.y2]="t.y"
                class="stroke-border"
              />
              <text
                [attr.x]="left - 6"
                [attr.y]="t.y + 3"
                text-anchor="end"
                font-size="10"
                class="fill-muted-foreground"
              >
                {{ t.label }}
              </text>
            }
            @for (c of m.columns; track c.index) {
              @if (c.ticketsBar; as bar) {
                <rect
                  [attr.x]="bar.x"
                  [attr.y]="bar.y"
                  [attr.width]="bar.width"
                  [attr.height]="bar.height"
                  rx="1.5"
                  class="fill-ember"
                  data-testid="chart-ticket-bar"
                />
              }
            }

            <!-- Revenue axis and bars (one currency) -->
            @if (m.hasRevenue) {
              @for (t of revenueTicks(); track t.y) {
                <line
                  [attr.x1]="left"
                  [attr.x2]="m.width - right"
                  [attr.y1]="t.y"
                  [attr.y2]="t.y"
                  class="stroke-border"
                />
                <text
                  [attr.x]="left - 6"
                  [attr.y]="t.y + 3"
                  text-anchor="end"
                  font-size="10"
                  class="fill-muted-foreground"
                >
                  {{ t.label }}
                </text>
              }
              @if (m.hasNegativeRevenue) {
                <line
                  [attr.x1]="left"
                  [attr.x2]="m.width - right"
                  [attr.y1]="m.revenueZeroY"
                  [attr.y2]="m.revenueZeroY"
                  class="stroke-border-strong"
                />
              }
              @for (c of m.columns; track c.index) {
                @if (c.revenueBar; as bar) {
                  <rect
                    [attr.x]="bar.x"
                    [attr.y]="bar.y"
                    [attr.width]="bar.width"
                    [attr.height]="bar.height"
                    rx="1.5"
                    [class]="bar.negative ? 'fill-destructive' : 'fill-pine'"
                    data-testid="chart-revenue-bar"
                  />
                }
              }
            }

            <!-- Events published in the range -->
            @for (line of m.markerLines; track line.date) {
              <line
                [attr.x1]="line.x"
                [attr.x2]="line.x"
                [attr.y1]="top"
                [attr.y2]="m.axisY - 6"
                stroke-width="1.5"
                stroke-dasharray="3 3"
                class="stroke-primary"
                data-testid="chart-marker"
                [attr.data-date]="line.date"
                [attr.data-titles]="line.titles.join(', ')"
              />
              <circle [attr.cx]="line.x" [attr.cy]="top" r="3" class="fill-primary" />
            }

            <!-- Date labels, decimated so they never overlap -->
            @for (l of axisLabels(); track l.x) {
              <text
                [attr.x]="l.x"
                [attr.y]="m.axisY"
                text-anchor="middle"
                font-size="10"
                class="fill-muted-foreground"
              >
                {{ l.text }}
              </text>
            }

            <!-- Pointer targets, one per day, on top of everything -->
            @for (c of m.columns; track c.index) {
              <rect
                [attr.x]="c.x"
                [attr.y]="top"
                [attr.width]="m.step"
                [attr.height]="m.axisY - top - 6"
                fill="transparent"
                (mouseenter)="setActive(c.index)"
                (click)="setActive(c.index)"
                data-testid="chart-day"
              />
            }
          </svg>
        </div>

        <div class="mt-3">
          <button
            type="button"
            class="btn btn-sm btn-ghost"
            [attr.aria-expanded]="showTable()"
            aria-controls="dashboard-sales-table"
            (click)="showTable.set(!showTable())"
            data-testid="chart-table-toggle"
          >
            {{
              (showTable() ? 'dashboard.sales.hideTable' : 'dashboard.sales.showTable') | transloco
            }}
          </button>
          @if (showTable()) {
            <div
              id="dashboard-sales-table"
              class="mt-2 max-h-72 overflow-auto rounded-md border border-border"
              tabindex="0"
              role="region"
              [attr.aria-label]="'dashboard.sales.tableLabel' | transloco"
              data-testid="chart-table"
            >
              <table class="w-full text-xs">
                <caption class="sr-only">
                  {{
                    'dashboard.sales.tableLabel' | transloco
                  }}
                </caption>
                <thead class="bg-muted text-muted-foreground sticky top-0">
                  <tr>
                    <th scope="col" class="text-left font-medium px-3 py-2">
                      {{ 'dashboard.sales.colDate' | transloco }}
                    </th>
                    <th scope="col" class="text-right font-medium px-3 py-2">
                      {{ 'dashboard.sales.colTickets' | transloco }}
                    </th>
                    @for (r of totals(); track r.currency) {
                      <th scope="col" class="text-right font-medium px-3 py-2 whitespace-nowrap">
                        {{ 'dashboard.sales.colRevenue' | transloco: { currency: r.currency } }}
                      </th>
                    }
                    @if (hasMarkers()) {
                      <th scope="col" class="text-left font-medium px-3 py-2">
                        {{ 'dashboard.sales.colPublished' | transloco }}
                      </th>
                    }
                  </tr>
                </thead>
                <tbody>
                  @for (row of tableRows(); track row.date) {
                    <tr class="border-t border-border/60" data-testid="chart-table-row">
                      <th scope="row" class="text-left font-normal px-3 py-1.5 whitespace-nowrap">
                        {{ row.date | localDate: 'EEE, MMM d' }}
                      </th>
                      <td class="text-right num px-3 py-1.5">{{ row.tickets | localNumber }}</td>
                      @for (cell of row.revenue; track $index) {
                        <td class="text-right num px-3 py-1.5 whitespace-nowrap">
                          {{ cell | money: totals()[$index].currency }}
                        </td>
                      }
                      @if (hasMarkers()) {
                        <td class="px-3 py-1.5">{{ row.published }}</td>
                      }
                    </tr>
                  }
                </tbody>
                <tfoot class="border-t border-border font-semibold">
                  <tr>
                    <th scope="row" class="text-left px-3 py-2">
                      {{ 'dashboard.sales.totalRow' | transloco }}
                    </th>
                    <td class="text-right num px-3 py-2">{{ tickets() | localNumber }}</td>
                    @for (r of totals(); track r.currency) {
                      <td class="text-right num px-3 py-2 whitespace-nowrap">
                        {{ r.total | money: r.currency }}
                      </td>
                    }
                    @if (hasMarkers()) {
                      <td></td>
                    }
                  </tr>
                </tfoot>
              </table>
            </div>
          }
        </div>
      }
    </section>
  `,
})
export class DashboardSalesComponent {
  private readonly service = inject(OrganizerDashboardService);
  private readonly language = inject(LanguageService);
  private readonly destroyRef = inject(DestroyRef);

  /** The window to draw; the page keeps it in the URL. */
  readonly range = input<SalesRange>(DEFAULT_SALES_RANGE);
  readonly rangeChange = output<SalesRange>();

  readonly status = signal<SectionStatus>('loading');
  readonly sales = signal<SalesChart | null>(null);
  readonly error = signal('');
  /** The currency the user picked; falls back to the first one the data has. */
  readonly currencyChoice = signal<string | null>(null);
  /** Index of the day whose figures are read out. */
  readonly active = signal<number | null>(null);
  readonly showTable = signal(false);
  readonly focused = signal(false);

  protected readonly left = CHART_LEFT;
  protected readonly right = CHART_RIGHT;
  protected readonly top = TICKETS_TOP - 4;

  private readonly scroller = viewChild<ElementRef<HTMLElement>>('scroller');
  private readonly requests$ = new Subject<SalesRange>();

  readonly rangeOptions = computed<SegmentedOption[]>(() =>
    SALES_RANGES.map((value) => ({ value, label: this.language.t(RANGE_LABEL[value]) })),
  );
  readonly days = computed(() => rangeDays(this.range()));
  readonly empty = computed(() => {
    const sales = this.sales();
    return sales !== null && isEmptySales(sales);
  });
  readonly tickets = computed(() => {
    const sales = this.sales();
    return sales ? totalTickets(sales) : 0;
  });
  readonly totals = computed(() => {
    const sales = this.sales();
    return sales ? revenueTotals(sales) : [];
  });
  readonly currencies = computed(() => this.totals().map((r) => r.currency));
  readonly currencyOptions = computed<SegmentedOption[]>(() =>
    this.currencies().map((value) => ({ value, label: value })),
  );
  readonly currency = computed<string | null>(() => {
    const list = this.currencies();
    const chosen = this.currencyChoice();
    return chosen !== null && list.includes(chosen) ? chosen : (list[0] ?? null);
  });

  readonly model = computed(() => {
    const sales = this.sales();
    return sales ? buildChartModel(sales, this.currency()) : null;
  });
  readonly activeColumn = computed(() => {
    const index = this.active();
    return index === null ? null : (this.model()?.columns[index] ?? null);
  });
  readonly hasMarkers = computed(() => (this.sales()?.markers.length ?? 0) > 0);

  readonly ticketTicks = computed(() =>
    (this.model()?.ticketTicks ?? []).map((t) => ({
      y: t.y,
      label: formatNumber(t.value, this.language.locale()),
    })),
  );
  readonly revenueTicks = computed(() => {
    const currency = this.currency();
    const locale = this.language.locale();
    let format: (value: number) => string = (value) => formatNumber(value, locale);
    if (currency) {
      try {
        const formatter = new Intl.NumberFormat(locale, {
          style: 'currency',
          currency,
          currencyDisplay: 'narrowSymbol',
          notation: 'compact',
          maximumFractionDigits: 1,
        });
        format = (value) => formatter.format(value);
      } catch {
        // An unknown currency code: plain numbers; the totals still name it.
      }
    }
    return (this.model()?.revenueTicks ?? []).map((t) => ({ y: t.y, label: format(t.value) }));
  });
  readonly axisLabels = computed(() =>
    (this.model()?.columns ?? [])
      .filter((c) => c.labelled)
      .map((c) => ({ x: c.center, text: formatDate(c.date, 'MMM d', this.language.locale()) })),
  );
  readonly summaryLabel = computed(() => {
    const sales = this.sales();
    if (!sales) return '';
    const locale = this.language.locale();
    return this.language.t('dashboard.sales.chartSummary', {
      from: formatDate(sales.start, 'MMM d', locale),
      to: formatDate(sales.end, 'MMM d', locale),
    });
  });
  readonly tableRows = computed(() => {
    const sales = this.sales();
    if (!sales) return [];
    const byCurrency = sales.revenue.map(
      (series) => new Map(series.days.map((d) => [d.date, d.net_revenue])),
    );
    return sales.days.map((day) => ({
      date: day.date,
      tickets: day.tickets,
      revenue: byCurrency.map((map) => map.get(day.date) ?? '0'),
      published: sales.markers
        .filter((m) => m.date === day.date)
        .map((m) => m.title)
        .join(', '),
    }));
  });

  constructor() {
    this.requests$
      .pipe(
        switchMap((range) =>
          this.service.getSales(range).pipe(
            map((sales) => ({ sales })),
            catchError((err: unknown) =>
              of({
                message: errorMessage(err, this.language, {
                  fallback: this.language.t('dashboard.sales.loadFailed'),
                }),
              }),
            ),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        if ('sales' in result) {
          this.sales.set(result.sales);
          this.status.set('ready');
        } else {
          this.error.set(result.message);
          this.status.set('error');
        }
      });

    // A new range cancels the request in flight (switchMap), so a slow old
    // answer never overwrites the newer one.
    effect(() => {
      const range = this.range();
      untracked(() => {
        this.load(range);
      });
    });
  }

  private load(range: SalesRange): void {
    this.status.set('loading');
    this.active.set(null);
    this.requests$.next(range);
  }

  retry(): void {
    this.load(this.range());
  }

  chooseRange(value: string): void {
    const range = SALES_RANGES.find((r) => r === value);
    if (range && range !== this.range()) this.rangeChange.emit(range);
  }

  setActive(index: number): void {
    this.active.set(index);
  }

  onFocus(): void {
    this.focused.set(true);
    // Tabbing in starts at the latest day.
    if (this.active() === null) {
      const count = this.model()?.columns.length ?? 0;
      if (count > 0) this.active.set(count - 1);
    }
  }

  onBlur(): void {
    this.focused.set(false);
    this.active.set(null);
  }

  onLeave(): void {
    if (!this.focused()) this.active.set(null);
  }

  onKeydown(event: KeyboardEvent): void {
    const count = this.model()?.columns.length ?? 0;
    if (count === 0) return;
    const current = this.active();
    let next: number;
    switch (event.key) {
      case 'ArrowRight':
        next = current === null ? 0 : Math.min(count - 1, current + 1);
        break;
      case 'ArrowLeft':
        next = current === null ? count - 1 : Math.max(0, current - 1);
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = count - 1;
        break;
      case 'Escape':
        this.active.set(null);
        return;
      default:
        return;
    }
    event.preventDefault();
    this.active.set(next);
    this.reveal(next);
  }

  /** Scrolls the chart (not the page) so the day the keyboard moved to is in view. */
  private reveal(index: number): void {
    const el = this.scroller()?.nativeElement;
    const model = this.model();
    if (!el || !model || !el.scrollWidth) return;
    const scale = el.scrollWidth / model.width;
    const left = (CHART_LEFT + index * model.step) * scale;
    const right = left + model.step * scale;
    if (left < el.scrollLeft) el.scrollLeft = Math.max(0, left - 4);
    else if (right > el.scrollLeft + el.clientWidth) el.scrollLeft = right - el.clientWidth + 4;
  }
}
