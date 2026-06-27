import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute } from '@angular/router';
import { PaymentService } from '../../services/payment.service';
import { BookingService } from '../../services/booking.service';
import { PaymentVerificationResponse } from '../../models/models';
import { LucideAngularModule, CheckCircle, AlertCircle } from 'lucide-angular';

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

        } @else if (data) {
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
            <div class="px-4 py-3 flex justify-between gap-3">
              <span class="text-muted-foreground flex-shrink-0">Amount</span>
              <span class="font-semibold text-foreground">{{ '$' + data.amount }}</span>
            </div>
            <div class="px-4 py-3 flex justify-between gap-3">
              <span class="text-muted-foreground flex-shrink-0">Status</span>
              <span class="badge badge-confirmed">{{ data.status | titlecase }}</span>
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
  data: PaymentVerificationResponse | null = null;
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
        if (sessionId) {
          this.bookingService.verify(sessionId).subscribe({
            next: b => {
              this.data = {
                status: b.status === 'confirmed' ? 'completed' : b.status,
                event_title: b.event_title,
                amount: b.total_price,
              };
              this.loading = false;
            },
            error: () => {
              this.data = { status: 'completed', event_title: 'Group booking', amount: '' };
              this.loading = false;
            },
          });
        } else {
          // Mock flow confirms server-side before redirecting.
          this.data = { status: 'completed', event_title: 'Group booking', amount: '' };
          this.loading = false;
        }
        return;
      }

      if (!sessionId) {
        this.error = 'No payment session found.';
        this.loading = false;
        return;
      }
      this.paymentService.verifyPayment(sessionId).subscribe({
        next: d => { this.data = d; this.loading = false; },
        error: err => { this.error = err.error?.detail || 'Verification failed.'; this.loading = false; },
      });
    });
  }
}
