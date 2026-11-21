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
import { LanguageService } from '../../i18n/language.service';
import { AuthService } from '../../services/auth.service';
import { ModalService } from '../../services/modal.service';
import type {
  DashboardSummary,
  OrganizerEvent,
  OrganizerEventPage,
} from '../../services/organizer-dashboard.service';
import { ToastService } from '../../services/toast.service';
import { DashboardComponent, parseQuery, toQueryParams } from './dashboard.component';
import { eventPage, organizerEvent, summary as makeSummary } from './dashboard.testing';

const API = environment.apiUrl;
const SUMMARY_URL = `${API}/organizer/dashboard/`;
const EVENTS_URL = `${API}/organizer/events/`;
const ACTIVITY_URL = `${API}/organizer/activity/`;

const organizerUser = {
  id: 1,
  username: 'org',
  is_staff: false,
  is_superuser: false,
  profile: { role: 'organizer' },
};
const superUser = { ...organizerUser, id: 2, username: 'root', is_superuser: true };

const events = (from: number, to: number, overrides: Partial<OrganizerEvent> = {}) =>
  Array.from({ length: to - from + 1 }, (_, i) => organizerEvent(from + i, overrides));

interface Options {
  user?: object;
  url?: string;
  summary?: DashboardSummary;
  first?: OrganizerEventPage;
  confirm?: boolean;
  /** false: open the page and answer nothing, for tests that script every response. */
  flush?: boolean;
}

async function setup(options: Options = {}) {
  TestBed.resetTestingModule();
  const modal = { open: vi.fn().mockResolvedValue(options.confirm ?? true) };
  TestBed.configureTestingModule({
    imports: [I18nTestingModule],
    providers: [
      provideRouter([
        { path: 'organizer/dashboard', component: DashboardComponent },
        { path: 'edit-event/:id', children: [] },
      ]),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: AuthService, useValue: { currentUser: options.user ?? organizerUser } },
      { provide: ModalService, useValue: modal },
    ],
  });
  const http = TestBed.inject(HttpTestingController);
  const router = TestBed.inject(Router);
  const toasts = TestBed.inject(ToastService);
  const harness = await RouterTestingHarness.create();
  const cmp = await harness.navigateByUrl(
    options.url ?? '/organizer/dashboard',
    DashboardComponent,
  );
  const el = harness.routeNativeElement!;

  // The element type is the caller's claim, like querySelector<T> itself.
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters
  const q = <T extends HTMLElement = HTMLElement>(testId: string) =>
    el.querySelector<T>(`[data-testid="${testId}"]`);
  const text = (testId: string) => q(testId)?.textContent.replace(/\s+/g, ' ').trim() ?? null;
  const settle = async () => {
    harness.detectChanges();
    await harness.fixture.whenStable();
    harness.detectChanges();
  };
  const cards = () =>
    Array.from(el.querySelectorAll<HTMLElement>('[data-testid="dashboard-event"]'));
  const titles = () => cards().map((c) => c.querySelector('h3')!.textContent.trim());
  const listRequest = () => http.expectOne((r) => r.url === EVENTS_URL);
  const summaryRequest = () => http.expectOne((r) => r.url === SUMMARY_URL);
  const activityRequest = () => http.expectOne((r) => r.url === ACTIVITY_URL);
  const tab = (label: string) =>
    Array.from(el.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((t) =>
      t.textContent.trim().startsWith(label),
    )!;
  const toastMessages = () => toasts.toasts().map((t) => t.message);

  const ctx = {
    cmp,
    http,
    router,
    harness,
    el,
    q,
    text,
    settle,
    cards,
    titles,
    listRequest,
    summaryRequest,
    activityRequest,
    tab,
    toastMessages,
    modal,
  };
  if (options.user === superUser || options.flush === false) return ctx;

  // First load: the three sections each ask for their own data.
  summaryRequest().flush(
    options.summary ?? makeSummary({ upcoming_next_7_days: 4, pending_approval: 1 }),
  );
  listRequest().flush(options.first ?? eventPage(events(1, 20), 23));
  activityRequest().flush({ results: [], next_cursor: null });
  await settle();
  return ctx;
}

const setupPending = (url?: string) => setup({ url, flush: false });

const params = (req: TestRequest) =>
  Object.fromEntries(req.request.params.keys().map((k) => [k, req.request.params.get(k)]));

describe('URL state', () => {
  it('reads tab, search and ordering, with defaults for anything missing or unknown', () => {
    expect(parseQuery(convertToParamMap({}))).toEqual({
      tab: 'upcoming',
      search: '',
      ordering: 'date',
    });
    expect(
      parseQuery(convertToParamMap({ tab: 'past', search: ' jazz ', ordering: '-tickets_sold' })),
    ).toEqual({ tab: 'past', search: 'jazz', ordering: '-tickets_sold' });
    expect(parseQuery(convertToParamMap({ tab: 'nope', ordering: 'x' }))).toEqual({
      tab: 'upcoming',
      search: '',
      ordering: 'date',
    });
    expect(parseQuery(convertToParamMap({ tab: 'drafts' })).ordering).toBe('-date');
  });

  it('writes only what differs from the defaults', () => {
    expect(toQueryParams({ tab: 'upcoming', search: '', ordering: 'date' })).toEqual({});
    expect(toQueryParams({ tab: 'past', search: '', ordering: '-date' })).toEqual({ tab: 'past' });
    expect(toQueryParams({ tab: 'upcoming', search: 'a', ordering: '-date' })).toEqual({
      search: 'a',
      ordering: '-date',
    });
  });
});

describe('DashboardComponent (organizer)', () => {
  describe('first load', () => {
    it('asks the server for page 1 of the upcoming tab, 20 per page, with no ordering or search', async () => {
      const { http } = await setupPending();
      const req = http.expectOne((r) => r.url === EVENTS_URL);
      expect(params(req)).toEqual({ tab: 'upcoming', page: '1', page_size: '20' });
      req.flush(eventPage([]));
    });

    it('shows the totals, the first 20 events and the "N of M" counter', async () => {
      const { text, cards, q } = await setup();
      expect(cards()).toHaveLength(20);
      expect(text('list-counter')).toBe('20 of 23');
      expect(text('live-region')).toBe('Upcoming: showing 20 of 23 events');
      expect(text('kpi-events')).toBe('18');
      expect(q('show-more')).not.toBeNull();
    });

    it('has no calendar view toggle and no placeholder text', async () => {
      const { el } = await setup();
      expect(el.textContent.toLowerCase()).not.toContain('calendar');
      expect(el.textContent.toLowerCase()).not.toContain('coming soon');
    });

    it('shows the tab counts from the summary on every tab', async () => {
      const { tab } = await setup();
      expect(tab('Upcoming').textContent.replace(/\s+/g, ' ').trim()).toBe('Upcoming 15');
      expect(tab('Past').textContent.replace(/\s+/g, ' ').trim()).toBe('Past 2');
      expect(tab('Drafts').textContent.replace(/\s+/g, ' ').trim()).toBe('Drafts 1');
      expect(tab('Inactive').textContent.replace(/\s+/g, ' ').trim()).toBe('Inactive 0');
    });

    it('restores tab, search and ordering from the URL (reload, back navigation)', async () => {
      const ctx = await setupPending(
        '/organizer/dashboard?tab=drafts&search=abc&ordering=-tickets_sold',
      );
      const req = ctx.http.expectOne((r) => r.url === EVENTS_URL);
      expect(params(req)).toEqual({
        tab: 'drafts',
        search: 'abc',
        ordering: '-tickets_sold',
        page: '1',
        page_size: '20',
      });
      req.flush(eventPage([]));
      await ctx.settle();
      expect(ctx.q<HTMLInputElement>('dashboard-search')!.value).toBe('abc');
      expect(ctx.q<HTMLSelectElement>('dashboard-sort')!.value).toBe('-tickets_sold');
      expect(ctx.tab('Drafts').getAttribute('aria-selected')).toBe('true');
    });
  });

  describe('tabs', () => {
    it('switching resets the list, asks for page 1 of that tab and puts it in the URL', async () => {
      const { tab, settle, listRequest, router, cards, q, http, text } = await setup();
      tab('Past').click();
      await settle();
      expect(router.url).toBe('/organizer/dashboard?tab=past');
      expect(cards()).toHaveLength(0);
      expect(q('list-loading')).not.toBeNull();

      const req = listRequest();
      expect(params(req)).toEqual({ tab: 'past', page: '1', page_size: '20' });
      req.flush(eventPage(events(101, 102), 2));
      await settle();
      expect(cards()).toHaveLength(2);
      expect(text('list-counter')).toBe('2 of 2');
      expect(tab('Past').getAttribute('aria-selected')).toBe('true');
      // The totals do not change with the tab, and are not fetched again.
      expect(text('kpi-events')).toBe('18');
      http.expectNone(SUMMARY_URL);
    });

    it('leaves the URL clean when going back to the default tab', async () => {
      const { tab, settle, listRequest, router } = await setup();
      tab('Past').click();
      await settle();
      listRequest().flush(eventPage([]));
      tab('Upcoming').click();
      await settle();
      expect(router.url).toBe('/organizer/dashboard');
      listRequest().flush(eventPage([]));
    });

    it('goes back to the tab default sort when the tab changes', async () => {
      const { q, settle, listRequest, tab, router } = await setup();
      const select = q<HTMLSelectElement>('dashboard-sort')!;
      select.value = '-sold_through';
      select.dispatchEvent(new Event('change'));
      await settle();
      listRequest().flush(eventPage([]));
      expect(router.url).toBe('/organizer/dashboard?ordering=-sold_through');

      tab('Drafts').click();
      await settle();
      expect(router.url).toBe('/organizer/dashboard?tab=drafts');
      const req = listRequest();
      expect(req.request.params.has('ordering')).toBe(false);
      req.flush(eventPage([]));
      await settle();
      expect(q<HTMLSelectElement>('dashboard-sort')!.value).toBe('-date');
    });

    it('moves with the arrow keys', async () => {
      const { tab, settle, listRequest, router } = await setup();
      tab('Upcoming').dispatchEvent(
        new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }),
      );
      await settle();
      expect(router.url).toBe('/organizer/dashboard?tab=past');
      listRequest().flush(eventPage([]));
    });

    it('is a tab panel labelled by the selected tab', async () => {
      const { el, tab } = await setup();
      const panel = el.querySelector('[role="tabpanel"]')!;
      expect(panel.getAttribute('aria-labelledby')).toBe(tab('Upcoming').id);
      expect(tab('Upcoming').getAttribute('aria-controls')).toBe(panel.id);
    });
  });

  describe('sort', () => {
    it('sends the chosen ordering, and none when it is the tab default', async () => {
      const { q, settle, listRequest, router } = await setup();
      const select = q<HTMLSelectElement>('dashboard-sort')!;
      expect(select.value).toBe('date');

      select.value = '-checkin_rate';
      select.dispatchEvent(new Event('change'));
      await settle();
      let req = listRequest();
      expect(params(req)).toEqual({
        tab: 'upcoming',
        ordering: '-checkin_rate',
        page: '1',
        page_size: '20',
      });
      expect(router.url).toBe('/organizer/dashboard?ordering=-checkin_rate');
      req.flush(eventPage([]));
      await settle();

      select.value = 'date';
      select.dispatchEvent(new Event('change'));
      await settle();
      req = listRequest();
      expect(req.request.params.has('ordering')).toBe(false);
      expect(router.url).toBe('/organizer/dashboard');
      req.flush(eventPage([]));
    });
  });

  describe('search', () => {
    const type = (input: HTMLInputElement, value: string) => {
      input.value = value;
      input.dispatchEvent(new Event('input'));
    };

    afterEach(() => {
      vi.useRealTimers();
    });

    it('is debounced by 300 ms: one request for the final text', async () => {
      const { q, settle, http, listRequest, router } = await setup();
      vi.useFakeTimers();
      const input = q<HTMLInputElement>('dashboard-search')!;
      type(input, 'j');
      await vi.advanceTimersByTimeAsync(100);
      type(input, 'ja');
      await vi.advanceTimersByTimeAsync(100);
      type(input, 'jazz');
      await vi.advanceTimersByTimeAsync(299);
      http.expectNone((r) => r.url === EVENTS_URL);

      await vi.advanceTimersByTimeAsync(1);
      await settle();
      const req = listRequest();
      expect(req.request.params.get('search')).toBe('jazz');
      expect(req.request.params.get('page')).toBe('1');
      expect(router.url).toBe('/organizer/dashboard?search=jazz');
      req.flush(eventPage([]));
      await settle();
      // What the user typed stays in the box while the list reloads.
      expect(input.value).toBe('jazz');
    });

    it('does not ask again when the text ends up as it was', async () => {
      const { q, http } = await setup();
      vi.useFakeTimers();
      const input = q<HTMLInputElement>('dashboard-search')!;
      type(input, 'x');
      await vi.advanceTimersByTimeAsync(100);
      type(input, '');
      await vi.advanceTimersByTimeAsync(400);
      http.expectNone((r) => r.url === EVENTS_URL);
    });

    it('lets a URL change (Back, a link) win over a keystroke still waiting for its debounce', async () => {
      const { q, settle, http, listRequest, router } = await setup();
      vi.useFakeTimers();
      const input = q<HTMLInputElement>('dashboard-search')!;
      type(input, 'abc');
      await vi.advanceTimersByTimeAsync(100);

      await router.navigateByUrl('/organizer/dashboard?search=jazz');
      await settle();
      const req = listRequest();
      expect(req.request.params.get('search')).toBe('jazz');
      req.flush(eventPage([]));
      await settle();
      expect(input.value).toBe('jazz');

      // The pending 'abc' is gone: it neither asks nor rewrites the URL.
      await vi.advanceTimersByTimeAsync(500);
      await settle();
      http.expectNone((r) => r.url === EVENTS_URL);
      expect(router.url).toBe('/organizer/dashboard?search=jazz');
      expect(input.value).toBe('jazz');
    });

    it('lets a URL change with the same search (Back to another tab) drop a pending keystroke', async () => {
      const { q, settle, http, listRequest, router, harness } = await setup();
      vi.useFakeTimers();
      const input = q<HTMLInputElement>('dashboard-search')!;
      type(input, 'abc');
      // A browser renders after the input event; the box now shows 'abc'.
      harness.detectChanges();
      await vi.advanceTimersByTimeAsync(100);

      // Only the tab changes; the search ('') equals the committed one.
      await router.navigateByUrl('/organizer/dashboard?tab=past');
      await settle();
      const req = listRequest();
      expect(req.request.params.get('tab')).toBe('past');
      expect(req.request.params.has('search')).toBe(false);
      req.flush(eventPage([]));
      await settle();
      expect(input.value).toBe('');

      await vi.advanceTimersByTimeAsync(500);
      await settle();
      http.expectNone((r) => r.url === EVENTS_URL);
      expect(router.url).toBe('/organizer/dashboard?tab=past');
    });

    it('keeps typing that continues while its own search is applied', async () => {
      const { q, settle, listRequest, router } = await setup();
      vi.useFakeTimers();
      const input = q<HTMLInputElement>('dashboard-search')!;
      type(input, 'jaz');
      await vi.advanceTimersByTimeAsync(300);
      type(input, 'jazz');
      await settle();
      listRequest().flush(eventPage([]));
      await settle();
      // The dashboard's own URL update must not reset what is being typed.
      expect(input.value).toBe('jazz');
      await vi.advanceTimersByTimeAsync(300);
      await settle();
      expect(router.url).toBe('/organizer/dashboard?search=jazz');
      listRequest().flush(eventPage([]));
    });

    it('says nothing matches and clears the search with one click', async () => {
      const { q, settle, listRequest, router, text } = await setup({
        url: '/organizer/dashboard?search=zzz',
        first: eventPage([]),
      });
      expect(text('list-empty')).toContain('No events match “zzz”');
      q('clear-search')!.click();
      await settle();
      expect(router.url).toBe('/organizer/dashboard');
      expect(q<HTMLInputElement>('dashboard-search')!.value).toBe('');
      const req = listRequest();
      expect(req.request.params.has('search')).toBe(false);
      req.flush(eventPage(events(1, 3)));
    });
  });

  describe('show more', () => {
    it('appends the next page and keeps the counter right', async () => {
      const { q, settle, listRequest, cards, text, titles } = await setup();
      q('show-more')!.click();
      await settle();
      expect(q('show-more')!.hasAttribute('disabled')).toBe(true);
      const req = listRequest();
      expect(params(req)).toEqual({ tab: 'upcoming', page: '2', page_size: '20' });
      req.flush(eventPage(events(21, 23), 23));
      await settle();
      expect(cards()).toHaveLength(23);
      expect(titles().slice(-3)).toEqual(['Event 21', 'Event 22', 'Event 23']);
      expect(titles()[0]).toBe('Event 1');
      expect(text('list-counter')).toBe('23 of 23');
      expect(text('live-region')).toBe('Upcoming: showing 23 of 23 events');
      expect(q('show-more')).toBeNull();
    });

    it('keeps the loaded events and offers a retry when the next page fails', async () => {
      const { q, settle, listRequest, cards } = await setup();
      q('show-more')!.click();
      listRequest().flush({}, { status: 500, statusText: 'Error' });
      await settle();
      expect(cards()).toHaveLength(20);
      expect(q('more-error')!.textContent).toContain('temporarily unavailable');
      q('show-more')!.click();
      await settle();
      const req = listRequest();
      expect(req.request.params.get('page')).toBe('2');
      req.flush(eventPage(events(21, 23), 23));
      await settle();
      expect(cards()).toHaveLength(23);
      expect(q('more-error')).toBeNull();
    });

    it('skips no event after a delete shifted the pages', async () => {
      const { q, settle, listRequest, http, cards, titles, summaryRequest } = await setup();
      // Delete one of the 20 loaded events: the server now has 22 and the
      // event that was number 21 sits in the first page's range.
      q('menu-trigger')!.click();
      await settle();
      q('menu-delete')!.click();
      await settle();
      http.expectOne(`${API}/events/1/`).flush(null, { status: 204, statusText: 'No Content' });
      summaryRequest().flush(makeSummary());
      await settle();
      expect(cards()).toHaveLength(19);

      q('show-more')!.click();
      await settle();
      const req = listRequest();
      expect(req.request.params.get('page')).toBe('1');
      req.flush(eventPage(events(2, 21), 22));
      await settle();
      expect(cards()).toHaveLength(20);
      expect(titles().at(-1)).toBe('Event 21');
    });

    it('does not bring back an event deleted while "Show more" was in flight', async () => {
      const { q, settle, http, listRequest, cards, titles, text } = await setup();
      q('show-more')!.click();
      await settle();
      const stale = listRequest();
      expect(params(stale)['page']).toBe('2');

      q('menu-trigger')!.click();
      await settle();
      q('menu-delete')!.click();
      await settle();
      http.expectOne(`${API}/events/1/`).flush(null, { status: 204, statusText: 'No Content' });
      await settle();

      // The stale page can no longer land; the list is asked again from what is loaded.
      expect(stale.cancelled).toBe(true);
      const again = listRequest();
      expect(params(again)['page']).toBe('1');
      // Even an answer that still contains the deleted event cannot bring it back.
      again.flush(eventPage(events(1, 20), 22));
      await settle();
      expect(titles()).not.toContain('Event 1');
      expect(cards()).toHaveLength(19);
      expect(text('list-counter')).toBe('19 of 21');
      expect(q('show-more')).not.toBeNull();
    });

    it('asks the next page when a page brings only events already loaded, so "Show more" never vanishes', async () => {
      const { q, settle, listRequest, cards, text } = await setup();
      q('show-more')!.click();
      await settle();
      listRequest().flush(eventPage(events(1, 20), 23, 'next-url'));
      await settle();
      expect(text('list-counter')).toBe('20 of 23');
      expect(q('show-more')).not.toBeNull();

      const req = listRequest();
      expect(params(req)['page']).toBe('3');
      req.flush(eventPage(events(21, 23), 23));
      await settle();
      expect(cards()).toHaveLength(23);
      expect(text('list-counter')).toBe('23 of 23');
      expect(q('show-more')).toBeNull();
    });

    it('gives up after a bounded number of empty pages, keeps the server count, and moves on at the next click', async () => {
      const { q, settle, http, listRequest, text } = await setup();
      q('show-more')!.click();
      await settle();
      for (const page of ['2', '3', '4', '5']) {
        const req = listRequest();
        expect(params(req)['page']).toBe(page);
        req.flush(eventPage([], 23, 'next-url'));
        await settle();
      }
      http.expectNone((r) => r.url === EVENTS_URL);
      expect(text('list-counter')).toBe('20 of 23');
      expect(q<HTMLButtonElement>('show-more')!.disabled).toBe(false);

      q('show-more')!.click();
      await settle();
      const req = listRequest();
      expect(params(req)['page']).toBe('6');
      req.flush(eventPage(events(21, 23), 23));
    });

    it('stops offering "Show more" when the server has no further page and nothing new came', async () => {
      const { q, settle, listRequest, text } = await setup();
      q('show-more')!.click();
      await settle();
      listRequest().flush(eventPage(events(1, 20), 23));
      await settle();
      expect(text('list-counter')).toBe('20 of 20');
      expect(q('show-more')).toBeNull();
    });
  });

  describe('stale responses', () => {
    it('cancels the request of a tab the user already left, so it can never overwrite the new list', async () => {
      const { tab, settle, listRequest, titles } = await setup();
      tab('Past').click();
      await settle();
      const slow = listRequest();
      tab('Drafts').click();
      await settle();
      const fast = listRequest();
      expect(slow.cancelled).toBe(true);
      expect(params(fast)['tab']).toBe('drafts');

      fast.flush(eventPage([organizerEvent(7, { title: 'A draft', status: 'draft' })], 1));
      await settle();
      expect(titles()).toEqual(['A draft']);
    });
  });

  describe('independent sections', () => {
    it('keeps the list working when the summary fails, and Retry brings the totals back', async () => {
      const ctx = await setupPending();
      ctx.http
        .expectOne((r) => r.url === SUMMARY_URL)
        .flush({}, { status: 500, statusText: 'Error' });
      ctx.http.expectOne((r) => r.url === EVENTS_URL).flush(eventPage(events(1, 3)));
      ctx.http.expectOne((r) => r.url === ACTIVITY_URL).flush({ results: [], next_cursor: null });
      await ctx.settle();
      expect(ctx.q('summary-error')).not.toBeNull();
      expect(ctx.cards()).toHaveLength(3);
      // No counts on the tabs while the totals are unknown.
      expect(ctx.tab('Upcoming').textContent.trim()).toBe('Upcoming');

      ctx.q('summary-error')!.querySelector('button')!.click();
      await ctx.settle();
      ctx.http.expectOne((r) => r.url === SUMMARY_URL).flush(makeSummary());
      await ctx.settle();
      expect(ctx.q('summary-error')).toBeNull();
      expect(ctx.text('kpi-events')).toBe('18');
    });

    it('keeps summary and activity when the list fails, and Retry reloads only the list', async () => {
      const ctx = await setupPending();
      ctx.http.expectOne((r) => r.url === SUMMARY_URL).flush(makeSummary());
      ctx.http
        .expectOne((r) => r.url === EVENTS_URL)
        .flush({}, { status: 500, statusText: 'Error' });
      ctx.http.expectOne((r) => r.url === ACTIVITY_URL).flush({ results: [], next_cursor: null });
      await ctx.settle();
      expect(ctx.q('list-error')!.textContent).toContain('temporarily unavailable');
      expect(ctx.q('summary-kpis')).not.toBeNull();
      expect(ctx.q('activity-empty')).not.toBeNull();

      ctx.q('list-error')!.querySelector('button')!.click();
      await ctx.settle();
      ctx.http.expectNone((r) => r.url === SUMMARY_URL);
      ctx.http.expectNone((r) => r.url === ACTIVITY_URL);
      ctx.http.expectOne((r) => r.url === EVENTS_URL).flush(eventPage(events(1, 2)));
      await ctx.settle();
      expect(ctx.q('list-error')).toBeNull();
      expect(ctx.cards()).toHaveLength(2);
    });

    it('keeps summary and list when the activity feed fails', async () => {
      const ctx = await setupPending();
      ctx.http.expectOne((r) => r.url === SUMMARY_URL).flush(makeSummary());
      ctx.http.expectOne((r) => r.url === EVENTS_URL).flush(eventPage(events(1, 2)));
      ctx.http
        .expectOne((r) => r.url === ACTIVITY_URL)
        .flush({}, { status: 500, statusText: 'Error' });
      await ctx.settle();
      expect(ctx.q('activity-error')).not.toBeNull();
      expect(ctx.q('summary-kpis')).not.toBeNull();
      expect(ctx.cards()).toHaveLength(2);
    });
  });

  describe('callouts', () => {
    it('switch to the relevant tab and reload its list', async () => {
      const { q, settle, listRequest, router, tab } = await setup({
        url: '/organizer/dashboard?tab=past',
      });
      expect(tab('Past').getAttribute('aria-selected')).toBe('true');
      q('callout-soon')!.click();
      await settle();
      expect(router.url.split('#')[0]).toBe('/organizer/dashboard?tab=upcoming');
      const req = listRequest();
      expect(params(req)['tab']).toBe('upcoming');
      req.flush(eventPage(events(1, 2)));
      await settle();
      expect(tab('Upcoming').getAttribute('aria-selected')).toBe('true');

      // The awaiting-approval link leads to the same tab (pending events live there).
      q('callout-approval')!.click();
      await settle();
      expect(router.url.split('#')[0]).toBe('/organizer/dashboard?tab=upcoming');
    });
  });

  describe('empty states', () => {
    it.each([
      ['upcoming', '', 'No upcoming events', false],
      ['past', '?tab=past', 'No past events', false],
      ['drafts', '?tab=drafts', 'No drafts', true],
      ['inactive', '?tab=inactive', 'No cancelled or rejected events', false],
    ])('%s', async (tabName, query, title, hasCreate) => {
      const { text, q } = await setup({
        url: `/organizer/dashboard${query}`,
        first: eventPage([]),
      });
      expect(text('list-empty')).toContain(title);
      expect(q('empty-create') !== null).toBe(hasCreate);
      const label = tabName.charAt(0).toUpperCase() + tabName.slice(1);
      expect(text('live-region')).toBe(`${label}: showing 0 of 0 events`);
    });

    it('offers "Create event" on the drafts tab as a link to the form', async () => {
      const { q } = await setup({ url: '/organizer/dashboard?tab=drafts', first: eventPage([]) });
      expect(q('empty-create')!.getAttribute('href')).toBe('/create-event');
    });
  });

  describe('duplicate', () => {
    async function openDuplicate(options: Options = {}) {
      const ctx = await setup(options);
      ctx.q('menu-trigger')!.click();
      await ctx.settle();
      return ctx;
    }

    it('creates the copy with the localized title, disables the item meanwhile, then opens its edit page', async () => {
      const { q, settle, http, router, toastMessages } = await openDuplicate();
      q('menu-duplicate')!.click();
      await settle();
      const req = http.expectOne(`${API}/events/1/clone/`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ title: 'Event 1 (copy)' });
      expect(q<HTMLButtonElement>('menu-duplicate')!.disabled).toBe(true);

      req.flush(organizerEvent(99, { status: 'draft' }));
      await settle();
      expect(router.url).toBe('/edit-event/99');
      expect(toastMessages()).toContain('Copy created as a draft. You can edit it now.');
    });

    it('sends the title in the active language', async () => {
      const { q, settle, http } = await openDuplicate();
      await TestBed.inject(LanguageService).setLang('ru');
      await settle();
      q('menu-duplicate')!.click();
      await settle();
      const req = http.expectOne(`${API}/events/1/clone/`);
      expect(req.request.body).toEqual({ title: 'Event 1 (копия)' });
      req.flush(organizerEvent(99));
    });

    it('trims a long title so the copy fits the 200 characters of the column', async () => {
      const long = 'x'.repeat(200);
      const { q, settle, http } = await openDuplicate({
        first: eventPage([organizerEvent(1, { title: long })], 1),
      });
      q('menu-duplicate')!.click();
      await settle();
      const req = http.expectOne(`${API}/events/1/clone/`);
      const title = (req.request.body as { title: string }).title;
      expect(title).toHaveLength(200);
      expect(title.endsWith(' (copy)')).toBe(true);
      req.flush(organizerEvent(99));
    });

    it('shows the server message, re-enables the item and stays on the page when it fails', async () => {
      const { q, settle, http, router, toastMessages } = await openDuplicate();
      q('menu-duplicate')!.click();
      http
        .expectOne(`${API}/events/1/clone/`)
        .flush(
          { error: 'You cannot duplicate this event.' },
          { status: 403, statusText: 'Forbidden' },
        );
      await settle();
      expect(toastMessages()).toContain('You cannot duplicate this event.');
      // The menu closed with the failure; opened again, the item is usable.
      q('menu-trigger')!.click();
      await settle();
      expect(q<HTMLButtonElement>('menu-duplicate')!.disabled).toBe(false);
      expect(router.url).toBe('/organizer/dashboard');
    });

    it('does not show an invented server text for an outage', async () => {
      const { q, settle, http, toastMessages } = await openDuplicate();
      q('menu-duplicate')!.click();
      http
        .expectOne(`${API}/events/1/clone/`)
        .flush('<html>', { status: 502, statusText: 'Bad Gateway' });
      await settle();
      expect(toastMessages().at(-1)).toContain('temporarily unavailable');
    });

    it('closes the menu and puts focus back on its button when the copy fails', async () => {
      const { q, el, settle, http } = await openDuplicate();
      q('menu-duplicate')!.click();
      await settle();
      http
        .expectOne(`${API}/events/1/clone/`)
        .flush({ error: 'No.' }, { status: 403, statusText: 'Forbidden' });
      await settle();
      expect(el.querySelector('[role="menu"]')).toBeNull();
      expect(document.activeElement).toBe(q('menu-trigger'));
    });

    it('does not navigate when the page was left before the copy was made', async () => {
      const { q, settle, http, router, harness, toastMessages } = await openDuplicate();
      q('menu-duplicate')!.click();
      await settle();
      const req = http.expectOne(`${API}/events/1/clone/`);
      await router.navigateByUrl('/edit-event/5');
      await harness.fixture.whenStable();
      // The request is dropped with the page, so its answer has nowhere to go.
      expect(req.cancelled).toBe(true);
      expect(router.url).toBe('/edit-event/5');
      expect(toastMessages()).not.toContain('Copy created as a draft. You can edit it now.');
    });
  });

  describe('delete', () => {
    async function openDelete(options: Options = {}) {
      const ctx = await setup(options);
      ctx.q('menu-trigger')!.click();
      await ctx.settle();
      return ctx;
    }

    it('asks first, then removes the card, decrements the counts and refreshes the summary', async () => {
      const { q, settle, http, summaryRequest, cards, text, tab, modal, toastMessages } =
        await openDelete();
      q('menu-delete')!.click();
      await settle();
      expect(modal.open).toHaveBeenCalledTimes(1);
      expect(modal.open.mock.calls[0][0]).toMatchObject({ isDestructive: true });

      http.expectOne(`${API}/events/1/`).flush(null, { status: 204, statusText: 'No Content' });
      await settle();
      expect(cards()).toHaveLength(19);
      expect(text('list-counter')).toBe('19 of 22');
      expect(tab('Upcoming').textContent.replace(/\s+/g, ' ').trim()).toBe('Upcoming 14');
      expect(toastMessages()).toContain('Event deleted.');

      // The server's totals replace the local decrement.
      summaryRequest().flush(
        makeSummary({ tabs: { upcoming: 14, past: 2, drafts: 1, inactive: 0 } }),
      );
      await settle();
      expect(text('kpi-events')).toBe('17');
    });

    it('does nothing when the user declines', async () => {
      const { q, settle, cards, http } = await openDelete({ confirm: false });
      q('menu-delete')!.click();
      await settle();
      http.expectNone(`${API}/events/1/`);
      expect(cards()).toHaveLength(20);
    });

    it('shows the server explanation for a 409 (the event has sales) and keeps the card', async () => {
      const { q, settle, http, cards, toastMessages } = await openDelete();
      q('menu-delete')!.click();
      await settle();
      http
        .expectOne(`${API}/events/1/`)
        .flush(
          { error: 'This event has sold tickets. Cancel it instead of deleting it.' },
          { status: 409, statusText: 'Conflict' },
        );
      await settle();
      expect(toastMessages()).toContain(
        'This event has sold tickets. Cancel it instead of deleting it.',
      );
      expect(toastMessages()).not.toContain('Failed to delete event.');
      expect(cards()).toHaveLength(20);
    });

    it('reads a DRF `detail` message too, and falls back to its own text when there is none', async () => {
      const { q, settle, http, toastMessages } = await openDelete();
      q('menu-delete')!.click();
      await settle();
      http
        .expectOne(`${API}/events/1/`)
        .flush({ detail: 'Not allowed.' }, { status: 403, statusText: 'Forbidden' });
      await settle();
      expect(toastMessages()).toContain('Not allowed.');

      q('menu-trigger')!.click();
      await settle();
      q('menu-delete')!.click();
      await settle();
      http.expectOne(`${API}/events/1/`).flush({}, { status: 409, statusText: 'Conflict' });
      await settle();
      expect(toastMessages()).toContain('Failed to delete event.');
    });

    it('is not offered for an event the user only co-organizes', async () => {
      const { q } = await openDelete({
        first: eventPage([organizerEvent(1, { is_owner: false })], 1),
      });
      expect(q('menu-delete')).toBeNull();
      expect(q('menu-edit')).not.toBeNull();
    });

    it('puts focus back on the menu button when the delete fails', async () => {
      const { q, el, settle, http } = await openDelete();
      q('menu-delete')!.click();
      await settle();
      http
        .expectOne(`${API}/events/1/`)
        .flush({ error: 'Nope.' }, { status: 409, statusText: 'Conflict' });
      await settle();
      expect(el.querySelector('[role="menu"]')).toBeNull();
      expect(document.activeElement).toBe(q('menu-trigger'));
    });

    it('reloads the activity feed in the background after a delete', async () => {
      const { q, settle, http, activityRequest } = await openDelete();
      q('menu-delete')!.click();
      await settle();
      http.expectOne(`${API}/events/1/`).flush(null, { status: 204, statusText: 'No Content' });
      await settle();
      const req = activityRequest();
      expect(req.request.params.has('cursor')).toBe(false);
      expect(q('activity-loading')).toBeNull();
      req.flush({ results: [], next_cursor: null });
    });

    it('is cancelled when the page is left before the server answers', async () => {
      const { q, settle, http, router, harness } = await openDelete();
      q('menu-delete')!.click();
      await settle();
      const req = http.expectOne(`${API}/events/1/`);
      await router.navigateByUrl('/edit-event/5');
      await harness.fixture.whenStable();
      expect(req.cancelled).toBe(true);
    });
  });

  describe('menus', () => {
    it('keeps one menu open at a time', async () => {
      const { el, settle } = await setup();
      const triggers = () =>
        Array.from(el.querySelectorAll<HTMLElement>('[data-testid="menu-trigger"]'));
      triggers()[0].click();
      await settle();
      expect(el.querySelectorAll('[role="menu"]')).toHaveLength(1);

      triggers()[1].click();
      await settle();
      expect(el.querySelectorAll('[role="menu"]')).toHaveLength(1);
      expect(triggers()[0].getAttribute('aria-expanded')).toBe('false');
      expect(triggers()[1].getAttribute('aria-expanded')).toBe('true');
    });

    it('closes on Esc and on a click elsewhere on the page', async () => {
      const { el, q, settle } = await setup();
      q('menu-trigger')!.click();
      await settle();
      q('menu-edit')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await settle();
      expect(el.querySelector('[role="menu"]')).toBeNull();

      q('menu-trigger')!.click();
      await settle();
      el.querySelector<HTMLElement>('h1')!.click();
      await settle();
      expect(el.querySelector('[role="menu"]')).toBeNull();
    });

    it('registers document listeners only while a menu is open', async () => {
      const { el, settle } = await setup();
      const add = vi.spyOn(document, 'addEventListener');
      const remove = vi.spyOn(document, 'removeEventListener');
      const count = (spy: typeof add, type: string) =>
        spy.mock.calls.filter((call) => call[0] === type).length;
      const trigger = el.querySelector<HTMLElement>('[data-testid="menu-trigger"]')!;

      trigger.click();
      await settle();
      // 20 cards, one pair of listeners.
      expect(count(add, 'click')).toBe(1);
      expect(count(add, 'keydown')).toBe(1);
      expect(count(remove, 'click')).toBe(0);

      trigger.click();
      await settle();
      expect(el.querySelector('[role="menu"]')).toBeNull();
      expect(count(remove, 'click')).toBe(1);
      expect(count(remove, 'keydown')).toBe(1);
      add.mockRestore();
      remove.mockRestore();
    });
  });

  describe('accessibility', () => {
    it('announces the loaded count in a polite live region', async () => {
      const { el, text } = await setup();
      const region = el.querySelector('[data-testid="live-region"]')!;
      expect(region.getAttribute('aria-live')).toBe('polite');
      expect(text('live-region')).toBe('Upcoming: showing 20 of 23 events');
    });

    it('announces a reload of the same tab again: the region is emptied, then filled', async () => {
      const { cmp, q, text, settle, listRequest } = await setup();
      const seen: string[] = [];
      const observer = new MutationObserver((records) => {
        for (const record of records) seen.push((record.oldValue ?? '').trim());
      });
      observer.observe(q('live-region')!, {
        characterData: true,
        characterDataOldValue: true,
        childList: true,
        subtree: true,
      });

      cmp.retryList();
      await settle();
      listRequest().flush(eventPage(events(1, 20), 23));
      await settle();
      await Promise.resolve();
      observer.disconnect();

      // Identical text, yet a change for the screen reader: it was empty in between.
      expect(seen).toContain('');
      expect(text('live-region')).toBe('Upcoming: showing 20 of 23 events');
    });

    it('names the tab in the announcement', async () => {
      const { text } = await setup({
        url: '/organizer/dashboard?tab=past',
        first: eventPage(events(101, 102), 2),
      });
      expect(text('live-region')).toBe('Past: showing 2 of 2 events');
    });
  });
});

describe('DashboardComponent (superuser)', () => {
  it('shows the moderation queue instead of the organizer dashboard and asks no organizer endpoint', async () => {
    const ctx = await setup({ user: superUser });
    const queue = ctx.http.expectOne((r) => r.url === `${API}/events/`);
    expect(queue.request.params.get('status')).toBe('pending');
    queue.flush({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: 5,
          title: 'Waiting',
          organizer: { username: 'host' },
          date: '2026-12-01T10:00:00Z',
          location: 'Almaty',
        },
      ],
    });
    await ctx.settle();
    expect(ctx.q('moderation-queue')).not.toBeNull();
    expect(ctx.el.querySelector('h1')!.textContent).toContain('Admin Panel');
    expect(ctx.q('summary-kpis')).toBeNull();
    expect(ctx.q('dashboard-search')).toBeNull();
    ctx.http.expectNone((r) => r.url.includes('/organizer/'));
  });
});
