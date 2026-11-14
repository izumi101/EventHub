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
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from '../../i18n/language.service';

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
  imports: [CommonModule, RouterModule, LucideAngularModule, MoneyPipe, TranslocoPipe],
  template: `
    <div class="min-h-screen bg-muted flex items-center justify-center px-4 py-12 pt-20">
      <div class="card w-full max-w-sm p-8 shadow-md text-center animate-scale-in">
        @if (loading) {
          <div class="flex flex-col items-center gap-4 py-8">
            <span class="spinner spinner-lg"></span>
            <p class="text-sm text-muted-foreground">
              {{ 'paymentSuccess.confirmingYourPayment' | transloco }}
            </p>
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
            <h1 class="text-xl font-bold text-foreground">
              {{ 'paymentSuccess.paymentSent' | transloco }}
            </h1>
            <p class="text-sm text-muted-foreground">
              {{ 'paymentSuccess.goBackToThe' | transloco }}
            </p>
          </div>
          <a routerLink="/" class="btn btn-ghost btn-full text-muted-foreground">{{
            'eventDetail.backToEvents' | transloco
          }}</a>
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
            <h1 class="text-xl font-bold text-foreground">
              {{ 'paymentSuccess.paymentConfirmed' | transloco }}
            </h1>
            <p class="text-sm text-muted-foreground">
              {{
                (isBooking
                  ? 'paymentSuccess.yourGroupBookingIs'
                  : 'paymentSuccess.yourRegistrationIsComplete'
                ) | transloco
              }}
            </p>
          </div>

          <div
            class="rounded-lg border border-border bg-muted/40 divide-y divide-border text-sm mb-6 text-left"
          >
            <div class="px-4 py-3 flex justify-between gap-3">
              <span class="text-muted-foreground flex-shrink-0">{{ 'nav.event' | transloco }}</span>
              <span class="font-medium text-foreground text-right">{{ data.event_title }}</span>
            </div>
            @if (data.amount) {
              <div class="px-4 py-3 flex justify-between gap-3">
                <span class="text-muted-foreground flex-shrink-0">{{
                  'checkout.amount' | transloco
                }}</span>
                <span class="font-semibold text-foreground">{{
                  data.amount | money: data.currency
                }}</span>
              </div>
            }
            <div class="px-4 py-3 flex justify-between gap-3">
              <span class="text-muted-foreground flex-shrink-0">{{
                'common.status' | transloco
              }}</span>
              <span class="badge badge-confirmed">{{ 'common.paid' | transloco }}</span>
            </div>
          </div>

          <div class="flex flex-col gap-2">
            @if (isBooking) {
              <a routerLink="/my-bookings" class="btn btn-primary btn-full">
                {{ 'paymentSuccess.viewBookingTickets' | transloco }}
              </a>
            } @else {
              <a routerLink="/my-registrations" class="btn btn-primary btn-full">
                {{ 'paymentSuccess.viewMyTickets' | transloco }}
              </a>
            }
            <a routerLink="/" class="btn btn-ghost btn-full text-muted-foreground">
              {{ 'eventDetail.backToEvents' | transloco }}
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
              <h1 class="text-xl font-bold text-foreground">
                {{ 'paymentSuccess.paymentRefunded' | transloco }}
              </h1>
              <p class="text-sm text-muted-foreground">
                {{ 'paymentSuccess.yourSeatHoldHad' | transloco }}
              </p>
            } @else if (data.outcome === 'failed') {
              <h1 class="text-xl font-bold text-foreground">
                {{ 'paymentSuccess.paymentDidNotGo' | transloco }}
              </h1>
              <p class="text-sm text-muted-foreground">
                {{ 'paymentSuccess.thePaymentWasNot' | transloco }}
              </p>
            } @else {
              <h1 class="text-xl font-bold text-foreground">
                {{ 'paymentSuccess.paymentIsProcessing' | transloco }}
              </h1>
              <p class="text-sm text-muted-foreground">
                {{
                  (isBooking
                    ? 'paymentSuccess.notConfirmedTickets'
                    : 'paymentSuccess.notConfirmedTicket'
                  ) | transloco
                }}
              </p>
            }
          </div>
          <div class="flex flex-col gap-2">
            @if (data.outcome === 'processing' && canRecheck) {
              @if (polling) {
                <p class="text-xs text-muted-foreground" role="status">
                  {{ 'paymentSuccess.checkingWithThePayment' | transloco }}
                </p>
              } @else {
                <button type="button" class="btn btn-primary btn-full" (click)="refresh()">
                  {{ 'paymentSuccess.checkAgain' | transloco }}
                </button>
              }
            }
            <a
              [routerLink]="isBooking ? '/my-bookings' : '/my-registrations'"
              class="btn btn-secondary btn-full"
            >
              {{
                (isBooking ? 'paymentSuccess.viewMyBookings' : 'paymentSuccess.viewMyTickets')
                  | transloco
              }}
            </a>
            <a routerLink="/" class="btn btn-ghost btn-full text-muted-foreground">{{
              'eventDetail.backToEvents' | transloco
            }}</a>
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
            <h1 class="text-xl font-bold text-foreground">
              {{ 'paymentSuccess.verificationFailed' | transloco }}
            </h1>
            <p class="text-sm text-muted-foreground">
              {{ error || ('paymentSuccess.couldNotVerifyYour' | transloco) }}
            </p>
          </div>

          <div class="flex flex-col gap-2">
            <a routerLink="/my-registrations" class="btn btn-secondary btn-full">
              {{ 'paymentSuccess.viewRegistrations' | transloco }}
            </a>
            <a routerLink="/" class="btn btn-ghost btn-full text-muted-foreground">
              {{ 'eventDetail.backToEvents' | transloco }}
            </a>
          </div>
        }
      </div>
    </div>
  `,
})
export class PaymentSuccessComponent implements OnInit {
  private i18n = inject(LanguageService);
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
              this.i18n.t('paymentSuccess.weCouldNotVerify'),
              'error',
              'detail',
            );
            this.loading = false;
          },
        });
        return;
      }

      if (!sessionId) {
        this.error = this.i18n.t('paymentSuccess.noPaymentSessionFound');
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
        this.error = apiErrorMessage(
          err,
          this.i18n.t('paymentSuccess.verificationFailed2'),
          'error',
          'detail',
        );
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
            this.error = this.i18n.t('paymentSuccess.weCouldNotReach');
            this.loading = false;
          }
        },
      });
  }
}
