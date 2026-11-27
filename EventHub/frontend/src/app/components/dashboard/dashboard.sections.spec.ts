import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { Router, convertToParamMap, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { environment } from '../../../environments/environment';
import { I18nTestingModule } from '../../i18n/testing';
import { AuthService } from '../../services/auth.service';
import { ModalService } from '../../services/modal.service';
import type {
  ReviewsSummary,
  SalesChart,
  TodayBlock,
} from '../../services/organizer-dashboard.service';
import { DashboardComponent, parseRange, rangeQueryParams } from './dashboard.component';
import {
  emptySales,
  eventPage,
  organizerEvent,
  reviewsSummary,
  salesChart,
  summary as makeSummary,
  todayBlock,
  todayEvent,
} from './dashboard.testing';

const API = environment.apiUrl;
const url = (path: string) => `${API}/organizer/${path}/`;
const organizerUser = {
  id: 1,
  username: 'org',
  is_staff: false,
  is_superuser: false,
  profile: { role: 'organizer' },
};

interface Answers {
  summary?: 'fail' | ReturnType<typeof makeSummary>;
  list?: 'fail' | ReturnType<typeof eventPage>;
  sales?: 'fail' | SalesChart;
  today?: 'fail' | TodayBlock;
  reviews?: 'fail' | ReviewsSummary;
}

async function setup(options: { url?: string; user?: object; answers?: Answers | false } = {}) {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule],
    providers: [
      provideRouter([{ path: 'organizer/dashboard', component: DashboardComponent }]),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: AuthService, useValue: { currentUser: options.user ?? organizerUser } },
      { provide: ModalService, useValue: { open: vi.fn() } },
    ],
  });
  const http = TestBed.inject(HttpTestingController);
  const router = TestBed.inject(Router);
  const harness = await RouterTestingHarness.create();
  await harness.navigateByUrl(options.url ?? '/organizer/dashboard', DashboardComponent);
  const el = harness.routeNativeElement!;
  const q = (testId: string) => el.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
  const text = (testId: string) => q(testId)?.textContent.replace(/\s+/g, ' ').trim() ?? null;
  const settle = async () => {
    harness.detectChanges();
    await harness.fixture.whenStable();
    harness.detectChanges();
  };
  const req = (path: string) => http.expectOne((r) => r.url === url(path));
  const respond = (request: TestRequest, answer: unknown) => {
    if (answer === 'fail') request.flush({}, { status: 500, statusText: 'Server Error' });
    else request.flush(answer as object);
  };
  const ctx = { http, router, harness, el, q, text, settle, req, respond };
  if (options.answers === false) return ctx;
  const a = options.answers ?? {};
  respond(req('dashboard'), a.summary ?? makeSummary());
  respond(req('events'), a.list ?? eventPage([organizerEvent(1)]));
  respond(req('activity'), { results: [], next_cursor: null });
  respond(req('sales'), a.sales ?? salesChart());
  respond(req('today'), a.today ?? todayBlock([]));
  respond(req('reviews'), a.reviews ?? reviewsSummary());
  await settle();
  return ctx;
}

const radio = (el: HTMLElement, label: string) =>
  Array.from(el.querySelectorAll<HTMLButtonElement>('[role="radio"]')).find(
    (r) => r.textContent.trim() === label,
  )!;

describe('URL: sales range', () => {
  it('reads 7d, 30d and 90d, and anything else is the default', () => {
    expect(parseRange(convertToParamMap({ range: '7d' }))).toBe('7d');
    expect(parseRange(convertToParamMap({ range: '90d' }))).toBe('90d');
    expect(parseRange(convertToParamMap({ range: '30d' }))).toBe('30d');
    expect(parseRange(convertToParamMap({}))).toBe('30d');
    expect(parseRange(convertToParamMap({ range: '1y' }))).toBe('30d');
    expect(parseRange(convertToParamMap({ range: '' }))).toBe('30d');
  });

  it('leaves the default out of the URL, like the default tab', () => {
    expect(rangeQueryParams('30d')).toEqual({});
    expect(rangeQueryParams('7d')).toEqual({ range: '7d' });
    expect(rangeQueryParams('90d')).toEqual({ range: '90d' });
  });
});

describe('DashboardComponent: batch A sections', () => {
  describe('sales range', () => {
    it('asks for the default 30 days at first, with nothing in the URL', async () => {
      const ctx = await setup({ answers: false });
      expect(ctx.req('sales').request.params.get('range')).toBe('30d');
      expect(ctx.router.url).toBe('/organizer/dashboard');
    });

    it('puts a chosen range in the request and the URL, and drops it again for 30 days', async () => {
      const { el, http, router, settle, req, respond } = await setup();
      radio(el, '7 days').click();
      await settle();
      expect(router.url).toBe('/organizer/dashboard?range=7d');
      const seven = req('sales');
      expect(seven.request.params.get('range')).toBe('7d');
      respond(seven, salesChart());
      await settle();
      expect(radio(el, '7 days').getAttribute('aria-checked')).toBe('true');

      radio(el, '90 days').click();
      await settle();
      expect(router.url).toBe('/organizer/dashboard?range=90d');
      respond(req('sales'), salesChart());
      await settle();

      radio(el, '30 days').click();
      await settle();
      expect(router.url).toBe('/organizer/dashboard');
      expect(req('sales').request.params.get('range')).toBe('30d');
      // The list was not asked again: only the chart changed.
      http.expectNone((r) => r.url === url('events'));
    });

    it('moves with the arrow keys', async () => {
      const { el, router, settle, req, respond } = await setup();
      radio(el, '30 days').dispatchEvent(
        new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true }),
      );
      await settle();
      expect(router.url).toBe('/organizer/dashboard?range=90d');
      respond(req('sales'), salesChart());
    });

    it.each([
      ['/organizer/dashboard?range=90d', '90d', '90 days'],
      ['/organizer/dashboard?range=7d', '7d', '7 days'],
      ['/organizer/dashboard?range=1y', '30d', '30 days'],
    ])(
      'restores %s on load (reload, back navigation, a shared link)',
      async (start, sent, label) => {
        const ctx = await setup({ url: start, answers: false });
        const sales = ctx.req('sales');
        expect(sales.request.params.get('range')).toBe(sent);
        ctx.respond(sales, salesChart());
        ctx.respond(ctx.req('dashboard'), makeSummary());
        ctx.respond(ctx.req('events'), eventPage([]));
        ctx.respond(ctx.req('activity'), { results: [], next_cursor: null });
        ctx.respond(ctx.req('today'), todayBlock([]));
        ctx.respond(ctx.req('reviews'), reviewsSummary());
        await ctx.settle();
        expect(radio(ctx.el, label).getAttribute('aria-checked')).toBe('true');
      },
    );

    it('survives a change of tab, search and sort, and they survive it', async () => {
      const { el, router, settle, req, respond, q } = await setup({
        url: '/organizer/dashboard?range=7d',
        answers: false,
      });
      respond(req('sales'), salesChart());
      respond(req('dashboard'), makeSummary());
      respond(req('events'), eventPage([organizerEvent(1)]));
      respond(req('activity'), { results: [], next_cursor: null });
      respond(req('today'), todayBlock([]));
      respond(req('reviews'), reviewsSummary());
      await settle();

      const past = Array.from(el.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((t) =>
        t.textContent.trim().startsWith('Past'),
      )!;
      past.click();
      await settle();
      expect(router.url).toBe('/organizer/dashboard?tab=past&range=7d');
      respond(req('events'), eventPage([]));
      await settle();

      radio(el, '90 days').click();
      await settle();
      expect(router.url).toBe('/organizer/dashboard?tab=past&range=90d');
      respond(req('sales'), salesChart());
      await settle();
      expect(q('list-empty')).not.toBeNull();
    });

    it('is kept by the links that lead back to the upcoming list', async () => {
      const { el, settle } = await setup({
        url: '/organizer/dashboard?range=7d',
        answers: false,
      });
      // Answer in any order: every request is pending.
      TestBed.inject(HttpTestingController)
        .match(() => true)
        .forEach((r) => {
          const path = r.request.url.replace(`${API}/organizer/`, '');
          if (path.startsWith('dashboard'))
            r.flush(makeSummary({ upcoming_next_7_days: 2, pending_approval: 1 }));
          else if (path.startsWith('events')) r.flush(eventPage([organizerEvent(1)]));
          else if (path.startsWith('activity')) r.flush({ results: [], next_cursor: null });
          else if (path.startsWith('sales')) r.flush(salesChart());
          else if (path.startsWith('today')) r.flush(todayBlock([todayEvent(1)], 4));
          else r.flush(reviewsSummary());
        });
      await settle();
      for (const id of ['callout-soon', 'callout-approval', 'today-more']) {
        const href = el.querySelector(`[data-testid="${id}"]`)!.getAttribute('href')!;
        expect(href, id).toContain('tab=upcoming');
        expect(href, id).toContain('range=7d');
      }
    });
  });

  describe('sections', () => {
    it('shows the sales chart, the reviews card and the list from their own answers', async () => {
      const { q, text } = await setup();
      expect(q('chart')).not.toBeNull();
      expect(text('chart-total-tickets')).toBe('12');
      expect(q('reviews-average')).not.toBeNull();
      expect(q('dashboard-event')).not.toBeNull();
    });

    it('puts the chart and the reviews right below the totals, above the list', async () => {
      const { q } = await setup();
      const order = (a: HTMLElement, b: HTMLElement) =>
        a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING;
      expect(order(q('summary-kpis')!, q('sales-section')!)).toBeTruthy();
      expect(order(q('sales-section')!, q('dashboard-search')!)).toBeTruthy();
      expect(order(q('reviews')!, q('dashboard-search')!)).toBeTruthy();
    });

    it('puts the today block above the list, below the chart', async () => {
      const { q } = await setup({ answers: { today: todayBlock([todayEvent(5)]) } });
      const after = (a: HTMLElement, b: HTMLElement) =>
        Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
      expect(q('today')).not.toBeNull();
      expect(after(q('sales-section')!, q('today')!)).toBe(true);
      expect(after(q('today')!, q('dashboard-search')!)).toBe(true);
      expect(after(q('today')!, q('dashboard-event')!)).toBe(true);
    });

    it('draws no today block when there is nothing today or this week', async () => {
      const { q, el } = await setup({ answers: { today: todayBlock([]) } });
      expect(q('today')).toBeNull();
      expect(el.textContent).not.toContain('Today & this week');
    });

    it('has the today block even when there are no events in the list at all', async () => {
      const { q } = await setup({
        answers: { list: eventPage([]), today: todayBlock([todayEvent(5)]) },
      });
      expect(q('list-empty')).not.toBeNull();
      expect(q('today')).not.toBeNull();
    });

    it('draws the today block while the list is still loading', async () => {
      const { q, req, respond, settle } = await setup({ answers: false });
      respond(req('today'), todayBlock([todayEvent(5)]));
      await settle();
      expect(q('list-loading')).not.toBeNull();
      expect(q('today')).not.toBeNull();
      expect(q('today-title')!.textContent.trim()).toBe('Today 5');
    });
  });

  describe('a failing section does not take the others down', () => {
    const failing: [keyof Answers, string][] = [
      ['sales', 'chart-error'],
      ['today', 'today-error'],
      ['reviews', 'reviews-error'],
      ['summary', 'summary-error'],
      ['list', 'list-error'],
    ];

    it.each(failing)(
      '%s fails alone: its error and a retry, the rest as usual',
      async (failed, errorId) => {
        // Something to show in each of the others.
        const answers: Answers = failed === 'today' ? {} : { today: todayBlock([todayEvent(5)]) };
        (answers as Record<string, unknown>)[failed] = 'fail';
        const { q, req, respond, settle, http } = await setup({ answers });
        expect(q(errorId), errorId).not.toBeNull();
        const shown: Record<string, string> = {
          sales: 'chart-total-tickets',
          today: 'today',
          reviews: 'reviews-average',
          summary: 'summary-kpis',
          list: 'dashboard-event',
        };
        for (const [section, testId] of Object.entries(shown)) {
          if (section === failed) continue;
          expect(q(testId), `${section} (${testId})`).not.toBeNull();
        }

        // The retry asks for that section again, and only that one.
        q(errorId)!.querySelector('button')!.click();
        await settle();
        const path = {
          sales: 'sales',
          today: 'today',
          reviews: 'reviews',
          summary: 'dashboard',
          list: 'events',
        }[failed];
        const fixtures = {
          sales: salesChart(),
          today: todayBlock([todayEvent(6)]),
          reviews: reviewsSummary(),
          summary: makeSummary(),
          list: eventPage([organizerEvent(1)]),
        };
        respond(req(path), fixtures[failed]);
        await settle();
        expect(q(errorId)).toBeNull();
        http.verify();
      },
    );

    it('keeps the totals, the list and the chart when only the activity feed fails', async () => {
      const ctx = await setup({ answers: false });
      ctx.respond(ctx.req('dashboard'), makeSummary());
      ctx.respond(ctx.req('events'), eventPage([organizerEvent(1)]));
      ctx.respond(ctx.req('activity'), 'fail');
      ctx.respond(ctx.req('sales'), salesChart());
      ctx.respond(ctx.req('today'), todayBlock([]));
      ctx.respond(ctx.req('reviews'), reviewsSummary());
      await ctx.settle();
      expect(ctx.q('activity-error')).not.toBeNull();
      expect(ctx.q('chart')).not.toBeNull();
      expect(ctx.q('reviews-average')).not.toBeNull();
      expect(ctx.q('dashboard-event')).not.toBeNull();
    });

    it('shows the no-sales message for an empty range, not an error', async () => {
      const { q, text } = await setup({ answers: { sales: emptySales(30) } });
      expect(text('chart-empty')).toBe('No sales in the last 30 days');
      expect(q('chart-error')).toBeNull();
    });
  });

  describe('a superuser', () => {
    it('sees the moderation queue, and no sales, today or reviews, and none is requested', async () => {
      const ctx = await setup({
        user: { ...organizerUser, id: 2, username: 'root', is_superuser: true },
        answers: false,
      });
      for (const path of ['sales', 'today', 'reviews', 'dashboard', 'activity']) {
        ctx.http.expectNone((r) => r.url === url(path));
      }
      expect(ctx.q('sales-section')).toBeNull();
      expect(ctx.q('reviews')).toBeNull();
      expect(ctx.q('today')).toBeNull();
      expect(ctx.q('chart-range')).toBeNull();
    });
  });
});
