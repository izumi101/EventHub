import type {
  SalesChart,
  SalesMarker,
  SalesRevenueSeries,
} from '../../services/organizer-dashboard.service';

/**
 * Geometry of the sales chart (an inline SVG, drawn without a chart library).
 * Everything here is a pure function of the API payload: the component only
 * formats labels and handles the pointer and the keyboard.
 *
 * Two panels share the x axis: tickets per day, and net revenue per day in one
 * currency. Both are bars from their own zero line, so a day on which refunds
 * exceed sales draws a bar below it. Currencies are never added together.
 */
export const CHART_LEFT = 64;
export const CHART_RIGHT = 10;
export const PLOT_HEIGHT = 84;
export const TICKETS_TOP = 24;
/** Space between the two panels (revenue title included). */
const PANEL_GAP = 38;
/** Space for the date labels under the last panel. */
const AXIS_SPACE = 22;
/** Minimum distance, in chart units, between two date labels. */
const LABEL_SPACING = 44;

export interface ChartTick {
  value: number;
  y: number;
}

export interface ChartBar {
  x: number;
  y: number;
  width: number;
  height: number;
  /** Revenue below the zero line (refunds exceeded sales). */
  negative: boolean;
}

export interface ChartMarkerLine {
  x: number;
  date: string;
  titles: string[];
}

export interface ChartColumn {
  index: number;
  date: string;
  tickets: number;
  /** Net revenue of the selected currency; null when no currency is drawn. */
  revenue: number | null;
  /** Left edge of the day's slot, and its middle. */
  x: number;
  center: number;
  ticketsBar: ChartBar | null;
  revenueBar: ChartBar | null;
  markers: SalesMarker[];
  /** Whether the date label under this day is drawn (the others are decimated). */
  labelled: boolean;
}

export interface ChartModel {
  width: number;
  height: number;
  step: number;
  columns: ChartColumn[];
  ticketTicks: ChartTick[];
  revenueTicks: ChartTick[];
  hasRevenue: boolean;
  ticketsBottom: number;
  revenueTitleY: number;
  revenueTop: number;
  revenueBottom: number;
  revenueZeroY: number;
  hasNegativeRevenue: boolean;
  axisY: number;
  markerLines: ChartMarkerLine[];
}

export interface NiceScale {
  lo: number;
  hi: number;
  ticks: number[];
}

/** 1, 2, 5 times a power of ten, at or above `raw`. */
function niceStep(raw: number): number {
  if (!(raw > 0) || !Number.isFinite(raw)) return 1;
  const base = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / base;
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return nice * base;
}

const clean = (value: number): number => Number(value.toFixed(10));

/**
 * Axis range with round tick values. It always contains 0 (a bar starts at
 * zero), reaches below it only for negative values, and `integer` keeps
 * the ticks whole numbers (tickets cannot be fractional).
 */
export function niceScale(min: number, max: number, integer = false, intervals = 3): NiceScale {
  const low = Math.min(0, min);
  const high = Math.max(0, max);
  const span = high - low || 1;
  let step = niceStep(span / intervals);
  if (integer) step = Math.max(1, step);
  const lo = clean(Math.floor(low / step) * step);
  let hi = clean(Math.ceil(high / step) * step);
  if (hi === lo) hi = clean(lo + step);
  const ticks: number[] = [];
  for (let value = lo; value <= hi + step / 1000; value = clean(value + step)) {
    ticks.push(value);
  }
  return { lo, hi, ticks };
}

/** Column width: wide for a week, narrow for a quarter. */
export function columnStep(days: number): number {
  if (days <= 8) return 40;
  if (days <= 31) return 20;
  return 7;
}

/** Net revenue per date of one currency's series (missing dates are 0). */
function revenueByDate(series: SalesRevenueSeries | undefined): Map<string, number> {
  const out = new Map<string, number>();
  for (const day of series?.days ?? []) out.set(day.date, Number(day.net_revenue) || 0);
  return out;
}

export function buildChartModel(sales: SalesChart, currency: string | null): ChartModel {
  const days = sales.days;
  const step = columnStep(days.length);
  const gap = step >= 20 ? 6 : step >= 10 ? 3 : 2;
  const barWidth = Math.max(2, step - gap);
  const width = CHART_LEFT + days.length * step + CHART_RIGHT;

  const series = sales.revenue.find((s) => s.currency === currency);
  const hasRevenue = series !== undefined;
  const revenue = revenueByDate(series);

  const ticketsBottom = TICKETS_TOP + PLOT_HEIGHT;
  const revenueTitleY = ticketsBottom + PANEL_GAP - 12;
  const revenueTop = ticketsBottom + PANEL_GAP;
  const revenueBottom = revenueTop + PLOT_HEIGHT;
  const axisY = (hasRevenue ? revenueBottom : ticketsBottom) + AXIS_SPACE - 6;
  const height = axisY + 8;

  const ticketScale = niceScale(0, Math.max(0, ...days.map((d) => d.tickets)), true);
  const ticketY = (value: number): number =>
    ticketsBottom - ((value - ticketScale.lo) / (ticketScale.hi - ticketScale.lo)) * PLOT_HEIGHT;

  const values = days.map((d) => revenue.get(d.date) ?? 0);
  const revenueScale = niceScale(Math.min(0, ...values), Math.max(0, ...values));
  const revenueY = (value: number): number =>
    revenueBottom - ((value - revenueScale.lo) / (revenueScale.hi - revenueScale.lo)) * PLOT_HEIGHT;
  const revenueZeroY = revenueY(0);

  const every = Math.max(1, Math.ceil(LABEL_SPACING / step));
  const markersByDate = new Map<string, SalesMarker[]>();
  for (const marker of sales.markers) {
    markersByDate.set(marker.date, [...(markersByDate.get(marker.date) ?? []), marker]);
  }

  const columns: ChartColumn[] = days.map((day, index) => {
    const x = CHART_LEFT + index * step;
    const barX = x + (step - barWidth) / 2;
    let ticketsBar: ChartBar | null = null;
    if (day.tickets > 0) {
      const top = ticketY(day.tickets);
      const barHeight = Math.max(2, ticketsBottom - top);
      ticketsBar = {
        x: barX,
        y: ticketsBottom - barHeight,
        width: barWidth,
        height: barHeight,
        negative: false,
      };
    }
    const value = hasRevenue ? values[index] : null;
    let revenueBar: ChartBar | null = null;
    if (value !== null && value !== 0) {
      const top = revenueY(value);
      const negative = value < 0;
      const barHeight = Math.max(2, Math.abs(top - revenueZeroY));
      revenueBar = {
        x: barX,
        y: negative ? revenueZeroY : revenueZeroY - barHeight,
        width: barWidth,
        height: barHeight,
        negative,
      };
    }
    return {
      index,
      date: day.date,
      tickets: day.tickets,
      revenue: value,
      x,
      center: x + step / 2,
      ticketsBar,
      revenueBar,
      markers: markersByDate.get(day.date) ?? [],
      // Counted from the last day, so "today" always has its label.
      labelled: (days.length - 1 - index) % every === 0,
    };
  });

  return {
    width,
    height,
    step,
    columns,
    ticketTicks: ticketScale.ticks.map((value) => ({ value, y: ticketY(value) })),
    revenueTicks: hasRevenue
      ? revenueScale.ticks.map((value) => ({ value, y: revenueY(value) }))
      : [],
    hasRevenue,
    ticketsBottom,
    revenueTitleY,
    revenueTop,
    revenueBottom,
    revenueZeroY,
    hasNegativeRevenue: values.some((v) => v < 0),
    axisY,
    markerLines: columns
      .filter((c) => c.markers.length > 0)
      .map((c) => ({ x: c.center, date: c.date, titles: c.markers.map((m) => m.title) })),
  };
}

/** Tickets sold over the range. */
export function totalTickets(sales: SalesChart): number {
  return sales.days.reduce((sum, day) => sum + day.tickets, 0);
}

/** Net revenue over the range, one entry per currency, exact to the cent. */
export function revenueTotals(sales: SalesChart): { currency: string; total: string }[] {
  return sales.revenue.map((series) => {
    const cents = series.days.reduce(
      (sum, day) => sum + Math.round(Number(day.net_revenue) * 100),
      0,
    );
    return { currency: series.currency, total: (cents / 100).toFixed(2) };
  });
}

/** Nothing to draw: no ticket and no money movement in the whole range. */
export function isEmptySales(sales: SalesChart): boolean {
  return (
    totalTickets(sales) === 0 &&
    sales.revenue.every((series) => series.days.every((day) => Number(day.net_revenue) === 0))
  );
}
