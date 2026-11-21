import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { I18nTestingModule } from '../../i18n/testing';
import type { Event } from '../../models/models';
import { AuthService } from '../../services/auth.service';
import { ModalService } from '../../services/modal.service';
import { ToastService } from '../../services/toast.service';
import { AdminModerationComponent } from './admin-moderation.component';

const URL = `${environment.apiUrl}/events/`;

const pending = (id: number): Event =>
  ({
    id,
    title: `Pending ${id}`,
    description: 'About',
    organizer: { id: 9, username: 'host', first_name: '', last_name: '' },
    date: '2026-12-11T19:00:00Z',
    location: 'Almaty',
    status: 'pending',
    is_free: true,
    is_online: false,
    max_participants: 50,
  }) as Event;

const items = (from: number, to: number) =>
  Array.from({ length: to - from + 1 }, (_, i) => pending(from + i));

function setup() {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, AdminModerationComponent],
    providers: [
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: AuthService, useValue: { currentUser: { is_superuser: true } } },
      { provide: ModalService, useValue: { open: vi.fn().mockResolvedValue(true) } },
    ],
  });
  const http = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(AdminModerationComponent);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const q = (testId: string) => el.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
  const rows = () => Array.from(el.querySelectorAll('[data-testid="pending-item"]'));
  const titles = () => rows().map((r) => r.querySelector('a')!.textContent.trim());
  const expectPage = (page: number) => {
    const req = http.expectOne((r) => r.url === URL);
    expect(req.request.params.get('status')).toBe('pending');
    expect(req.request.params.get('page')).toBe(String(page));
    return req;
  };
  const toasts = TestBed.inject(ToastService);
  return { http, fixture, el, q, rows, titles, expectPage, toasts };
}

describe('AdminModerationComponent pending queue', () => {
  it('shows the real total, the position in the queue and a polite announcement', () => {
    const { fixture, el, q, rows, expectPage } = setup();
    expectPage(1).flush({ count: 5, next: 'n', previous: null, results: items(1, 2) });
    fixture.detectChanges();
    expect(el.textContent).toContain('Awaiting approval (5)');
    expect(rows()).toHaveLength(2);
    expect(q('pending-counter')!.textContent.trim()).toBe('2 of 5');
    const live = q('live-region')!;
    expect(live.getAttribute('aria-live')).toBe('polite');
    expect(live.textContent.trim()).toBe('Showing 2 of 5 events');
    expect(q('pending-more')).not.toBeNull();
  });

  it('"Show more" requests the next page, appends it and announces it', () => {
    const { fixture, q, rows, expectPage } = setup();
    expectPage(1).flush({ count: 3, next: 'n', previous: null, results: items(1, 2) });
    fixture.detectChanges();

    q('pending-more')!.click();
    fixture.detectChanges();
    expect(q('pending-more')!.hasAttribute('disabled')).toBe(true);
    expectPage(2).flush({ count: 3, next: null, previous: 'p', results: items(3, 3) });
    fixture.detectChanges();
    expect(rows()).toHaveLength(3);
    expect(q('pending-counter')!.textContent.trim()).toBe('3 of 3');
    expect(q('live-region')!.textContent.trim()).toBe('Showing 3 of 3 events');
    expect(q('pending-more')).toBeNull();
  });

  it('says the queue is empty', () => {
    const { fixture, q, expectPage } = setup();
    expectPage(1).flush({ count: 0, next: null, previous: null, results: [] });
    fixture.detectChanges();
    expect(q('pending-empty')).not.toBeNull();
    expect(q('pending-more')).toBeNull();
  });

  it('after an approve removes the item, lowers the total and asks for the right next page', async () => {
    const { http, fixture, q, titles, expectPage } = setup();
    expectPage(1).flush({ count: 5, next: 'n', previous: null, results: items(1, 2) });
    fixture.detectChanges();
    q('pending-more')!.click();
    expectPage(2).flush({ count: 5, next: 'n', previous: 'p', results: items(3, 4) });
    fixture.detectChanges();

    q('approve')!.click();
    await fixture.whenStable();
    http
      .expectOne(`${environment.apiUrl}/events/1/approve/`)
      .flush({}, { status: 200, statusText: 'OK' });
    fixture.detectChanges();
    expect(titles()).toEqual(['Pending 2', 'Pending 3', 'Pending 4']);
    expect(q('pending-counter')!.textContent.trim()).toBe('3 of 4');
    expect(q('live-region')!.textContent.trim()).toBe('Showing 3 of 4 events');

    // 3 are loaded and the page size is 2: the missing one is on page 2, which now
    // holds 4 and 5; 4 is already shown and is not repeated.
    q('pending-more')!.click();
    expectPage(2).flush({ count: 4, next: null, previous: 'p', results: items(4, 5) });
    fixture.detectChanges();
    expect(titles()).toEqual(['Pending 2', 'Pending 3', 'Pending 4', 'Pending 5']);
    expect(q('pending-counter')!.textContent.trim()).toBe('4 of 4');
    expect(q('pending-more')).toBeNull();
  });

  it('after a reject skips nothing: the next page is derived from what is loaded', async () => {
    const { http, fixture, q, titles, expectPage } = setup();
    expectPage(1).flush({ count: 3, next: 'n', previous: null, results: items(1, 2) });
    fixture.detectChanges();

    q('reject')!.click();
    await fixture.whenStable();
    http
      .expectOne(`${environment.apiUrl}/events/1/reject/`)
      .flush({}, { status: 200, statusText: 'OK' });
    fixture.detectChanges();
    expect(titles()).toEqual(['Pending 2']);
    expect(q('pending-counter')!.textContent.trim()).toBe('1 of 2');

    // One loaded, page size 2: the rest is on page 1 again.
    q('pending-more')!.click();
    expectPage(1).flush({ count: 2, next: null, previous: null, results: items(2, 3) });
    fixture.detectChanges();
    expect(titles()).toEqual(['Pending 2', 'Pending 3']);
    expect(q('pending-more')).toBeNull();
  });

  it('keeps the item and tells the user when an approve fails', async () => {
    const { http, fixture, q, rows, toasts, expectPage } = setup();
    expectPage(1).flush({ count: 2, next: null, previous: null, results: items(1, 2) });
    fixture.detectChanges();
    q('approve')!.click();
    await fixture.whenStable();
    http
      .expectOne(`${environment.apiUrl}/events/1/approve/`)
      .flush({}, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    expect(rows()).toHaveLength(2);
    expect(q('pending-counter')!.textContent.trim()).toBe('2 of 2');
    expect(toasts.toasts().length).toBe(1);
  });

  it('shows an error with Retry, and retrying reloads the first page', () => {
    const { fixture, q, rows, expectPage } = setup();
    expectPage(1).flush({}, { status: 503, statusText: 'Unavailable' });
    fixture.detectChanges();
    const error = q('pending-error')!;
    expect(error.getAttribute('role')).toBe('alert');
    expect(error.textContent.trim().length).toBeGreaterThan(0);

    error.querySelector('button')!.click();
    fixture.detectChanges();
    expectPage(1).flush({ count: 1, next: null, previous: null, results: items(1, 1) });
    fixture.detectChanges();
    expect(q('pending-error')).toBeNull();
    expect(rows()).toHaveLength(1);
  });

  it('keeps the loaded page when "show more" fails, and offers it again', () => {
    const { fixture, q, rows, expectPage } = setup();
    expectPage(1).flush({ count: 3, next: 'n', previous: null, results: items(1, 2) });
    fixture.detectChanges();
    q('pending-more')!.click();
    expectPage(2).flush({}, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    expect(rows()).toHaveLength(2);
    expect(q('pending-more-error')).not.toBeNull();
    expect(q('pending-more')!.hasAttribute('disabled')).toBe(false);
  });
});
