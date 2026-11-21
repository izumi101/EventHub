import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { LanguageService } from '../../i18n/language.service';
import { I18nTestingModule } from '../../i18n/testing';
import type { ActivityFeed } from '../../services/organizer-dashboard.service';
import { DashboardActivityComponent } from './dashboard-activity.component';
import { activityItem } from './dashboard.testing';

const URL = `${environment.apiUrl}/organizer/activity/`;

function setup() {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, DashboardActivityComponent],
    providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
  });
  const http = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(DashboardActivityComponent);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const q = (testId: string) => el.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
  const items = () => Array.from(el.querySelectorAll<HTMLElement>('[data-testid="activity-item"]'));
  const expectFeed = () => http.expectOne((r) => r.url === URL);
  const answer = (feed: ActivityFeed) => {
    expectFeed().flush(feed);
    fixture.detectChanges();
  };
  return { http, fixture, el, q, items, expectFeed, answer };
}

describe('DashboardActivityComponent', () => {
  it('asks for the first 10 items, without a cursor, and shows a skeleton meanwhile', () => {
    const { q, expectFeed } = setup();
    expect(q('activity-loading')).not.toBeNull();
    const req = expectFeed();
    expect(req.request.params.get('limit')).toBe('10');
    expect(req.request.params.has('cursor')).toBe(false);
    req.flush({ results: [], next_cursor: null });
  });

  it('writes one sentence per activity type, with its own icon', () => {
    const { items, answer } = setup();
    answer({
      results: [
        activityItem('registration', 1),
        activityItem('group_booking', 2, { quantity: 4, attendee_name: 'Aigerim K.' }),
        activityItem('check_in', 3),
        activityItem('refund', 4, {
          amount: '15000.00',
          currency: 'KZT',
          attendee_name: 'Timur S.',
        }),
      ],
      next_cursor: null,
    });
    const rows = items();
    expect(rows.map((r) => r.dataset['type'])).toEqual([
      'registration',
      'group_booking',
      'check_in',
      'refund',
    ]);
    const sentence = (i: number) =>
      rows[i]
        .querySelector('[data-testid="activity-text"]')!
        .textContent.replace(/\s+/g, ' ')
        .trim();
    expect(sentence(0)).toBe('Dias A. registered');
    expect(sentence(1)).toBe('Group booking by Aigerim K.: 4 seats');
    expect(sentence(2)).toBe('Dias A. checked in');
    expect(sentence(3)).toMatch(/^Refund of KZT\s*15[,\s]?000(\.00)? to Timur S\.$/);
    // Every row has an icon, and no two types share one.
    const icons = rows.map((r) => r.querySelector('lucide-icon')!.innerHTML);
    expect(new Set(icons).size).toBe(4);
  });

  it('uses the singular for a booking of one seat', () => {
    const { items, answer } = setup();
    answer({ results: [activityItem('group_booking', 1, { quantity: 1 })], next_cursor: null });
    expect(items()[0].textContent).toContain('1 seat');
    expect(items()[0].textContent).not.toContain('1 seats');
  });

  it('uses the plural forms of the active language', async () => {
    const { fixture, items, answer } = setup();
    await TestBed.inject(LanguageService).setLang('ru');
    answer({
      results: [
        activityItem('group_booking', 1, { quantity: 1 }),
        activityItem('group_booking', 2, { quantity: 3 }),
        activityItem('group_booking', 3, { quantity: 5 }),
      ],
      next_cursor: null,
    });
    fixture.detectChanges();
    const texts = items().map((r) => r.textContent);
    expect(texts[0]).toContain('1 место');
    expect(texts[1]).toContain('3 места');
    expect(texts[2]).toContain('5 мест');
  });

  it('links the event title to its attendees page', () => {
    const { q, answer } = setup();
    answer({
      results: [activityItem('registration', 1, { event_id: 42, event_title: 'Jazz Night' })],
      next_cursor: null,
    });
    const link = q('activity-event-link') as HTMLAnchorElement;
    expect(link.textContent.trim()).toBe('Jazz Night');
    expect(link.getAttribute('href')).toBe('/organizer/events/42/attendees');
  });

  it('shows a relative time with the exact time in the title and datetime', () => {
    const { q, answer } = setup();
    const occurred = new Date(Date.now() - 5 * 60_000).toISOString();
    answer({
      results: [activityItem('check_in', 1, { occurred_at: occurred })],
      next_cursor: null,
    });
    const time = q('activity-time')!;
    expect(time.textContent.trim()).toMatch(/^5 min/);
    expect(time.tagName).toBe('TIME');
    expect(time.getAttribute('datetime')).toBe(occurred);
    expect(time.getAttribute('title')).toMatch(/\d{4}/);
  });

  it('pages with the cursor the server gave, appends, and drops a repeated item', () => {
    const { q, items, expectFeed, answer, fixture } = setup();
    answer({
      results: [activityItem('registration', 1), activityItem('registration', 2)],
      next_cursor: 'cursor-1',
    });
    expect(items()).toHaveLength(2);
    expect(q('activity-more')).not.toBeNull();

    q('activity-more')!.click();
    fixture.detectChanges();
    expect(q('activity-more')!.hasAttribute('disabled')).toBe(true);
    const req = expectFeed();
    expect(req.request.params.get('cursor')).toBe('cursor-1');
    expect(req.request.params.get('limit')).toBe('10');
    req.flush({
      results: [activityItem('registration', 2), activityItem('check_in', 3)],
      next_cursor: null,
    });
    fixture.detectChanges();
    expect(items()).toHaveLength(3);
    expect(q('activity-more')).toBeNull();
  });

  it('shows the empty state when nothing happened in 30 days', () => {
    const { q, answer } = setup();
    answer({ results: [], next_cursor: null });
    expect(q('activity-empty')!.textContent.trim()).toBe('No activity in the last 30 days');
  });

  it('shows an error with Retry, and retrying loads the feed', () => {
    const { q, expectFeed, fixture } = setup();
    expectFeed().flush({}, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();
    expect(q('activity-error')!.textContent).toContain('temporarily unavailable');

    q('activity-error')!.querySelector('button')!.click();
    fixture.detectChanges();
    expect(q('activity-loading')).not.toBeNull();
    expectFeed().flush({ results: [activityItem('registration', 1)], next_cursor: null });
    fixture.detectChanges();
    expect(q('activity-error')).toBeNull();
    expect(q('activity-list')).not.toBeNull();
  });

  it('keeps the loaded items when "show more" fails and retries the same page', () => {
    const { q, items, expectFeed, fixture } = setup();
    expectFeed().flush({ results: [activityItem('registration', 1)], next_cursor: 'c1' });
    fixture.detectChanges();

    q('activity-more')!.click();
    expectFeed().flush({}, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();
    expect(items()).toHaveLength(1);
    expect(q('activity-more-error')).not.toBeNull();
    expect(q('activity-more')!.textContent).toContain('Retry');

    q('activity-more')!.click();
    const retry = expectFeed();
    expect(retry.request.params.get('cursor')).toBe('c1');
    retry.flush({ results: [activityItem('check_in', 2)], next_cursor: null });
    fixture.detectChanges();
    expect(items()).toHaveLength(2);
    expect(q('activity-more-error')).toBeNull();
  });

  describe('refresh', () => {
    it('reloads the first page when the page bumps refreshToken, keeping the list on screen', () => {
      const { fixture, q, items, expectFeed, answer } = setup();
      answer({ results: [activityItem('registration', 1)], next_cursor: null });
      expect(items()).toHaveLength(1);

      fixture.componentRef.setInput('refreshToken', 1);
      fixture.detectChanges();
      expect(q('activity-loading')).toBeNull();
      expect(items()).toHaveLength(1);
      const req = expectFeed();
      expect(req.request.params.has('cursor')).toBe(false);
      req.flush({
        results: [activityItem('check_in', 2), activityItem('registration', 1)],
        next_cursor: null,
      });
      fixture.detectChanges();
      expect(items()).toHaveLength(2);
    });

    it('makes no request while refreshToken is still 0', () => {
      const { fixture, http, answer } = setup();
      answer({ results: [], next_cursor: null });
      fixture.detectChanges();
      http.expectNone((r) => r.url === URL);
    });

    it('keeps the loaded feed when a background refresh fails', () => {
      const { fixture, q, items, expectFeed, answer } = setup();
      answer({ results: [activityItem('registration', 1)], next_cursor: 'c1' });
      fixture.componentRef.setInput('refreshToken', 1);
      fixture.detectChanges();
      expectFeed().flush({}, { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();
      expect(q('activity-error')).toBeNull();
      expect(items()).toHaveLength(1);
      expect(q('activity-more')).not.toBeNull();
    });
  });

  describe('relative times', () => {
    afterEach(() => {
      vi.useRealTimers();
    });

    it('re-render every 60 s without a request, and the timer stops on destroy', () => {
      vi.useFakeTimers();
      const { fixture, http, q, answer } = setup();
      answer({ results: [activityItem('check_in', 1)], next_cursor: null });
      expect(q('activity-time')!.textContent.trim()).toMatch(/^5 min/);

      vi.advanceTimersByTime(60_000);
      fixture.detectChanges();
      expect(q('activity-time')!.textContent.trim()).toMatch(/^6 min/);
      http.expectNone((r) => r.url === URL);

      const before = vi.getTimerCount();
      fixture.destroy();
      expect(vi.getTimerCount()).toBe(before - 1);
    });
  });
});
