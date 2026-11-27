import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { I18nTestingModule } from '../../i18n/testing';
import { LanguageService } from '../../i18n/language.service';
import type { OrganizerEvent } from '../../services/organizer-dashboard.service';
import { DashboardEventCardComponent } from './dashboard-event-card.component';
import { organizerEvent } from './dashboard.testing';

@Component({
  standalone: true,
  imports: [DashboardEventCardComponent],
  template: `
    <button type="button" id="outside">outside</button>
    <app-dashboard-event-card
      [event]="ev()"
      [menuOpen]="open()"
      [duplicating]="duplicating()"
      (menuOpenChange)="open.set($event)"
      (duplicate)="duplicated = duplicated + 1"
      (remove)="removed = removed + 1"
    />
  `,
})
class HostComponent {
  readonly ev = signal<OrganizerEvent>(organizerEvent(1));
  readonly open = signal(false);
  readonly duplicating = signal(false);
  duplicated = 0;
  removed = 0;
}

function render(event: OrganizerEvent = organizerEvent(1)) {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, HostComponent],
    providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(HostComponent);
  fixture.componentInstance.ev.set(event);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  // The element type is the caller's claim, like querySelector<T> itself.
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters
  const q = <T extends HTMLElement = HTMLElement>(testId: string) =>
    el.querySelector<T>(`[data-testid="${testId}"]`);
  const text = (testId: string) => q(testId)?.textContent.replace(/\s+/g, ' ').trim() ?? null;
  const flush = async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  };
  return { fixture, host: fixture.componentInstance, el, q, text, flush };
}

describe('DashboardEventCardComponent', () => {
  describe('status', () => {
    it.each([
      ['draft', 'Draft'],
      ['pending', 'Pending approval'],
      ['published', 'Published'],
      ['completed', 'Completed'],
      ['rejected', 'Rejected'],
      ['cancelled', 'Cancelled'],
    ] as const)('shows only the translated badge for %s', (status, label) => {
      const { el, text } = render(organizerEvent(1, { status }));
      expect(text('status-badge')).toBe(label);
      // The raw English status code is not shown anywhere on the card.
      expect(el.textContent).not.toContain(status);
    });

    it('shows the badge in the active language', async () => {
      const { fixture, text } = render(organizerEvent(1, { status: 'published' }));
      await TestBed.inject(LanguageService).setLang('ru');
      fixture.detectChanges();
      expect(text('status-badge')).toBe('Опубликовано');
    });
  });

  describe('capacity', () => {
    it('fills the bar by the real percentage and labels it', () => {
      const { q, text } = render(
        organizerEvent(1, { stats: { sold_through_pct: 42.5, tickets_sold: 17, capacity: 40 } }),
      );
      expect(q('capacity-bar')!.style.width).toBe('42.5%');
      expect(text('capacity-label')).toBe('42.5% sold');
      expect(text('capacity-count')).toBe('17/40');
    });

    it('clamps the bar to 100% but labels the real figure as overbooked', () => {
      const { q, text, el } = render(
        organizerEvent(1, { stats: { sold_through_pct: 135, tickets_sold: 54, capacity: 40 } }),
      );
      expect(q('capacity-bar')!.style.width).toBe('100%');
      expect(text('capacity-label')).toBe('135% sold, overbooked');
      expect(q('capacity-label')!.className).toContain('text-destructive');
      expect(el.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('100');
    });

    it('does not mark exactly full as overbooked', () => {
      const { q, text } = render(organizerEvent(1, { stats: { sold_through_pct: 100 } }));
      expect(q('capacity-bar')!.style.width).toBe('100%');
      expect(text('capacity-label')).toBe('100% sold');
    });

    it('keeps an empty bar for an event with no sales', () => {
      const { q } = render(organizerEvent(1, { stats: { sold_through_pct: 0, tickets_sold: 0 } }));
      expect(q('capacity-bar')!.style.width).toBe('0%');
    });
  });

  describe('numbers', () => {
    it('shows tickets sold, pending, check-in rate and count from the stats', () => {
      const { text } = render(
        organizerEvent(1, {
          stats: { tickets_sold: 12, pending: 4, checkin_rate_pct: 58.3, checked_in: 7 },
        }),
      );
      expect(text('tickets-sold')).toBe('12');
      expect(text('pending-count')).toBe('Pending: 4');
      expect(text('checkin-rate')).toBe('58.3%');
      expect(text('dashboard-event')).toContain('7 checked in');
    });

    it('shows revenue of a paid event in its own currency', () => {
      const { text } = render(
        organizerEvent(1, { stats: { net_revenue: '45000.00', currency: 'KZT' } }),
      );
      expect(text('event-revenue')).toMatch(/KZT\s*45[,\s]?000/);
    });

    it('shows revenue of a paid event even when it is zero, never in dollars by default', () => {
      const { text } = render(
        organizerEvent(1, { stats: { net_revenue: '0.00', currency: 'KZT' } }),
      );
      expect(text('event-revenue')).toContain('KZT');
      expect(text('event-revenue')).not.toContain('$');
    });

    it('hides revenue of a free event with no money in', () => {
      const { q } = render(organizerEvent(1, { is_free: true, stats: { net_revenue: '0.00' } }));
      expect(q('event-revenue')).toBeNull();
    });

    it('shows revenue of a free event that took donations', () => {
      const { q } = render(organizerEvent(1, { is_free: true, stats: { net_revenue: '1500.00' } }));
      expect(q('event-revenue')).not.toBeNull();
    });
  });

  describe('links and ownership', () => {
    it('links to the attendees and the public page', () => {
      const { q } = render(organizerEvent(7));
      expect(q('attendees-link')!.getAttribute('href')).toBe('/organizer/events/7/attendees');
      expect(q('view-link')!.getAttribute('href')).toBe('/events/7');
    });

    it('shows a co-organizer badge and no Delete item when the user does not own the event', async () => {
      const { host, q, flush } = render(organizerEvent(1, { is_owner: false }));
      expect(q('coorganizer-badge')?.textContent.trim()).toBe('Co-organizer');
      host.open.set(true);
      await flush();
      expect(q('menu-edit')).not.toBeNull();
      expect(q('menu-duplicate')).not.toBeNull();
      expect(q('menu-delete')).toBeNull();
    });

    it('offers Delete, and no co-organizer badge, to the owner', async () => {
      const { host, q, flush } = render(organizerEvent(1, { is_owner: true }));
      expect(q('coorganizer-badge')).toBeNull();
      host.open.set(true);
      await flush();
      q('menu-delete')!.click();
      expect(host.removed).toBe(1);
    });
  });

  describe('actions menu', () => {
    it('is a button with aria-haspopup and aria-expanded that opens a role=menu', async () => {
      const { host, q, el, flush } = render();
      const trigger = q('menu-trigger')!;
      expect(trigger.getAttribute('aria-haspopup')).toBe('menu');
      expect(trigger.getAttribute('aria-expanded')).toBe('false');
      expect(el.querySelector('[role="menu"]')).toBeNull();

      trigger.click();
      await flush();
      expect(host.open()).toBe(true);
      expect(trigger.getAttribute('aria-expanded')).toBe('true');
      expect(el.querySelectorAll('[role="menu"] [role="menuitem"]').length).toBe(3);
      expect(trigger.getAttribute('aria-controls')).toBe(el.querySelector('[role="menu"]')!.id);
    });

    it('gives the icon-only button an accessible name with the event title', () => {
      const { q } = render(organizerEvent(1, { title: 'Jazz Night' }));
      expect(q('menu-trigger')!.getAttribute('aria-label')).toBe('Menu for Jazz Night');
    });

    it('moves focus into the menu when it opens', async () => {
      const { host, q, flush } = render();
      host.open.set(true);
      await flush();
      expect(document.activeElement).toBe(q('menu-edit'));
    });

    it('closes on Esc and returns focus to its button', async () => {
      const { host, q, flush } = render();
      host.open.set(true);
      await flush();
      q('menu-edit')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await flush();
      expect(host.open()).toBe(false);
      expect(document.activeElement).toBe(q('menu-trigger'));
      expect(q('menu-trigger')!.getAttribute('aria-expanded')).toBe('false');
    });

    it('closes on a click outside, and stays open on a click inside the menu', async () => {
      const { host, el, q, flush } = render();
      host.open.set(true);
      await flush();
      q('menu-duplicate')!.click();
      await flush();
      expect(host.open()).toBe(true);

      el.querySelector<HTMLElement>('#outside')!.click();
      await flush();
      expect(host.open()).toBe(false);
    });

    it('moves between items with the arrow keys, Home and End, wrapping around', async () => {
      const { host, q, flush } = render();
      host.open.set(true);
      await flush();
      const menu = q('menu-edit')!.parentElement!;
      const press = (key: string) =>
        menu.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
      press('ArrowDown');
      expect(document.activeElement).toBe(q('menu-duplicate'));
      press('ArrowDown');
      expect(document.activeElement).toBe(q('menu-delete'));
      press('ArrowDown');
      expect(document.activeElement).toBe(q('menu-edit'));
      press('ArrowUp');
      expect(document.activeElement).toBe(q('menu-delete'));
      press('Home');
      expect(document.activeElement).toBe(q('menu-edit'));
      press('End');
      expect(document.activeElement).toBe(q('menu-delete'));
    });

    it('closes when Tab leaves it', async () => {
      const { host, q, flush } = render();
      host.open.set(true);
      await flush();
      q('menu-edit')!.parentElement!.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }),
      );
      await flush();
      expect(host.open()).toBe(false);
    });

    it('moves focus to its button when Tab leaves the menu, and does not swallow the Tab', async () => {
      const { host, q, flush } = render();
      host.open.set(true);
      await flush();
      expect(document.activeElement).toBe(q('menu-edit'));
      const tab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
      q('menu-edit')!.parentElement!.dispatchEvent(tab);
      await flush();
      expect(host.open()).toBe(false);
      // The focused item is gone with the menu: focus must not fall back to the page.
      expect(document.activeElement).toBe(q('menu-trigger'));
      expect(tab.defaultPrevented).toBe(false);
    });

    it('has its document listeners only while the menu is open', async () => {
      const add = vi.spyOn(document, 'addEventListener');
      const remove = vi.spyOn(document, 'removeEventListener');
      const count = (spy: typeof add, type: string) =>
        spy.mock.calls.filter((call) => call[0] === type).length;
      const { host, flush } = render();
      expect(count(add, 'click')).toBe(0);
      expect(count(add, 'keydown')).toBe(0);

      host.open.set(true);
      await flush();
      expect(count(add, 'click')).toBe(1);
      expect(count(add, 'keydown')).toBe(1);

      host.open.set(false);
      await flush();
      expect(count(remove, 'click')).toBe(1);
      expect(count(remove, 'keydown')).toBe(1);
      add.mockRestore();
      remove.mockRestore();
    });

    it('disables Duplicate while a copy is being made', async () => {
      const { host, q, flush } = render();
      host.open.set(true);
      await flush();
      expect(q<HTMLButtonElement>('menu-duplicate')!.disabled).toBe(false);
      q('menu-duplicate')!.click();
      expect(host.duplicated).toBe(1);

      host.duplicating.set(true);
      await flush();
      expect(q<HTMLButtonElement>('menu-duplicate')!.disabled).toBe(true);
      expect(q('menu-duplicate')!.textContent).toContain('Duplicating');
    });
  });
});
