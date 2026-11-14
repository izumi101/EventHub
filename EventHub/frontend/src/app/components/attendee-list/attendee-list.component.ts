import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { EventService } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { ModalService } from '../../services/modal.service';
import { BookingDto, BookingService } from '../../services/booking.service';
import { Event as EventModel, EventAttendee, EventStatsResponse } from '../../models/models';
import {
  LucideAngularModule,
  Search,
  Users,
  CircleCheckBig,
  ScanLine,
  Download,
  RotateCcw,
  DollarSign,
  Mail,
} from 'lucide-angular';
import { DialogDirective } from '../../directives/dialog.directive';
import { apiErrorMessage } from '../../api/api-error';
import { TranslocoPipe } from '@jsverse/transloco';
import { LocalDatePipe } from '../../i18n/locale.pipes';
import { LanguageService } from '../../i18n/language.service';

@Component({
  selector: 'app-attendee-list',
  standalone: true,
  imports: [
    DialogDirective,
    CommonModule,
    RouterModule,
    FormsModule,
    LucideAngularModule,
    TranslocoPipe,
    LocalDatePipe,
  ],
  template: `
    <div class="page-root">
      <div class="container max-w-4xl py-8">
        <!-- Breadcrumb -->
        <nav
          class="flex items-center gap-1.5 text-sm text-muted-foreground mb-6"
          [attr.aria-label]="'attendees.breadcrumb' | transloco"
        >
          <a routerLink="/organizer/dashboard" class="hover:text-foreground transition-colors">{{
            'nav.dashboard' | transloco
          }}</a>
          <span>/</span>
          <span class="text-foreground font-medium truncate max-w-xs">
            {{ event?.title || ('nav.event' | transloco) }}
          </span>
          <span>/</span>
          <span class="text-muted-foreground">{{ 'nav.attendees' | transloco }}</span>
        </nav>

        <!-- Header -->
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h1 class="text-2xl font-bold text-foreground">{{ 'nav.attendees' | transloco }}</h1>
            @if (event) {
              <p class="text-sm text-muted-foreground mt-1">
                {{ event.title }} · {{ event.date | localDate: 'MMM d, y' }}
              </p>
            }
          </div>

          <div class="flex items-center gap-2 flex-wrap">
            <button
              (click)="showMessage = true"
              class="btn btn-secondary btn-sm flex items-center gap-1.5"
            >
              <lucide-icon [img]="icons.Mail" class="w-4 h-4" aria-hidden="true" />
              {{ 'attendees.message' | transloco }}
            </button>
            <button
              (click)="exportCsv()"
              [disabled]="exporting"
              class="btn btn-secondary btn-sm flex items-center gap-1.5"
            >
              <lucide-icon [img]="icons.Download" class="w-4 h-4" aria-hidden="true" />
              {{ (exporting ? 'attendees.exporting' : 'attendees.exportExcel') | transloco }}
            </button>
            <a routerLink="/scan" class="btn btn-primary btn-sm flex items-center gap-1.5">
              <lucide-icon [img]="icons.ScanLine" class="w-4 h-4" aria-hidden="true" />
              {{ 'attendees.scanTickets' | transloco }}
            </a>

            <!-- Stats -->
            @if (stats) {
              <div class="flex items-center gap-4 text-sm">
                <div class="text-center">
                  <p class="font-bold text-foreground text-lg">{{ stats.total_registrations }}</p>
                  <p class="text-xs text-muted-foreground">
                    {{ 'attendees.registered' | transloco }}
                  </p>
                </div>
                <div class="w-px h-8 bg-border"></div>
                <div class="text-center">
                  <p class="font-bold text-foreground text-lg">{{ stats.checked_in }}</p>
                  <p class="text-xs text-muted-foreground">
                    {{ 'analytics.checkedIn' | transloco }}
                  </p>
                </div>
                <div class="w-px h-8 bg-border"></div>
                <div class="text-center">
                  <p class="font-bold text-primary text-lg">{{ stats.check_in_rate }}%</p>
                  <p class="text-xs text-muted-foreground">{{ 'attendees.rate' | transloco }}</p>
                </div>
              </div>
            }
          </div>
        </div>

        <!-- Search -->
        <label
          class="flex items-center gap-2 mb-4 max-w-xs border border-border rounded-md px-3 h-9 bg-background focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-shadow cursor-text"
        >
          <lucide-icon
            [img]="icons.Search"
            class="w-4 h-4 text-muted-foreground flex-shrink-0"
            aria-hidden="true"
          />
          <input
            type="search"
            [(ngModel)]="searchQuery"
            (input)="onSearch()"
            [placeholder]="'attendees.searchAttendees' | transloco"
            class="flex-1 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
            [attr.aria-label]="'attendees.searchAttendees2' | transloco"
          />
        </label>

        <!-- Table / list -->
        @if (loading) {
          <div class="flex items-center justify-center py-16 gap-3 text-muted-foreground">
            <span class="spinner"></span>
            <span class="text-sm">{{ 'attendees.loadingAttendees' | transloco }}</span>
          </div>
        } @else if (filtered.length === 0) {
          <div class="flex flex-col items-center justify-center py-16 text-center">
            <lucide-icon
              [img]="icons.Users"
              class="w-8 h-8 text-muted-foreground/40 mb-3"
              aria-hidden="true"
            />
            <p class="text-sm text-muted-foreground">
              {{
                (searchQuery ? 'attendees.noAttendeesMatchYour' : 'attendees.noAttendeesYet')
                  | transloco
              }}
            </p>
          </div>
        } @else {
          <!-- Desktop table -->
          <div class="card overflow-hidden hidden sm:block">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-border bg-muted/40">
                  <th
                    class="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide"
                  >
                    {{ 'attendees.attendee' | transloco }}
                  </th>
                  <th
                    class="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide"
                  >
                    {{ 'common.status' | transloco }}
                  </th>
                  <th
                    class="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide"
                  >
                    {{ 'attendees.payment' | transloco }}
                  </th>
                  <th
                    class="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide"
                  >
                    {{ 'attendees.checkIn' | transloco }}
                  </th>
                  <th
                    class="text-right px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide"
                  >
                    {{ 'common.actions' | transloco }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-border">
                @for (reg of filtered; track reg.id) {
                  <tr
                    class="hover:bg-muted/30 transition-colors"
                    [class.bg-[color:var(--pine-50)]]="reg.is_checked_in"
                  >
                    <td class="px-4 py-3">
                      <div class="flex items-center gap-2.5">
                        <div
                          class="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary flex-shrink-0"
                        >
                          {{
                            reg.full_name.charAt(0).toUpperCase() ||
                              reg.username.charAt(0).toUpperCase()
                          }}
                        </div>
                        <div class="min-w-0">
                          <p class="font-medium text-foreground truncate">
                            {{ reg.full_name || reg.username }}
                          </p>
                          <p class="text-xs text-muted-foreground truncate">
                            {{ reg.email || '@' + reg.username }}
                          </p>
                          @if (reg.answers.length) {
                            <div class="flex flex-wrap gap-1 mt-1">
                              @for (a of reg.answers; track a.label) {
                                <span
                                  class="text-[10px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded"
                                  [title]="a.label"
                                >
                                  {{ a.label }}:
                                  <span class="text-foreground font-medium">{{
                                    a.answer || '—'
                                  }}</span>
                                </span>
                              }
                            </div>
                          }
                        </div>
                      </div>
                    </td>
                    <td class="px-4 py-3">
                      <span class="badge {{ statusBadgeClass(reg.status) }}">{{
                        statusLabel(reg.status)
                      }}</span>
                      @if (reg.promo) {
                        <span
                          class="ml-1 text-[10px] font-bold uppercase text-primary bg-primary/10 px-1.5 py-0.5 rounded"
                          >{{ reg.promo.code }}</span
                        >
                      }
                    </td>
                    <td class="px-4 py-3">
                      @if (reg.payment) {
                        @if (reg.payment.status === 'refunded') {
                          <span class="text-xs text-[color:var(--destructive)] font-medium">{{
                            'attendees.refundedRefundedamountCurrency'
                              | transloco
                                : {
                                    refundedAmount: reg.payment.refunded_amount,
                                    currency: currency,
                                  }
                          }}</span>
                        } @else if (+reg.payment.refunded_amount > 0) {
                          <span class="text-xs text-foreground"
                            >{{ reg.payment.net_amount }} {{ currency }}</span
                          >
                          <span class="text-[10px] text-ember ml-1"
                            >(−{{ reg.payment.refunded_amount }} {{ currency }})</span
                          >
                        } @else {
                          <span class="text-xs text-foreground font-medium"
                            >{{ reg.payment.amount }} {{ currency }}</span
                          >
                          <span class="text-[10px] text-muted-foreground ml-1">{{
                            reg.payment.method === 'offline' ? 'cash' : 'card'
                          }}</span>
                        }
                      } @else {
                        <span class="text-xs text-muted-foreground">—</span>
                      }
                    </td>
                    <td class="px-4 py-3">
                      @if (reg.is_checked_in) {
                        <span
                          class="flex items-center gap-1 text-xs text-[color:var(--pine-600)] font-medium"
                        >
                          <lucide-icon
                            [img]="icons.CircleCheckBig"
                            class="w-3.5 h-3.5"
                            aria-hidden="true"
                          />
                          {{ reg.checked_in_at | localDate: 'HH:mm' }}
                        </span>
                      } @else if (reg.status === 'confirmed') {
                        <span class="text-xs text-muted-foreground">{{
                          'attendees.awaitingScan' | transloco
                        }}</span>
                      } @else {
                        <span class="text-xs text-muted-foreground">—</span>
                      }
                    </td>
                    <td class="px-4 py-3 text-right whitespace-nowrap">
                      @if (reg.status === 'pending') {
                        <button
                          (click)="markPaid(reg)"
                          [disabled]="actingId === reg.id"
                          class="text-xs font-medium text-[color:var(--pine-600)] hover:text-[color:var(--pine-600)] inline-flex items-center gap-1"
                        >
                          <lucide-icon [img]="icons.DollarSign" class="w-3.5 h-3.5" />
                          {{ 'attendees.markPaid' | transloco }}
                        </button>
                      } @else if (reg.payment?.is_refundable) {
                        <button
                          (click)="openRefund(reg)"
                          class="text-xs font-medium text-[color:var(--destructive)] hover:text-[color:var(--destructive)] inline-flex items-center gap-1"
                        >
                          <lucide-icon [img]="icons.RotateCcw" class="w-3.5 h-3.5" />
                          {{ 'attendees.refund' | transloco }}
                        </button>
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <!-- Mobile cards -->
          <div class="sm:hidden space-y-3">
            @for (reg of filtered; track reg.id) {
              <div
                class="card p-4"
                [class.border-l-4]="true"
                [class.border-l-emerald-400]="reg.is_checked_in"
              >
                <div class="flex items-center gap-3 mb-3">
                  <div
                    class="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center text-sm font-bold text-primary"
                  >
                    {{
                      reg.full_name.charAt(0).toUpperCase() || reg.username.charAt(0).toUpperCase()
                    }}
                  </div>
                  <div class="flex-1 min-w-0">
                    <p class="text-sm font-semibold text-foreground truncate">
                      {{ reg.full_name || reg.username }}
                    </p>
                    <p class="text-xs text-muted-foreground truncate">
                      {{ reg.email || '@' + reg.username }}
                    </p>
                  </div>
                  <span class="badge {{ statusBadgeClass(reg.status) }}">{{
                    statusLabel(reg.status)
                  }}</span>
                </div>

                <div class="flex items-center justify-between text-xs">
                  @if (reg.payment) {
                    <span class="text-foreground font-medium">
                      @if (reg.payment.status === 'refunded') {
                        {{
                          'attendees.refundedRefundedamountCurrency'
                            | transloco
                              : { refundedAmount: reg.payment.refunded_amount, currency: currency }
                        }}
                      } @else {
                        {{ reg.payment.net_amount }} {{ currency }}
                      }
                    </span>
                  } @else {
                    <span class="text-muted-foreground">{{
                      'attendees.noPayment' | transloco
                    }}</span>
                  }

                  @if (reg.status === 'pending') {
                    <button
                      (click)="markPaid(reg)"
                      [disabled]="actingId === reg.id"
                      class="text-[color:var(--pine-600)] font-medium"
                    >
                      {{ 'attendees.markPaid' | transloco }}
                    </button>
                  } @else if (reg.payment?.is_refundable) {
                    <button
                      (click)="openRefund(reg)"
                      class="text-[color:var(--destructive)] font-medium"
                    >
                      {{ 'attendees.refund' | transloco }}
                    </button>
                  }
                </div>
              </div>
            }
          </div>
        }

        <!-- Group bookings -->
        @if (bookings.length) {
          <section class="mt-10" aria-labelledby="group-bookings-heading">
            <h2 id="group-bookings-heading" class="text-base font-semibold text-foreground mb-3">
              {{ 'attendees.groupBookings' | transloco }}
            </h2>
            <div class="card divide-y divide-border">
              @for (b of bookings; track b.id) {
                <div class="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div class="min-w-0">
                    <p class="text-sm font-semibold text-foreground">
                      {{
                        'attendees.ownerusernameSeatcountSeats'
                          | transloco
                            : {
                                ownerUsername: b.owner_username,
                                seatCount: b.seat_count || b.seats.length,
                              }
                      }}
                    </p>
                    <p class="text-xs text-muted-foreground">
                      {{ b.created_at | localDate: 'MMM d, y · h:mm a' }} ·
                      @if (b.status === 'refunded') {
                        <span class="text-[color:var(--destructive)] font-medium">{{
                          'attendees.refundedAmountpaidCurrency'
                            | transloco: { amountPaid: b.amount_paid, currency: b.currency }
                        }}</span>
                      } @else if (b.status === 'confirmed') {
                        {{
                          'attendees.paidAmountpaidCurrency'
                            | transloco
                              : { amountPaid: b.amount_paid || b.total_due, currency: b.currency }
                        }}
                      } @else {
                        {{
                          'attendees.awaitingPaymentTotaldueCurrency'
                            | transloco: { totalDue: b.total_due, currency: b.currency }
                        }}
                      }
                    </p>
                  </div>
                  @if (b.status === 'confirmed') {
                    <button
                      (click)="refundBooking(b)"
                      [disabled]="refundingBookingId === b.id"
                      class="btn btn-secondary btn-sm text-[color:var(--destructive)] flex-shrink-0"
                    >
                      {{
                        (refundingBookingId === b.id
                          ? 'attendees.refunding'
                          : 'attendees.refundBooking'
                        ) | transloco
                      }}
                    </button>
                  }
                </div>
              }
            </div>
          </section>
        }
      </div>
    </div>

    <!-- Refund modal -->
    @if (refundReg) {
      <div
        class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4 animate-fade-in"
      >
        <div
          class="card w-full max-w-sm p-6 animate-slide-up"
          appDialog
          dismissOnBackdrop
          (dismiss)="refundReg = null"
        >
          <h3 class="text-lg font-bold text-foreground mb-1">
            {{ 'attendees.refundTicket' | transloco }}
          </h3>
          <p class="text-sm text-muted-foreground mb-4">
            {{
              'attendees.fullnamePaidNetamountCurrency'
                | transloco
                  : {
                      fullName: refundReg.full_name || refundReg.username,
                      netAmount: refundReg.payment?.net_amount,
                      currency: currency,
                    }
            }}
          </p>

          <label
            for="attendee-list-refund-amount"
            class="block text-sm font-medium text-foreground mb-1.5"
            >{{ 'attendees.amountToRefund' | transloco }}</label
          >
          <div class="flex items-center gap-2 mb-2">
            <span class="text-muted-foreground">$</span>
            <input
              id="attendee-list-refund-amount"
              type="number"
              [(ngModel)]="refundAmount"
              [max]="refundReg.payment?.net_amount ?? null"
              min="0"
              step="0.01"
              class="input flex-1"
            />
            <button
              (click)="refundAmount = refundReg.payment?.net_amount || ''"
              class="btn btn-ghost btn-sm text-xs"
            >
              {{ 'attendees.full' | transloco }}
            </button>
          </div>

          <label
            for="attendee-list-refund-reason"
            class="block text-sm font-medium text-foreground mb-1.5 mt-3"
            >{{ 'attendees.reasonOptional' | transloco }}</label
          >
          <input
            id="attendee-list-refund-reason"
            [(ngModel)]="refundReason"
            [placeholder]="'attendees.eGEventCancelled' | transloco"
            class="input w-full mb-4"
          />

          <div class="flex gap-2">
            <button (click)="refundReg = null" class="btn btn-secondary flex-1">
              {{ 'common.cancel' | transloco }}
            </button>
            <button
              (click)="confirmRefund()"
              [disabled]="refunding || !refundAmount"
              class="btn btn-danger flex-1"
            >
              {{
                refunding
                  ? ('attendees.refunding' | transloco)
                  : ('attendees.refundAmount'
                    | transloco: { amount: refundAmount || '0', currency: currency })
              }}
            </button>
          </div>
        </div>
      </div>
    }

    <!-- Message attendees modal -->
    @if (showMessage) {
      <div
        class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4 animate-fade-in"
      >
        <div
          class="card w-full max-w-md p-6 animate-slide-up"
          appDialog
          dismissOnBackdrop
          (dismiss)="showMessage = false"
        >
          <h3 class="text-lg font-bold text-foreground mb-1 flex items-center gap-2">
            <lucide-icon [img]="icons.Mail" class="w-5 h-5 text-primary" />
            {{ 'attendees.messageAttendees' | transloco }}
          </h3>
          <p class="text-sm text-muted-foreground mb-4">
            {{ 'attendees.sendsAnInApp' | transloco }}
          </p>

          <label
            for="attendee-list-msg-audience"
            class="block text-sm font-medium text-foreground mb-1.5"
            >{{ 'attendees.sendTo' | transloco }}</label
          >
          <select
            id="attendee-list-msg-audience"
            [(ngModel)]="msgAudience"
            class="input w-full mb-3"
          >
            <option value="all">{{ 'attendees.everyone' | transloco }}</option>
            <option value="confirmed">{{ 'attendees.confirmedOnly' | transloco }}</option>
            <option value="pending">{{ 'attendees.pendingPayment' | transloco }}</option>
            <option value="checked_in">{{ 'analytics.checkedIn' | transloco }}</option>
          </select>

          <label
            for="attendee-list-msg-subject"
            class="block text-sm font-medium text-foreground mb-1.5"
            >{{ 'attendees.subject' | transloco }}</label
          >
          <input
            id="attendee-list-msg-subject"
            [(ngModel)]="msgSubject"
            [placeholder]="'attendees.eGScheduleUpdate' | transloco"
            class="input w-full mb-3"
          />

          <label
            for="attendee-list-msg-body"
            class="block text-sm font-medium text-foreground mb-1.5"
            >{{ 'attendees.message' | transloco }}</label
          >
          <textarea
            id="attendee-list-msg-body"
            [(ngModel)]="msgBody"
            rows="4"
            [placeholder]="'attendees.writeYourMessageTo' | transloco"
            class="input resize-none w-full mb-4"
          ></textarea>

          <div class="flex gap-2">
            <button (click)="showMessage = false" class="btn btn-secondary flex-1">
              {{ 'common.cancel' | transloco }}
            </button>
            <button
              (click)="sendMessage()"
              [disabled]="sending || !msgSubject.trim() || !msgBody.trim()"
              class="btn btn-primary flex-1"
            >
              {{ (sending ? 'attendees.sending' : 'attendees.sendMessage') | transloco }}
            </button>
          </div>
        </div>
      </div>
    }
  `,
})
export class AttendeeListComponent implements OnInit {
  private i18n = inject(LanguageService);
  private route = inject(ActivatedRoute);
  private eventService = inject(EventService);
  private toastService = inject(ToastService);
  private bookingService = inject(BookingService);
  private modalService = inject(ModalService);

  eventId: number | null = null;
  event: EventModel | null = null;
  registrations: EventAttendee[] = [];
  filtered: EventAttendee[] = [];
  stats: EventStatsResponse | null = null;
  loading = true;
  searchQuery = '';
  exporting = false;
  actingId: number | null = null;

  // Refund modal
  refundReg: EventAttendee | null = null;
  refundAmount: string | number = '';
  refundReason = '';
  refunding = false;

  // Group bookings
  bookings: BookingDto[] = [];
  refundingBookingId: string | null = null;

  // Message modal
  showMessage = false;
  msgAudience = 'all';
  msgSubject = '';
  msgBody = '';
  sending = false;

  readonly icons = {
    Search,
    Users,
    CircleCheckBig,
    ScanLine,
    Download,
    RotateCcw,
    DollarSign,
    Mail,
  };

  get currency(): string {
    return this.event?.currency || 'USD';
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.eventId = +id;
      this.loadData();
    }
  }

  loadData(): void {
    if (!this.eventId) return;
    this.loading = true;
    this.eventService.getEvent(this.eventId).subscribe((e) => {
      this.event = e;
    });
    this.eventService.getEventStats(this.eventId).subscribe((s) => {
      this.stats = s;
    });
    this.bookingService.listForEvent(this.eventId).subscribe({
      next: (bookings) => {
        this.bookings = bookings;
      },
      error: () => {
        this.bookings = [];
      },
    });
    this.eventService.getEventRegistrations(this.eventId).subscribe({
      next: (regs) => {
        this.registrations = regs.filter((r) => r.status !== 'cancelled');
        this.filtered = [...this.registrations];
        this.loading = false;
      },
      error: () => {
        this.loading = false;
      },
    });
  }

  onSearch(): void {
    const q = this.searchQuery.toLowerCase().trim();
    this.filtered = q
      ? this.registrations.filter((r) => r.username.toLowerCase().includes(q))
      : [...this.registrations];
  }

  statusBadgeClass(status: string): string {
    const map: Record<string, string> = {
      confirmed: 'badge-confirmed',
      pending: 'badge-pending',
      rejected: 'badge-rejected',
      cancelled: 'badge-rejected',
    };
    return map[status] ?? 'badge-pending';
  }

  statusLabel(status: string): string {
    const map: Record<string, string> = {
      confirmed: this.i18n.t('common.confirmed'),
      pending: this.i18n.t('attendees.pendingPayment'),
      rejected: this.i18n.t('common.cancelled'),
      cancelled: this.i18n.t('common.cancelled'),
    };
    return map[status] ?? status;
  }

  exportCsv(): void {
    if (!this.eventId) return;
    this.exporting = true;
    this.eventService.exportAttendees(this.eventId).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${(this.event?.title || 'event').replace(/\s+/g, '-')}-attendees.xlsx`;
        a.click();
        window.URL.revokeObjectURL(url);
        this.exporting = false;
      },
      error: () => {
        this.exporting = false;
        this.toastService.error(this.i18n.t('attendees.exportFailed'));
      },
    });
  }

  markPaid(reg: EventAttendee): void {
    this.actingId = reg.id;
    this.eventService.markOfflinePaid(reg.id).subscribe({
      next: () => {
        this.toastService.success(this.i18n.t('attendees.markedAsPaid'));
        this.actingId = null;
        this.loadData();
      },
      error: () => {
        this.actingId = null;
        this.toastService.error(this.i18n.t('attendees.couldNotMarkAs'));
      },
    });
  }

  openRefund(reg: EventAttendee): void {
    this.refundReg = reg;
    this.refundAmount = reg.payment?.net_amount || '';
    this.refundReason = '';
  }

  confirmRefund(): void {
    if (!this.refundReg) return;
    this.refunding = true;
    this.eventService
      .refundRegistration(this.refundReg.id, {
        amount: String(this.refundAmount),
        reason: this.refundReason,
      })
      .subscribe({
        next: () => {
          this.toastService.success(this.i18n.t('attendees.refundIssued'));
          this.refunding = false;
          this.refundReg = null;
          this.loadData();
        },
        error: (err) => {
          this.refunding = false;
          this.toastService.error(
            apiErrorMessage(err, this.i18n.t('attendees.refundFailed'), 'error'),
          );
        },
      });
  }

  async refundBooking(b: BookingDto): Promise<void> {
    const ok = await this.modalService.open({
      title: this.i18n.t('attendees.refundGroupBooking'),
      message: this.i18n.t('attendees.refundBookingMessage', {
        ownerUsername: b.owner_username,
        amountPaid: b.amount_paid || b.total_due,
        currency: b.currency,
        seatsLength: b.seats.length,
      }),
      confirmText: this.i18n.t('attendees.refund'),
      isDestructive: true,
    });
    if (!ok) return;
    this.refundingBookingId = b.id;
    this.bookingService.refund(b.id).subscribe({
      next: () => {
        this.refundingBookingId = null;
        this.toastService.success(this.i18n.t('attendees.groupBookingRefunded'));
        this.loadData();
      },
      error: (err) => {
        this.refundingBookingId = null;
        this.toastService.error(
          apiErrorMessage(err, this.i18n.t('attendees.refundFailed'), 'error'),
        );
      },
    });
  }

  sendMessage(): void {
    if (!this.eventId || !this.msgSubject.trim() || !this.msgBody.trim()) return;
    this.sending = true;
    this.eventService
      .broadcast(this.eventId, {
        subject: this.msgSubject.trim(),
        body: this.msgBody.trim(),
        audience: this.msgAudience,
      })
      .subscribe({
        next: (res) => {
          this.sending = false;
          this.showMessage = false;
          this.msgSubject = '';
          this.msgBody = '';
          this.toastService.success(
            this.i18n.t(res.email_enabled ? 'attendees.sentToEmailed' : 'attendees.sentTo', {
              recipients: res.recipients,
              emailed: res.emailed,
            }),
          );
        },
        error: (err) => {
          this.sending = false;
          this.toastService.error(
            apiErrorMessage(err, this.i18n.t('attendees.couldNotSendMessage'), 'error'),
          );
        },
      });
  }
}
