import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule, ActivatedRoute } from '@angular/router';
import { BookingService, BookingDto, BookingSeatDto } from '../../services/booking.service';
import { ToastService } from '../../services/toast.service';
import { AuthService } from '../../services/auth.service';
import { LucideAngularModule, Users, Check, Armchair } from 'lucide-angular';
import * as QRCode from 'qrcode';
import { DialogDirective } from '../../directives/dialog.directive';
import { apiErrorMessage } from '../../api/api-error';
import { TranslocoPipe } from '@jsverse/transloco';
import { LocalDatePipe } from '../../i18n/locale.pipes';
import { LanguageService } from '../../i18n/language.service';

@Component({
  selector: 'app-booking-claim',
  standalone: true,
  imports: [
    DialogDirective,
    CommonModule,
    FormsModule,
    RouterModule,
    LucideAngularModule,
    TranslocoPipe,
    LocalDatePipe,
  ],
  template: `
    <div class="page-root">
      <div class="container max-w-lg py-10">
        @if (loading) {
          <div class="flex justify-center py-24"><span class="spinner spinner-lg"></span></div>
        } @else if (!booking) {
          <div class="text-center py-20">
            <h1 class="text-xl font-bold text-foreground mb-2">
              {{ 'bookingClaim.inviteNotFound' | transloco }}
            </h1>
            <p class="text-sm text-muted-foreground">
              {{ 'bookingClaim.thisBookingLinkIs' | transloco }}
            </p>
            <a routerLink="/" class="btn btn-primary btn-sm mt-5">{{
              'bookingClaim.browseEvents' | transloco
            }}</a>
          </div>
        } @else {
          <div class="text-center mb-6">
            <div
              class="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-3"
            >
              <lucide-icon [img]="icons.Users" class="w-6 h-6 text-primary" />
            </div>
            <h1 class="text-xl font-bold text-foreground">
              {{
                'bookingClaim.ownerusernameInvitedYou'
                  | transloco: { ownerUsername: booking.owner_username }
              }}
            </h1>
            <p class="text-sm text-muted-foreground mt-1">{{ booking.event_title }}</p>
            <p class="text-xs text-muted-foreground">
              {{ booking.event_date | localDate: 'EEE, MMM d, y · h:mm a' }} ·
              {{ booking.event_location }}
            </p>
          </div>

          @if (booking.status === 'confirmed') {
            <!-- Paid: every seat is a live ticket — claim yours and grab the QR -->
            <div class="note note-success mb-4 text-center">
              {{ 'bookingClaim.bookingConfirmedPaidClaim' | transloco }}
            </div>
            @if (!isLoggedIn) {
              <p class="text-xs text-center text-muted-foreground mb-4">
                <a
                  routerLink="/login"
                  [queryParams]="{ returnUrl: '/booking/' + token }"
                  class="underline"
                  >{{ 'bookingClaim.signIn' | transloco }}</a
                >
                {{ 'bookingClaim.beforeClaimingToGet' | transloco }}
              </p>
            }
            <div class="space-y-2">
              @for (s of booking.seats; track s.id) {
                <div class="card p-4">
                  <div class="flex items-center justify-between gap-3">
                    <div class="flex items-center gap-3 min-w-0">
                      <div
                        class="w-9 h-9 rounded-lg bg-muted flex items-center justify-center flex-shrink-0"
                      >
                        <lucide-icon [img]="icons.Armchair" class="w-4 h-4 text-muted-foreground" />
                      </div>
                      <div class="min-w-0">
                        <p class="text-sm font-semibold text-foreground">
                          {{ 'bookingClaim.rowRowSeatCol' | transloco: { row: s.row, col: s.col } }}
                        </p>
                        <p
                          class="text-xs"
                          [class]="
                            s.attendee_name
                              ? 'text-[color:var(--pine-600)]'
                              : 'text-muted-foreground'
                          "
                        >
                          {{ s.attendee_name || ('bookingClaim.unclaimed' | transloco) }}
                        </p>
                      </div>
                    </div>

                    @if (s.attendee_name || s.claimed) {
                      <!-- Only your own seat carries a QR; other guests' tickets stay private. -->
                      @if (s.ticket_uuid && qrCodes[s.ticket_uuid]) {
                        <button
                          class="bg-white rounded-lg p-1.5 ring-1 ring-border shadow-sm cursor-zoom-in flex-shrink-0"
                          (click)="zoomSeat = s"
                          [title]="'bookingClaim.showTicketQr' | transloco"
                        >
                          <img [src]="qrCodes[s.ticket_uuid]" alt="QR" class="w-14 h-14 block" />
                        </button>
                      } @else {
                        <span class="text-xs text-muted-foreground flex-shrink-0">{{
                          'bookingClaim.claimed' | transloco
                        }}</span>
                      }
                    } @else if (claimingId === s.seat_id) {
                      <div class="flex gap-2">
                        <input
                          [(ngModel)]="claimName"
                          [placeholder]="'bookingClaim.yourName' | transloco"
                          class="input h-9 text-sm w-28"
                          (keyup.enter)="confirmClaim(s)"
                        />
                        <button
                          (click)="confirmClaim(s)"
                          [disabled]="!claimName.trim()"
                          class="btn btn-primary btn-sm"
                        >
                          {{ 'bookingClaim.claim' | transloco }}
                        </button>
                      </div>
                    } @else {
                      <button
                        (click)="startClaim(s)"
                        class="btn btn-secondary btn-sm flex-shrink-0"
                      >
                        {{ 'bookingClaim.claimSeat' | transloco }}
                      </button>
                    }
                  </div>
                </div>
              }
            </div>
            <p class="text-xs text-center text-muted-foreground mt-5">
              {{ 'bookingClaim.showYourQrAt' | transloco }}
            </p>
          } @else if (booking.status !== 'holding') {
            <div class="card p-5 text-center">
              <p class="text-sm text-muted-foreground">
                {{ 'bookingClaim.thisBookingIsNo' | transloco }}
              </p>
            </div>
          } @else {
            <p class="text-sm text-center text-muted-foreground mb-4">
              {{ 'bookingClaim.tapASeatTo' | transloco }}
            </p>
            <div class="space-y-2">
              @for (s of booking.seats; track s.id) {
                <div
                  class="card p-4 flex items-center justify-between transition-colors"
                  [class.ring-2]="claimingId === s.seat_id"
                  [class.ring-primary]="claimingId === s.seat_id"
                >
                  <div class="flex items-center gap-3">
                    <div class="w-9 h-9 rounded-lg bg-muted flex items-center justify-center">
                      <lucide-icon [img]="icons.Armchair" class="w-4 h-4 text-muted-foreground" />
                    </div>
                    <div>
                      <p class="text-sm font-semibold text-foreground">
                        {{ 'bookingClaim.rowRowSeatCol' | transloco: { row: s.row, col: s.col } }}
                      </p>
                      <p class="text-xs text-muted-foreground capitalize">
                        {{ s.zone }} · {{ s.price }} {{ booking.currency }}
                      </p>
                    </div>
                  </div>

                  @if (s.attendee_name) {
                    <span
                      class="flex items-center gap-1 text-sm text-[color:var(--pine-600)] font-medium"
                    >
                      <lucide-icon [img]="icons.Check" class="w-4 h-4" />
                      {{ s.attendee_name }}
                    </span>
                  } @else if (claimingId === s.seat_id) {
                    <div class="flex gap-2">
                      <input
                        [(ngModel)]="claimName"
                        [placeholder]="'bookingClaim.yourName' | transloco"
                        class="input h-9 text-sm w-28"
                        (keyup.enter)="confirmClaim(s)"
                      />
                      <button
                        (click)="confirmClaim(s)"
                        [disabled]="!claimName.trim()"
                        class="btn btn-primary btn-sm"
                      >
                        {{ 'bookingClaim.claim' | transloco }}
                      </button>
                    </div>
                  } @else {
                    <button (click)="startClaim(s)" class="btn btn-secondary btn-sm">
                      {{ 'bookingClaim.claimSeat' | transloco }}
                    </button>
                  }
                </div>
              }
            </div>

            <p class="text-xs text-center text-muted-foreground mt-5">
              {{ 'bookingClaim.theOrganizerPaysFor' | transloco }}
            </p>
          }
        }
      </div>
    </div>

    <!-- QR zoom -->
    @if (zoomSeat) {
      <div
        class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in"
      >
        <div
          class="bg-card rounded-2xl p-6 max-w-xs w-full text-center shadow-xl ring-1 ring-border animate-slide-up"
          appDialog
          dismissOnBackdrop
          (dismiss)="zoomSeat = null"
        >
          <h3 class="text-base font-bold text-foreground leading-tight">
            {{ 'bookingClaim.rowRowSeatCol' | transloco: { row: zoomSeat.row, col: zoomSeat.col } }}
          </h3>
          <p class="text-xs text-muted-foreground mt-1 mb-5">
            {{
              'bookingClaim.attendeenameShowAtThe'
                | transloco: { attendeeName: zoomSeat.attendee_name }
            }}
          </p>
          @if (zoomSeat.ticket_uuid && qrCodes[zoomSeat.ticket_uuid]) {
            <div class="bg-white rounded-xl p-4 inline-block ring-1 ring-border shadow-sm">
              <img
                [src]="qrCodes[zoomSeat.ticket_uuid]"
                [alt]="'bookingClaim.ticketQrCode' | transloco"
                class="w-56 h-56"
              />
            </div>
          }
          <button (click)="zoomSeat = null" class="btn btn-secondary btn-full mt-5">
            {{ 'common.close' | transloco }}
          </button>
        </div>
      </div>
    }
  `,
})
export class BookingClaimComponent implements OnInit {
  private i18n = inject(LanguageService);
  private route = inject(ActivatedRoute);
  private bookingService = inject(BookingService);
  private toast = inject(ToastService);
  private auth = inject(AuthService);

  token = '';
  booking: BookingDto | null = null;
  loading = false;

  claimingId: number | null = null;
  claimName = '';
  zoomSeat: BookingSeatDto | null = null;
  qrCodes: Record<string, string> = {};

  readonly icons = { Users, Check, Armchair };

  get isLoggedIn(): boolean {
    return this.auth.isLoggedIn;
  }

  ngOnInit(): void {
    this.token = this.route.snapshot.paramMap.get('token') || '';
    this.loading = true;
    this.bookingService.getShared(this.token).subscribe({
      next: (b) => {
        this.booking = b;
        this.loading = false;
        this.generateQrs();
      },
      error: () => {
        this.booking = null;
        this.loading = false;
      },
    });
  }

  /** Claimed seats on a paid booking get their QR tickets rendered locally. */
  private generateQrs(): void {
    if (this.booking?.status !== 'confirmed') return;
    for (const s of this.booking.seats) {
      const uuid = s.ticket_uuid; // null unless this seat is yours
      if (!uuid || this.qrCodes[uuid]) continue;
      const url = `${window.location.origin}/validate/${uuid}`;
      QRCode.toDataURL(url, { width: 300, margin: 0 })
        .then((dataUrl) => {
          this.qrCodes[uuid] = dataUrl;
        })
        .catch(() => {
          // The seat still shows its ticket number; the QR is only a convenience.
        });
    }
  }

  startClaim(s: BookingSeatDto): void {
    this.claimingId = s.seat_id;
    this.claimName = '';
  }

  confirmClaim(s: BookingSeatDto): void {
    if (!this.claimName.trim()) return;
    this.bookingService.claimSeat(this.token, s.seat_id, this.claimName.trim()).subscribe({
      next: (b) => {
        this.booking = b;
        this.claimingId = null;
        this.claimName = '';
        this.toast.success(this.i18n.t('bookingClaim.seatClaimed'));
        this.generateQrs();
      },
      error: (err) =>
        this.toast.error(
          apiErrorMessage(err, this.i18n.t('bookingClaim.couldNotClaimSeat'), 'error'),
        ),
    });
  }
}
