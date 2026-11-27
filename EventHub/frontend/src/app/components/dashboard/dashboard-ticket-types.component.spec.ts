import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { LanguageService } from '../../i18n/language.service';
import { I18nTestingModule } from '../../i18n/testing';
import type { EventAnalytics } from '../../services/event.service';
import { DashboardTicketTypesComponent } from './dashboard-ticket-types.component';
import { eventAnalytics } from './dashboard.testing';

@Component({
  standalone: true,
  imports: [DashboardTicketTypesComponent],
  template: `<app-dashboard-ticket-types [eventId]="id()" title="Gala night" />`,
})
class HostComponent {
  readonly id = signal(7);
}

const isAnalytics = (id: number) => (r: { url: string }) =>
  r.url.endsWith(`/events/${id}/analytics/`);

function setup() {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, HostComponent],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  const http = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(HostComponent);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const q = (testId: string) => el.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
  const all = (testId: string) =>
    Array.from(el.querySelectorAll<HTMLElement>(`[data-testid="${testId}"]`));
  const toggle = () => q('ticket-types-toggle') as HTMLButtonElement;
  const click = () => {
    toggle().click();
    fixture.detectChanges();
  };
  const request = () => http.expectOne(isAnalytics(7));
  const answer = (data: EventAnalytics) => {
    request().flush(data);
    fixture.detectChanges();
  };
  const cells = (row: HTMLElement) =>
    Array.from(row.querySelectorAll('th, td')).map((c) =>
      c.textContent.replace(/\s+/g, ' ').trim(),
    );
  return { http, fixture, el, q, all, toggle, click, request, answer, cells };
}

describe('DashboardTicketTypesComponent', () => {
  describe('the disclosure', () => {
    it('is closed at first, asks for nothing, and is wired for assistive technology', () => {
      const { http, q, toggle } = setup();
      http.expectNone(isAnalytics(7));
      expect(toggle().textContent.trim()).toBe('Ticket types');
      expect(toggle().getAttribute('aria-expanded')).toBe('false');
      const panel = q('ticket-types-panel')!;
      expect(toggle().getAttribute('aria-controls')).toBe(panel.id);
      expect(panel.hidden).toBe(true);
      expect(panel.children).toHaveLength(0);
    });

    it('opens on click and says so', () => {
      const { q, toggle, click, request } = setup();
      click();
      expect(toggle().getAttribute('aria-expanded')).toBe('true');
      expect(q('ticket-types-panel')!.hidden).toBe(false);
      request();
    });
  });

  describe('lazy loading', () => {
    it('fetches the event analytics on the first opening, with a skeleton meanwhile', () => {
      const { q, click, request } = setup();
      click();
      expect(q('ticket-types-loading')).not.toBeNull();
      expect(q('ticket-types-loading')!.innerHTML).toContain('motion-reduce:animate-none');
      expect(request().request.method).toBe('GET');
    });

    it('fetches only once: closing and opening again uses what it has', () => {
      const { http, q, click, answer } = setup();
      click();
      answer(eventAnalytics());
      click();
      expect(q('ticket-types-panel')!.hidden).toBe(true);
      click();
      http.expectNone(isAnalytics(7));
      expect(q('ticket-types-table')).not.toBeNull();
    });

    it('does not ask twice when opened and closed again while still loading', () => {
      const { http, click } = setup();
      click();
      click();
      click();
      http.expectOne(isAnalytics(7));
    });
  });

  describe('the table', () => {
    it('shows sold, remaining or unlimited, and revenue per tier', () => {
      const { all, cells, click, answer } = setup();
      click();
      answer(eventAnalytics());
      const rows = all('ticket-types-row').map(cells);
      expect(rows).toHaveLength(2);
      expect(rows[0][0]).toBe('Standard');
      expect(rows[0][1]).toBe('6');
      expect(rows[0][2]).toBe('4');
      expect(rows[0][3]).toMatch(/KZT\s*60,000\.00/);
      expect(rows[1][0]).toBe('General');
      expect(rows[1][1]).toBe('3');
      expect(rows[1][2]).toBe('Unlimited');
      expect(rows[1][3]).toMatch(/KZT\s*30,000\.00/);
    });

    it('shows a sold-out tier as 0 left, not as unlimited', () => {
      const { all, cells, click, answer } = setup();
      click();
      answer(
        eventAnalytics({
          by_ticket_type: [{ name: 'VIP', count: 5, revenue: 100000, quantity: 5, remaining: 0 }],
        }),
      );
      expect(cells(all('ticket-types-row')[0])[2]).toBe('0');
    });

    it('gives group bookings their own label, translated', async () => {
      const { all, cells, click, answer, fixture } = setup();
      click();
      answer(
        eventAnalytics({
          by_ticket_type: [
            { name: 'Group booking', count: 8, revenue: 80000, quantity: null, remaining: null },
          ],
        }),
      );
      expect(cells(all('ticket-types-row')[0])[0]).toBe('Group booking');
      await TestBed.inject(LanguageService).setLang('ru');
      fixture.detectChanges();
      expect(cells(all('ticket-types-row')[0])[0]).toBe('Групповое бронирование');
      expect(cells(all('ticket-types-row')[0])[2]).toBe('Без ограничений');
    });

    it('shows a tier the organizer named exactly as typed, even when it reads like a server row', () => {
      const { all, cells, click, answer } = setup();
      click();
      answer(
        eventAnalytics({
          by_ticket_type: [
            { name: 'Group booking', count: 1, revenue: 1, quantity: 10, remaining: 9 },
          ],
        }),
      );
      expect(cells(all('ticket-types-row')[0])[0]).toBe('Group booking');
      expect(cells(all('ticket-types-row')[0])[2]).toBe('9');
    });

    it('lists two tiers with the same name as two rows', () => {
      const { all, click, answer } = setup();
      click();
      answer(
        eventAnalytics({
          by_ticket_type: [
            { name: 'Early', count: 1, revenue: 10, quantity: 5, remaining: 4 },
            { name: 'Early', count: 2, revenue: 20, quantity: 5, remaining: 3 },
          ],
        }),
      );
      expect(all('ticket-types-row')).toHaveLength(2);
    });

    it('shows revenue in the currency of the event', () => {
      const { all, cells, click, answer } = setup();
      click();
      answer(
        eventAnalytics({
          currency: 'USD',
          by_ticket_type: [{ name: 'Std', count: 2, revenue: 50, quantity: null, remaining: null }],
        }),
      );
      expect(cells(all('ticket-types-row')[0])[3]).toBe('$50.00');
    });

    it('is a table with a caption and column headers', () => {
      const { q, click, answer } = setup();
      click();
      answer(eventAnalytics());
      const table = q('ticket-types-table')!;
      expect(table.querySelector('caption')!.textContent.trim()).toBe('Ticket types of Gala night');
      expect(
        Array.from(table.querySelectorAll('thead th')).map((h) => h.textContent.trim()),
      ).toEqual(['Type', 'Sold', 'Left', 'Revenue']);
      expect(table.parentElement!.classList).toContain('overflow-x-auto');
      expect(q('ticket-types-revenue')!.classList).toContain('whitespace-nowrap');
    });

    it('says nothing was sold yet when the event has no sales', () => {
      const { q, click, answer } = setup();
      click();
      answer(eventAnalytics({ by_ticket_type: [] }));
      expect(q('ticket-types-empty')!.textContent.trim()).toBe('No tickets sold yet.');
      expect(q('ticket-types-table')).toBeNull();
    });
  });

  describe('a failed load', () => {
    it('shows the error inside the section, and a retry that loads it', () => {
      const { http, q, all, click, request, answer, fixture } = setup();
      click();
      request().flush({}, { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();
      expect(q('ticket-types-error')!.getAttribute('role')).toBe('alert');
      expect(q('ticket-types-table')).toBeNull();

      q('ticket-types-error')!.querySelector('button')!.click();
      fixture.detectChanges();
      expect(q('ticket-types-loading')).not.toBeNull();
      answer(eventAnalytics());
      expect(q('ticket-types-error')).toBeNull();
      expect(all('ticket-types-row')).toHaveLength(2);
      http.verify();
    });

    it('tries again when the section is closed and opened after a failure', () => {
      const { http, q, click, request, fixture } = setup();
      click();
      request().flush({}, { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();
      click();
      click();
      http.expectOne(isAnalytics(7));
      expect(q('ticket-types-loading')).not.toBeNull();
    });

    it('does not fail when the card goes away while loading', () => {
      const { fixture, click, request } = setup();
      click();
      const req = request();
      fixture.destroy();
      expect(req.cancelled).toBe(true);
    });
  });
});
