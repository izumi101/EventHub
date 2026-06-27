import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { EventService, PromoQuote, EventQuestion, TicketType } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { Event, Seat, SeatMap } from '../../models/models';
import { SeatSelectorComponent } from '../seat-selector/seat-selector.component';

/** The "Confirm registration" checkout dialog.
 *
 *  Owns everything the buyer selects — ticket tier, seat, promo code,
 *  donation amount, organizer questions, notes — and the resulting price
 *  math. On confirm it emits the ready-to-send registration payload; the
 *  parent page runs the actual registration / payment / queue flow. */
@Component({
  selector: 'app-event-checkout-modal',
  standalone: true,
  imports: [CommonModule, FormsModule, SeatSelectorComponent],
  template: `
    <div
      class="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4 animate-fade-in"
      (click)="closed.emit()"
    >
      <div
        class="card w-full max-w-md shadow-lg animate-slide-up"
        (click)="$event.stopPropagation()"
      >
        <div class="flex items-center justify-between p-5 border-b border-border">
          <h2 class="text-base font-semibold text-foreground">Confirm registration</h2>
          <button
            (click)="closed.emit()"
            class="btn btn-ghost btn-sm w-8 h-8 p-0 text-muted-foreground"
            aria-label="Close"
          >✕</button>
        </div>

        <div class="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          <!-- Summary -->
          <div class="p-3 rounded-lg bg-muted border border-border text-sm">
            <div class="flex justify-between mb-1.5">
              <span class="text-muted-foreground">Event</span>
              <span class="font-medium text-foreground text-right max-w-[200px] truncate">{{ event.title }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-muted-foreground">Price</span>
              <span class="font-semibold text-foreground">{{ event.is_free ? 'Free' : '$' + currentGaPrice }}</span>
            </div>
            @if (selectedSeat) {
              <div class="flex justify-between border-t border-border pt-1.5 mt-1.5">
                <span class="text-muted-foreground">Seat</span>
                <span class="font-medium text-foreground">Row {{ selectedSeat.row }}, Seat {{ selectedSeat.col }}</span>
              </div>
            }
            @if (selectedTicketType) {
              <div class="flex justify-between border-t border-border pt-1.5 mt-1.5">
                <span class="text-muted-foreground">Ticket</span>
                <span class="font-medium text-foreground">{{ selectedTicketType.name }}</span>
              </div>
            }
            @if (promoQuote) {
              <div class="flex justify-between text-[color:var(--pine-600)] mt-1.5">
                <span>Promo {{ promoQuote.code }}</span>
                <span class="font-medium">−{{ '$' + promoQuote.savings }}</span>
              </div>
            }
            @if (showFeeLines()) {
              <div class="flex justify-between text-muted-foreground mt-1.5">
                <span>Subtotal</span>
                <span>{{ '$' + checkoutSubtotal }}</span>
              </div>
              @if (taxAmount > 0) {
                <div class="flex justify-between text-muted-foreground">
                  <span>Tax ({{ event.tax_percent }}%)</span>
                  <span>{{ '$' + taxAmount.toFixed(2) }}</span>
                </div>
              }
              @if (feeAmount > 0) {
                <div class="flex justify-between text-muted-foreground">
                  <span>Service fee ({{ event.service_fee_percent }}%)</span>
                  <span>{{ '$' + feeAmount.toFixed(2) }}</span>
                </div>
              }
            }
            @if (selectedTicketType || promoQuote || showFeeLines()) {
              <div class="flex justify-between border-t border-border pt-1.5 mt-1.5">
                <span class="text-foreground font-semibold">Total</span>
                <span class="text-foreground font-bold">{{ '$' + checkoutTotal }}</span>
              </div>
            }
          </div>

          <!-- Ticket tier selection -->
          @if (event.has_ticket_types) {
            <div class="space-y-2">
              <p class="text-sm font-semibold text-foreground">Choose your ticket</p>
              @for (tt of event.ticket_types; track tt.id) {
                <button
                  type="button"
                  (click)="selectTicketType(tt)"
                  [disabled]="tt.sale_state !== 'on_sale'"
                  class="w-full text-left p-3 rounded-xl border-2 transition-all"
                  [class]="selectedTicketType?.id === tt.id
                    ? 'border-primary bg-primary/5'
                    : tt.sale_state !== 'on_sale'
                      ? 'border-border opacity-50 cursor-not-allowed'
                      : 'border-border hover:border-primary/40'"
                >
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                      <div class="flex items-center gap-2">
                        <span class="font-semibold text-foreground">{{ tt.name }}</span>
                        @if (tt.kind === 'donation') { <span class="text-[10px] font-bold uppercase text-ember bg-ember/10 px-1.5 py-0.5 rounded">Donation</span> }
                      </div>
                      @if (tt.description) { <p class="text-xs text-muted-foreground mt-0.5">{{ tt.description }}</p> }
                      <p class="text-xs mt-1" [class]="tierAvailabilityClass(tt)">{{ tierAvailabilityLabel(tt) }}</p>
                    </div>
                    <div class="text-right flex-shrink-0">
                      <span class="font-bold text-foreground">
                        @if (tt.kind === 'free') { Free }
                        @else if (tt.kind === 'donation') { {{ '$' + tt.price }}+ }
                        @else { {{ '$' + tt.price }} }
                      </span>
                    </div>
                  </div>

                  <!-- Donation amount input -->
                  @if (selectedTicketType?.id === tt.id && tt.kind === 'donation') {
                    <div class="mt-3 flex items-center gap-2" (click)="$event.stopPropagation()">
                      <span class="text-muted-foreground">$</span>
                      <input type="number" [(ngModel)]="donationAmount" [min]="tt.price" step="1"
                        class="input flex-1" placeholder="Amount" />
                    </div>
                  }
                </button>
              }
            </div>
          }

          <!-- Promo code (paid events) -->
          @if (showPromoField()) {
            <div>
              <label class="block text-sm font-medium text-foreground mb-1.5">Promo code</label>
              @if (!promoQuote) {
                <div class="flex gap-2">
                  <input
                    [(ngModel)]="promoInput"
                    (keyup.enter)="applyPromo()"
                    placeholder="Enter code"
                    class="input flex-1 uppercase"
                    [class.input-error]="promoError"
                  />
                  <button
                    (click)="applyPromo()"
                    [disabled]="!promoInput.trim() || checkingPromo"
                    class="btn btn-secondary"
                  >
                    {{ checkingPromo ? '…' : 'Apply' }}
                  </button>
                </div>
                @if (promoError) {
                  <p class="text-xs text-destructive mt-1">{{ promoError }}</p>
                }
              } @else {
                <div class="flex items-center justify-between p-2.5 rounded-lg bg-[color:var(--pine-50)] border border-transparent">
                  <span class="text-sm font-medium text-[color:var(--pine-600)]">
                    ✓ {{ promoQuote.code }} applied — you save {{ '$' + promoQuote.savings }}
                  </span>
                  <button (click)="removePromo()" class="text-xs text-[color:var(--pine-600)] hover:underline">Remove</button>
                </div>
              }
            </div>
          }

          <!-- Seat selector (only seat-map events, not ticket-typed) -->
          @if (!event.is_free && !event.has_ticket_types && !seatMapMissing) {
            <div class="border-t border-border pt-4">
              @if (loadingSeatMap || !seatMap) {
                <div class="flex flex-col items-center gap-2 py-6 text-muted-foreground">
                  <span class="spinner spinner-sm"></span>
                  <span class="text-sm">Loading seats…</span>
                </div>
              } @else {
                <app-seat-selector
                  [seats]="seatMap.seats"
                  [eventId]="event.id"
                  (seatSelected)="selectedSeat = $event"
                ></app-seat-selector>
              }
            </div>
          }
          @if (!event.is_free && !event.has_ticket_types && seatMapMissing) {
            <p class="text-xs text-muted-foreground border-t border-border pt-4">
              General admission — no assigned seating for this event.
            </p>
          }

          <!-- Custom organizer questions -->
          @if (questions.length) {
            <div class="border-t border-border pt-4 space-y-3">
              <p class="text-sm font-semibold text-foreground">A few questions from the organizer</p>
              @for (q of questions; track q.id) {
                <div>
                  <label class="block text-sm font-medium text-foreground mb-1.5">
                    {{ q.label }}
                    @if (q.is_required) { <span class="text-destructive">*</span> }
                  </label>

                  @switch (q.question_type) {
                    @case ('textarea') {
                      <textarea [(ngModel)]="answers[q.id]" rows="2" class="input resize-none w-full"></textarea>
                    }
                    @case ('dropdown') {
                      <select [(ngModel)]="answers[q.id]" class="input w-full">
                        <option value="">Select…</option>
                        @for (opt of q.options; track opt) { <option [value]="opt">{{ opt }}</option> }
                      </select>
                    }
                    @case ('checkbox') {
                      <label class="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                        <input type="checkbox" [(ngModel)]="answers[q.id]" class="w-4 h-4 rounded" />
                        Yes
                      </label>
                    }
                    @case ('date') {
                      <input type="date" [(ngModel)]="answers[q.id]" class="input w-full" />
                    }
                    @case ('phone') {
                      <input type="tel" [(ngModel)]="answers[q.id]" placeholder="+1 555 000 0000" class="input w-full" />
                    }
                    @default {
                      <input type="text" [(ngModel)]="answers[q.id]" class="input w-full" />
                    }
                  }
                </div>
              }
            </div>
          }

          <!-- Notes -->
          <div>
            <label for="reg-notes" class="block text-sm font-medium text-foreground mb-1.5">
              Additional notes <span class="text-muted-foreground font-normal">(optional)</span>
            </label>
            <textarea
              id="reg-notes"
              [(ngModel)]="registrationNotes"
              placeholder="Dietary requirements, questions for the organizer..."
              rows="3"
              class="input resize-none"
            ></textarea>
          </div>
        </div>

        <div class="flex items-center gap-3 p-5 border-t border-border">
          <button (click)="closed.emit()" class="btn btn-secondary flex-1">
            Cancel
          </button>
          <button
            (click)="submit()"
            [disabled]="registering || !canConfirm()"
            class="btn btn-primary flex-1"
          >
            @if (registering) {
              <span class="spinner spinner-sm"></span>
              Processing...
            } @else if (event.has_ticket_types && !selectedTicketType) {
              Choose a ticket
            } @else if (!event.is_free && !event.has_ticket_types && !seatMapMissing && (loadingSeatMap || !seatMap)) {
              Loading seats…
            } @else if (!event.is_free && !event.has_ticket_types && !seatMapMissing && !selectedSeat) {
              Select a seat to continue
            } @else if (confirmIsPaid()) {
              Proceed to payment — {{ '$' + checkoutTotal }}
            } @else {
              Confirm registration
            }
          </button>
        </div>
      </div>
    </div>
  `,
})
export class EventCheckoutModalComponent implements OnInit {
  @Input({ required: true }) event!: Event;
  /** The dynamic GA price quoted on the page (falls back to event.price). */
  @Input() currentGaPrice = '0.00';
  /** True while the parent runs the registration / payment flow. */
  @Input() registering = false;

  @Output() closed = new EventEmitter<void>();
  /** Emits the ready-to-send registration payload (without affiliate code —
   *  the parent owns referral attribution). */
  @Output() confirmed = new EventEmitter<Record<string, any>>();

  registrationNotes = '';

  // Seat selection
  seatMap: SeatMap | null = null;
  selectedSeat: Seat | null = null;
  loadingSeatMap = false;
  // Paid events without a seat map are general admission — still purchasable.
  seatMapMissing = false;

  // Promo code
  promoInput = '';
  promoQuote: PromoQuote | null = null;
  promoError = '';
  checkingPromo = false;

  // Ticket types
  selectedTicketType: TicketType | null = null;
  donationAmount: number | null = null;

  // Custom questions
  questions: EventQuestion[] = [];
  answers: Record<number, any> = {};

  constructor(
    private eventService: EventService,
    private toastService: ToastService,
  ) {}

  ngOnInit(): void {
    this.eventService.getEventQuestions(this.event.id).subscribe({
      next: qs => { this.questions = qs; },
      error: () => {},
    });

    // Seat map only matters for paid events without ticket tiers.
    if (!this.event.is_free) {
      this.loadingSeatMap = true;
      this.eventService.getSeatMap(this.event.id).subscribe({
        next: (sm: SeatMap) => {
          this.seatMap = sm;
          this.loadingSeatMap = false;
        },
        error: err => {
          this.loadingSeatMap = false;
          // 404 = no seat map → general admission, purchase proceeds without a seat.
          if (err.status === 404) {
            this.seatMapMissing = true;
          } else {
            this.toastService.error('Failed to load seat map');
          }
        },
      });
    }
  }

  // ── Ticket types ──
  selectTicketType(tt: TicketType): void {
    if (tt.sale_state !== 'on_sale') return;
    this.selectedTicketType = tt;
    if (tt.kind === 'donation') {
      this.donationAmount = Number(tt.price);
    } else {
      this.donationAmount = null;
    }
    // Promo no longer applies once a free tier is picked.
    if (tt.kind === 'free') this.removePromo();
  }

  tierAvailabilityLabel(tt: TicketType): string {
    switch (tt.sale_state) {
      case 'sold_out': return 'Sold out';
      case 'scheduled': return 'Sales not started yet';
      case 'ended': return 'Sales ended';
      case 'inactive': return 'Unavailable';
      default:
        if (tt.available !== null && tt.available <= 10) return `Only ${tt.available} left`;
        return 'Available';
    }
  }

  tierAvailabilityClass(tt: TicketType): string {
    if (tt.sale_state !== 'on_sale') return 'text-muted-foreground';
    if (tt.available !== null && tt.available <= 10) return 'text-warning font-medium';
    return 'text-[color:var(--pine-600)]';
  }

  // ── Promo ──
  showPromoField(): boolean {
    if (this.event.has_ticket_types) {
      // Only for a selected paid/donation tier.
      return !!this.selectedTicketType && this.selectedTicketType.kind !== 'free';
    }
    return !this.event.is_free;
  }

  applyPromo(): void {
    if (!this.promoInput.trim()) return;
    this.checkingPromo = true;
    this.promoError = '';
    // Quote against the price the attendee actually selected (tier / seat).
    const ctx: { ticket_type_id?: number; seat_id?: number } = {};
    if (this.selectedTicketType) ctx.ticket_type_id = this.selectedTicketType.id;
    else if (this.selectedSeat) ctx.seat_id = this.selectedSeat.id;
    this.eventService.validatePromo(this.event.id, this.promoInput.trim(), ctx).subscribe({
      next: q => { this.promoQuote = q; this.checkingPromo = false; },
      error: err => {
        this.promoError = err.error?.error || 'Invalid promo code';
        this.promoQuote = null;
        this.checkingPromo = false;
      },
    });
  }

  removePromo(): void {
    this.promoQuote = null;
    this.promoInput = '';
    this.promoError = '';
  }

  // ── Price math ──

  /** Base price after tier/seat + promo, before tax & fees. */
  get checkoutSubtotalNum(): number {
    let base = 0;
    if (this.selectedTicketType) {
      if (this.selectedTicketType.kind === 'free') base = 0;
      else if (this.selectedTicketType.kind === 'donation') base = Number(this.donationAmount || this.selectedTicketType.price);
      else base = Number(this.selectedTicketType.price);
    } else if (this.selectedSeat) {
      base = Number((this.selectedSeat as any).price ?? this.event.price);
    } else {
      // GA: the dynamic price that will actually be charged.
      base = Number(this.currentGaPrice);
    }
    if (this.promoQuote) {
      if (this.promoQuote.discount_type === 'percent') {
        base = base * (1 - Number(this.promoQuote.discount_value) / 100);
      } else {
        base = Math.max(0, base - Number(this.promoQuote.discount_value));
      }
    }
    return base;
  }

  get checkoutSubtotal(): string { return this.checkoutSubtotalNum.toFixed(2); }

  get taxAmount(): number {
    const pct = Number(this.event.tax_percent || 0);
    return this.checkoutSubtotalNum > 0 ? this.checkoutSubtotalNum * pct / 100 : 0;
  }

  get feeAmount(): number {
    const pct = Number(this.event.service_fee_percent || 0);
    return this.checkoutSubtotalNum > 0 ? this.checkoutSubtotalNum * pct / 100 : 0;
  }

  showFeeLines(): boolean {
    const hasFees = Number(this.event.tax_percent || 0) > 0 || Number(this.event.service_fee_percent || 0) > 0;
    return hasFees && this.event.fees_passed_to_buyer !== false && this.checkoutSubtotalNum > 0;
  }

  get checkoutTotal(): string {
    let total = this.checkoutSubtotalNum;
    if (this.event.fees_passed_to_buyer !== false) {
      total += this.taxAmount + this.feeAmount;
    }
    return total.toFixed(2);
  }

  // ── Confirm ──

  confirmIsPaid(): boolean {
    if (this.event.has_ticket_types) {
      return !!this.selectedTicketType && this.selectedTicketType.kind !== 'free'
        && Number(this.checkoutTotal) > 0;
    }
    return !this.event.is_free;
  }

  canConfirm(): boolean {
    if (this.event.has_ticket_types) return !!this.selectedTicketType;
    if (this.event.is_free) return true;
    if (this.seatMapMissing) return true; // general admission
    return !!this.seatMap && !!this.selectedSeat;
  }

  submit(): void {
    // Ticket-typed events require a tier; seat-map events require a seat.
    if (this.event.has_ticket_types) {
      if (!this.selectedTicketType) { this.toastService.error('Please choose a ticket'); return; }
      if (this.selectedTicketType.kind === 'donation') {
        const min = Number(this.selectedTicketType.price);
        if (Number(this.donationAmount) < min) {
          this.toastService.error(`Minimum contribution is $${min}`);
          return;
        }
      }
    } else if (!this.event.is_free && !this.seatMapMissing && !this.selectedSeat) {
      this.toastService.error('Please select a seat');
      return;
    }

    // Enforce required custom questions.
    const missing = this.questions.find(q => q.is_required && !this.answers[q.id] && this.answers[q.id] !== false);
    if (missing) {
      this.toastService.error(`Please answer: ${missing.label}`);
      return;
    }

    const payload: Record<string, any> = { notes: this.registrationNotes };
    if (this.selectedSeat) payload['seat_id'] = this.selectedSeat.id;
    if (this.selectedTicketType) payload['ticket_type_id'] = this.selectedTicketType.id;
    if (this.selectedTicketType?.kind === 'donation') payload['donation_amount'] = this.donationAmount;
    if (this.promoQuote) payload['promo_code'] = this.promoQuote.code;
    if (this.questions.length) payload['answers'] = this.answers;

    this.confirmed.emit(payload);
  }
}
