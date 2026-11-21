import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { I18nTestingModule } from '../../i18n/testing';
import type { DashboardSummary } from '../../services/organizer-dashboard.service';
import {
  DashboardSummaryComponent,
  salesTrend,
  type SectionStatus,
} from './dashboard-summary.component';
import { summary } from './dashboard.testing';

function render(value: DashboardSummary | null, status: SectionStatus = 'ready') {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, DashboardSummaryComponent],
    providers: [provideRouter([])],
  });
  const fixture = TestBed.createComponent(DashboardSummaryComponent);
  fixture.componentRef.setInput('summary', value);
  fixture.componentRef.setInput('status', status);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const text = (testId: string) =>
    el.querySelector(`[data-testid="${testId}"]`)?.textContent.replace(/\s+/g, ' ').trim() ?? null;
  return { fixture, el, text };
}

describe('salesTrend', () => {
  it.each([
    [6, 3, { direction: 'up', delta: 3, percent: 100 }],
    [2, 8, { direction: 'down', delta: -6, percent: 75 }],
    [4, 4, { direction: 'flat', delta: 0, percent: null }],
    [5, 0, { direction: 'up', delta: 5, percent: null }],
    [0, 5, { direction: 'down', delta: -5, percent: 100 }],
    [0, 0, null],
  ])('%i now vs %i before', (last, previous, expected) => {
    expect(salesTrend(last, previous)).toEqual(expected);
  });
});

describe('DashboardSummaryComponent', () => {
  it('shows an up arrow, "+N" and the percent when sales grew', () => {
    const { el, text } = render(summary({ sales_last_7_days: 6, sales_previous_7_days: 3 }));
    expect(text('kpi-sales')).toBe('6');
    expect(text('sales-trend')).toContain('+3');
    expect(text('sales-trend')).toContain('(+100%)');
    expect(el.querySelector('[data-testid="sales-trend"]')?.getAttribute('data-direction')).toBe(
      'up',
    );
    expect(el.querySelector('[data-testid="sales-trend"] lucide-icon')).not.toBeNull();
  });

  it('shows a down arrow and "−N" (a real minus sign) when sales fell', () => {
    const { el, text } = render(summary({ sales_last_7_days: 2, sales_previous_7_days: 8 }));
    expect(text('sales-trend')).toContain('−6');
    expect(text('sales-trend')).toContain('(−75%)');
    expect(el.querySelector('[data-testid="sales-trend"]')?.getAttribute('data-direction')).toBe(
      'down',
    );
  });

  it('shows a neutral "0" without arrow or percent when both weeks are equal and not zero', () => {
    const { el, text } = render(summary({ sales_last_7_days: 4, sales_previous_7_days: 4 }));
    const trend = el.querySelector('[data-testid="sales-trend"]')!;
    expect(trend.getAttribute('data-direction')).toBe('flat');
    expect(trend.querySelector('lucide-icon')).toBeNull();
    expect(trend.querySelector('span[aria-hidden="true"]')!.textContent.trim()).toBe('0');
    expect(text('sales-trend')).not.toContain('%');
  });

  it('shows no trend at all when both weeks are zero', () => {
    const { el } = render(summary({ sales_last_7_days: 0, sales_previous_7_days: 0 }));
    expect(el.querySelector('[data-testid="sales-trend"]')).toBeNull();
  });

  it('shows the change but no percent when there was nothing to compare with', () => {
    const { text } = render(summary({ sales_last_7_days: 5, sales_previous_7_days: 0 }));
    expect(text('sales-trend')).toContain('+5');
    expect(text('sales-trend')).not.toContain('%');
  });

  it('announces the trend in words to screen readers', () => {
    const { el } = render(summary({ sales_last_7_days: 6, sales_previous_7_days: 3 }));
    expect(el.querySelector('[data-testid="sales-trend"] .sr-only')?.textContent).toContain(
      'Up 3 compared with the previous 7 days',
    );
  });

  it('counts events as the sum of the tab counts, whatever tab is open', () => {
    const { text } = render(summary({ tabs: { upcoming: 15, past: 2, drafts: 1, inactive: 4 } }));
    expect(text('kpi-events')).toBe('22');
  });

  it('shows the check-in rate and totals from the summary', () => {
    const { text } = render(
      summary({ tickets_sold: 1234, checkin_rate_pct: 33.3, checked_in: 411 }),
    );
    expect(text('kpi-tickets')).toMatch(/^1[,\s]?234$/);
    expect(text('kpi-checkin')).toBe('33.3%');
  });

  it('shows one revenue line per currency and never adds them together', () => {
    const { el } = render(
      summary({
        revenue: [
          { currency: 'KZT', net_revenue: '124000.00' },
          { currency: 'USD', net_revenue: '350.50' },
        ],
      }),
    );
    const lines = Array.from(el.querySelectorAll('[data-testid="kpi-revenue"]')).map((e) =>
      e.textContent.replace(/\s+/g, ' ').trim(),
    );
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatch(/KZT\s*124[,\s]?000/);
    expect(lines[1]).toContain('$350.50');
  });

  it('shows a dash when there is no revenue', () => {
    const { text } = render(summary({ revenue: [] }));
    expect(text('kpi-revenue')).toBe('—');
  });

  it('shows the two callouts as links that open the upcoming tab, only when above zero', () => {
    const { el } = render(summary({ upcoming_next_7_days: 4, pending_approval: 1 }));
    const soon = el.querySelector<HTMLAnchorElement>('[data-testid="callout-soon"]')!;
    const approval = el.querySelector<HTMLAnchorElement>('[data-testid="callout-approval"]')!;
    expect(soon.textContent.trim()).toBe('4 events in the next 7 days');
    expect(approval.textContent.trim()).toBe('1 event awaiting approval');
    for (const link of [soon, approval]) {
      expect(link.getAttribute('href')).toContain('tab=upcoming');
    }
  });

  it('hides a callout that is zero, and the whole row when both are', () => {
    const one = render(summary({ upcoming_next_7_days: 0, pending_approval: 2 }));
    expect(one.el.querySelector('[data-testid="callout-soon"]')).toBeNull();
    expect(one.el.querySelector('[data-testid="callout-approval"]')).not.toBeNull();
    const none = render(summary({ upcoming_next_7_days: 0, pending_approval: 0 }));
    expect(none.el.querySelector('[data-testid="callouts"]')).toBeNull();
  });

  it('says it could not load, with a Retry button, and keeps no numbers', () => {
    const { fixture, el } = render(null, 'error');
    let retried = 0;
    fixture.componentInstance.retry.subscribe(() => retried++);
    expect(el.querySelector('[data-testid="summary-error"]')?.textContent).toContain(
      'Could not load your totals.',
    );
    el.querySelector<HTMLButtonElement>('[data-testid="summary-error"] button')!.click();
    expect(retried).toBe(1);
    expect(el.querySelector('[data-testid="kpi-events"]')).toBeNull();
  });

  it('shows a loading skeleton while loading', () => {
    const { el } = render(null, 'loading');
    expect(el.querySelector('[role="status"]')).not.toBeNull();
    expect(el.querySelector('[data-testid="kpi-events"]')).toBeNull();
  });
});
