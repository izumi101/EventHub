import { Component, EventEmitter, Input, Output } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { EventCheckoutModalComponent } from './event-checkout-modal.component';
import { SeatSelectorComponent } from '../seat-selector/seat-selector.component';
import { EventService, type RegisterPayload } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import type { Event, Seat } from '../../models/models';
import { I18nTestingModule } from '../../i18n/testing';

// The real seat selector opens a WebSocket; the modal only needs its output.
@Component({ selector: 'app-seat-selector', standalone: true, template: '' })
class SeatSelectorStub {
  @Input() seats: Seat[] = [];
  @Input() eventId: number | null = null;
  @Input() currency = 'USD';
  @Output() readonly seatSelected = new EventEmitter<Seat | null>();
}

const seat = (id: number, price: string | null): Seat =>
  ({ id, row: 'A', col: id, price, price_zone: 'standard' }) as unknown as Seat;

const eventWith = (over: Record<string, unknown> = {}): Event =>
  ({
    id: 7,
    title: 'Gig',
    currency: 'KZT',
    price: '100.00',
    is_free: false,
    has_ticket_types: false,
    ticket_types: [],
    tax_percent: '0',
    service_fee_percent: '0',
    fees_passed_to_buyer: false,
    ...over,
  }) as unknown as Event;

type SeatMapResult = 'general-admission' | 'error' | { seats: Seat[] };

function setup(event: Event, opts: { seatMap?: SeatMapResult; gaPrice?: string } = {}) {
  const seatMap = opts.seatMap ?? 'general-admission';
  const eventService = {
    getEventQuestions: vi.fn(() => of([])),
    getSeatMap: vi.fn(() => {
      if (seatMap === 'general-admission')
        return throwError(() => ({ status: 404, error: { detail: 'Not found' } }));
      if (seatMap === 'error') return throwError(() => ({ status: 500 }));
      return of(seatMap);
    }),
    validatePromo: vi.fn(),
  };
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, EventCheckoutModalComponent],
    providers: [{ provide: EventService, useValue: eventService }],
  });
  TestBed.overrideComponent(EventCheckoutModalComponent, {
    remove: { imports: [SeatSelectorComponent] },
    add: { imports: [SeatSelectorStub] },
  });
  const fixture = TestBed.createComponent(EventCheckoutModalComponent);
  fixture.componentRef.setInput('event', event);
  fixture.componentRef.setInput('currentGaPrice', opts.gaPrice ?? '100.00');
  fixture.detectChanges();
  const cmp = fixture.componentInstance;
  const emitted: RegisterPayload[] = [];
  cmp.confirmed.subscribe((p) => emitted.push(p));
  const toasts = () => TestBed.inject(ToastService).toasts();
  const text = () => (fixture.nativeElement as HTMLElement).textContent;
  return { fixture, cmp, eventService, emitted, toasts, text };
}

const tier = (over: Record<string, unknown>) =>
  ({
    id: 1,
    name: 'Standard',
    kind: 'paid',
    price: '50.00',
    sale_state: 'on_sale',
    available: null,
    ...over,
  }) as never;

describe('EventCheckoutModalComponent price breakdown', () => {
  it('charges the dynamic GA price when no seat or tier is picked', () => {
    const { cmp } = setup(eventWith(), { gaPrice: '80.00' });
    expect(cmp.checkoutSubtotal).toBe('80.00');
    expect(cmp.checkoutTotal).toBe('80.00');
  });

  it('prefers the selected seat price over the GA price and recomputes when the seat changes', () => {
    const { cmp } = setup(eventWith(), { gaPrice: '80.00' });
    cmp.selectedSeat = seat(1, '150.00');
    expect(cmp.checkoutTotal).toBe('150.00');
    cmp.selectedSeat = seat(2, '40.00');
    expect(cmp.checkoutTotal).toBe('40.00');
    cmp.selectedSeat = seat(3, null); // no zone price: falls back to the event price
    expect(cmp.checkoutTotal).toBe('100.00');
  });

  it('adds tax and service fee on top when fees are passed to the buyer', () => {
    const { cmp, fixture, text } = setup(
      eventWith({ tax_percent: '12', service_fee_percent: '5', fees_passed_to_buyer: true }),
    );
    expect(cmp.checkoutSubtotal).toBe('100.00');
    expect(cmp.taxAmount).toBeCloseTo(12, 10);
    expect(cmp.feeAmount).toBeCloseTo(5, 10);
    expect(cmp.checkoutTotal).toBe('117.00');
    expect(cmp.showFeeLines()).toBe(true);
    fixture.detectChanges();
    expect(text()).toContain('Tax (12%)');
    expect(text()).toContain('Service fee (5%)');
  });

  it('keeps the total at the subtotal and hides fee lines when the organizer absorbs fees', () => {
    const { cmp, fixture, text } = setup(
      eventWith({ tax_percent: '12', service_fee_percent: '5', fees_passed_to_buyer: false }),
    );
    expect(cmp.checkoutTotal).toBe('100.00');
    expect(cmp.showFeeLines()).toBe(false);
    fixture.detectChanges();
    expect(text()).not.toContain('Tax (');
  });

  it('applies a percent promo before tax and fees', () => {
    const { cmp } = setup(eventWith({ tax_percent: '10', fees_passed_to_buyer: true }));
    cmp.promoQuote = { code: 'HALF', discount_type: 'percent', discount_value: '50' } as never;
    expect(cmp.checkoutSubtotal).toBe('50.00');
    expect(cmp.checkoutTotal).toBe('55.00'); // 50 + 10% tax on the discounted price
  });

  it('applies a fixed promo and never lets the price go below zero', () => {
    const { cmp } = setup(eventWith({ tax_percent: '10', fees_passed_to_buyer: true }));
    cmp.promoQuote = { code: 'M30', discount_type: 'fixed', discount_value: '30' } as never;
    expect(cmp.checkoutSubtotal).toBe('70.00');
    cmp.promoQuote = { code: 'BIG', discount_type: 'fixed', discount_value: '500' } as never;
    expect(cmp.checkoutSubtotal).toBe('0.00');
    expect(cmp.taxAmount).toBe(0);
    expect(cmp.checkoutTotal).toBe('0.00');
  });

  it('shows the promo error from the backend and keeps no quote when the code is rejected', () => {
    const { cmp, eventService } = setup(eventWith());
    eventService.validatePromo.mockReturnValue(
      throwError(() => ({ status: 400, error: { error: 'Promo code expired' } })),
    );
    cmp.promoInput = ' EXPIRED ';
    cmp.applyPromo();
    expect(eventService.validatePromo).toHaveBeenCalledWith(7, 'EXPIRED', {});
    expect(cmp.promoError).toBe('Promo code expired');
    expect(cmp.promoQuote).toBeNull();
    expect(cmp.checkingPromo).toBe(false);
  });

  it('quotes the promo against the selected seat', () => {
    const { cmp, eventService } = setup(eventWith());
    eventService.validatePromo.mockReturnValue(
      of({ code: 'X', discount_type: 'percent', discount_value: '10', savings: '15.00' }),
    );
    cmp.selectedSeat = seat(5, '150.00');
    cmp.promoInput = 'x';
    cmp.applyPromo();
    expect(eventService.validatePromo).toHaveBeenCalledWith(7, 'x', { seat_id: 5 });
    expect(cmp.checkoutSubtotal).toBe('135.00');
  });
});

describe('EventCheckoutModalComponent validation and payload', () => {
  it('blocks confirmation until a seat is selected on a seat-map event, then sends seat_id', () => {
    const { cmp, emitted, toasts, fixture, text } = setup(eventWith(), {
      seatMap: { seats: [seat(1, '100.00')] },
    });
    fixture.detectChanges();
    expect(cmp.canConfirm()).toBe(false);
    expect(text()).toContain('Select a seat to continue');

    cmp.submit();
    expect(emitted).toEqual([]);
    expect(toasts().map((t) => t.message)).toContain('Please select a seat');

    cmp.selectedSeat = seat(1, '100.00');
    expect(cmp.canConfirm()).toBe(true);
    cmp.submit();
    expect(emitted).toHaveLength(1);
    expect(emitted[0].seat_id).toBe(1);
  });

  it('lets a paid event without a seat map (404) go ahead as general admission', () => {
    const { cmp, emitted } = setup(eventWith(), { seatMap: 'general-admission' });
    expect(cmp.seatMapMissing).toBe(true);
    expect(cmp.canConfirm()).toBe(true);
    cmp.registrationNotes = 'vegan';
    cmp.submit();
    expect(emitted).toEqual([{ notes: 'vegan' }]);
  });

  it('does not treat a seat-map server error as general admission', () => {
    const { cmp, toasts } = setup(eventWith(), { seatMap: 'error' });
    expect(cmp.seatMapMissing).toBe(false);
    expect(cmp.canConfirm()).toBe(false);
    expect(toasts().map((t) => t.message)).toContain('Failed to load seat map');
  });

  it('rejects a donation below the tier minimum and accepts it once raised', () => {
    const donation = tier({ id: 3, kind: 'donation', price: '10.00', name: 'Support' });
    const { cmp, emitted, toasts } = setup(
      eventWith({ has_ticket_types: true, ticket_types: [donation] }),
    );
    cmp.selectTicketType(donation);
    expect(cmp.donationAmount).toBe(10); // prefilled with the minimum

    cmp.donationAmount = 5;
    cmp.submit();
    expect(emitted).toEqual([]);
    expect(toasts().some((t) => t.type === 'error' && t.message.includes('10'))).toBe(true);

    cmp.donationAmount = 25;
    expect(cmp.checkoutTotal).toBe('25.00');
    cmp.submit();
    expect(emitted).toHaveLength(1);
    expect(emitted[0]).toMatchObject({ ticket_type_id: 3, donation_amount: 25 });
  });

  it('requires a ticket tier on a tiered event and ignores tiers that are not on sale', () => {
    const soldOut = tier({ id: 9, sale_state: 'sold_out' });
    const { cmp, emitted, toasts } = setup(
      eventWith({ has_ticket_types: true, ticket_types: [soldOut] }),
    );
    cmp.selectTicketType(soldOut);
    expect(cmp.selectedTicketType).toBeNull();
    cmp.submit();
    expect(emitted).toEqual([]);
    expect(toasts().map((t) => t.message)).toContain('Please choose a ticket');
  });

  it('treats a free tier as unpaid: total 0, no payment step, and drops an applied promo', () => {
    const free = tier({ id: 4, kind: 'free', price: '0.00' });
    const { cmp } = setup(eventWith({ has_ticket_types: true, ticket_types: [free] }));
    cmp.promoQuote = { code: 'X', discount_type: 'percent', discount_value: '10' } as never;
    cmp.selectTicketType(free);
    expect(cmp.promoQuote).toBeNull();
    expect(cmp.checkoutTotal).toBe('0.00');
    expect(cmp.confirmIsPaid()).toBe(false);
  });

  it('blocks submit when a required organizer question is unanswered', () => {
    const { cmp, emitted, toasts } = setup(eventWith(), { seatMap: 'general-admission' });
    cmp.questions = [
      { id: 1, label: 'Company', is_required: true, question_type: 'text' } as never,
    ];
    cmp.submit();
    expect(emitted).toEqual([]);
    expect(toasts().map((t) => t.message)).toContain('Please answer: Company');
  });

  it('sends the applied promo code in the registration payload', () => {
    const { cmp, emitted } = setup(eventWith(), { seatMap: 'general-admission' });
    cmp.promoQuote = { code: 'SAVE10', discount_type: 'percent', discount_value: '10' } as never;
    cmp.submit();
    expect(emitted[0].promo_code).toBe('SAVE10');
  });
});
