import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { environment } from '../../../environments/environment';
import { LanguageService } from '../../i18n/language.service';
import { I18nTestingModule } from '../../i18n/testing';
import type { SalesChart, SalesRange } from '../../services/organizer-dashboard.service';
import { DashboardSalesComponent } from './dashboard-sales.component';
import { emptySales, revenueSeries, salesChart } from './dashboard.testing';

const URL = `${environment.apiUrl}/organizer/sales/`;

function setup(range: SalesRange = '30d') {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, DashboardSalesComponent],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  const http = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(DashboardSalesComponent);
  fixture.componentRef.setInput('range', range);
  const chosen: SalesRange[] = [];
  fixture.componentInstance.rangeChange.subscribe((r) => chosen.push(r));
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const q = (testId: string) => el.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
  const all = (testId: string) =>
    Array.from(el.querySelectorAll<SVGElement | HTMLElement>(`[data-testid="${testId}"]`));
  const text = (testId: string) => q(testId)?.textContent.replace(/\s+/g, ' ').trim() ?? null;
  const request = () => http.expectOne((r) => r.url === URL);
  const answer = (sales: SalesChart) => {
    request().flush(sales);
    fixture.detectChanges();
  };
  const radio = (label: string) =>
    Array.from(el.querySelectorAll<HTMLButtonElement>('[role="radio"]')).find(
      (r) => r.textContent.trim() === label,
    )!;
  const scroller = () => q('chart-scroll')!;
  const key = (name: string, times = 1) => {
    for (let i = 0; i < times; i++) {
      scroller().dispatchEvent(
        new KeyboardEvent('keydown', { key: name, bubbles: true, cancelable: true }),
      );
    }
    fixture.detectChanges();
  };
  const focus = () => {
    scroller().dispatchEvent(new Event('focus'));
    fixture.detectChanges();
  };
  return {
    http,
    fixture,
    el,
    q,
    all,
    text,
    request,
    answer,
    radio,
    chosen,
    scroller,
    key,
    focus,
  };
}

const twoCurrencies = () =>
  salesChart({
    revenue: [
      revenueSeries('KZT', '2026-11-15', [0, 20000, 0, 50000, 10000, 0, 40000]),
      revenueSeries('USD', '2026-11-15', [0, 0, 0, 0, 30, 0, 0]),
    ],
  });

describe('DashboardSalesComponent', () => {
  describe('loading', () => {
    it('asks for the chosen range and shows a skeleton until the answer', () => {
      const { q, request, fixture } = setup('90d');
      expect(q('chart-loading')).not.toBeNull();
      expect(q('chart')).toBeNull();
      const req = request();
      expect(req.request.params.get('range')).toBe('90d');
      req.flush(salesChart());
      fixture.detectChanges();
      expect(q('chart-loading')).toBeNull();
      expect(q('chart')).not.toBeNull();
    });

    it('moves the skeleton and its pulse out of the way of reduced motion', () => {
      const { q } = setup();
      expect(q('chart-loading')!.innerHTML).toContain('motion-reduce:animate-none');
    });
  });

  describe('range toggle', () => {
    it('is a radio group of 7, 30 and 90 days with the current range checked', () => {
      const { el, radio, answer } = setup('30d');
      answer(salesChart());
      const group = el.querySelector('[role="radiogroup"]')!;
      expect(group.getAttribute('aria-label')).toBe('Time range');
      expect(radio('7 days').getAttribute('aria-checked')).toBe('false');
      expect(radio('30 days').getAttribute('aria-checked')).toBe('true');
      expect(radio('90 days').getAttribute('aria-checked')).toBe('false');
    });

    it('reports a choice, and does not draw it until the page puts it in the URL', () => {
      const { radio, answer, chosen, http } = setup('30d');
      answer(salesChart());
      radio('7 days').click();
      expect(chosen).toEqual(['7d']);
      http.expectNone((r) => r.url === URL);
    });

    it('ignores a click on the range that is already chosen', () => {
      const { radio, answer, chosen } = setup('30d');
      answer(salesChart());
      radio('30 days').click();
      expect(chosen).toEqual([]);
    });

    it('asks again with the new range, and drops the request still in flight', () => {
      const { fixture, http, request, q } = setup('30d');
      const first = request();
      fixture.componentRef.setInput('range', '7d');
      fixture.detectChanges();
      expect(first.cancelled).toBe(true);
      expect(q('chart-loading')).not.toBeNull();
      const second = http.expectOne((r) => r.url === URL);
      expect(second.request.params.get('range')).toBe('7d');
      second.flush(salesChart());
      fixture.detectChanges();
      expect(q('chart')).not.toBeNull();
    });

    it('can be used while the chart loads or failed', () => {
      const { q, radio, chosen, request, fixture } = setup('30d');
      expect(q('chart-loading')).not.toBeNull();
      radio('90 days').click();
      expect(chosen).toEqual(['90d']);
      request().flush({}, { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();
      expect(q('chart-error')).not.toBeNull();
      radio('7 days').click();
      expect(chosen).toEqual(['90d', '7d']);
    });
  });

  describe('totals', () => {
    it('shows tickets and the revenue of the range, from the zero-filled days', () => {
      const { text, answer } = setup();
      answer(salesChart());
      expect(text('chart-total-tickets')).toBe('12');
      expect(text('chart-total-revenue')).toMatch(/120[,\s]000\.00/);
      expect(text('chart-period')).toBe('Nov 15 – Nov 21');
    });

    it('shows one revenue line per currency and never adds them up', () => {
      const { all, answer } = setup();
      answer(twoCurrencies());
      const lines = all('chart-total-revenue').map((l) =>
        l.textContent.replace(/\s+/g, ' ').trim(),
      );
      expect(lines).toHaveLength(2);
      expect(lines[0]).toMatch(/KZT.*120[,\s]000\.00/);
      expect(lines[1]).toMatch(/\$30\.00|USD.*30\.00/);
    });

    it('shows a dash when there was no money, only free tickets', () => {
      const { text, answer } = setup();
      answer(salesChart({ revenue: [] }));
      expect(text('chart-total-tickets')).toBe('12');
      expect(text('chart-total-revenue')).toBe('—');
    });
  });

  describe('chart', () => {
    it('draws a ticket bar and a revenue bar for each day with sales', () => {
      const { all, answer } = setup();
      answer(salesChart());
      expect(all('chart-ticket-bar')).toHaveLength(4);
      expect(all('chart-revenue-bar')).toHaveLength(4);
      expect(all('chart-day')).toHaveLength(7);
    });

    it('is one image with a spoken summary, in a scroll container the keyboard can reach', () => {
      const { q, answer } = setup();
      answer(salesChart());
      const svg = q('chart')!;
      expect(svg.getAttribute('role')).toBe('img');
      expect(svg.getAttribute('aria-label')).toBe(
        'Tickets sold and net revenue per day, Nov 15 to Nov 21.',
      );
      const scroller = q('chart-scroll')!;
      expect(scroller.getAttribute('tabindex')).toBe('0');
      expect(scroller.getAttribute('role')).toBe('group');
      expect(document.getElementById('dashboard-sales-hint')!.textContent).toContain('arrow keys');
    });

    it('scrolls inside its container on a narrow screen and never widens the page', () => {
      const { q, answer } = setup();
      answer(salesChart());
      expect(q('chart-scroll')!.classList).toContain('overflow-x-auto');
      expect(q('chart')!.style.minWidth).toBe('354px');
      expect(q('sales-section')!.classList).toContain('min-w-0');
    });

    it('labels the axis with dates in the current locale', async () => {
      const { q, answer, fixture } = setup();
      answer(salesChart());
      const labels = () =>
        Array.from(q('chart')!.querySelectorAll('text')).map((t) => t.textContent.trim());
      expect(labels()).toContain('Nov 21');
      expect(labels()).toContain('Nov 15');

      await TestBed.inject(LanguageService).setLang('ru');
      fixture.detectChanges();
      expect(labels().some((l) => l.includes('нояб'))).toBe(true);
      expect(labels()).not.toContain('Nov 21');
    });

    it('formats the revenue axis as money in the revenue currency', () => {
      const { q, answer } = setup();
      answer(salesChart());
      const labels = Array.from(q('chart')!.querySelectorAll('text')).map((t) =>
        t.textContent.trim(),
      );
      // Compact amounts of the chosen currency: 50K, 100K and so on.
      expect(labels.some((l) => l.includes('K') && /₸|KZT/.test(l))).toBe(true);
    });

    it('has no animation of its own, so reduced motion has nothing to switch off', () => {
      const { q, answer } = setup();
      answer(salesChart());
      expect(q('chart')!.innerHTML).not.toMatch(/animate|transition|<animate/);
    });
  });

  describe("a day's figures", () => {
    it('starts at the latest day when the chart gets the focus', () => {
      const { text, focus, answer } = setup();
      answer(salesChart());
      expect(text('chart-readout')).toContain('Hover, tap or use the arrow keys');
      focus();
      expect(text('chart-readout')).toMatch(
        /^Sat, Nov 21 · 4 tickets · .*40[,\s]000\.00 net revenue$/,
      );
    });

    it('moves with the arrow keys, Home and End, and stops at the ends', () => {
      const { text, focus, key, answer } = setup();
      answer(salesChart());
      focus();
      key('ArrowLeft', 2);
      expect(text('chart-readout')).toContain('Thu, Nov 19 · 1 ticket ·');
      key('Home');
      expect(text('chart-readout')).toContain('Sun, Nov 15 · 0 tickets');
      key('ArrowLeft');
      expect(text('chart-readout')).toContain('Sun, Nov 15');
      key('End');
      expect(text('chart-readout')).toContain('Sat, Nov 21');
      key('ArrowRight');
      expect(text('chart-readout')).toContain('Sat, Nov 21');
    });

    it('marks the day the readout is about, and clears on Escape', () => {
      const { q, focus, key, answer } = setup();
      answer(salesChart());
      expect(q('chart-active')).toBeNull();
      focus();
      expect(q('chart-active')).not.toBeNull();
      key('Escape');
      expect(q('chart-active')).toBeNull();
    });

    it('follows the pointer, and is cleared when it leaves', () => {
      const { q, all, text, fixture, answer } = setup();
      answer(salesChart());
      all('chart-day')[1].dispatchEvent(new MouseEvent('mouseenter'));
      fixture.detectChanges();
      expect(text('chart-readout')).toContain('Mon, Nov 16 · 2 tickets');
      q('chart')!.dispatchEvent(new MouseEvent('mouseleave'));
      fixture.detectChanges();
      expect(text('chart-readout')).toContain('Hover, tap or use the arrow keys');
    });

    it('is announced politely only while the keyboard drives it', () => {
      const { q, focus, answer, scroller, fixture } = setup();
      answer(salesChart());
      expect(q('chart-readout')!.getAttribute('aria-live')).toBe('off');
      focus();
      expect(q('chart-readout')!.getAttribute('aria-live')).toBe('polite');
      scroller().dispatchEvent(new Event('blur'));
      fixture.detectChanges();
      expect(q('chart-readout')!.getAttribute('aria-live')).toBe('off');
    });

    it('uses the plural of the language', async () => {
      const { text, focus, answer, fixture } = setup();
      answer(salesChart());
      await TestBed.inject(LanguageService).setLang('ru');
      fixture.detectChanges();
      focus();
      expect(text('chart-readout')).toContain('4 билета');
    });
  });

  describe('markers', () => {
    const withMarkers = () =>
      salesChart({
        markers: [
          { date: '2026-11-17', event_id: 13, title: 'Stand-up Almaty', kind: 'published' },
        ],
      });

    it('draws a vertical line on the day an event was published', () => {
      const { all, answer } = setup();
      answer(withMarkers());
      const lines = all('chart-marker');
      expect(lines).toHaveLength(1);
      expect(lines[0].getAttribute('data-date')).toBe('2026-11-17');
      expect(lines[0].getAttribute('data-titles')).toBe('Stand-up Almaty');
    });

    it("names the event in the day's figures", () => {
      const { q, focus, key, answer } = setup();
      answer(withMarkers());
      focus();
      expect(q('chart-readout-marker')).toBeNull();
      key('ArrowLeft', 4);
      expect(q('chart-readout-marker')!.textContent.trim()).toBe('Published: Stand-up Almaty');
    });

    it('draws no line, and says nothing about publishing, when there are no markers', () => {
      const { all, el, answer } = setup();
      answer(salesChart());
      expect(all('chart-marker')).toHaveLength(0);
      expect(el.textContent).not.toContain('Published');
    });
  });

  describe('currencies', () => {
    it('offers no switcher for one currency', () => {
      const { q, answer } = setup();
      answer(salesChart());
      expect(q('chart-currency')).toBeNull();
    });

    it('draws the first currency, and switches to another without mixing them', () => {
      const { q, all, radio, text, fixture, answer } = setup();
      answer(twoCurrencies());
      expect(q('chart-currency')).not.toBeNull();
      expect(radio('KZT').getAttribute('aria-checked')).toBe('true');
      expect(all('chart-revenue-bar')).toHaveLength(4);
      expect(q('chart')!.textContent).toContain('Net revenue per day, KZT');

      radio('USD').click();
      fixture.detectChanges();
      expect(radio('USD').getAttribute('aria-checked')).toBe('true');
      expect(all('chart-revenue-bar')).toHaveLength(1);
      expect(q('chart')!.textContent).toContain('Net revenue per day, USD');
      // The totals and the tickets do not change with the currency.
      expect(all('chart-total-revenue')).toHaveLength(2);
      expect(text('chart-total-tickets')).toBe('12');
    });

    it("shows the day's revenue in the chosen currency", () => {
      const { radio, focus, key, text, fixture, answer } = setup();
      answer(twoCurrencies());
      radio('USD').click();
      fixture.detectChanges();
      focus();
      key('ArrowLeft', 2);
      expect(text('chart-readout')).toMatch(/Thu, Nov 19 · 1 ticket · .*30\.00.* net revenue/);
      expect(text('chart-readout')).not.toMatch(/10[,\s]000/);
    });

    it('falls back to the first currency when the chosen one is gone (another range)', () => {
      const { radio, fixture, http, answer } = setup();
      answer(twoCurrencies());
      radio('USD').click();
      fixture.detectChanges();
      fixture.componentRef.setInput('range', '90d');
      fixture.detectChanges();
      http.expectOne((r) => r.url === URL).flush(salesChart());
      fixture.detectChanges();
      expect(fixture.componentInstance.currency()).toBe('KZT');
    });
  });

  describe('table fallback', () => {
    it('is hidden until asked for, then lists every day with its figures and the totals', () => {
      const { q, all, answer, fixture } = setup();
      answer(salesChart());
      const toggle = q('chart-table-toggle') as HTMLButtonElement;
      expect(q('chart-table')).toBeNull();
      expect(toggle.getAttribute('aria-expanded')).toBe('false');
      expect(toggle.textContent.trim()).toBe('Show as table');

      toggle.click();
      fixture.detectChanges();
      expect(toggle.getAttribute('aria-expanded')).toBe('true');
      expect(toggle.getAttribute('aria-controls')).toBe(q('chart-table')!.id);
      expect(toggle.textContent.trim()).toBe('Hide table');
      const rows = all('chart-table-row').map((r) =>
        Array.from(r.querySelectorAll('th, td')).map((c) =>
          c.textContent.replace(/\s+/g, ' ').trim(),
        ),
      );
      expect(rows).toHaveLength(7);
      expect(rows[3][0]).toBe('Wed, Nov 18');
      expect(rows[3][1]).toBe('5');
      expect(rows[3][2]).toMatch(/50[,\s]000\.00/);
      const table = q('chart-table')!;
      expect(table.querySelector('caption')!.textContent.trim()).toBe('Sales by day');
      expect(
        Array.from(table.querySelectorAll('thead th')).map((h) => h.textContent.trim()),
      ).toEqual(['Date', 'Tickets', 'Net revenue, KZT']);
      const footer = Array.from(table.querySelectorAll('tfoot th, tfoot td')).map((c) =>
        c.textContent.replace(/\s+/g, ' ').trim(),
      );
      expect(footer[0]).toBe('Total');
      expect(footer[1]).toBe('12');
      expect(footer[2]).toMatch(/120[,\s]000\.00/);

      toggle.click();
      fixture.detectChanges();
      expect(q('chart-table')).toBeNull();
    });

    it('has a column per currency, and one for the events published', () => {
      const sales = twoCurrencies();
      sales.markers = [
        { date: '2026-11-17', event_id: 13, title: 'Stand-up Almaty', kind: 'published' },
      ];
      const { q, all, answer, fixture } = setup();
      answer(sales);
      (q('chart-table-toggle') as HTMLButtonElement).click();
      fixture.detectChanges();
      const headers = Array.from(q('chart-table')!.querySelectorAll('thead th')).map((h) =>
        h.textContent.trim(),
      );
      expect(headers).toEqual([
        'Date',
        'Tickets',
        'Net revenue, KZT',
        'Net revenue, USD',
        'Published',
      ]);
      const cells = Array.from(all('chart-table-row')[2].querySelectorAll('th, td')).map((c) =>
        c.textContent.replace(/\s+/g, ' ').trim(),
      );
      expect(cells[cells.length - 1]).toBe('Stand-up Almaty');
    });

    it('scrolls inside its own region and can be focused', () => {
      const { q, answer, fixture } = setup();
      answer(salesChart());
      (q('chart-table-toggle') as HTMLButtonElement).click();
      fixture.detectChanges();
      const region = q('chart-table')!;
      expect(region.classList).toContain('overflow-auto');
      expect(region.getAttribute('tabindex')).toBe('0');
      expect(region.getAttribute('role')).toBe('region');
    });
  });

  describe('empty and error states', () => {
    it.each([
      ['7d', 7, 'No sales in the last 7 days'],
      ['30d', 30, 'No sales in the last 30 days'],
      ['90d', 90, 'No sales in the last 90 days'],
    ] as const)('says there were no sales in %s, and draws no chart', (range, days, message) => {
      const { q, text, answer } = setup(range);
      answer(emptySales(days));
      expect(text('chart-empty')).toBe(message);
      expect(q('chart')).toBeNull();
      expect(q('chart-totals')).toBeNull();
      // The toggle stays, so another range can be tried.
      expect(q('chart-range')).not.toBeNull();
    });

    it('shows a retry button on a failed load, and loads again from it', () => {
      const { q, text, request, answer, fixture } = setup();
      request().flush({}, { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();
      expect(q('chart-error')!.getAttribute('role')).toBe('alert');
      expect(text('chart-error')).toContain('Retry');
      q('chart-error')!.querySelector('button')!.click();
      fixture.detectChanges();
      expect(q('chart-loading')).not.toBeNull();
      answer(salesChart());
      expect(q('chart-error')).toBeNull();
      expect(q('chart')).not.toBeNull();
    });
  });
});
