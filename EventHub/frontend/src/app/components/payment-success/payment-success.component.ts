import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute, convertToParamMap } from '@angular/router';
import { Subscription } from 'rxjs';
import { PaymentService } from '../../services/payment.service';
import { BookingService } from '../../services/booking.service';
import { AuthService } from '../../services/auth.service';
import {
  PaymentOutcome,
  PaymentPollingService,
  paymentOutcome,
} from '../../services/payment-polling.service';
import { BookingStatus, PaymentStatus } from '../../models/models';
import { MoneyPipe } from '../../pipes/money.pipe';
import { LucideAngularModule, CircleCheckBig, CircleAlert, Smartphone } from 'lucide-angular';
import { apiErrorMessage } from '../../api/api-error';

// A Freedom Pay return is confirmed by its server notification, which can
// lag the browser by a few seconds: poll for this long, then offer a button.
const POLL_INTERVAL_MS = 2000;
const POLL_MAX_MS = 60 * 1000;

/** What the page tells the buyer, from a ticket payment or a group booking. */
type Outcome = 'paid' | 'processing' | 'refunded' | 'failed';

const POLL_OUTCOME: Record<PaymentOutcome, Outcome> = {
  paid: 'paid',
  waiting: 'processing',
  failed: 'failed',
  refunded: 'refunded',
};

interface PaymentResult {
  outcome: Outcome;
  event_title: string;
  amount: string;
  currency?: string;
}

// Keyed by the API's status enums: a status the backend adds later won't
// compile until someone decides how this page presents it.
const PAYMENT_OUTCOME: Record<PaymentStatus, Outcome> = {
  completed: 'paid',
  refunded: 'refunded',
  pending: 'processing',
  // The provider declined the payment or the payment page timed out: no
  // money was taken and the buyer can start the payment again.
  failed: 'failed',
  expired: 'failed',
  // The buyer's bank is reviewing a paid ticket; it stays valid meanwhile.
  disputed: 'processing',
};

// A booking that ended (expired/cancelled) by the time the money arrived is
// refunded automatically by the backend.
const BOOKING_OUTCOME: Record<BookingStatus, Outcome> = {
  confirmed: 'paid',
  refunded: 'refunded',
  expired: 'refunded',
  cancelled: 'refunded',
  holding: 'processing',
};

@Component({
  selector: 'app-payment-success',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule, MoneyPipe],
  template: `
    <div class="min-h-screen bg-muted flex items-center justify-center px-4 py-12 pt-20">
      <div class="card w-full max-w-sm p-8 shadow-md text-center animate-scale-in">
        @if (loading) {
          <div class="flex flex-col items-center gap-4 py-8">
            <span class="spinner spinner-lg"></span>
            <p class="text-sm text-muted-foreground">Confirming your payment...</p>
          </div>
        } @else if (otherDevice) {
          <!-- Paid from a second device (QR code): the buyer is signed in elsewhere -->
          <div class="flex flex-col items-center gap-3 mb-6">
            <div
              class="w-16 h-16 rounded-full bg-[color:var(--pine-50)] flex items-center justify-center"
            >
              <lucide-icon
                [img]="icons.Smartphone"
                class="w-8 h-8 text-[color:var(--pine-600)]"
                aria-hidden="true"
              />
            </div>
            <h1 class="text-xl font-bold text-foreground">Payment sent</h1>
            <p class="text-sm text-muted-foreground">
              Go back to the device where you started the purchase: the ticket appears there as soon
              as the payment provider confirms it. You can close this page.
            </p>
          </div>
          <a routerLink="/" class="btn btn-ghost btn-full text-muted-foreground">Back to events</a>
        } @else if (data && data.outcome === 'paid') {
          <div class="flex flex-col items-center gap-3 mb-6">
            <div
              class="w-16 h-16 rounded-full bg-[color:var(--pine-50)] flex items-center justify-center"
            >
              <lucide-icon
                [img]="icons.CircleCheckBig"
                class="w-8 h-8 text-[color:var(--pine-600)]"
                aria-hidden="true"
              />
            </div>
            <h1 class="text-xl font-bold text-foreground">Payment confirmed</h1>
            <p class="text-sm text-muted-foreground">
              {{ isBooking ? 'Your group booking is confirmed' : 'Your registration is complete' }}
            </p>
          </div>

          <div
            class="rounded-lg border border-border bg-muted/40 divide-y divide-border text-sm mb-6 text-left"
          >
            <div class="px-4 py-3 flex justify-between gap-3">
              <span class="text-muted-foreground flex-shrink-0">Event</span>
              <span class="font-medium text-foreground text-right">{{ data.event_title }}</span>
            </div>
            @if (data.amount) {
              <div class="px-4 py-3 flex justify-between gap-3">
                <span class="text-muted-foreground flex-shrink-0">Amount</span>
                <span class="font-semibold text-foreground">{{
                  data.amount | money: data.currency
                }}</span>
              </div>
            }
            <div class="px-4 py-3 flex justify-between gap-3">
              <span class="text-muted-foreground flex-shrink-0">Status</span>
              <span class="badge badge-confirmed">Paid</span>
            </div>
          </div>

          <div class="flex flex-col gap-2">
            @if (isBooking) {
              <a routerLink="/my-bookings" class="btn btn-primary btn-full">
                View booking & tickets
              </a>
            } @else {
              <a routerLink="/my-registrations" class="btn btn-primary btn-full">
                View my tickets
              </a>
            }
            <a routerLink="/" class="btn btn-ghost btn-full text-muted-foreground">
              Back to events
            </a>
          </div>
        } @else if (data) {
          <!-- Not (yet) paid: processing, failed / expired, or refunded because the hold had ended -->
          <div class="flex flex-col items-center gap-3 mb-6">
            <div
              class="w-16 h-16 rounded-full bg-[color:var(--destructive-50)] flex items-center justify-center"
            >
              <lucide-icon
                [img]="icons.CircleAlert"
                class="w-8 h-8 text-[color:var(--destructive)]"
                aria-hidden="true"
              />
            </div>
            @if (data.outcome === 'refunded') {
              <h1 class="text-xl font-bold text-foreground">Payment refunded</h1>
              <p class="text-sm text-muted-foreground">
                Your seat hold had ended before the payment arrived, so the money was returned
                automatically. Please book again.
              </p>
            } @else if (data.outcome === 'failed') {
              <h1 class="text-xl font-bold text-foreground">Payment did not go through</h1>
              <p class="text-sm text-muted-foreground">
                The payment was not completed and no money was taken. You can try again from your
                tickets while your seat is still held.
              </p>
            } @else {
              <h1 class="text-xl font-bold text-foreground">Payment is processing</h1>
              <p class="text-sm text-muted-foreground">
                We haven't received the confirmation yet.
                {{ isBooking ? 'Your tickets' : 'Your ticket' }} will appear in your account as soon
                as it does.
              </p>
            }
          </div>
          <div class="flex flex-col gap-2">
            @if (data.outcome === 'processing' && canRecheck) {
              @if (polling) {
                <p class="text-xs text-muted-foreground" role="status">
                  Checking with the payment provider…
                </p>
              } @else {
                <button type="button" class="btn btn-primary btn-full" (click)="refresh()">
                  Check again
                </button>
              }
            }
            <a
              [routerLink]="isBooking ? '/my-bookings' : '/my-registrations'"
              class="btn btn-secondary btn-full"
            >
              {{ isBooking ? 'View my bookings' : 'View my tickets' }}
            </a>
            <a routerLink="/" class="btn btn-ghost btn-full text-muted-foreground"
              >Back to events</a
            >
          </div>
        } @else {
          <!-- Error -->
          <div class="flex flex-col items-center gap-3 mb-6">
            <div
              class="w-16 h-16 rounded-full bg-[color:var(--destructive-50)] flex items-center justify-center"
            >
              <lucide-icon
                [img]="icons.CircleAlert"
                class="w-8 h-8 text-[color:var(--destructive)]"
                aria-hidden="true"
              />
            </div>
            <h1 class="text-xl font-bold text-foreground">Verification failed</h1>
            <p class="text-sm text-muted-foreground">
              {{ error || 'Could not verify your payment. Please contact support.' }}
            </p>
          </div>

          <div class="flex flex-col gap-2">
            <a routerLink="/my-registrations" class="btn btn-secondary btn-full">
              View registrations
            </a>
            <a routerLink="/" class="btn btn-ghost btn-full text-muted-foreground">
              Back to events
            </a>
          </div>
        }
      </div>
    </div>
  `,
})
export class PaymentSuccessComponent implements OnInit {
  private paymentService = inject(PaymentService);
  private bookingService = inject(BookingService);
  private auth = inject(AuthService);
  private poller = inject(PaymentPollingService);
  private route = inject(ActivatedRoute);
  private destroyRef = inject(DestroyRef);

  loading = true;
  data: PaymentResult | null = null;
  error = '';
  isBooking = false;
  /** The payment page sent a signed-out device here (a phone that paid by QR code). */
  otherDevice = false;
  /** True while a Freedom Pay payment is being polled. */
  polling = false;

  private sessionId: string | null = null;
  private paymentId: number | null = null;
  private pollSubscription?: Subscription;

  readonly icons = { CircleCheckBig, CircleAlert, Smartphone };

  /** "Check again" is offered for a ticket payment and for any Freedom Pay
   *  payment (a group booking's included). */
  get canRecheck(): boolean {
    return !this.isBooking || this.paymentId !== null;
  }

  ngOnInit(): void {
    this.route.queryParams.subscribe((params) => {
      const query = convertToParamMap(params);
      const sessionId = query.get('session_id');
      const bookingId = query.get('booking_id');
      this.isBooking = Boolean(bookingId);

      // Freedom Pay return (success page of the provider): our payment id,
      // for a single ticket or (with booking_id) a group booking.
      const paymentId = Number(query.get('payment'));
      if (query.get('provider') === 'freedompay' && Number.isInteger(paymentId) && paymentId > 0) {
        // The status endpoint is owner-only: a phone that scanned the QR code
        // is not signed in, and the ticket shows up on the buyer's device.
        if (!this.auth.getToken()) {
          this.otherDevice = true;
          this.loading = false;
          return;
        }
        this.paymentId = paymentId;
        this.watchPayment();
        return;
      }

      // Group booking — verify with the backend (confirms it even when the
      // Stripe webhook is not forwarded, e.g. local dev with a real key).
      if (bookingId) {
        // With a Stripe session: verify (confirms even when the webhook is
        // not forwarded). Mock flow: read the booking's real state.
        const booking$ = sessionId
          ? this.bookingService.verify(sessionId)
          : this.bookingService.get(bookingId);
        booking$.subscribe({
          next: (b) => {
            this.data = {
              outcome: BOOKING_OUTCOME[b.status],
              event_title: b.event_title,
              amount: b.total_due,
              currency: b.currency,
            };
            this.loading = false;
          },
          error: (err) => {
            // Never claim success we couldn't verify.
            this.error = apiErrorMessage(
              err,
              'We could not verify this payment yet.',
              'error',
              'detail',
            );
            this.loading = false;
          },
        });
        return;
      }

      if (!sessionId) {
        this.error = 'No payment session found.';
        this.loading = false;
        return;
      }
      this.sessionId = sessionId;
      this.verify(sessionId);
    });
  }

  /** "Check again" on a payment that is still processing. */
  refresh(): void {
    if (this.paymentId) {
      this.watchPayment();
    } else if (this.sessionId) {
      this.verify(this.sessionId);
    }
  }

  private verify(sessionId: string): void {
    this.paymentService.verifyPayment(sessionId).subscribe({
      next: (d) => {
        this.data = {
          outcome: PAYMENT_OUTCOME[d.status],
          event_title: d.event_title,
          amount: d.amount,
          currency: d.currency,
        };
        this.loading = false;
      },
      error: (err) => {
        this.error = apiErrorMessage(err, 'Verification failed.', 'error', 'detail');
        this.loading = false;
      },
    });
  }

  /** Poll the payment until it settles (max POLL_MAX_MS), never forever. */
  private watchPayment(): void {
    if (this.paymentId === null) return;
    this.pollSubscription?.unsubscribe();
    this.polling = true;
    this.pollSubscription = this.poller
      .poll(this.paymentId, POLL_INTERVAL_MS, POLL_MAX_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (status) => {
          this.data = {
            outcome: POLL_OUTCOME[paymentOutcome(status)],
            event_title: status.event_title,
            amount: status.amount,
            currency: status.currency,
          };
          this.loading = false;
        },
        complete: () => {
          this.polling = false;
          if (!this.data) {
            this.error =
              'We could not reach the payment service yet. Check your tickets in a moment.';
            this.loading = false;
          }
        },
      });
  }
}
