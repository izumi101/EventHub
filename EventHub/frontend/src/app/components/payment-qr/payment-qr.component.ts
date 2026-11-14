import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  OnDestroy,
  OnInit,
  Output,
  inject,
  signal,
} from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { CheckoutSessionResponse } from '../../models/models';
import { DialogDirective } from '../../directives/dialog.directive';
import { MoneyPipe } from '../../pipes/money.pipe';
import {
  PaymentOutcome,
  PaymentPollingService,
  paymentOutcome,
} from '../../services/payment-polling.service';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from '../../i18n/language.service';

type QrState = PaymentOutcome | 'stopped';

/** What the dialog needs from a checkout answer (single ticket or group booking). */
export type QrCheckout = Pick<
  CheckoutSessionResponse,
  'checkout_url' | 'provider' | 'qr_code' | 'amount' | 'currency'
> & { payment_id: number };

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_MS = 10 * 60 * 1000;

/**
 * Pay a ticket or a group booking with a phone: shows the payment page's QR
 * code (Freedom Pay) and watches the payment until it settles, then opens
 * the success page. "Pay on this device" goes to the same payment page in
 * this browser.
 */
@Component({
  selector: 'app-payment-qr',
  standalone: true,
  imports: [DialogDirective, MoneyPipe, TranslocoPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 animate-fade-in"
    >
      <div
        class="card w-full max-w-sm p-6 text-center animate-slide-up"
        appDialog
        dismissOnBackdrop
        (dismiss)="close()"
      >
        <h2 class="text-lg font-bold text-foreground mb-1">
          {{ (bookingId ? 'paymentQr.payForYourGroup' : 'paymentQr.payForYourTicket') | transloco }}
        </h2>
        <p class="text-sm text-muted-foreground">{{ 'paymentQr.scanWithYourPhone' | transloco }}</p>
        @if (checkout.qr_code) {
          <img
            [src]="checkout.qr_code"
            [alt]="
              'paymentQr.qrAlt'
                | transloco: { amount: (checkout.amount | money: checkout.currency) }
            "
            width="240"
            height="240"
            class="mx-auto my-4 rounded-lg border border-border bg-white p-2"
          />
        }
        <p class="text-2xl font-semibold text-foreground mb-2" data-testid="qr-amount">
          {{ checkout.amount | money: checkout.currency }}
        </p>
        <p class="text-sm mb-4" role="status" aria-live="polite" data-testid="qr-status">
          {{ statusText() }}
        </p>
        @if (state() === 'stopped') {
          <button type="button" class="btn btn-secondary btn-full mb-2" (click)="startPolling()">
            {{ 'paymentQr.checkPaymentStatus' | transloco }}
          </button>
        }
        <button type="button" class="btn btn-primary btn-full mb-2" (click)="payHere()">
          {{ 'paymentQr.payOnThisDevice' | transloco }}
        </button>
        <button
          type="button"
          class="btn btn-ghost btn-full text-muted-foreground"
          (click)="close()"
        >
          {{ 'common.close' | transloco }}
        </button>
      </div>
    </div>
  `,
})
export class PaymentQrComponent implements OnInit, OnDestroy {
  private i18n = inject(LanguageService);
  private poller = inject(PaymentPollingService);
  private router = inject(Router);
  private document = inject(DOCUMENT);

  @Input({ required: true }) checkout!: QrCheckout;
  /** Set for a group booking: the success page then shows the booking. */
  @Input() bookingId: string | null = null;
  /** The dialog was dismissed without a finished payment. */
  @Output() readonly closed = new EventEmitter<void>();

  readonly state = signal<QrState>('waiting');
  private subscription?: Subscription;

  ngOnInit(): void {
    this.startPolling();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  statusText(): string {
    switch (this.state()) {
      case 'paid':
        return this.bookingId
          ? this.i18n.t('paymentQr.paymentReceivedOpeningYour')
          : this.i18n.t('paymentQr.paymentReceivedOpeningYour2');
      case 'failed':
        return this.i18n.t('paymentQr.thePaymentDidNot');
      case 'refunded':
        return this.i18n.t('paymentQr.thePaymentArrivedAfter');
      case 'stopped':
        return this.i18n.t('paymentQr.weStoppedCheckingIf');
      default:
        return this.i18n.t('paymentQr.waitingForThePayment');
    }
  }

  startPolling(): void {
    this.stopPolling();
    this.state.set('waiting');
    let settled = false;
    this.subscription = this.poller
      .poll(this.checkout.payment_id, POLL_INTERVAL_MS, POLL_MAX_MS)
      .subscribe({
        next: (status) => {
          const outcome = paymentOutcome(status);
          this.state.set(outcome);
          if (outcome !== 'waiting') settled = true;
          if (outcome === 'paid') {
            const queryParams: Record<string, string | number> = {
              provider: this.checkout.provider,
              payment: this.checkout.payment_id,
            };
            if (this.bookingId) queryParams['booking_id'] = this.bookingId;
            void this.router.navigate(['/payment/success'], { queryParams });
          }
        },
        complete: () => {
          if (!settled) this.state.set('stopped');
        },
      });
  }

  payHere(): void {
    this.stopPolling();
    this.redirect(this.checkout.checkout_url);
  }

  close(): void {
    this.stopPolling();
    this.closed.emit();
  }

  /** Full-page navigation to the provider (overridden in tests). */
  protected redirect(url: string): void {
    this.document.defaultView?.location.assign(url);
  }

  private stopPolling(): void {
    this.subscription?.unsubscribe();
    this.subscription = undefined;
  }
}
