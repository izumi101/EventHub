import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute } from '@angular/router';
import { PaymentService } from '../../services/payment.service';
import { BookingService } from '../../services/booking.service';
import { BookingStatus, PaymentStatus } from '../../models/models';
import { LucideAngularModule, CheckCircle, AlertCircle } from 'lucide-angular';

/** What the page tells the buyer, from a ticket payment or a group booking. */
type Outcome = 'paid' | 'processing' | 'refunded';

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
  failed: 'processing',
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
  imports: [CommonModule, RouterModule, LucideAngularModule],
  template: `
    <div class="min-h-screen bg-muted flex items-center justify-center px-4 py-12 pt-20">
      <div class="card w-full max-w-sm p-8 shadow-md text-center animate-scale-in">

        @if (loading) {
          <div class="flex flex-col items-center gap-4 py-8">
            <span class="spinner spinner-lg"></span>
            <p class="text-sm text-muted-foreground">Confirming your payment...</p>
          </div>

        } @else if (data && data.outcome === 'paid') {
          <div class="flex flex-col items-center gap-3 mb-6">
            <div class="w-16 h-16 rounded-full bg-[color:var(--pine-50)] flex items-center justify-center">
              <lucide-icon [img]="icons.CheckCircle" class="w-8 h-8 text-[color:var(--pine-600)]" aria-hidden="true"></lucide-icon>
            </div>
            <h1 class="text-xl font-bold text-foreground">Payment confirmed</h1>
            <p class="text-sm text-muted-foreground">Your registration is complete</p>
          </div>

          <div class="rounded-lg border border-border bg-muted/40 divide-y divide-border text-sm mb-6 text-left">
            <div class="px-4 py-3 flex justify-between gap-3">
              <span class="text-muted-foreground flex-shrink-0">Event</span>
              <span class="font-medium text-foreground text-right">{{ data.event_title }}</span>
            </div>
            @if (data.amount) {
              <div class="px-4 py-3 flex justify-between gap-3">
                <span class="text-muted-foreground flex-shrink-0">Amount</span>
                <span class="font-semibold text-foreground">{{ data.amount }} {{ data.currency || '' }}</span>
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
          <!-- Not (yet) paid: still processing, or refunded because the hold had ended -->
          <div class="flex flex-col items-center gap-3 mb-6">
            <div class="w-16 h-16 rounded-full bg-[color:var(--destructive-50)] flex items-center justify-center">
              <lucide-icon [img]="icons.AlertCircle" class="w-8 h-8 text-[color:var(--destructive)]" aria-hidden="true"></lucide-icon>
            </div>
            @if (data.outcome === 'refunded') {
              <h1 class="text-xl font-bold text-foreground">Payment refunded</h1>
              <p class="text-sm text-muted-foreground">
                Your seat hold had ended before the payment arrived, so the money was returned automatically.
                Please book again.
              </p>
            } @else {
              <h1 class="text-xl font-bold text-foreground">Payment is processing</h1>
              <p class="text-sm text-muted-foreground">
                We haven't received the confirmation yet. Your ticket will appear in your account as soon as it does.
              </p>
            }
          </div>
          <div class="flex flex-col gap-2">
            <a [routerLink]="isBooking ? '/my-bookings' : '/my-registrations'" class="btn btn-secondary btn-full">
              {{ isBooking ? 'View my bookings' : 'View my tickets' }}
            </a>
            <a routerLink="/" class="btn btn-ghost btn-full text-muted-foreground">Back to events</a>
          </div>

        } @else {
          <!-- Error -->
          <div class="flex flex-col items-center gap-3 mb-6">
            <div class="w-16 h-16 rounded-full bg-[color:var(--destructive-50)] flex items-center justify-center">
              <lucide-icon [img]="icons.AlertCircle" class="w-8 h-8 text-[color:var(--destructive)]" aria-hidden="true"></lucide-icon>
            </div>
            <h1 class="text-xl font-bold text-foreground">Verification failed</h1>
            <p class="text-sm text-muted-foreground">{{ error || 'Could not verify your payment. Please contact support.' }}</p>
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
  loading = true;
  data: PaymentResult | null = null;
  error = '';
  isBooking = false;

  readonly icons = { CheckCircle, AlertCircle };

  constructor(
    private paymentService: PaymentService,
    private bookingService: BookingService,
    private route: ActivatedRoute,
  ) {}

  ngOnInit(): void {
    this.route.queryParams.subscribe(params => {
      const sessionId = params['session_id'];
      const bookingId = params['booking_id'];

      // Group booking — verify with the backend (confirms it even when the
      // Stripe webhook is not forwarded, e.g. local dev with a real key).
      if (bookingId) {
        this.isBooking = true;
        // With a Stripe session: verify (confirms even when the webhook is
        // not forwarded). Mock flow: read the booking's real state.
        const booking$ = sessionId ? this.bookingService.verify(sessionId) : this.bookingService.get(bookingId);
        booking$.subscribe({
          next: b => {
            this.data = {
              outcome: BOOKING_OUTCOME[b.status],
              event_title: b.event_title,
              amount: b.total_due ?? b.total_price,
              currency: b.currency,
            };
            this.loading = false;
          },
          error: err => {
            // Never claim success we couldn't verify.
            this.error = err.error?.error || err.error?.detail || 'We could not verify this payment yet.';
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
      this.paymentService.verifyPayment(sessionId).subscribe({
        next: d => {
          this.data = {
            outcome: PAYMENT_OUTCOME[d.status],
            event_title: d.event_title,
            amount: d.amount,
            currency: d.currency,
          };
          this.loading = false;
        },
        error: err => { this.error = err.error?.error || err.error?.detail || 'Verification failed.'; this.loading = false; },
      });
    });
  }
}
