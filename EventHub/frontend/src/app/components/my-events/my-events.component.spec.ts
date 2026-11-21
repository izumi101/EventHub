import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { I18nTestingModule } from '../../i18n/testing';
import { LanguageService } from '../../i18n/language.service';
import type { Event } from '../../models/models';
import { ModalService } from '../../services/modal.service';
import { ToastService } from '../../services/toast.service';
import { MyEventsComponent } from './my-events.component';

const URL = `${environment.apiUrl}/my-events/`;

const event = (id: number): Event =>
  ({
    id,
    title: `My event ${id}`,
    status: 'published',
    date: '2026-12-11T19:00:00Z',
    location: 'Almaty',
    image: null,
  }) as Event;

const events = (from: number, to: number) =>
  Array.from({ length: to - from + 1 }, (_, i) => event(from + i));

function setup() {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, MyEventsComponent],
    providers: [
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: ModalService, useValue: { open: vi.fn().mockResolvedValue(true) } },
    ],
  });
  const http = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(MyEventsComponent);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const q = (testId: string) => el.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
  const rows = () => el.querySelectorAll('.card > div');
  const page = (n: number) => {
    const req = http.expectOne((r) => r.url === URL);
    expect(req.request.params.get('page')).toBe(String(n));
    return req;
  };
  const toasts = TestBed.inject(ToastService);
  return { http, fixture, el, q, rows, page, toasts };
}

describe('MyEventsComponent pagination', () => {
  it('loads page 1 and shows how many of all the events are on screen', () => {
    const { fixture, q, rows, page } = setup();
    page(1).flush({ count: 30, next: 'next', previous: null, results: events(1, 12) });
    fixture.detectChanges();
    expect(rows()).toHaveLength(12);
    expect(q('events-counter')!.textContent.trim()).toBe('12 of 30');
    expect(q('events-more')).not.toBeNull();
  });

  it('shows no "Show more" when everything fits on the first page', () => {
    const { fixture, q, page } = setup();
    page(1).flush({ count: 3, next: null, previous: null, results: events(1, 3) });
    fixture.detectChanges();
    expect(q('events-counter')!.textContent.trim()).toBe('3 of 3');
    expect(q('events-more')).toBeNull();
  });

  it('appends the next page, page by page, until all are shown', () => {
    const { fixture, q, rows, page } = setup();
    page(1).flush({ count: 30, next: 'n', previous: null, results: events(1, 12) });
    fixture.detectChanges();

    q('events-more')!.click();
    fixture.detectChanges();
    expect(q('events-more')!.hasAttribute('disabled')).toBe(true);
    page(2).flush({ count: 30, next: 'n', previous: 'p', results: events(13, 24) });
    fixture.detectChanges();
    expect(rows()).toHaveLength(24);

    q('events-more')!.click();
    page(3).flush({ count: 30, next: null, previous: 'p', results: events(25, 30) });
    fixture.detectChanges();
    expect(rows()).toHaveLength(30);
    expect(q('events-counter')!.textContent.trim()).toBe('30 of 30');
    expect(q('events-more')).toBeNull();
  });

  it('keeps what is loaded and tells the user when the next page fails', () => {
    const { fixture, q, rows, page, toasts } = setup();
    page(1).flush({ count: 30, next: 'n', previous: null, results: events(1, 12) });
    fixture.detectChanges();
    q('events-more')!.click();
    page(2).flush({}, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    expect(rows()).toHaveLength(12);
    expect(toasts.toasts().length).toBe(1);
    expect(q('events-more')!.hasAttribute('disabled')).toBe(false);
  });

  it('skips no event after a delete shifted the pages', async () => {
    const { http, fixture, el, q, rows, page } = setup();
    page(1).flush({ count: 14, next: 'n', previous: null, results: events(1, 12) });
    fixture.detectChanges();

    el.querySelector<HTMLElement>('[title="Delete event"]')!.click();
    await fixture.whenStable();
    http
      .expectOne(`${environment.apiUrl}/events/1/`)
      .flush(null, { status: 204, statusText: 'No' });
    fixture.detectChanges();
    expect(rows()).toHaveLength(11);
    expect(q('events-counter')!.textContent.trim()).toBe('11 of 13');

    // 11 are loaded and the page size is 12: the page that holds the missing ones is page 1.
    q('events-more')!.click();
    page(1).flush({ count: 13, next: null, previous: null, results: events(2, 13) });
    fixture.detectChanges();
    expect(rows()).toHaveLength(12);

    // Now a full page is loaded: the last event is on page 2.
    q('events-more')!.click();
    page(2).flush({ count: 13, next: null, previous: 'p', results: events(14, 14) });
    fixture.detectChanges();
    expect(rows()).toHaveLength(13);
    expect(q('events-more')).toBeNull();
  });

  it('looks one page further when a page brings nothing new, trusting the server count', () => {
    const { fixture, q, rows, page } = setup();
    page(1).flush({ count: 30, next: 'n', previous: null, results: events(1, 12) });
    fixture.detectChanges();
    q('events-more')!.click();
    // An event created elsewhere shifted the order: page 2 repeats what is shown.
    page(2).flush({ count: 30, next: 'n', previous: 'p', results: events(1, 12) });
    page(3).flush({ count: 30, next: null, previous: 'p', results: events(13, 24) });
    fixture.detectChanges();
    expect(rows()).toHaveLength(24);
    expect(q('events-counter')!.textContent.trim()).toBe('24 of 30');
    expect(q('events-more')).not.toBeNull();
  });

  it('gives up after a few empty pages but never asks for the same page again', () => {
    const { fixture, q, http, page } = setup();
    page(1).flush({ count: 30, next: 'n', previous: null, results: events(1, 12) });
    fixture.detectChanges();
    q('events-more')!.click();
    for (const n of [2, 3, 4, 5]) {
      page(n).flush({ count: 30, next: 'n', previous: 'p', results: events(1, 12) });
    }
    http.expectNone((r) => r.url === URL);
    fixture.detectChanges();
    // Still 30 on the server: the user can try again, and it goes on from page 6.
    expect(q('events-more')!.hasAttribute('disabled')).toBe(false);
    q('events-more')!.click();
    page(6).flush({ count: 30, next: null, previous: 'p', results: events(13, 30) });
    fixture.detectChanges();
    expect(q('events-counter')!.textContent.trim()).toBe('30 of 30');
  });

  it('shows the server explanation when a delete is refused', async () => {
    const { http, fixture, el, page, toasts } = setup();
    page(1).flush({ count: 1, next: null, previous: null, results: events(1, 1) });
    fixture.detectChanges();
    el.querySelector<HTMLElement>('[title="Delete event"]')!.click();
    await fixture.whenStable();
    http
      .expectOne(`${environment.apiUrl}/events/1/`)
      .flush({ error: 'Has sales.' }, { status: 409, statusText: 'Conflict' });
    expect(toasts.toasts().map((t) => t.message)).toContain('Has sales.');
  });
});

describe('MyEventsComponent status badge', () => {
  const withStatuses = () =>
    ['draft', 'pending', 'published', 'completed', 'rejected', 'cancelled'].map(
      (status, i) => ({ ...event(i + 1), status }) as Event,
    );
  const badges = (el: HTMLElement) =>
    Array.from(el.querySelectorAll<HTMLElement>('[data-testid="status-badge"]'));

  it('shows the translated status in English and keeps the colour classes', () => {
    const { fixture, el, page } = setup();
    page(1).flush({ count: 6, next: null, previous: null, results: withStatuses() });
    fixture.detectChanges();
    expect(badges(el).map((b) => b.textContent.trim())).toEqual([
      'Draft',
      'Pending approval',
      'Published',
      'Completed',
      'Rejected',
      'Cancelled',
    ]);
    expect(badges(el).map((b) => b.className)).toEqual([
      expect.stringContaining('badge-pending'),
      expect.stringContaining('badge-pending'),
      expect.stringContaining('badge-published'),
      expect.stringContaining('badge-completed'),
      expect.stringContaining('badge-rejected'),
      expect.stringContaining('badge-rejected'),
    ]);
  });

  it('shows the translated status in Russian', async () => {
    const { fixture, el, page } = setup();
    await TestBed.inject(LanguageService).setLang('ru');
    page(1).flush({ count: 6, next: null, previous: null, results: withStatuses() });
    fixture.detectChanges();
    expect(badges(el).map((b) => b.textContent.trim())).toEqual([
      'Черновик',
      'Ожидает одобрения',
      'Опубликовано',
      'Завершено',
      'Отклонено',
      'Отменено',
    ]);
  });
});
