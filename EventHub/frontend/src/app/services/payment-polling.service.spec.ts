import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { PaymentStatus, PaymentStatusResponse } from '../models/models';
import { PaymentPollingService, paymentOutcome } from './payment-polling.service';
import { PaymentService } from './payment.service';

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

function setup(getPaymentStatus: ReturnType<typeof vi.fn>) {
  TestBed.configureTestingModule({
    providers: [{ provide: PaymentService, useValue: { getPaymentStatus } }],
  });
  return TestBed.inject(PaymentPollingService);
}

describe('PaymentPollingService', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('asks at once, then every interval, and stops after the first final answer', () => {
    const answers = [status('pending'), status('pending'), status('completed', 'confirmed')];
    const get = vi.fn(() => of(answers.shift() ?? status('completed', 'confirmed')));
    const seen: string[] = [];
    let done = false;
    setup(get)
      .poll(7, 2000, 60_000)
      .subscribe({ next: (s) => seen.push(s.status), complete: () => (done = true) });

    vi.advanceTimersByTime(0);
    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith(7);
    vi.advanceTimersByTime(4000);
    expect(seen).toEqual(['pending', 'pending', 'completed']);
    expect(done).toBe(true);
    vi.advanceTimersByTime(10_000);
    expect(get).toHaveBeenCalledTimes(3);
  });

  it('gives up after the maximum time without a final answer', () => {
    const get = vi.fn(() => of(status('pending')));
    let done = false;
    setup(get)
      .poll(7, 2000, 10_000)
      .subscribe({ complete: () => (done = true) });
    vi.advanceTimersByTime(10_000);
    expect(done).toBe(true);
    const calls = get.mock.calls.length;
    vi.advanceTimersByTime(20_000);
    expect(get.mock.calls.length).toBe(calls);
  });

  it('skips a failed request and keeps asking', () => {
    const get = vi
      .fn()
      .mockReturnValueOnce(throwError(() => new Error('offline')))
      .mockReturnValue(of(status('failed')));
    const seen: string[] = [];
    setup(get)
      .poll(7, 2000, 60_000)
      .subscribe((s) => seen.push(s.status));
    vi.advanceTimersByTime(2000);
    expect(seen).toEqual(['failed']);
  });

  it('stops asking when unsubscribed', () => {
    const get = vi.fn(() => of(status('pending')));
    const subscription = setup(get).poll(7, 2000, 60_000).subscribe();
    vi.advanceTimersByTime(2000);
    subscription.unsubscribe();
    const calls = get.mock.calls.length;
    vi.advanceTimersByTime(20_000);
    expect(get.mock.calls.length).toBe(calls);
  });

  it('maps statuses to what the buyer is told', () => {
    expect(paymentOutcome(status('completed', 'confirmed'))).toBe('paid');
    // Paid after the hold ended: refunded automatically, never a ticket.
    expect(paymentOutcome(status('completed', 'cancelled'))).toBe('refunded');
    expect(paymentOutcome(status('refunded'))).toBe('refunded');
    expect(paymentOutcome(status('failed'))).toBe('failed');
    expect(paymentOutcome(status('expired'))).toBe('failed');
    expect(paymentOutcome(status('pending'))).toBe('waiting');
  });
});
