import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { PaymentSuccessComponent } from './payment-success.component';
import { PaymentService } from '../../services/payment.service';
import { BookingService } from '../../services/booking.service';

function render(params: Record<string, string>, payment: object, booking: object) {
  TestBed.configureTestingModule({
    imports: [PaymentSuccessComponent],
    providers: [
      provideRouter([]),
      { provide: ActivatedRoute, useValue: { queryParams: of(params) } },
      { provide: PaymentService, useValue: payment },
      { provide: BookingService, useValue: booking },
    ],
  });
  const fixture = TestBed.createComponent(PaymentSuccessComponent);
  fixture.detectChanges();
  return (fixture.nativeElement as HTMLElement).textContent || '';
}

describe('PaymentSuccessComponent', () => {
  it('confirms only a completed payment', () => {
    const text = render(
      { session_id: 'cs_1' },
      {
        verifyPayment: () =>
          of({ status: 'completed', event_title: 'Gig', amount: '5000.00', currency: 'KZT' }),
      },
      {},
    );
    expect(text).toContain('Payment confirmed');
    expect(text).toContain('5,000.00');
  });

  it('explains an automatic refund instead of claiming success', () => {
    const text = render(
      { session_id: 'cs_1' },
      {
        verifyPayment: () => of({ status: 'refunded', event_title: 'Gig', amount: '10' }),
      },
      {},
    );
    expect(text).toContain('Payment refunded');
    expect(text).not.toContain('Payment confirmed');
  });

  for (const status of ['failed', 'expired']) {
    it(`asks the buyer to try again when the payment is ${status}`, () => {
      const text = render(
        { session_id: 'cs_1' },
        { verifyPayment: () => of({ status, event_title: 'Gig', amount: '10' }) },
        {},
      );
      expect(text).toContain('Payment did not go through');
      expect(text).toContain('no money was taken');
      expect(text).not.toContain('Payment confirmed');
      expect(text).not.toContain('Payment is processing');
    });
  }

  it('keeps a disputed payment as processing, never as confirmed', () => {
    const text = render(
      { session_id: 'cs_1' },
      { verifyPayment: () => of({ status: 'disputed', event_title: 'Gig', amount: '10' }) },
      {},
    );
    expect(text).toContain('Payment is processing');
    expect(text).not.toContain('Payment confirmed');
  });

  it('still shows a pending payment as processing', () => {
    const text = render(
      { session_id: 'cs_1' },
      { verifyPayment: () => of({ status: 'pending', event_title: 'Gig', amount: '10' }) },
      {},
    );
    expect(text).toContain('Payment is processing');
  });

  it('shows an error when a group booking cannot be verified', () => {
    const text = render(
      { booking_id: 'b1', session_id: 'cs_2' },
      {},
      {
        verify: () => throwError(() => ({ error: { error: 'Booking not found' } })),
      },
    );
    expect(text).toContain('Booking not found');
    expect(text).not.toContain('Payment confirmed');
  });
});

describe('PaymentSuccessComponent verification requests', () => {
  it('verifies the session id taken from the return URL', () => {
    const verifyPayment = vi.fn(() =>
      of({ status: 'completed', event_title: 'Gig', amount: '5000.00', currency: 'KZT' }),
    );
    render({ session_id: 'cs_abc' }, { verifyPayment }, {});
    expect(verifyPayment).toHaveBeenCalledTimes(1);
    expect(verifyPayment).toHaveBeenCalledWith('cs_abc');
  });

  it('shows an error and never calls the gateway verification when the session id is missing', () => {
    const verifyPayment = vi.fn();
    const text = render({}, { verifyPayment }, {});
    expect(verifyPayment).not.toHaveBeenCalled();
    expect(text).toContain('Verification failed');
    expect(text).toContain('No payment session found.');
    expect(text).not.toContain('Payment confirmed');
  });

  it('shows the backend message when verification is rejected, never a success view', () => {
    const text = render(
      { session_id: 'cs_bad' },
      {
        verifyPayment: () =>
          throwError(() => ({ status: 404, error: { error: 'Unknown session' } })),
      },
      {},
    );
    expect(text).toContain('Unknown session');
    expect(text).not.toContain('Payment confirmed');
  });

  it('verifies a group booking by session id when Stripe returns one', () => {
    const verify = vi.fn(() =>
      of({ status: 'confirmed', event_title: 'Gig', total_due: '300.00', currency: 'KZT' }),
    );
    const get = vi.fn();
    const text = render({ booking_id: 'b1', session_id: 'cs_2' }, {}, { verify, get });
    expect(verify).toHaveBeenCalledWith('cs_2');
    expect(get).not.toHaveBeenCalled();
    expect(text).toContain('Payment confirmed');
    expect(text).toContain('300.00');
    expect(text).toContain('View booking & tickets');
  });

  it('reads the real booking state when there is no session (mock flow) and reports an expired hold as refunded', () => {
    const get = vi.fn(() =>
      of({ status: 'expired', event_title: 'Gig', total_due: '300.00', currency: 'KZT' }),
    );
    const text = render({ booking_id: 'b7' }, {}, { get });
    expect(get).toHaveBeenCalledWith('b7');
    expect(text).toContain('Payment refunded');
    expect(text).not.toContain('Payment confirmed');
  });
});
