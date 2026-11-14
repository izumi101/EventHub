import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { EventService } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { PaymentService } from '../../services/payment.service';
import { Registration } from '../../models/models';
import {
  LucideAngularModule,
  Calendar,
  MapPin,
  Clock,
  Download,
  Share2,
  Ticket,
  FileText,
} from 'lucide-angular';
import * as QRCode from 'qrcode';
import { MoneyPipe } from '../../pipes/money.pipe';
import { DialogDirective } from '../../directives/dialog.directive';
import { apiErrorMessage } from '../../api/api-error';
import { canShareFiles, supportsWebShare } from '../../utils/browser-support';
import { TranslocoPipe } from '@jsverse/transloco';
import { LocalDatePipe } from '../../i18n/locale.pipes';
import { LanguageService } from '../../i18n/language.service';

@Component({
  selector: 'app-my-registrations',
  standalone: true,
  imports: [
    DialogDirective,
    MoneyPipe,
    CommonModule,
    FormsModule,
    RouterModule,
    LucideAngularModule,
    TranslocoPipe,
    LocalDatePipe,
  ],
  template: `
    <div class="page-root">
      <div class="container max-w-3xl py-8">
        <!-- Header -->
        <div class="flex items-center justify-between mb-7">
          <div>
            <h1 class="text-2xl font-bold text-foreground">
              {{ 'myRegistrations.myTickets' | transloco }}
            </h1>
            <p class="text-sm text-muted-foreground mt-1">
              {{ 'myRegistrations.yourEventRegistrationsAnd' | transloco }}
            </p>
          </div>
        </div>

        <!-- Tabs -->
        <div class="flex border-b border-border mb-6">
          <button
            (click)="activeTab = 'upcoming'"
            class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px"
            [class]="
              activeTab === 'upcoming'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            "
          >
            <span class="flex items-center gap-1.5">
              <lucide-icon [img]="icons.Calendar" class="w-4 h-4" aria-hidden="true" />
              {{
                'myRegistrations.upcomingUpcomingregslength'
                  | transloco: { upcomingRegsLength: upcomingRegs.length }
              }}
            </span>
          </button>
          <button
            (click)="activeTab = 'past'"
            class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px"
            [class]="
              activeTab === 'past'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            "
          >
            <span class="flex items-center gap-1.5">
              <lucide-icon [img]="icons.Clock" class="w-4 h-4" aria-hidden="true" />
              {{
                'myRegistrations.pastPastregslength'
                  | transloco: { pastRegsLength: pastRegs.length }
              }}
            </span>
          </button>
        </div>

        <!-- Loading -->
        @if (loading) {
          <div class="flex items-center justify-center py-20 gap-3 text-muted-foreground">
            <span class="spinner"></span>
            <span class="text-sm">{{ 'myRegistrations.loadingTickets' | transloco }}</span>
          </div>
        } @else {
          @if (visibleRegs.length === 0) {
            @if (activeTab === 'upcoming') {
              <div class="flex flex-col items-center justify-center py-20 text-center">
                <div
                  class="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center mb-4"
                >
                  <lucide-icon
                    [img]="icons.Ticket"
                    class="w-8 h-8 text-primary/50"
                    aria-hidden="true"
                  />
                </div>
                <h3 class="text-base font-semibold text-foreground mb-1">
                  {{ 'myRegistrations.noTicketsYet' | transloco }}
                </h3>
                <p class="text-sm text-muted-foreground mb-5 max-w-xs">
                  {{ 'myRegistrations.whenYouRegisterFor' | transloco }}
                </p>
                <a routerLink="/" class="btn btn-primary btn-sm">{{
                  'favorites.discoverEvents' | transloco
                }}</a>
              </div>
            } @else {
              <div class="flex flex-col items-center justify-center py-20 text-center">
                <div
                  class="w-16 h-16 rounded-2xl bg-gradient-to-br from-muted to-muted/50 flex items-center justify-center mb-4"
                >
                  <lucide-icon
                    [img]="icons.Clock"
                    class="w-8 h-8 text-muted-foreground/50"
                    aria-hidden="true"
                  />
                </div>
                <h3 class="text-base font-semibold text-foreground mb-1">
                  {{ 'myRegistrations.noPastTickets' | transloco }}
                </h3>
                <p class="text-sm text-muted-foreground">
                  {{ 'myRegistrations.yourAttendedEventsWill' | transloco }}
                </p>
              </div>
            }
          } @else {
            <div class="space-y-5">
              @for (reg of visibleRegs; track reg.id) {
                <!-- ═══ BOARDING PASS TICKET ═══ -->
                <div
                  class="ticket group rounded-2xl overflow-hidden shadow-md hover:shadow-xl transition-all duration-300 ring-1 ring-border bg-card"
                >
                  <!-- ── Hero header (image + gradient overlay) ── -->
                  <div
                    class="relative h-32 cursor-pointer overflow-hidden"
                    [routerLink]="['/events', reg.event.id]"
                  >
                    @if (reg.event.image) {
                      <img
                        [src]="reg.event.image"
                        [alt]="reg.event.title"
                        class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                      />
                    } @else {
                      <div class="w-full h-full" [class]="heroBg(reg.event.id)"></div>
                    }
                    <!-- Dark gradient overlay -->
                    <div
                      class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-black/10"
                    ></div>
                    <!-- Status top-right -->
                    <div class="absolute top-3 right-3 flex items-center gap-1.5">
                      @if (reg.ticket_type) {
                        <span
                          class="text-[11px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full bg-white/90 text-primary backdrop-blur-sm"
                        >
                          {{ reg.ticket_type.name }}
                        </span>
                      }
                      <span
                        class="text-[11px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-full backdrop-blur-sm"
                        [class]="statusPillClass(reg.status)"
                        >{{ statusLabel(reg.status) }}</span
                      >
                    </div>
                    @if (reg.is_checked_in) {
                      <div class="absolute top-3 left-3">
                        <span
                          class="flex items-center gap-1 text-[11px] font-bold text-white bg-pine backdrop-blur-sm px-2.5 py-1 rounded-full"
                        >
                          <span class="w-1.5 h-1.5 bg-white rounded-full animate-pulse"></span>
                          {{ 'analytics.checkedIn' | transloco }}
                        </span>
                      </div>
                    }
                    <!-- Event title over image -->
                    <div class="absolute bottom-3 left-4 right-4">
                      <h3
                        class="text-white font-bold text-lg leading-tight drop-shadow-lg line-clamp-1"
                      >
                        {{ reg.event.title }}
                      </h3>
                    </div>
                  </div>

                  <!-- ── Perforation line ── -->
                  <div class="relative flex items-center px-4">
                    <span
                      class="absolute -left-3 w-6 h-6 rounded-full bg-background ring-1 ring-border z-10"
                    ></span>
                    <div class="flex-1 border-t-2 border-dashed border-border my-0"></div>
                    <span
                      class="absolute -right-3 w-6 h-6 rounded-full bg-background ring-1 ring-border z-10"
                    ></span>
                  </div>

                  <!-- ── Body ── -->
                  <div class="flex gap-0">
                    <!-- Left: event details + actions -->
                    <div class="flex-1 px-5 py-4 min-w-0">
                      <div class="grid grid-cols-2 gap-x-4 gap-y-3 mb-4">
                        <div>
                          <p
                            class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-0.5"
                          >
                            {{ 'common.date' | transloco }}
                          </p>
                          <p class="text-sm font-semibold text-foreground">
                            {{ reg.event.date | localDate: 'MMM d, y' }}
                          </p>
                          <p class="text-xs text-muted-foreground">
                            {{ reg.event.date | localDate: 'h:mm a' }}
                          </p>
                        </div>
                        <div>
                          <p
                            class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-0.5"
                          >
                            {{ 'eventForm.venue' | transloco }}
                          </p>
                          <p class="text-sm font-semibold text-foreground truncate">
                            {{ reg.event.location }}
                          </p>
                        </div>
                        @if (reg.seat) {
                          <div>
                            <p
                              class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-0.5"
                            >
                              {{ 'checkout.seat' | transloco }}
                            </p>
                            <p class="text-sm font-semibold text-foreground">
                              {{
                                'myRegistrations.rowRowCol'
                                  | transloco: { row: reg.seat.row, col: reg.seat.col }
                              }}
                            </p>
                          </div>
                          <div>
                            <p
                              class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-0.5"
                            >
                              {{ 'myRegistrations.zone' | transloco }}
                            </p>
                            <span
                              class="inline-block text-[11px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-md {{
                                zoneBadgeClass(reg.seat.zone)
                              }}"
                              >{{ reg.seat.zone }}</span
                            >
                          </div>
                        }
                      </div>

                      <!-- Actions: tickets can't be cancelled by the client —
                             paid ones can only go through a refund request,
                             free ones have no exit action at all. -->
                      <div
                        class="js-ticket-actions flex items-center gap-2 pt-3 border-t border-border/60"
                      >
                        @if (reg.refund_request?.status === 'pending') {
                          <span class="text-xs font-medium text-warning">{{
                            'myRegistrations.refundPendingReview' | transloco
                          }}</span>
                        } @else if (reg.refund_request?.status === 'rejected') {
                          <span class="text-xs font-medium text-ember">{{
                            'myRegistrations.refundDeclined' | transloco
                          }}</span>
                        } @else if (isPaidConfirmed(reg)) {
                          @if (reg.is_checked_in) {
                            <span class="text-xs text-muted-foreground">{{
                              'myRegistrations.ticketUsedForEntry' | transloco
                            }}</span>
                          } @else if (reg.event.refundable === false) {
                            <span class="text-xs text-muted-foreground">{{
                              'myRegistrations.nonRefundable' | transloco
                            }}</span>
                          } @else {
                            <button
                              (click)="openRefund(reg)"
                              class="text-xs font-medium text-muted-foreground hover:text-destructive transition-colors"
                            >
                              {{ 'myRegistrations.requestRefund' | transloco }}
                            </button>
                          }
                        }

                        @if (reg.status === 'pending') {
                          <button
                            (click)="completePayment(reg, $event)"
                            [disabled]="payingId === reg.id"
                            class="ml-auto btn btn-sm btn-primary text-xs flex items-center gap-1.5"
                          >
                            @if (payingId === reg.id) {
                              <span class="spinner spinner-sm"></span>
                            }
                            {{ 'eventDetail.completePayment' | transloco }}
                          </button>
                        }
                        @if (reg.status === 'confirmed') {
                          @if (reg.payment && +reg.payment.amount > 0) {
                            <button
                              (click)="openInvoice(reg)"
                              class="btn btn-sm btn-ghost text-xs flex items-center gap-1 text-muted-foreground"
                            >
                              <lucide-icon [img]="icons.FileText" class="w-3.5 h-3.5" />
                              {{ 'myRegistrations.invoice' | transloco }}
                            </button>
                          }
                          <button
                            (click)="exportTicket(reg, $event)"
                            [disabled]="exportingId === reg.id"
                            class="ml-auto btn btn-sm btn-secondary text-xs flex items-center gap-1.5"
                          >
                            @if (exportingId === reg.id) {
                              <span class="spinner spinner-sm"></span>
                            } @else {
                              <lucide-icon
                                [img]="isMobile ? icons.Share2 : icons.Download"
                                class="w-3.5 h-3.5"
                              />
                            }
                            {{
                              (isMobile ? 'eventDetail.share' : 'myRegistrations.downloadPdf')
                                | transloco
                            }}
                          </button>
                        }
                      </div>
                    </div>

                    <!-- Right: QR stub (confirmed only) -->
                    @if (reg.status === 'confirmed') {
                      <div
                        class="relative flex-shrink-0 w-36 flex flex-col items-center justify-center gap-2.5 px-4 py-4 border-l-2 border-dashed border-border bg-muted/30"
                      >
                        <!-- Notches -->
                        <span
                          class="absolute -left-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-background ring-1 ring-border z-10"
                        ></span>

                        <button
                          (click)="showQr(reg)"
                          class="bg-white rounded-xl p-2 shadow-md ring-1 ring-border hover:ring-primary/50 hover:shadow-lg transition-all cursor-zoom-in"
                          [title]="'myBookings.tapToEnlarge' | transloco"
                        >
                          @if (qrCodes[reg.ticket_uuid]) {
                            <img
                              [src]="qrCodes[reg.ticket_uuid]"
                              alt="QR"
                              class="w-20 h-20 block"
                            />
                          } @else {
                            <div class="w-20 h-20 flex items-center justify-center">
                              <span class="spinner spinner-sm"></span>
                            </div>
                          }
                        </button>
                        <div class="text-center">
                          <p
                            class="text-[10px] font-mono font-bold text-foreground tracking-wider leading-none"
                          >
                            #{{ reg.ticket_uuid.substring(0, 8).toUpperCase() }}
                          </p>
                          <p class="text-[9px] text-muted-foreground mt-0.5">
                            {{ 'myRegistrations.tapToEnlarge2' | transloco }}
                          </p>
                        </div>
                      </div>
                    }
                  </div>
                </div>
              }
            </div>
          }
        }
      </div>
    </div>

    <!-- QR enlarge modal -->
    @if (qrModalReg) {
      <div
        class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in"
      >
        <div
          class="bg-card rounded-2xl p-6 max-w-xs w-full text-center shadow-xl ring-1 ring-border animate-slide-up"
          appDialog
          dismissOnBackdrop
          (dismiss)="qrModalReg = null"
        >
          <span class="badge badge-confirmed mb-3">{{ 'common.confirmed' | transloco }}</span>
          <h3 class="text-base font-bold text-foreground leading-tight">
            {{ qrModalReg.event.title }}
          </h3>
          <p class="text-xs text-muted-foreground mt-1 mb-5">
            {{ 'myRegistrations.showThisCodeTo' | transloco }}
          </p>

          <div class="bg-white rounded-xl p-4 inline-block ring-1 ring-border shadow-sm">
            @if (qrCodes[qrModalReg.ticket_uuid]) {
              <img
                [src]="qrCodes[qrModalReg.ticket_uuid]"
                [alt]="'bookingClaim.ticketQrCode' | transloco"
                class="w-56 h-56"
              />
            } @else {
              <div class="w-56 h-56 flex items-center justify-center">
                <span class="spinner"></span>
              </div>
            }
          </div>

          <div class="mt-4 space-y-1">
            <p class="text-sm font-mono font-semibold text-foreground tracking-wider">
              #{{ qrModalReg.ticket_uuid.substring(0, 8).toUpperCase() }}
            </p>
            @if (qrModalReg.seat) {
              <p class="text-xs text-muted-foreground">
                {{
                  'myRegistrations.rowRowSeatCol'
                    | transloco: { row: qrModalReg.seat.row, col: qrModalReg.seat.col }
                }}
                <span class="uppercase">({{ qrModalReg.seat.zone }})</span>
              </p>
            }
          </div>

          <button (click)="qrModalReg = null" class="btn btn-secondary btn-full mt-5">
            {{ 'common.close' | transloco }}
          </button>
        </div>
      </div>
    }

    <!-- Refund request modal -->
    @if (refundReg) {
      <div
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 animate-fade-in"
      >
        <div
          class="bg-card rounded-2xl p-6 max-w-md w-full shadow-xl ring-1 ring-border animate-slide-up"
          appDialog
          dismissOnBackdrop
          (dismiss)="refundReg = null"
        >
          <h3 class="text-lg font-bold text-foreground mb-1">
            {{ 'eventDetail.requestARefund' | transloco }}
          </h3>
          <p class="text-sm text-muted-foreground mb-4">
            {{
              'myRegistrations.forTitleNetamountThe'
                | transloco
                  : {
                      title: refundReg.event.title,
                      netAmount: (refundReg.payment?.net_amount | money: refundReg.event.currency),
                    }
            }}
          </p>
          <label
            for="my-registrations-refund-reason"
            class="block text-sm font-medium text-foreground mb-1.5"
            >{{ 'myRegistrations.reason' | transloco }}
            <span class="text-muted-foreground font-normal">{{
              'checkout.optional' | transloco
            }}</span></label
          >
          <textarea
            id="my-registrations-refund-reason"
            [(ngModel)]="refundReason"
            rows="3"
            [placeholder]="'myRegistrations.whyAreYouRequesting' | transloco"
            class="input resize-none w-full mb-4"
          ></textarea>
          <div class="flex gap-2">
            <button (click)="refundReg = null" class="btn btn-secondary flex-1">
              {{ 'common.cancel' | transloco }}
            </button>
            <button
              (click)="submitRefundRequest()"
              [disabled]="submittingRefund"
              class="btn btn-primary flex-1"
            >
              {{
                (submittingRefund ? 'eventDetail.submitting' : 'myRegistrations.submitRequest')
                  | transloco
              }}
            </button>
          </div>
        </div>
      </div>
    }
  `,
})
export class MyRegistrationsComponent implements OnInit {
  private i18n = inject(LanguageService);
  private eventService = inject(EventService);
  private toastService = inject(ToastService);
  private paymentService = inject(PaymentService);

  registrations: Registration[] = [];
  loading = false;
  activeTab: 'upcoming' | 'past' = 'upcoming';
  exportingId: number | null = null;
  payingId: number | null = null;
  isMobile = false;
  qrModalReg: Registration | null = null;
  refundReg: Registration | null = null;
  refundReason = '';
  submittingRefund = false;

  // Locally generated QR data-URLs, keyed by ticket UUID (no third-party service).
  qrCodes: Record<string, string> = {};

  get upcomingRegs(): Registration[] {
    const now = Date.now();
    return this.registrations.filter((r) => new Date(r.event.date).getTime() >= now);
  }

  get pastRegs(): Registration[] {
    const now = Date.now();
    return this.registrations.filter((r) => new Date(r.event.date).getTime() < now);
  }

  get visibleRegs(): Registration[] {
    return this.activeTab === 'upcoming' ? this.upcomingRegs : this.pastRegs;
  }

  readonly icons = { Calendar, MapPin, Clock, Download, Share2, Ticket, FileText };

  ngOnInit(): void {
    this.loadRegistrations();
    if (typeof window !== 'undefined') {
      this.isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
        navigator.userAgent,
      );
    }
  }

  loadRegistrations(): void {
    this.loading = true;
    this.eventService.getMyRegistrations().subscribe({
      next: (res) => {
        this.registrations = res.results;
        this.loading = false;
        this.generateQrCodes();
      },
      error: () => {
        this.toastService.error(this.i18n.t('myRegistrations.failedToLoadRegistrations'));
        this.loading = false;
      },
    });
  }

  /** Generate QR codes locally — works offline, no UUIDs sent to third parties. */
  private generateQrCodes(): void {
    for (const reg of this.registrations) {
      if (reg.status !== 'confirmed' || this.qrCodes[reg.ticket_uuid]) continue;
      const url = `${window.location.origin}/validate/${reg.ticket_uuid}`;
      QRCode.toDataURL(url, { width: 300, margin: 0 })
        .then((dataUrl) => {
          this.qrCodes[reg.ticket_uuid] = dataUrl;
        })
        .catch(() => {
          // The ticket still lists its UUID; the QR is only a convenience.
        });
    }
  }

  statusStripeClass(status: string): string {
    const map: Record<string, string> = {
      confirmed: 'bg-[color:var(--pine-50)]0',
      pending: 'bg-amber-400',
      rejected: 'bg-red-400',
      cancelled: 'bg-gray-300',
    };
    return map[status] ?? 'bg-gray-300';
  }

  statusPillClass(status: string): string {
    const map: Record<string, string> = {
      confirmed: 'bg-[color:var(--pine-50)]0/90 text-white',
      pending: 'bg-amber-400/90 text-white',
      rejected: 'bg-[color:var(--destructive-50)]0/90 text-white',
      cancelled: 'bg-gray-500/80 text-white',
    };
    return map[status] ?? 'bg-gray-500/80 text-white';
  }

  heroBg(eventId: number): string {
    const gradients = [
      'bg-gradient-to-br from-ember via-orange-600 to-rose-600',
      'bg-gradient-to-br from-amber-500 via-orange-600 to-ember',
      'bg-gradient-to-br from-pine via-emerald-700 to-teal-700',
      'bg-gradient-to-br from-orange-500 via-rose-500 to-pink-600',
      'bg-gradient-to-br from-rose-600 via-ember to-amber-600',
    ];
    return gradients[eventId % gradients.length];
  }

  zoneBadgeClass(zone: string): string {
    const map: Record<string, string> = {
      vip: 'bg-blue-100 text-blue-700',
      premium: 'bg-purple-100 text-purple-700',
      standard: 'bg-[color:var(--pine-50)] text-[color:var(--pine-600)]',
    };
    return map[zone] ?? 'bg-muted text-muted-foreground';
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
      pending: this.i18n.t('myRegistrations.paymentPending'),
      rejected: this.i18n.t('common.cancelled'),
      cancelled: this.i18n.t('common.cancelled'),
    };
    return map[status] ?? status;
  }

  showQr(reg: Registration): void {
    this.qrModalReg = reg;
  }

  openInvoice(reg: Registration): void {
    // Fetched with the auth header and opened as a blob — the JWT never
    // appears in a URL (no leaks into history/server logs).
    this.eventService.getInvoiceBlob(reg.id).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank');
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      },
      error: () => this.toastService.error(this.i18n.t('myRegistrations.couldNotLoadThe')),
    });
  }

  isPaidConfirmed(reg: Registration): boolean {
    return reg.status === 'confirmed' && !!reg.payment && reg.payment.is_refundable;
  }

  openRefund(reg: Registration): void {
    this.refundReg = reg;
    this.refundReason = '';
  }

  submitRefundRequest(): void {
    if (!this.refundReg) return;
    this.submittingRefund = true;
    this.eventService.requestRefund(this.refundReg.event.id, this.refundReason).subscribe({
      next: () => {
        this.submittingRefund = false;
        this.refundReg = null;
        this.toastService.success(this.i18n.t('myRegistrations.refundRequestSubmittedThe'));
        this.loadRegistrations();
      },
      error: (err) => {
        this.submittingRefund = false;
        this.toastService.error(
          apiErrorMessage(err, this.i18n.t('myRegistrations.couldNotSubmitRequest'), 'error'),
        );
      },
    });
  }

  async exportTicket(reg: Registration, evt: MouseEvent): Promise<void> {
    evt.stopPropagation();
    this.exportingId = reg.id;
    try {
      const el = (evt.currentTarget as HTMLElement).closest<HTMLElement>('.ticket');
      if (!el) throw new Error('Element not found');

      const actions = el.querySelector<HTMLElement>('.js-ticket-actions');
      if (actions) actions.style.display = 'none';

      // Heavy PDF libraries are loaded on demand, not in the initial bundle.
      const [{ jsPDF }, { default: html2canvas }] = await Promise.all([
        import('jspdf'),
        import('html2canvas'),
      ]);
      const canvas = await html2canvas(el, { scale: 2, useCORS: true, backgroundColor: '#ffffff' });
      if (actions) actions.style.display = 'flex';

      const img = canvas.toDataURL('image/png');
      const pdf = new jsPDF({
        orientation: 'landscape',
        unit: 'mm',
        format: [(canvas.width * 0.264583) / 2, (canvas.height * 0.264583) / 2],
      });
      const w = pdf.internal.pageSize.getWidth();
      const h = (pdf.getImageProperties(img).height * w) / pdf.getImageProperties(img).width;
      pdf.addImage(img, 'PNG', 0, 0, w, h);
      const fileName = `Ticket-${reg.event.title.replace(/\s+/g, '-')}.pdf`;

      if (this.isMobile && supportsWebShare()) {
        const blob = pdf.output('blob');
        const file = new File([blob], fileName, { type: 'application/pdf' });
        if (canShareFiles([file])) {
          await navigator.share({
            files: [file],
            title: this.i18n.t('myRegistrations.shareTitle', { title: reg.event.title }),
          });
          this.toastService.success(this.i18n.t('myRegistrations.ticketShared'));
          return;
        }
      }
      pdf.save(fileName);
    } catch {
      this.toastService.error(this.i18n.t('myRegistrations.failedToExportTicket'));
    } finally {
      this.exportingId = null;
    }
  }

  completePayment(reg: Registration, evt: MouseEvent): void {
    evt.stopPropagation();
    this.payingId = reg.id;
    this.paymentService.createCheckoutSession(reg.id).subscribe({
      next: (res) => {
        window.location.href = res.checkout_url;
      },
      error: () => {
        this.payingId = null;
        this.toastService.error(this.i18n.t('eventDetail.couldNotStartPayment'));
        this.loadRegistrations();
      },
    });
  }
}
