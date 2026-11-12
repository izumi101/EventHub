import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { NEVER, of, throwError } from 'rxjs';
import { GroupBookingComponent } from './group-booking.component';
import { EventService } from '../../services/event.service';
import { BookingService } from '../../services/booking.service';
import { ToastService } from '../../services/toast.service';
import { AuthService } from '../../services/auth.service';
import { PaymentService } from '../../services/payment.service';
import type { Seat } from '../../models/models';

const NOW = new Date('2026-11-12T10:00:00Z');

const seat = (id: number, price: string): Seat =>
  ({ id, row: 'B', col: id, price, price_zone: 'standard' }) as unknown as Seat;

const holdFor = (seconds: number, over: Record<string, unknown> = {}) => ({
  id: 'bk-1',
  share_token: 'tok',
  seats: [],
  seat_count: 2,
  total_price: '200.00',
  total_due: '224.00',
  currency: 'KZT',
  hold_expires_at: new Date(NOW.getTime() + seconds * 1000).toISOString(),
  ...over,
});

function setup() {
  const eventService = {
    getEvent: vi.fn(() => of({ id: 7, title: 'Gig', currency: 'KZT' })),
    getSeatMap: vi.fn(() => of({ seats: [], zone_prices: [] })),
  };
  // The QR dialog polls the payment; these tests never settle it.
  const paymentService = { getPaymentStatus: vi.fn(() => NEVER) };
  const bookingService = {
    create: vi.fn(),
    checkout: vi.fn(),
    cancel: vi.fn(),
    get: vi.fn(),
  };
  TestBed.configureTestingModule({
    imports: [GroupBookingComponent],
    providers: [
      provideRouter([]),
      { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => '7' } } } },
      { provide: EventService, useValue: eventService },
      { provide: BookingService, useValue: bookingService },
      { provide: PaymentService, useValue: paymentService },
      { provide: AuthService, useValue: {} },
    ],
  });
  const cmp = TestBed.createComponent(GroupBookingComponent).componentInstance;
  cmp.ngOnInit();
  const toasts = () => TestBed.inject(ToastService).toasts();
  return { cmp, eventService, bookingService, toasts };
}

/** Selects two seats and holds them for `seconds`. */
function hold(s: ReturnType<typeof setup>, seconds: number) {
  s.bookingService.create.mockReturnValue(of(holdFor(seconds)));
  s.cmp.onSelection([seat(1, '100.00'), seat(2, '100.00')]);
  s.cmp.holdSeats();
}

describe('GroupBookingComponent payment flow', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('sums the selected seat prices into the selection total', () => {
    const { cmp } = setup();
    cmp.onSelection([seat(1, '10.50'), seat(2, '20.25')]);
    expect(cmp.selectionTotal).toBe('30.75');
  });

  it('holds the selected seat ids and formats the countdown as m:ss', () => {
    const s = setup();
    hold(s, 125);
    expect(s.bookingService.create).toHaveBeenCalledWith(7, [1, 2]);
    expect(s.cmp.booking?.id).toBe('bk-1');
    expect(s.cmp.countdown).toBe('2:05');
    vi.advanceTimersByTime(66_000);
    expect(s.cmp.countdown).toBe('0:59');
    expect(s.cmp.secondsLeft).toBe(59);
    s.cmp.ngOnDestroy();
  });

  it('clears the booking and selection, toasts and refreshes the seat map when the hold expires', () => {
    const s = setup();
    hold(s, 3);
    const mapCallsBefore = s.eventService.getSeatMap.mock.calls.length;

    vi.advanceTimersByTime(3_000);

    expect(s.cmp.secondsLeft).toBe(0);
    expect(s.cmp.booking).toBeNull();
    expect(s.cmp.selected).toEqual([]);
    expect(s.toasts().map((t) => t.message)).toContain('Your seat hold has expired.');
    expect(s.eventService.getSeatMap.mock.calls.length).toBe(mapCallsBefore + 1);

    // The timer is stopped: no second expiry toast and no further map reloads.
    vi.advanceTimersByTime(3_000);
    expect(s.toasts().filter((t) => t.message === 'Your seat hold has expired.')).toHaveLength(1);
    expect(s.eventService.getSeatMap.mock.calls.length).toBe(mapCallsBefore + 1);
  });

  it('stops the countdown timer when the component is destroyed', () => {
    const s = setup();
    hold(s, 100);
    s.cmp.ngOnDestroy();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('pay() sets paying and redirects the browser to the gateway checkout_url', () => {
    const s = setup();
    hold(s, 600);
    const loc = { href: 'http://localhost/group', origin: 'http://localhost' };
    vi.stubGlobal('location', loc);
    s.bookingService.checkout.mockReturnValue(of({ checkout_url: 'https://pay.example/c/1' }));

    s.cmp.pay();

    expect(s.bookingService.checkout).toHaveBeenCalledWith('bk-1');
    expect(s.cmp.paying).toBe(true); // stays true: the page is navigating away
    expect(loc.href).toBe('https://pay.example/c/1');
    s.cmp.ngOnDestroy();
  });

  it('pay() resets paying and toasts when checkout cannot be started, without redirecting', () => {
    const s = setup();
    hold(s, 600);
    const loc = { href: 'http://localhost/group', origin: 'http://localhost' };
    vi.stubGlobal('location', loc);
    s.bookingService.checkout.mockReturnValue(throwError(() => ({ status: 500 })));

    s.cmp.pay();

    expect(s.cmp.paying).toBe(false);
    expect(s.toasts().map((t) => t.message)).toContain('Payment could not be started.');
    expect(loc.href).toBe('http://localhost/group');
    s.cmp.ngOnDestroy();
  });

  it('pay() does nothing without a held booking', () => {
    const s = setup();
    s.cmp.pay();
    expect(s.bookingService.checkout).not.toHaveBeenCalled();
    expect(s.cmp.paying).toBe(false);
  });

  it('pay() shows the QR dialog for a Freedom Pay answer instead of leaving the page', () => {
    const s = setup();
    hold(s, 120);
    const loc = { href: 'http://localhost/group', origin: 'http://localhost' };
    vi.stubGlobal('location', loc);
    s.bookingService.checkout.mockReturnValue(
      of({
        checkout_url: 'http://fpay.example/pay.html?customer=1',
        mock: false,
        session_id: '1030000000001',
        provider: 'freedompay',
        payment_id: 42,
        qr_code: 'data:image/png;base64,iVBORw0KGgo=',
        amount: '224.00',
        currency: 'KZT',
      }),
    );
    // Opening the payment page extended the hold on the server.
    s.bookingService.get.mockReturnValue(of({ ...holdFor(900), status: 'holding' }));

    s.cmp.pay();

    expect(loc.href).toBe('http://localhost/group');
    expect(s.cmp.qrCheckout).toEqual(
      expect.objectContaining({ payment_id: 42, provider: 'freedompay', amount: '224.00' }),
    );
    expect(s.cmp.paying).toBe(true);
    expect(s.bookingService.get).toHaveBeenCalledWith('bk-1');
    expect(s.cmp.countdown).toBe('15:00');

    // Closing the dialog without paying lets the buyer try again.
    s.cmp.onQrClosed();
    expect(s.cmp.qrCheckout).toBeNull();
    expect(s.cmp.paying).toBe(false);
    expect(s.cmp.booking?.id).toBe('bk-1');
    s.cmp.ngOnDestroy();
  });

  it('renders the QR dialog for the booking with the amount formatted', () => {
    const s = setup();
    const fixture = TestBed.createComponent(GroupBookingComponent);
    const cmp = fixture.componentInstance;
    cmp.event = { id: 7, title: 'Gig', currency: 'KZT' } as never;
    cmp.booking = holdFor(600) as never;
    cmp.qrCheckout = {
      checkout_url: 'http://fpay.example/pay.html?customer=1',
      provider: 'freedompay',
      payment_id: 42,
      qr_code: 'data:image/png;base64,iVBORw0KGgo=',
      amount: '225000.00',
      currency: 'KZT',
    };
    s.cmp.ngOnDestroy();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('app-payment-qr')).not.toBeNull();
    expect(el.textContent).toContain('Pay for your group booking');
    expect(el.querySelector('[data-testid="qr-amount"]')!.textContent).toContain('225,000.00');
    expect(el.textContent).not.toContain('225000.00');
    fixture.destroy();
  });

  it('a page restored from the back/forward cache re-enables the pay button', () => {
    const s = setup();
    hold(s, 600);
    s.cmp.paying = true;
    s.bookingService.get.mockReturnValue(of({ ...holdFor(500), status: 'holding' }));

    s.cmp.onPageShow({ persisted: true } as PageTransitionEvent);

    expect(s.cmp.paying).toBe(false);
    expect(s.cmp.qrCheckout).toBeNull();
    expect(s.cmp.countdown).toBe('8:20');
    s.cmp.ngOnDestroy();
  });

  it('a normal page load does not touch the payment state', () => {
    const s = setup();
    hold(s, 600);
    s.cmp.paying = true;
    s.cmp.onPageShow({ persisted: false } as PageTransitionEvent);
    expect(s.cmp.paying).toBe(true);
    expect(s.bookingService.get).not.toHaveBeenCalled();
    s.cmp.ngOnDestroy();
  });

  it('release seats cancels the booking, clears state and reloads the seat map', () => {
    const s = setup();
    hold(s, 600);
    s.bookingService.cancel.mockReturnValue(of({ status: 'cancelled' }));
    const mapCallsBefore = s.eventService.getSeatMap.mock.calls.length;

    s.cmp.cancelHold();

    expect(s.bookingService.cancel).toHaveBeenCalledWith('bk-1');
    expect(s.cmp.booking).toBeNull();
    expect(s.cmp.selected).toEqual([]);
    expect(s.toasts().map((t) => t.message)).toContain('Seats released');
    expect(s.eventService.getSeatMap.mock.calls.length).toBe(mapCallsBefore + 1);
    // The countdown interval is cleared: it no longer touches the component.
    s.cmp.countdown = 'sentinel';
    vi.advanceTimersByTime(2_000);
    expect(s.cmp.countdown).toBe('sentinel');
  });

  it('keeps the hold when releasing fails', () => {
    const s = setup();
    hold(s, 600);
    s.bookingService.cancel.mockReturnValue(throwError(() => ({ status: 500 })));
    s.cmp.cancelHold();
    expect(s.cmp.booking).not.toBeNull();
    expect(s.toasts().map((t) => t.message)).toContain('Could not release seats');
    s.cmp.ngOnDestroy();
  });

  it('shows the backend reason and reloads the seat map when a seat is already taken', () => {
    const s = setup();
    s.bookingService.create.mockReturnValue(
      throwError(() => ({ status: 409, error: { error: 'Seat B1 is taken' } })),
    );
    s.cmp.onSelection([seat(1, '100.00')]);
    const mapCallsBefore = s.eventService.getSeatMap.mock.calls.length;

    s.cmp.holdSeats();

    expect(s.cmp.booking).toBeNull();
    expect(s.cmp.holding).toBe(false);
    expect(s.toasts().map((t) => t.message)).toContain('Seat B1 is taken');
    expect(s.eventService.getSeatMap.mock.calls.length).toBe(mapCallsBefore + 1);
  });
});
