import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { LanguageService } from '../../i18n/language.service';
import { I18nTestingModule } from '../../i18n/testing';
import type { EventAnalytics } from '../../services/event.service';
import { eventAnalytics } from '../dashboard/dashboard.testing';
import { EventAnalyticsComponent } from './event-analytics.component';

async function setup(analytics: EventAnalytics = eventAnalytics()) {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule],
    providers: [
      provideRouter([
        { path: 'organizer/events/:id/analytics', component: EventAnalyticsComponent },
      ]),
      provideHttpClient(),
      provideHttpClientTesting(),
    ],
  });
  const http = TestBed.inject(HttpTestingController);
  const harness = await RouterTestingHarness.create();
  await harness.navigateByUrl('/organizer/events/5/analytics', EventAnalyticsComponent);
  http.expectOne((r) => r.url.endsWith('/events/5/')).flush({ id: 5, title: 'Gala night' });
  http.expectOne((r) => r.url.endsWith('/events/5/analytics/')).flush(analytics);
  harness.detectChanges();
  const el = harness.routeNativeElement!;
  const rows = () =>
    Array.from(el.querySelectorAll<HTMLElement>('[data-testid="ticket-type-row"]')).map((row) => ({
      name: row.querySelector('span')!.textContent.replace(/\s+/g, ' ').trim(),
      stock: row
        .querySelector('[data-testid="ticket-type-stock"]')!
        .textContent.replace(/\s+/g, ' ')
        .trim(),
      figures: row.querySelector(':scope > span')!.textContent.replace(/\s+/g, ' ').trim(),
    }));
  return { el, rows, harness };
}

describe('EventAnalyticsComponent: sales by ticket type', () => {
  it('shows what is left of each tier, and unlimited for a tier without a cap', async () => {
    const { rows } = await setup();
    const [standard, general] = rows();
    expect(standard.name).toBe('Standard');
    expect(standard.stock).toBe('4 left of 10');
    expect(standard.figures).toMatch(/^6 · KZT\s*60,000\.00$/);
    expect(general.name).toBe('General');
    expect(general.stock).toBe('Unlimited');
    expect(general.figures).toMatch(/^3 · KZT\s*30,000\.00$/);
  });

  it('shows a sold-out tier as 0 left of its quantity', async () => {
    const { rows } = await setup(
      eventAnalytics({
        by_ticket_type: [{ name: 'VIP', count: 5, revenue: 100000, quantity: 5, remaining: 0 }],
      }),
    );
    expect(rows()[0].stock).toBe('0 left of 5');
  });

  it('names group bookings with their own label, which is unlimited', async () => {
    const { rows } = await setup(
      eventAnalytics({
        by_ticket_type: [
          { name: 'Group booking', count: 8, revenue: 80000, quantity: null, remaining: null },
        ],
      }),
    );
    expect(rows()[0].name).toBe('Group booking');
    expect(rows()[0].stock).toBe('Unlimited');
  });

  it('lists tiers that share a name as separate rows', async () => {
    const { rows } = await setup(
      eventAnalytics({
        by_ticket_type: [
          { name: 'Early', count: 1, revenue: 10, quantity: 5, remaining: 4 },
          { name: 'Early', count: 2, revenue: 20, quantity: 5, remaining: 3 },
        ],
      }),
    );
    expect(rows().map((r) => r.stock)).toEqual(['4 left of 5', '3 left of 5']);
  });

  it('keeps a long amount inside its row', async () => {
    const { el } = await setup(
      eventAnalytics({
        by_ticket_type: [
          {
            name: 'A very long ticket type name that keeps going and going',
            count: 12000,
            revenue: 4367625000.5,
            quantity: null,
            remaining: null,
          },
        ],
      }),
    );
    const row = el.querySelector('[data-testid="ticket-type-row"]')!;
    expect(row.querySelector('.whitespace-nowrap')!.textContent).toMatch(/4,367,625,000\.50/);
    expect(row.querySelector('.min-w-0')).not.toBeNull();
    expect(row.querySelector('.break-words')).not.toBeNull();
  });

  it('speaks the plural of the language', async () => {
    const { rows, harness } = await setup(
      eventAnalytics({
        by_ticket_type: [
          { name: 'A', count: 1, revenue: 1, quantity: 10, remaining: 1 },
          { name: 'B', count: 1, revenue: 1, quantity: 10, remaining: 3 },
          { name: 'C', count: 1, revenue: 1, quantity: null, remaining: null },
        ],
      }),
    );
    await TestBed.inject(LanguageService).setLang('ru');
    harness.detectChanges();
    expect(rows().map((r) => r.stock)).toEqual([
      'Остался 1 из 10',
      'Осталось 3 из 10',
      'Без ограничений',
    ]);
  });

  it('still says "No sales yet" for an event without sales', async () => {
    const { el } = await setup(eventAnalytics({ by_ticket_type: [] }));
    expect(el.textContent).toContain('No sales yet.');
  });
});
