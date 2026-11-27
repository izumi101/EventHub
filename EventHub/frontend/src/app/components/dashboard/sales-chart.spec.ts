import {
  buildChartModel,
  columnStep,
  isEmptySales,
  niceScale,
  revenueTotals,
  totalTickets,
} from './sales-chart';
import { dates, emptySales, revenueSeries, salesChart } from './dashboard.testing';

describe('niceScale', () => {
  it('starts at zero and ends on a round number above the data', () => {
    expect(niceScale(0, 7, true)).toEqual({ lo: 0, hi: 10, ticks: [0, 5, 10] });
    expect(niceScale(0, 120000)).toEqual({ lo: 0, hi: 150000, ticks: [0, 50000, 100000, 150000] });
  });

  it('keeps tickets whole: one ticket gives the ticks 0 and 1, never 0.5', () => {
    expect(niceScale(0, 1, true).ticks).toEqual([0, 1]);
    expect(niceScale(0, 0, true).ticks).toEqual([0, 1]);
  });

  it('reaches below zero only for negative values', () => {
    const scale = niceScale(-5000, 60000);
    expect(scale.lo).toBe(-50000);
    expect(scale.hi).toBe(100000);
    expect(scale.ticks).toContain(0);
    expect(niceScale(0, 10).lo).toBe(0);
  });

  it('copes with cents without floating point noise in the ticks', () => {
    const { ticks } = niceScale(0, 0.3);
    expect(ticks).toEqual([0, 0.1, 0.2, 0.3]);
  });
});

describe('columnStep', () => {
  it('narrows the columns as the range grows', () => {
    expect(columnStep(7)).toBe(40);
    expect(columnStep(30)).toBe(20);
    expect(columnStep(90)).toBe(7);
  });
});

describe('buildChartModel', () => {
  it('draws one column per day, as wide as the range needs', () => {
    const model = buildChartModel(salesChart(), 'KZT');
    expect(model.columns).toHaveLength(7);
    expect(model.step).toBe(40);
    expect(model.width).toBe(64 + 7 * 40 + 10);
    expect(model.columns.map((c) => c.tickets)).toEqual([0, 2, 0, 5, 1, 0, 4]);
  });

  it('scales bar heights to the values and draws nothing for a zero day', () => {
    const model = buildChartModel(salesChart(), 'KZT');
    const heights = model.columns.map((c) => c.ticketsBar?.height ?? 0);
    expect(heights[0]).toBe(0);
    expect(heights[2]).toBe(0);
    expect(heights[3] / heights[1]).toBeCloseTo(2.5);
    // Every bar stands on the axis and stays inside the panel.
    for (const column of model.columns) {
      if (column.ticketsBar) {
        expect(column.ticketsBar.y + column.ticketsBar.height).toBeCloseTo(model.ticketsBottom);
        expect(column.ticketsBar.y).toBeGreaterThanOrEqual(24);
      }
    }
    const revenue = model.columns.map((c) => c.revenueBar?.height ?? 0);
    expect(revenue[3] / revenue[1]).toBeCloseTo(2.5);
  });

  it('keeps a one-ticket day visible next to a big one', () => {
    const sales = salesChart({
      days: dates('2026-11-15', 7).map((date, i) => ({ date, tickets: i === 0 ? 1 : 500 })),
    });
    const model = buildChartModel(sales, 'KZT');
    expect(model.columns[0].ticketsBar!.height).toBeGreaterThanOrEqual(2);
  });

  it('draws refunds above sales as a bar below the zero line', () => {
    const sales = salesChart({
      revenue: [revenueSeries('KZT', '2026-11-15', [0, 20000, -10000, 0, 0, 0, 0])],
    });
    const model = buildChartModel(sales, 'KZT');
    const [, sale, refund] = model.columns;
    expect(model.hasNegativeRevenue).toBe(true);
    expect(sale.revenueBar!.negative).toBe(false);
    expect(sale.revenueBar!.y + sale.revenueBar!.height).toBeCloseTo(model.revenueZeroY);
    expect(refund.revenueBar!.negative).toBe(true);
    expect(refund.revenueBar!.y).toBeCloseTo(model.revenueZeroY);
    expect(model.revenueZeroY).toBeLessThan(model.revenueBottom);
    expect(model.revenueTicks.map((t) => t.value)).toContain(0);
  });

  it('draws only the chosen currency, and no revenue panel for one that is not there', () => {
    const sales = salesChart({
      revenue: [
        revenueSeries('KZT', '2026-11-15', [0, 20000, 0, 50000, 10000, 0, 40000]),
        revenueSeries('USD', '2026-11-15', [0, 0, 0, 0, 30, 0, 0]),
      ],
    });
    const usd = buildChartModel(sales, 'USD');
    expect(usd.hasRevenue).toBe(true);
    expect(usd.columns.map((c) => c.revenue)).toEqual([0, 0, 0, 0, 30, 0, 0]);
    expect(usd.columns.filter((c) => c.revenueBar)).toHaveLength(1);

    const none = buildChartModel(sales, null);
    expect(none.hasRevenue).toBe(false);
    expect(none.revenueTicks).toEqual([]);
    expect(none.columns.every((c) => c.revenueBar === null && c.revenue === null)).toBe(true);
    expect(none.height).toBeLessThan(usd.height);
  });

  it('labels every other day of a week and every third day of a month, counting back from the last', () => {
    const week = buildChartModel(salesChart(), 'KZT');
    expect(week.columns.filter((c) => c.labelled).map((c) => c.index)).toEqual([0, 2, 4, 6]);

    const month = buildChartModel(emptySales(30), null);
    const labelled = month.columns.filter((c) => c.labelled).map((c) => c.index);
    expect(labelled[labelled.length - 1]).toBe(29);
    expect(labelled).toHaveLength(10);
    expect(labelled[1] - labelled[0]).toBe(3);
  });

  it('keeps the date labels of a quarter at least 44 units apart', () => {
    const model = buildChartModel(emptySales(90), null);
    const labelled = model.columns.filter((c) => c.labelled);
    expect(labelled[labelled.length - 1].index).toBe(89);
    for (let i = 1; i < labelled.length; i++) {
      expect(labelled[i].center - labelled[i - 1].center).toBeGreaterThanOrEqual(44);
    }
  });

  describe('markers', () => {
    const published = (date: string, title: string, event_id = 1) => ({
      date,
      event_id,
      title,
      kind: 'published' as const,
    });

    it('draws a vertical line at the day an event was published', () => {
      const sales = salesChart({ markers: [published('2026-11-17', 'Stand-up Almaty')] });
      const model = buildChartModel(sales, 'KZT');
      const column = model.columns[2];
      expect(column.markers.map((m) => m.title)).toEqual(['Stand-up Almaty']);
      expect(model.markerLines).toEqual([
        { x: column.center, date: '2026-11-17', titles: ['Stand-up Almaty'] },
      ]);
    });

    it('puts several events of one day on one line, and ignores a day outside the range', () => {
      const sales = salesChart({
        markers: [
          published('2026-11-17', 'A', 1),
          published('2026-11-17', 'B', 2),
          published('2026-10-01', 'Old', 3),
        ],
      });
      const model = buildChartModel(sales, 'KZT');
      expect(model.markerLines).toHaveLength(1);
      expect(model.markerLines[0].titles).toEqual(['A', 'B']);
    });

    it('draws nothing when there are no markers', () => {
      expect(buildChartModel(salesChart(), 'KZT').markerLines).toEqual([]);
    });
  });
});

describe('range totals', () => {
  it('sums tickets over the range', () => {
    expect(totalTickets(salesChart())).toBe(12);
  });

  it('sums each currency on its own, exact to the cent', () => {
    const sales = salesChart({
      revenue: [
        revenueSeries('KZT', '2026-11-15', [0.1, 0.2, 0, 0, 0, 0, 0]),
        revenueSeries('USD', '2026-11-15', [10, -2.5, 0, 0, 0, 0, 0]),
      ],
    });
    expect(revenueTotals(sales)).toEqual([
      { currency: 'KZT', total: '0.30' },
      { currency: 'USD', total: '7.50' },
    ]);
  });
});

describe('isEmptySales', () => {
  it('is true only when nothing was sold and no money moved', () => {
    expect(isEmptySales(emptySales(30))).toBe(true);
    expect(isEmptySales(salesChart())).toBe(false);
    // Free tickets: sales without money.
    expect(isEmptySales({ ...salesChart(), revenue: [] })).toBe(false);
    // Refunds of earlier sales: money without tickets.
    const refundsOnly = {
      ...emptySales(7),
      revenue: [revenueSeries('KZT', '2026-10-23', [0, -5000, 0, 0, 0, 0, 0])],
    };
    expect(isEmptySales(refundsOnly)).toBe(false);
  });
});
