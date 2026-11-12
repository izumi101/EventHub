import { Injectable, inject } from '@angular/core';
import { EMPTY, Observable, catchError, exhaustMap, takeUntil, takeWhile, timer } from 'rxjs';
import { PaymentStatusResponse } from '../models/models';
import { PaymentService } from './payment.service';

/** What a payment status means for the buyer. */
export type PaymentOutcome = 'waiting' | 'paid' | 'failed' | 'refunded';

/** A payment the provider has finished with (no further change expected). */
export function isTerminal(status: PaymentStatusResponse): boolean {
  return status.status !== 'pending';
}

export function paymentOutcome(status: PaymentStatusResponse): PaymentOutcome {
  switch (status.status) {
    case 'completed':
      // Money that arrived after the seat hold ended is refunded automatically.
      return status.registration_status === 'confirmed' ? 'paid' : 'refunded';
    case 'refunded':
      return 'refunded';
    case 'failed':
    case 'expired':
      return 'failed';
    case 'disputed':
    case 'pending':
      return 'waiting';
  }
}

@Injectable({ providedIn: 'root' })
export class PaymentPollingService {
  private payments = inject(PaymentService);

  /**
   * Polls GET /payments/status/{id}/ every `intervalMs` (first request at
   * once). Emits every answer and completes after the first terminal one,
   * or after `maxMs` without one. A failed request is skipped (the next tick
   * asks again); a slow one is never overlapped. Unsubscribe to stop early.
   */
  poll(
    paymentId: number,
    intervalMs = 2000,
    maxMs = 10 * 60 * 1000,
  ): Observable<PaymentStatusResponse> {
    return timer(0, intervalMs).pipe(
      takeUntil(timer(maxMs)),
      exhaustMap(() => this.payments.getPaymentStatus(paymentId).pipe(catchError(() => EMPTY))),
      takeWhile((status) => !isTerminal(status), true),
    );
  }
}
