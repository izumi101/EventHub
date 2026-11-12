import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { PaymentSuccessComponent } from './payment-success.component';
import { PaymentService } from '../../services/payment.service';
import { BookingService } from '../../services/booking.service';
import { PaymentStatus, PaymentStatusResponse } from '../../models/models';

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
    event_id: 1,
    event_title: 'Gig',
    amount: '5000.00',
    currency: 'KZT',
  };
}

function render(answers: PaymentStatusResponse[]) {
  const getPaymentStatus = vi.fn(() => of(answers.length > 1 ? answers.shift()! : answers[0]));
  const verifyPayment = vi.fn();
  TestBed.configureTestingModule({
    imports: [PaymentSuccessComponent],
    providers: [
      provideRouter([]),
      {
        provide: ActivatedRoute,
        useValue: {
          queryParams: of({ provider: 'freedompay', payment: '7', pg_order_id: '7', pg_sig: 'x' }),
        },
      },
      { provide: PaymentService, useValue: { getPaymentStatus, verifyPayment } },
      { provide: BookingService, useValue: {} },
    ],
  });
  const fixture = TestBed.createComponent(PaymentSuccessComponent);
  fixture.detectChanges();
  const text = () => (fixture.nativeElement as HTMLElement).textContent || '';
  const tick = (ms: number) => {
    vi.advanceTimersByTime(ms);
    fixture.detectChanges();
  };
  return { fixture, text, tick, getPaymentStatus, verifyPayment };
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
    expect(text()).toContain('5000.00 KZT');
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
});
