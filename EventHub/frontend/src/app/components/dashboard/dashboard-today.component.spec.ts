import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter, type Params } from '@angular/router';
import { environment } from '../../../environments/environment';
import { LanguageService } from '../../i18n/language.service';
import { I18nTestingModule } from '../../i18n/testing';
import type { TodayBlock } from '../../services/organizer-dashboard.service';
import { DashboardTodayComponent } from './dashboard-today.component';
import { todayBlock, todayEvent } from './dashboard.testing';

const URL = `${environment.apiUrl}/organizer/today/`;
const NOW = new Date('2026-11-21T10:00:00Z');
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

function setup(linkParams?: Params) {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, DashboardTodayComponent],
    providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
  });
  const http = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(DashboardTodayComponent);
  if (linkParams) fixture.componentRef.setInput('linkParams', linkParams);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const q = (testId: string) => el.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
  const all = (testId: string) =>
    Array.from(el.querySelectorAll<HTMLElement>(`[data-testid="${testId}"]`));
  const text = (testId: string) => q(testId)?.textContent.replace(/\s+/g, ' ').trim() ?? null;
  const request = () => http.expectOne((r) => r.url === URL);
  const answer = (block: TodayBlock) => {
    request().flush(block);
    fixture.detectChanges();
  };
  return { http, fixture, el, q, all, text, request, answer };
}

describe('DashboardTodayComponent', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('when there is nothing to show', () => {
    it('draws nothing while loading, and asks the server once', () => {
      const { el, request } = setup();
      expect(el.textContent.trim()).toBe('');
      expect(el.querySelector('[role="status"]')).toBeNull();
      request();
    });

    it('draws nothing at all when no event is in progress or coming within 7 days', () => {
      const { el, q, answer } = setup();
      answer(todayBlock([]));
      expect(q('today')).toBeNull();
      expect(el.textContent.trim()).toBe('');
    });

    it('draws nothing even when the server counts more events than it sent', () => {
      const { q, answer } = setup();
      answer(todayBlock([], 3));
      expect(q('today')).toBeNull();
      expect(q('today-more')).toBeNull();
    });
  });

  describe('an event', () => {
    const inHours = (hours: number, minutes = 0) =>
      new Date(NOW.getTime() + hours * HOUR + minutes * MINUTE).toISOString();

    it('shows its title, place, time and numbers', () => {
      const { q, all, text, answer } = setup();
      answer(
        todayBlock([
          todayEvent(7, {
            title: 'Stand-up Almaty',
            location: 'Almaty, Abay Ave 1',
            date: inHours(3, 5),
            stats: { tickets_sold: 1250, checked_in: 40, capacity: 3000 },
          }),
        ]),
      );
      expect(all('today-event')).toHaveLength(1);
      expect(text('today-title')).toBe('Stand-up Almaty');
      expect(q('today')!.textContent).toContain('Almaty, Abay Ave 1');
      expect(q('today')!.querySelector('time')!.getAttribute('datetime')).toBe(inHours(3, 5));
      expect(text('today-sold')).toBe('1,250 of 3,000 tickets sold');
      expect(text('today-checked-in')).toBe('40 checked in');
    });

    it('links the title to the event page', () => {
      const { q, answer } = setup();
      answer(todayBlock([todayEvent(7)]));
      expect(q('today-title')!.getAttribute('href')).toBe('/events/7');
    });

    it('links to scan, attendees and check-in lists, each named for its event', () => {
      const { q, answer } = setup();
      answer(todayBlock([todayEvent(7, { title: 'Gala' })]));
      expect(q('today-scan')!.getAttribute('href')).toBe('/scan');
      expect(q('today-attendees')!.getAttribute('href')).toBe('/organizer/events/7/attendees');
      expect(q('today-checkin-lists')!.getAttribute('href')).toBe(
        '/organizer/events/7/checkin-lists',
      );
      expect(q('today-scan')!.getAttribute('aria-label')).toBe('Scan: Gala');
      expect(q('today-attendees')!.getAttribute('aria-label')).toBe('Attendees: Gala');
      expect(q('today-checkin-lists')!.getAttribute('aria-label')).toBe('Check-in Lists: Gala');
    });

    it('lists events in the order the server sent them', () => {
      const { all, answer } = setup();
      answer(todayBlock([todayEvent(1), todayEvent(2), todayEvent(3)]));
      expect(all('today-title').map((a) => a.textContent.trim())).toEqual([
        'Today 1',
        'Today 2',
        'Today 3',
      ]);
    });

    it('marks an event that still waits for approval, and one the organizer only co-manages', () => {
      const { el, answer } = setup();
      answer(todayBlock([todayEvent(1, { status: 'pending', is_owner: false })]));
      expect(el.textContent).toContain('Pending approval');
      expect(el.textContent).toContain('Co-organizer');
    });

    it('does not repeat "Published" on every row', () => {
      const { el, answer } = setup();
      answer(todayBlock([todayEvent(1)]));
      expect(el.textContent).not.toContain('Published');
    });
  });

  describe('countdown', () => {
    it.each([
      [2 * 24 * HOUR + 3 * HOUR + 10 * MINUTE, 'Starts in 2 d 3 h'],
      [3 * HOUR + 5 * MINUTE, 'Starts in 3 h 5 min'],
      [2 * HOUR, 'Starts in 2 h'],
      [12 * MINUTE + 30_000, 'Starts in 12 min'],
      [30_000, 'Starts in less than a minute'],
    ])('%i ms ahead reads "%s"', (ahead, expected) => {
      const { text, answer } = setup();
      answer(todayBlock([todayEvent(1, { date: new Date(NOW.getTime() + ahead).toISOString() })]));
      expect(text('today-countdown')).toBe(expected);
    });

    it('shows "In progress" instead of a countdown for an event that has started', () => {
      const { q, text, answer } = setup();
      answer(
        todayBlock([
          todayEvent(1, { in_progress: true, date: new Date(NOW.getTime() - HOUR).toISOString() }),
        ]),
      );
      expect(text('today-in-progress')).toBe('In progress');
      expect(q('today-countdown')).toBeNull();
    });

    it('moves on every minute without asking the server again', () => {
      const { fixture, http, text, answer } = setup();
      answer(
        todayBlock([
          todayEvent(1, { date: new Date(NOW.getTime() + 3 * HOUR + 5 * MINUTE).toISOString() }),
        ]),
      );
      expect(text('today-countdown')).toBe('Starts in 3 h 5 min');

      vi.advanceTimersByTime(MINUTE);
      fixture.detectChanges();
      expect(text('today-countdown')).toBe('Starts in 3 h 4 min');

      vi.advanceTimersByTime(4 * MINUTE);
      fixture.detectChanges();
      expect(text('today-countdown')).toBe('Starts in 3 h');

      http.expectNone((r) => r.url === URL);
    });

    it('says the event is starting when its time has come while the page stayed open', () => {
      const { fixture, text, answer } = setup();
      answer(
        todayBlock([todayEvent(1, { date: new Date(NOW.getTime() + 2 * MINUTE).toISOString() })]),
      );
      expect(text('today-countdown')).toBe('Starts in 2 min');
      vi.advanceTimersByTime(3 * MINUTE);
      fixture.detectChanges();
      expect(text('today-countdown')).toBe('Starting now');
    });

    it('stops its timer when the page is left', () => {
      const { fixture, answer } = setup();
      answer(
        todayBlock([todayEvent(1, { date: new Date(NOW.getTime() + 3 * HOUR).toISOString() })]),
      );
      const before = vi.getTimerCount();
      expect(before).toBeGreaterThan(0);
      fixture.destroy();
      expect(vi.getTimerCount()).toBe(before - 1);
      // Nothing ticks any more, whatever time passes.
      vi.advanceTimersByTime(10 * MINUTE);
      expect(vi.getTimerCount()).toBe(before - 1);
    });

    it('is written in the current language', async () => {
      const { fixture, text, answer } = setup();
      answer(
        todayBlock([
          todayEvent(1, { date: new Date(NOW.getTime() + 3 * HOUR + 5 * MINUTE).toISOString() }),
        ]),
      );
      await TestBed.inject(LanguageService).setLang('ru');
      fixture.detectChanges();
      expect(text('today-countdown')).toBe('Начнётся через 3 ч 5 мин');
      await TestBed.inject(LanguageService).setLang('kk');
      fixture.detectChanges();
      expect(text('today-countdown')).toBe('3 сағ 5 мин кейін басталады');
    });
  });

  describe('events beyond the ten shown', () => {
    it.each([
      [1, '+1 more event this week'],
      [3, '+3 more events this week'],
    ])('links "%i more" to the Upcoming tab', (more, label) => {
      const { q, text, answer } = setup();
      answer(todayBlock([todayEvent(1)], more));
      expect(text('today-more')).toBe(label);
      const href = q('today-more')!.getAttribute('href')!;
      expect(href).toContain('tab=upcoming');
      expect(href).toContain('#dashboard-events');
    });

    it('keeps what else the page has in its URL (the chart range)', () => {
      const { q, answer } = setup({ tab: 'upcoming', range: '7d' });
      answer(todayBlock([todayEvent(1)], 2));
      expect(q('today-more')!.getAttribute('href')).toContain('range=7d');
    });

    it('has no such link when everything fits', () => {
      const { q, answer } = setup();
      answer(todayBlock([todayEvent(1)], 0));
      expect(q('today-more')).toBeNull();
    });

    it('uses the plural of the language', async () => {
      const { fixture, text, answer } = setup();
      answer(todayBlock([todayEvent(1)], 5));
      await TestBed.inject(LanguageService).setLang('ru');
      fixture.detectChanges();
      expect(text('today-more')).toBe('Ещё 5 событий на этой неделе');
    });
  });

  describe('a failed load', () => {
    it('says so, offers a retry, and shows the events when it works', () => {
      const { q, text, request, answer, fixture } = setup();
      request().flush({}, { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();
      expect(q('today-error')!.getAttribute('role')).toBe('alert');
      expect(text('today-error')).toContain('Retry');
      q('today-error')!.querySelector('button')!.click();
      fixture.detectChanges();
      expect(q('today-error')).toBeNull();
      answer(todayBlock([todayEvent(1)]));
      expect(q('today')).not.toBeNull();
    });
  });
});
