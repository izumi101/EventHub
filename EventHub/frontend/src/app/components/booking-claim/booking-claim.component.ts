import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule, ActivatedRoute } from '@angular/router';
import { BookingService, BookingDto, BookingSeatDto } from '../../services/booking.service';
import { ToastService } from '../../services/toast.service';
import { LucideAngularModule, Users, Check, Armchair } from 'lucide-angular';
import * as QRCode from 'qrcode';

@Component({
  selector: 'app-booking-claim',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-lg py-10">
        @if (loading) {
          <div class="flex justify-center py-24"><span class="spinner spinner-lg"></span></div>
        } @else if (!booking) {
          <div class="text-center py-20">
            <h1 class="text-xl font-bold text-foreground mb-2">Invite not found</h1>
            <p class="text-sm text-muted-foreground">This booking link is invalid or has expired.</p>
            <a routerLink="/" class="btn btn-primary btn-sm mt-5">Browse events</a>
          </div>
        } @else {
          <div class="text-center mb-6">
            <div class="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-3">
              <lucide-icon [img]="icons.Users" class="w-6 h-6 text-primary"></lucide-icon>
            </div>
            <h1 class="text-xl font-bold text-foreground">{{ booking.owner_username }} invited you</h1>
            <p class="text-sm text-muted-foreground mt-1">{{ booking.event_title }}</p>
            <p class="text-xs text-muted-foreground">{{ booking.event_date | date:'EEE, MMM d, y · h:mm a' }} · {{ booking.event_location }}</p>
          </div>

          @if (booking.status === 'confirmed') {
            <!-- Paid: every seat is a live ticket — claim yours and grab the QR -->
            <div class="note note-success mb-4 text-center">
              Booking confirmed & paid. Claim your seat to put your name on the ticket.
            </div>
            <div class="space-y-2">
              @for (s of booking.seats; track s.id) {
                <div class="card p-4">
                  <div class="flex items-center justify-between gap-3">
                    <div class="flex items-center gap-3 min-w-0">
                      <div class="w-9 h-9 rounded-lg bg-muted flex items-center justify-center flex-shrink-0">
                        <lucide-icon [img]="icons.Armchair" class="w-4 h-4 text-muted-foreground"></lucide-icon>
                      </div>
                      <div class="min-w-0">
                        <p class="text-sm font-semibold text-foreground">Row {{ s.row }}, Seat {{ s.col }}</p>
                        <p class="text-xs" [class]="s.attendee_name ? 'text-[color:var(--pine-600)]' : 'text-muted-foreground'">
                          {{ s.attendee_name || 'Unclaimed' }}
                        </p>
                      </div>
                    </div>

                    @if (s.attendee_name) {
                      @if (qrCodes[s.ticket_uuid]) {
                        <button class="bg-white rounded-lg p-1.5 ring-1 ring-border shadow-sm cursor-zoom-in flex-shrink-0" (click)="zoomSeat = s" title="Show ticket QR">
                          <img [src]="qrCodes[s.ticket_uuid]" alt="QR" class="w-14 h-14 block" />
                        </button>
                      }
                    } @else if (claimingId === s.seat_id) {
                      <div class="flex gap-2">
                        <input [(ngModel)]="claimName" placeholder="Your name" class="input h-9 text-sm w-28" (keyup.enter)="confirmClaim(s)" />
                        <button (click)="confirmClaim(s)" [disabled]="!claimName.trim()" class="btn btn-primary btn-sm">Claim</button>
                      </div>
                    } @else {
                      <button (click)="startClaim(s)" class="btn btn-secondary btn-sm flex-shrink-0">Claim seat</button>
                    }
                  </div>
                </div>
              }
            </div>
            <p class="text-xs text-center text-muted-foreground mt-5">
              Show your QR at the entrance — each seat has its own ticket.
            </p>
          } @else if (booking.status !== 'holding') {
            <div class="card p-5 text-center">
              <p class="text-sm text-muted-foreground">This booking is no longer active.</p>
            </div>
          } @else {
            <p class="text-sm text-center text-muted-foreground mb-4">Tap a seat to claim it with your name</p>
            <div class="space-y-2">
              @for (s of booking.seats; track s.id) {
                <div
                  class="card p-4 flex items-center justify-between transition-colors"
                  [class.ring-2]="claimingId === s.id"
                  [class.ring-primary]="claimingId === s.id"
                >
                  <div class="flex items-center gap-3">
                    <div class="w-9 h-9 rounded-lg bg-muted flex items-center justify-center">
                      <lucide-icon [img]="icons.Armchair" class="w-4 h-4 text-muted-foreground"></lucide-icon>
                    </div>
                    <div>
                      <p class="text-sm font-semibold text-foreground">Row {{ s.row }}, Seat {{ s.col }}</p>
                      <p class="text-xs text-muted-foreground capitalize">{{ s.zone }} · {{ '$' + s.price }}</p>
                    </div>
                  </div>

                  @if (s.attendee_name) {
                    <span class="flex items-center gap-1 text-sm text-[color:var(--pine-600)] font-medium">
                      <lucide-icon [img]="icons.Check" class="w-4 h-4"></lucide-icon>
                      {{ s.attendee_name }}
                    </span>
                  } @else if (claimingId === s.id) {
                    <div class="flex gap-2">
                      <input
                        [(ngModel)]="claimName"
                        placeholder="Your name"
                        class="input h-9 text-sm w-28"
                        (keyup.enter)="confirmClaim(s)"
                      />
                      <button (click)="confirmClaim(s)" [disabled]="!claimName.trim()" class="btn btn-primary btn-sm">Claim</button>
                    </div>
                  } @else {
                    <button (click)="startClaim(s)" class="btn btn-secondary btn-sm">Claim seat</button>
                  }
                </div>
              }
            </div>

            <p class="text-xs text-center text-muted-foreground mt-5">
              The organizer pays for the whole group. You just pick your seat.
            </p>
          }
        }
      </div>
    </div>

    <!-- QR zoom -->
    @if (zoomSeat) {
      <div class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in" (click)="zoomSeat = null">
        <div class="bg-card rounded-2xl p-6 max-w-xs w-full text-center shadow-xl ring-1 ring-border animate-slide-up" (click)="$event.stopPropagation()">
          <h3 class="text-base font-bold text-foreground leading-tight">Row {{ zoomSeat.row }}, Seat {{ zoomSeat.col }}</h3>
          <p class="text-xs text-muted-foreground mt-1 mb-5">{{ zoomSeat.attendee_name }} — show at the entrance</p>
          @if (qrCodes[zoomSeat.ticket_uuid]) {
            <div class="bg-white rounded-xl p-4 inline-block ring-1 ring-border shadow-sm">
              <img [src]="qrCodes[zoomSeat.ticket_uuid]" alt="Ticket QR code" class="w-56 h-56" />
            </div>
          }
          <button (click)="zoomSeat = null" class="btn btn-secondary btn-full mt-5">Close</button>
        </div>
      </div>
    }
  `,
})
export class BookingClaimComponent implements OnInit {
  token = '';
  booking: BookingDto | null = null;
  loading = false;

  claimingId: number | null = null;
  claimName = '';
  zoomSeat: BookingSeatDto | null = null;
  qrCodes: Record<string, string> = {};

  readonly icons = { Users, Check, Armchair };

  constructor(
    private route: ActivatedRoute,
    private bookingService: BookingService,
    private toast: ToastService,
  ) {}

  ngOnInit(): void {
    this.token = this.route.snapshot.paramMap.get('token') || '';
    this.loading = true;
    this.bookingService.getShared(this.token).subscribe({
      next: b => { this.booking = b; this.loading = false; this.generateQrs(); },
      error: () => { this.booking = null; this.loading = false; },
    });
  }

  /** Claimed seats on a paid booking get their QR tickets rendered locally. */
  private generateQrs(): void {
    if (!this.booking || this.booking.status !== 'confirmed') return;
    for (const s of this.booking.seats) {
      if (!s.attendee_name || this.qrCodes[s.ticket_uuid]) continue;
      const url = `${window.location.origin}/validate/${s.ticket_uuid}`;
      QRCode.toDataURL(url, { width: 300, margin: 0 })
        .then(dataUrl => { this.qrCodes[s.ticket_uuid] = dataUrl; })
        .catch(() => {});
    }
  }

  startClaim(s: BookingSeatDto): void {
    this.claimingId = s.seat_id;
    this.claimName = '';
  }

  confirmClaim(s: BookingSeatDto): void {
    if (!this.claimName.trim()) return;
    this.bookingService.claimSeat(this.token, s.seat_id, this.claimName.trim()).subscribe({
      next: b => {
        this.booking = b;
        this.claimingId = null;
        this.claimName = '';
        this.toast.success('Seat claimed!');
        this.generateQrs();
      },
      error: err => this.toast.error(err.error?.error || 'Could not claim seat'),
    });
  }
}
