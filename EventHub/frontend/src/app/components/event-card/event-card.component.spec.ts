import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { EventCardComponent } from './event-card.component';
import { I18nTestingModule } from '../../i18n/testing';
import type { Event } from '../../models/models';

function eventWith(overrides: Partial<Event>): Event {
  return {
    id: 1,
    title: 'Jazz Night',
    location: 'KBTU, Almaty',
    date: '2026-12-11T19:00:00Z',
    category: { id: 1, name: 'Music', icon: 'music', event_count: 1 },
    price: '0.00',
    price_from: '0.00',
    currency: 'KZT',
    is_free: true,
    is_online: false,
    has_ticket_types: false,
    available_spots: 50,
    max_participants: 100,
    ...overrides,
  } as Event;
}

function priceText(event: Event): string {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, EventCardComponent],
    providers: [provideRouter([])],
  });
  const fixture = TestBed.createComponent(EventCardComponent);
  fixture.componentInstance.event = event;
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  return (
    el.querySelector('[data-testid="card-price"]')?.textContent.replace(/\s+/g, ' ').trim() ?? ''
  );
}

describe('EventCardComponent price label', () => {
  it('says Free for a free event, never a zero amount', () => {
    const text = priceText(eventWith({}));
    expect(text).toBe('Free');
    expect(text).not.toMatch(/0\s*₸/);
  });

  it('shows the cheapest tier with "from" when the base price is zero', () => {
    const text = priceText(
      eventWith({ is_free: false, has_ticket_types: true, price: '0.00', price_from: '5000.00' }),
    );
    expect(text).toMatch(/^from \D*5[\s,.]?000/);
  });

  it('says Free when the cheapest tier costs nothing (free + donation tiers)', () => {
    const text = priceText(
      eventWith({ is_free: false, has_ticket_types: true, price: '0.00', price_from: '0.00' }),
    );
    expect(text).toBe('Free');
  });

  it('shows the plain price for an event without ticket types', () => {
    const text = priceText(eventWith({ is_free: false, price: '9000.00', price_from: '9000.00' }));
    expect(text).toMatch(/9[\s,.]?000/);
    expect(text).not.toContain('from');
  });

  it('never labels the first card as Featured', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [I18nTestingModule, EventCardComponent],
      providers: [provideRouter([])],
    });
    const fixture = TestBed.createComponent(EventCardComponent);
    fixture.componentInstance.event = eventWith({});
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Featured');
  });
});
