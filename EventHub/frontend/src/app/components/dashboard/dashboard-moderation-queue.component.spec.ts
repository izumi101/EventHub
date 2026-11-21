import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { I18nTestingModule } from '../../i18n/testing';
import type { Event } from '../../models/models';
import { DashboardModerationQueueComponent } from './dashboard-moderation-queue.component';

const URL = `${environment.apiUrl}/events/`;

const pending = (id: number): Event =>
  ({
    id,
    title: `Pending ${id}`,
    organizer: { id: 9, username: 'host', first_name: '', last_name: '' },
    date: '2026-12-11T19:00:00Z',
    location: 'Almaty',
    status: 'pending',
  }) as Event;

function setup() {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, DashboardModerationQueueComponent],
    providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
  });
  const http = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(DashboardModerationQueueComponent);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const q = (testId: string) => el.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
  const rows = () => Array.from(el.querySelectorAll('[data-testid="queue-item"]'));
  const expectPage = (page: number) => {
    const req = http.expectOne((r) => r.url === URL);
    expect(req.request.params.get('status')).toBe('pending');
    expect(req.request.params.get('page')).toBe(String(page));
    return req;
  };
  return { http, fixture, el, q, rows, expectPage };
}

describe('DashboardModerationQueueComponent', () => {
  it('shows the real count, a link to every event and the position in the queue', () => {
    const { fixture, q, rows, expectPage } = setup();
    expectPage(1).flush({
      count: 27,
      next: 'next',
      previous: null,
      results: [pending(1), pending(2)],
    });
    fixture.detectChanges();
    expect(q('moderation-queue')!.textContent).toContain('Awaiting approval (27)');
    expect(rows()).toHaveLength(2);
    expect(rows()[0].querySelector('a')!.getAttribute('href')).toBe('/events/1');
    expect(rows()[0].textContent).toContain('by @host');
    expect(q('queue-counter')!.textContent.trim()).toBe('2 of 27');
  });

  it('shows the title without a count while loading and on error, never "(0)"', () => {
    const { fixture, q, expectPage } = setup();
    const heading = () => q('moderation-queue')!.querySelector('h2')!.textContent.trim();
    expect(q('queue-loading')).not.toBeNull();
    expect(heading()).toBe('Awaiting approval');

    expectPage(1).flush({}, { status: 503, statusText: 'Unavailable' });
    fixture.detectChanges();
    expect(q('queue-error')).not.toBeNull();
    expect(heading()).toBe('Awaiting approval');

    q('queue-error')!.querySelector('button')!.click();
    fixture.detectChanges();
    expect(heading()).toBe('Awaiting approval');
    expectPage(1).flush({ count: 4, next: null, previous: null, results: [pending(1)] });
    fixture.detectChanges();
    expect(heading()).toBe('Awaiting approval (4)');
  });

  it('pages: "Show more" requests the next page and appends it', () => {
    const { fixture, q, rows, expectPage } = setup();
    expectPage(1).flush({ count: 3, next: 'n', previous: null, results: [pending(1), pending(2)] });
    fixture.detectChanges();

    q('queue-more')!.click();
    fixture.detectChanges();
    expect(q('queue-more')!.hasAttribute('disabled')).toBe(true);
    expectPage(2).flush({ count: 3, next: null, previous: 'p', results: [pending(3)] });
    fixture.detectChanges();
    expect(rows()).toHaveLength(3);
    expect(q('queue-counter')!.textContent.trim()).toBe('3 of 3');
    expect(q('queue-more')).toBeNull();
  });

  it('links to the moderation page, where events are approved or rejected', () => {
    const { fixture, q, expectPage } = setup();
    expectPage(1).flush({ count: 0, next: null, previous: null, results: [] });
    fixture.detectChanges();
    expect(q('queue-moderation-link')!.getAttribute('href')).toBe('/admin/moderation');
  });

  it('says the queue is empty', () => {
    const { fixture, q, expectPage } = setup();
    expectPage(1).flush({ count: 0, next: null, previous: null, results: [] });
    fixture.detectChanges();
    expect(q('queue-empty')!.textContent).toContain('queue is empty');
  });

  it('shows an error with Retry, and retrying reloads the first page', () => {
    const { fixture, q, rows, expectPage } = setup();
    expectPage(1).flush({}, { status: 503, statusText: 'Unavailable' });
    fixture.detectChanges();
    expect(q('queue-error')).not.toBeNull();

    q('queue-error')!.querySelector('button')!.click();
    fixture.detectChanges();
    expectPage(1).flush({ count: 1, next: null, previous: null, results: [pending(1)] });
    fixture.detectChanges();
    expect(q('queue-error')).toBeNull();
    expect(rows()).toHaveLength(1);
  });

  it('keeps the loaded page when "show more" fails', () => {
    const { fixture, el, q, rows, expectPage } = setup();
    expectPage(1).flush({ count: 3, next: 'n', previous: null, results: [pending(1), pending(2)] });
    fixture.detectChanges();
    q('queue-more')!.click();
    expectPage(2).flush({}, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    expect(rows()).toHaveLength(2);
    expect(el.querySelector('[role="alert"]')).not.toBeNull();
    expect(q('queue-more')).not.toBeNull();
  });
});
