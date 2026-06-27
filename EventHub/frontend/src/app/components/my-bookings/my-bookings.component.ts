import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { BookingService, BookingDto, BookingSeatDto } from '../../services/booking.service';
import { ToastService } from '../../services/toast.service';
import { LucideAngularModule, Users, Copy, Check, Clock, Armchair, Ticket } from 'lucide-angular';
import * as QRCode from 'qrcode';

@Component({
  selector: 'app-my-bookings',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-3xl py-8">

        <div class="mb-7">
          <h1 class="text-2xl font-bold text-foreground">My Bookings</h1>
          <p class="text-sm text-muted-foreground mt-1">Group seat reservations you own — each seat is its own ticket</p>
        </div>

        @if (loading) {
          <div class="flex items-center justify-center py-20 gap-3 text-muted-foreground">
            <span class="spinner"></span>
            <span class="text-sm">Loading bookings…</span>
          </div>
        } @else if (bookings.length === 0) {
          <div class="flex flex-col items-center justify-center py-20 text-center">
            <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center mb-4">
              <lucide-icon [img]="icons.Users" class="w-8 h-8 text-primary/50" aria-hidden="true"></lucide-icon>
            </div>
            <h3 class="text-base font-semibold text-foreground mb-1">No group bookings</h3>
            <p class="text-sm text-muted-foreground mb-5 max-w-xs">
              Book several seats at once from an event page and they'll appear here.
            </p>
            <a routerLink="/" class="btn btn-primary btn-sm">Discover events</a>
          </div>
        } @else {
          <div class="space-y-5">
            @for (b of bookings; track b.id) {
              <div class="card overflow-hidden">
                <div class="p-5 flex items-start justify-between gap-3 flex-wrap">
                  <div class="min-w-0">
                    <a [routerLink]="['/events', b.event_id]" class="font-semibold text-foreground hover:text-primary transition-colors">
                      {{ b.event_title }}
                    </a>
                    <p class="text-xs text-muted-foreground mt-0.5">
                      {{ b.event_date | date:'EEE, MMM d, y · h:mm a' }} · {{ b.event_location }}
                    </p>
                    <p class="text-xs text-muted-foreground mt-1">
                      {{ b.seat_count }} seats · {{ '$' + b.total_price }}
                    </p>
                  </div>
                  <span class="text-[11px] font-bold uppercase px-2.5 py-1 rounded-full"
                    [class]="b.status === 'confirmed'
                      ? 'text-[color:var(--pine-600)] bg-[color:var(--pine-50)]'
                      : 'text-warning bg-[color:var(--warning-50)]'">
                    {{ b.status }}
                  </span>
                </div>

                <!-- Holding: share link + countdown hint -->
                @if (b.status === 'holding') {
                  <div class="px-5 pb-4">
                    <div class="flex items-center gap-2 p-2.5 rounded-lg bg-[color:var(--warning-50)] text-warning text-xs mb-3">
                      <lucide-icon [img]="icons.Clock" class="w-4 h-4 flex-shrink-0"></lucide-icon>
                      Seats are held until {{ b.hold_expires_at | date:'h:mm a' }} — complete the payment from the event page.
                    </div>
                    <label class="block text-xs font-medium text-muted-foreground mb-1.5">Invite friends to claim their seats</label>
                    <div class="flex gap-2">
                      <input readonly [value]="shareUrl(b)" class="input flex-1 text-xs" />
                      <button (click)="copyLink(b)" class="btn btn-secondary btn-sm flex-shrink-0">
                        <lucide-icon [img]="copiedId === b.id ? icons.Check : icons.Copy" class="w-4 h-4"></lucide-icon>
                      </button>
                    </div>
                  </div>
                }

                <!-- Seats / tickets -->
                <div class="border-t border-border divide-y divide-border">
                  @for (s of b.seats; track s.id) {
                    <div class="px-5 py-3 flex items-center gap-4">
                      <div class="w-9 h-9 rounded-lg bg-muted flex items-center justify-center flex-shrink-0">
                        <lucide-icon [img]="icons.Armchair" class="w-4 h-4 text-muted-foreground"></lucide-icon>
                      </div>
                      <div class="flex-1 min-w-0">
                        <p class="text-sm font-semibold text-foreground">
                          Row {{ s.row }}, Seat {{ s.col }}
                          <span class="text-xs font-normal text-muted-foreground capitalize">· {{ s.zone }} · {{ '$' + s.price }}</span>
                        </p>
                        <p class="text-xs" [class]="s.attendee_name ? 'text-[color:var(--pine-600)]' : 'text-muted-foreground'">
                          {{ s.attendee_name || 'Unclaimed' }}
                          @if (s.is_checked_in) { <span class="text-[color:var(--pine-600)] font-medium">· checked in</span> }
                        </p>
                      </div>
                      @if (b.status === 'confirmed') {
                        @if (qrCodes[s.ticket_uuid]) {
                          <button class="bg-white rounded-lg p-1.5 ring-1 ring-border shadow-sm cursor-zoom-in" (click)="zoomSeat = s" title="Tap to enlarge">
                            <img [src]="qrCodes[s.ticket_uuid]" alt="QR" class="w-14 h-14 block" />
                          </button>
                        } @else {
                          <span class="spinner spinner-sm"></span>
                        }
                      }
                    </div>
                  }
                </div>

                @if (b.status === 'confirmed') {
                  <div class="px-5 py-3 border-t border-border bg-muted/30">
                    <p class="text-xs text-muted-foreground flex items-center gap-1.5">
                      <lucide-icon [img]="icons.Ticket" class="w-3.5 h-3.5"></lucide-icon>
                      Each seat has its own QR ticket — share the invite link and friends see theirs too.
                    </p>
                    <div class="flex gap-2 mt-2">
                      <input readonly [value]="shareUrl(b)" class="input flex-1 text-xs" />
                      <button (click)="copyLink(b)" class="btn btn-secondary btn-sm flex-shrink-0">
                        <lucide-icon [img]="copiedId === b.id ? icons.Check : icons.Copy" class="w-4 h-4"></lucide-icon>
                      </button>
                    </div>
                  </div>
                }
              </div>
            }
          </div>
        }
      </div>
    </div>

    <!-- QR zoom modal -->
    @if (zoomSeat) {
      <div class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in" (click)="zoomSeat = null">
        <div class="bg-card rounded-2xl p-6 max-w-xs w-full text-center shadow-xl ring-1 ring-border animate-slide-up" (click)="$event.stopPropagation()">
          <h3 class="text-base font-bold text-foreground leading-tight">Row {{ zoomSeat.row }}, Seat {{ zoomSeat.col }}</h3>
          <p class="text-xs text-muted-foreground mt-1 mb-5">{{ zoomSeat.attendee_name || 'Unclaimed seat' }} — show at the entrance</p>
          @if (qrCodes[zoomSeat.ticket_uuid]) {
            <div class="bg-white rounded-xl p-4 inline-block ring-1 ring-border shadow-sm">
              <img [src]="qrCodes[zoomSeat.ticket_uuid]" alt="Ticket QR code" class="w-56 h-56" />
            </div>
          }
          <p class="text-sm font-mono font-semibold text-foreground tracking-wider mt-4">
            #{{ zoomSeat.ticket_uuid.substring(0, 8).toUpperCase() }}
          </p>
          <button (click)="zoomSeat = null" class="btn btn-secondary btn-full mt-5">Close</button>
        </div>
      </div>
    }
  `,
})
export class MyBookingsComponent implements OnInit {
  bookings: BookingDto[] = [];
  loading = false;
  copiedId: string | null = null;
  zoomSeat: BookingSeatDto | null = null;
  qrCodes: Record<string, string> = {};

  readonly icons = { Users, Copy, Check, Clock, Armchair, Ticket };

  constructor(private bookingService: BookingService, private toast: ToastService) {}

  ngOnInit(): void {
    this.loading = true;
    this.bookingService.mine().subscribe({
      next: list => {
        this.bookings = list;
        this.loading = false;
        this.generateQrs();
      },
      error: () => { this.loading = false; this.toast.error('Failed to load bookings.'); },
    });
  }

  private generateQrs(): void {
    for (const b of this.bookings) {
      if (b.status !== 'confirmed') continue;
      for (const s of b.seats) {
        if (this.qrCodes[s.ticket_uuid]) continue;
        const url = `${window.location.origin}/validate/${s.ticket_uuid}`;
        QRCode.toDataURL(url, { width: 300, margin: 0 })
          .then(dataUrl => { this.qrCodes[s.ticket_uuid] = dataUrl; })
          .catch(() => {});
      }
    }
  }

  shareUrl(b: BookingDto): string {
    return `${window.location.origin}/booking/${b.share_token}`;
  }

  copyLink(b: BookingDto): void {
    navigator.clipboard.writeText(this.shareUrl(b)).then(() => {
      this.copiedId = b.id;
      setTimeout(() => (this.copiedId = null), 2000);
    });
  }
}
