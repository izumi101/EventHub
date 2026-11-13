import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { PaymentSuccessComponent } from './payment-success.component';
import { PaymentService } from '../../services/payment.service';
import { BookingService } from '../../services/booking.service';
import { AuthService } from '../../services/auth.service';
import { PaymentStatus, PaymentStatusResponse } from '../../models/models';
import { I18nTestingModule } from '../../i18n/testing';

// The Freedom Pay return (/payment/success?provider=freedompay&payment=<id>):
// the page polls the payment until it settles, never shows "processing" forever.

function status(
  value: PaymentStatus,
  registration: PaymentStatusResponse['registration_status'] = 'pending',
): PaymentStatusResponse {
  return {
    payment_id: 7,
    provider: 'freedompay',
    status: value,
    registration_id: 3,
    registration_status: registration,
    booking_id: null,
    booking_status: null,
    event_id: 1,
    event_title: 'Gig',
    amount: '5000.00',
    currency: 'KZT',
  };
}

function bookingStatus(
  value: PaymentStatus,
  booking: PaymentStatusResponse['booking_status'],
): PaymentStatusResponse {
  return {
    ...status(value),
    registration_id: null,
    registration_status: null,
    booking_id: 'bk-1',
    booking_status: booking,
    amount: '225000.00',
  };
}

function render(
  answers: PaymentStatusResponse[],
  signedIn = true,
  extraQuery: Record<string, string> = {},
) {
  const getPaymentStatus = vi.fn(() => of(answers.length > 1 ? answers.shift()! : answers[0]));
  const verifyPayment = vi.fn();
  const bookingService = { get: vi.fn(), verify: vi.fn() };
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, PaymentSuccessComponent],
    providers: [
      provideRouter([]),
      {
        provide: ActivatedRoute,
        useValue: {
          queryParams: of({
            provider: 'freedompay',
            payment: '7',
            pg_order_id: '7',
            pg_sig: 'x',
            ...extraQuery,
          }),
        },
      },
      { provide: PaymentService, useValue: { getPaymentStatus, verifyPayment } },
      { provide: BookingService, useValue: bookingService },
      { provide: AuthService, useValue: { getToken: () => (signedIn ? 'access' : null) } },
    ],
  });
  const fixture = TestBed.createComponent(PaymentSuccessComponent);
  fixture.detectChanges();
  const text = () => (fixture.nativeElement as HTMLElement).textContent || '';
  const tick = (ms: number) => {
    vi.advanceTimersByTime(ms);
    fixture.detectChanges();
  };
  return { fixture, text, tick, getPaymentStatus, verifyPayment, bookingService };
}

describe('PaymentSuccessComponent (Freedom Pay return)', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('polls the payment until it is confirmed', () => {
    const { text, tick, getPaymentStatus, verifyPayment } = render([
      status('pending'),
      status('completed', 'confirmed'),
    ]);
    tick(0);
    expect(text()).toContain('Payment is processing');
    tick(2000);
    expect(text()).toContain('Payment confirmed');
    expect(text()).toContain('5,000.00');
    expect(text()).not.toContain('5000.00 KZT');
    expect(getPaymentStatus).toHaveBeenCalledWith(7);
    expect(verifyPayment).not.toHaveBeenCalled();
    tick(10_000);
    expect(getPaymentStatus).toHaveBeenCalledTimes(2);
  });

  it('explains a payment that arrived too late as refunded', () => {
    const { text, tick } = render([status('completed', 'cancelled')]);
    tick(0);
    expect(text()).toContain('Payment refunded');
    expect(text()).not.toContain('Payment confirmed');
  });

  it('stops after a minute and offers a manual check', () => {
    const { fixture, text, tick, getPaymentStatus } = render([status('pending')]);
    tick(0);
    expect(text()).toContain('Checking with the payment provider');
    tick(60_000);
    expect(text()).toContain('Payment is processing');
    expect(text()).toContain('Check again');
    const calls = getPaymentStatus.mock.calls.length;
    tick(30_000);
    expect(getPaymentStatus.mock.calls.length).toBe(calls);

    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((b) => b.textContent.includes('Check again'))!;
    button.click();
    tick(0);
    expect(getPaymentStatus.mock.calls.length).toBe(calls + 1);
  });

  it('stops polling when the page is left', () => {
    const { fixture, tick, getPaymentStatus } = render([status('pending')]);
    tick(2000);
    fixture.destroy();
    const calls = getPaymentStatus.mock.calls.length;
    vi.advanceTimersByTime(30_000);
    expect(getPaymentStatus.mock.calls.length).toBe(calls);
  });

  it('tells a signed-out phone that paid by QR code to go back to the buyer device', () => {
    const { text, tick, getPaymentStatus } = render([status('completed', 'confirmed')], false);
    tick(0);
    expect(text()).toContain('Payment sent');
    expect(text()).toContain('device where you started the purchase');
    expect(text()).not.toContain('Verification failed');
    expect(text()).not.toContain('Payment confirmed');
    tick(10_000);
    expect(getPaymentStatus).not.toHaveBeenCalled();
  });

  it('polls a group booking payment and links to the booking once it is confirmed', () => {
    const { text, tick, getPaymentStatus, bookingService } = render(
      [bookingStatus('pending', 'holding'), bookingStatus('completed', 'confirmed')],
      true,
      { booking_id: 'bk-1' },
    );
    tick(0);
    expect(text()).toContain('Payment is processing');
    expect(text()).toContain('Your tickets will appear');
    tick(2000);
    expect(text()).toContain('Payment confirmed');
    expect(text()).toContain('Your group booking is confirmed');
    expect(text()).toContain('View booking & tickets');
    expect(text()).toContain('225,000.00');
    expect(text()).not.toContain('225000.00');
    expect(getPaymentStatus).toHaveBeenCalledWith(7);
    expect(bookingService.get).not.toHaveBeenCalled();
  });

  it('offers a manual check for a group booking payment that is still processing', () => {
    const { text, tick } = render([bookingStatus('pending', 'holding')], true, {
      booking_id: 'bk-1',
    });
    tick(60_000);
    expect(text()).toContain('Check again');
  });

  it('explains a group payment that arrived after the hold ended as refunded', () => {
    const { text, tick } = render([bookingStatus('completed', 'expired')], true, {
      booking_id: 'bk-1',
    });
    tick(0);
    expect(text()).toContain('Payment refunded');
  });

  it('tells a signed-out phone that paid a group booking to go back to the buyer device', () => {
    const { text, tick, getPaymentStatus, bookingService } = render(
      [bookingStatus('completed', 'confirmed')],
      false,
      { booking_id: 'bk-1' },
    );
    tick(0);
    expect(text()).toContain('Payment sent');
    expect(text()).not.toContain('Verification failed');
    expect(getPaymentStatus).not.toHaveBeenCalled();
    expect(bookingService.get).not.toHaveBeenCalled();
  });
});
