import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute, Router } from '@angular/router';
import { EventService } from '../../services/event.service';
import { BookingService, BookingDto } from '../../services/booking.service';
import { ToastService } from '../../services/toast.service';
import { AuthService } from '../../services/auth.service';
import { Event, Seat, ZonePrice } from '../../models/models';
import { SeatMapSvgComponent } from '../seat-map-svg/seat-map-svg.component';
import { LucideAngularModule, ChevronLeft, Users, Copy, Check, Clock, Ticket } from 'lucide-angular';

@Component({
  selector: 'app-group-booking',
  standalone: true,
  imports: [CommonModule, RouterModule, SeatMapSvgComponent, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-6xl py-6">

        <a [routerLink]="['/events', eventId]" class="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4">
          <lucide-icon [img]="icons.ChevronLeft" class="w-4 h-4"></lucide-icon> Back to event
        </a>

        @if (loading) {
          <div class="flex justify-center py-24"><span class="spinner spinner-lg"></span></div>
        } @else if (event) {
          <div class="flex items-center gap-3 mb-6">
            <div class="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
              <lucide-icon [img]="icons.Users" class="w-5 h-5 text-primary"></lucide-icon>
            </div>
            <div>
              <h1 class="text-xl font-bold text-foreground">Group booking</h1>
              <p class="text-sm text-muted-foreground">{{ event.title }} · pick up to 8 seats</p>
            </div>
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-6">

            <!-- Seat map -->
            <div class="card p-4">
              @if (seats.length) {
                <app-seat-map-svg
                  [seats]="seats"
                  [eventId]="eventId"
                  [maxSelection]="8"
                  [zonePrices]="zonePrices"
                  (selectionChange)="onSelection($event)"
                ></app-seat-map-svg>
              } @else {
                <p class="text-sm text-muted-foreground py-10 text-center">No seat map for this event.</p>
              }
            </div>

            <!-- Side panel -->
            <aside class="lg:sticky lg:top-20 self-start">
              <div class="card p-5">

                @if (!booking) {
                  <!-- SELECT PHASE -->
                  <h2 class="font-semibold text-foreground mb-3">Your selection</h2>
                  @if (selected.length === 0) {
                    <p class="text-sm text-muted-foreground py-6 text-center">Tap seats on the map to add them.</p>
                  } @else {
                    <ul class="space-y-2 mb-4">
                      @for (s of selected; track s.id) {
                        <li class="flex items-center justify-between text-sm">
                          <span class="text-foreground">Row {{ s.row }}, Seat {{ s.col }}
                            <span class="text-xs text-muted-foreground capitalize ml-1">({{ s.price_zone }})</span>
                          </span>
                          <span class="font-semibold text-foreground">{{ '$' + s.price }}</span>
                        </li>
                      }
                    </ul>
                    <div class="flex items-center justify-between border-t border-border pt-3 mb-4">
                      <span class="text-sm text-muted-foreground">{{ selected.length }} seat(s)</span>
                      <span class="text-lg font-bold text-foreground">{{ '$' + selectionTotal }}</span>
                    </div>
                  }
                  <button
                    (click)="holdSeats()"
                    [disabled]="selected.length === 0 || holding"
                    class="btn btn-primary btn-full"
                  >
                    {{ holding ? 'Holding…' : 'Hold seats for 10 min' }}
                  </button>
                } @else {
                  <!-- HOLD PHASE -->
                  <div class="flex items-center justify-between mb-3">
                    <h2 class="font-semibold text-foreground">Seats held</h2>
                    <span class="flex items-center gap-1 text-sm font-mono font-semibold"
                          [class]="secondsLeft < 60 ? 'text-ember' : 'text-warning'">
                      <lucide-icon [img]="icons.Clock" class="w-4 h-4"></lucide-icon>
                      {{ countdown }}
                    </span>
                  </div>

                  <ul class="space-y-2 mb-4">
                    @for (s of booking.seats; track s.id) {
                      <li class="flex items-center justify-between text-sm">
                        <span class="text-foreground">
                          Row {{ s.row }}, Seat {{ s.col }}
                          @if (s.attendee_name) {
                            <span class="text-xs text-[color:var(--pine-600)] ml-1">· {{ s.attendee_name }}</span>
                          } @else {
                            <span class="text-xs text-muted-foreground ml-1">· unclaimed</span>
                          }
                        </span>
                        <span class="font-semibold text-foreground">{{ '$' + s.price }}</span>
                      </li>
                    }
                  </ul>

                  <div class="flex items-center justify-between border-t border-border pt-3 mb-4">
                    <span class="text-sm text-muted-foreground">{{ booking.seat_count }} seats</span>
                    <span class="text-lg font-bold text-foreground">{{ '$' + booking.total_price }}</span>
                  </div>

                  <!-- Share link -->
                  <div class="mb-4">
                    <label class="block text-xs font-medium text-muted-foreground mb-1.5">Invite friends to claim a seat</label>
                    <div class="flex gap-2">
                      <input readonly [value]="shareUrl" class="input flex-1 text-xs" />
                      <button (click)="copyLink()" class="btn btn-secondary btn-sm flex-shrink-0">
                        <lucide-icon [img]="copied ? icons.Check : icons.Copy" class="w-4 h-4"></lucide-icon>
                      </button>
                    </div>
                  </div>

                  <button (click)="pay()" [disabled]="paying" class="btn btn-primary btn-full mb-2">
                    {{ paying ? 'Processing…' : 'Pay for group — $' + booking.total_price }}
                  </button>
                  <button (click)="cancelHold()" class="btn btn-ghost btn-full btn-sm text-muted-foreground">
                    Release seats
                  </button>
                }
              </div>
            </aside>
          </div>
        }
      </div>
    </div>
  `,
})
export class GroupBookingComponent implements OnInit, OnDestroy {
  eventId = 0;
  event: Event | null = null;
  seats: Seat[] = [];
  zonePrices: ZonePrice[] = [];
  loading = false;

  selected: Seat[] = [];
  booking: BookingDto | null = null;

  holding = false;
  paying = false;
  copied = false;

  secondsLeft = 0;
  countdown = '10:00';
  private timer?: ReturnType<typeof setInterval>;

  readonly icons = { ChevronLeft, Users, Copy, Check, Clock, Ticket };

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private eventService: EventService,
    private bookingService: BookingService,
    private toast: ToastService,
    public authService: AuthService,
  ) {}

  ngOnInit(): void {
    this.eventId = Number(this.route.snapshot.paramMap.get('id'));
    this.loading = true;
    this.eventService.getEvent(this.eventId).subscribe({
      next: ev => { this.event = ev; this.loading = false; },
      error: () => { this.loading = false; },
    });
    this.eventService.getSeatMap(this.eventId).subscribe({
      next: sm => { this.seats = sm.seats || []; this.zonePrices = sm.zone_prices || []; },
      error: () => {},
    });
  }

  ngOnDestroy(): void {
    if (this.timer) clearInterval(this.timer);
  }

  get selectionTotal(): string {
    return this.selected.reduce((sum, s) => sum + Number(s.price || 0), 0).toFixed(2);
  }

  get shareUrl(): string {
    return this.booking ? `${window.location.origin}/booking/${this.booking.share_token}` : '';
  }

  onSelection(seats: Seat[]): void {
    this.selected = seats;
  }

  holdSeats(): void {
    if (!this.selected.length) return;
    this.holding = true;
    const ids = this.selected.map(s => s.id);
    this.bookingService.create(this.eventId, ids).subscribe({
      next: b => {
        this.booking = b;
        this.holding = false;
        this.startCountdown();
      },
      error: err => {
        this.holding = false;
        this.toast.error(err.error?.error || 'Could not hold seats. Some may be taken.');
        // refresh map
        this.eventService.getSeatMap(this.eventId).subscribe(sm => { this.seats = sm.seats || []; });
      },
    });
  }

  pay(): void {
    if (!this.booking) return;
    this.paying = true;
    this.bookingService.checkout(this.booking.id).subscribe({
      next: res => { window.location.href = res.checkout_url; },
      error: () => { this.paying = false; this.toast.error('Payment could not be started.'); },
    });
  }

  cancelHold(): void {
    if (!this.booking) return;
    this.bookingService.cancel(this.booking.id).subscribe({
      next: () => {
        this.booking = null;
        this.selected = [];
        if (this.timer) clearInterval(this.timer);
        this.toast.success('Seats released');
        this.eventService.getSeatMap(this.eventId).subscribe(sm => { this.seats = sm.seats || []; });
      },
      error: () => this.toast.error('Could not release seats'),
    });
  }

  copyLink(): void {
    navigator.clipboard.writeText(this.shareUrl).then(() => {
      this.copied = true;
      setTimeout(() => (this.copied = false), 2000);
    });
  }

  private startCountdown(): void {
    if (!this.booking?.hold_expires_at) return;
    const end = new Date(this.booking.hold_expires_at).getTime();
    const tick = () => {
      this.secondsLeft = Math.max(0, Math.floor((end - Date.now()) / 1000));
      const m = Math.floor(this.secondsLeft / 60);
      const s = this.secondsLeft % 60;
      this.countdown = `${m}:${s.toString().padStart(2, '0')}`;
      if (this.secondsLeft <= 0) {
        if (this.timer) clearInterval(this.timer);
        this.toast.error('Your seat hold has expired.');
        this.booking = null;
        this.selected = [];
        this.eventService.getSeatMap(this.eventId).subscribe(sm => { this.seats = sm.seats || []; });
      }
    };
    tick();
    this.timer = setInterval(tick, 1000);
  }
}
