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
    expect(text).toContain('5000.00 KZT');
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
