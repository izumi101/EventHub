import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, OnChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LucideAngularModule, AlertTriangle, Wifi, WifiOff } from 'lucide-angular';
import { Seat } from '../../models/models';
import { SeatWsService, WsSeatUpdate } from '../../services/seat-ws.service';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-seat-selector',
  standalone: true,
  imports: [CommonModule, LucideAngularModule],
  template: `
    <div class="space-y-4">
      <!-- Header + live indicator -->
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-base font-semibold text-foreground">Select your seat</h2>
          <p class="text-xs text-muted-foreground">Click an available seat</p>
        </div>
        <div class="flex items-center gap-1.5 text-xs" [class]="wsConnected ? 'text-[color:var(--pine-600)]' : 'text-muted-foreground'">
          <span class="relative flex h-2 w-2">
            @if (wsConnected) {
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-2 w-2 bg-[color:var(--pine-50)]0"></span>
            } @else {
              <span class="relative inline-flex rounded-full h-2 w-2 bg-gray-300"></span>
            }
          </span>
          {{ wsConnected ? 'Live' : 'Offline' }}
        </div>
      </div>

      <!-- Legend -->
      <div class="flex flex-wrap gap-4 text-xs">
        <div class="flex items-center gap-1.5">
          <div class="w-4 h-4 rounded border-2 border-emerald-500 bg-[color:var(--pine-50)]"></div>
          <span>Available</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-4 h-4 rounded border-2 border-blue-400 bg-blue-50"></div>
          <span>VIP</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-4 h-4 rounded bg-gray-200 border-2 border-gray-300"></div>
          <span>Taken</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-4 h-4 rounded border-2 border-primary bg-primary/20"></div>
          <span>Selected</span>
        </div>
      </div>

      <!-- Stage indicator -->
      <div class="text-center">
        <div class="inline-block px-10 py-1.5 rounded-t-xl bg-muted border border-b-0 border-border text-xs font-medium text-muted-foreground tracking-widest uppercase">
          Stage
        </div>
      </div>

      <!-- Seat Grid -->
      <div class="overflow-x-auto">
        <div class="inline-block min-w-full">
          <div class="space-y-1.5">
            @for (row of rows; track row) {
              <div class="flex items-center gap-2">
                <span class="text-xs text-muted-foreground w-5 text-right font-mono flex-shrink-0">{{ row }}</span>
                <div class="flex gap-1 flex-1 justify-center">
                  @for (seat of seatsByRow[row]; track seat.id) {
                    <button
                      (click)="selectSeat(seat)"
                      [disabled]="!seat.is_available"
                      [class]="seatClass(seat)"
                      [title]="'Row ' + seat.row + ', Seat ' + seat.col + ' — ' + seat.price_zone"
                    >
                      <span class="text-[10px] font-medium">{{ seat.col }}</span>
                    </button>
                  }
                </div>
                <span class="text-xs text-muted-foreground w-5 font-mono flex-shrink-0">{{ row }}</span>
              </div>
            }
          </div>
          <!-- Column numbers -->
          <div class="flex items-center gap-2 mt-2 pl-7">
            <div class="flex gap-1 flex-1 justify-center">
              @for (col of cols; track col) {
                <div class="w-7 h-4 flex items-center justify-center text-[10px] text-muted-foreground font-mono">{{ col }}</div>
              }
            </div>
          </div>
        </div>
      </div>

      <!-- Price zone labels -->
      <div class="flex justify-center gap-6 text-xs text-muted-foreground border-t border-border pt-3">
        <span>Rows 1–2: <strong class="text-blue-600">VIP</strong></span>
        <span>Rows 3–6: <strong class="text-[color:var(--pine-600)]">Standard</strong></span>
      </div>

      <!-- Selected seat summary -->
      @if (selectedSeat) {
        <div class="p-3 rounded-lg bg-[color:var(--pine-50)] border border-transparent flex items-center justify-between">
          <div>
            <p class="text-sm font-semibold text-[color:var(--pine-600)]">
              Row {{ selectedSeat.row }}, Seat {{ selectedSeat.col }}
            </p>
            <p class="text-xs text-[color:var(--pine-600)] capitalize">{{ selectedSeat.price_zone }} zone</p>
          </div>
          <button (click)="deselect()" class="text-xs text-[color:var(--pine-600)] hover:text-[color:var(--pine-600)] underline">Change</button>
        </div>
      } @else {
        <div class="p-3 rounded-lg bg-[color:var(--warning-50)] border border-transparent flex items-start gap-2 text-sm text-warning">
          <lucide-icon [img]="icons.AlertTriangle" class="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true"></lucide-icon>
          <span>Select a seat to continue</span>
        </div>
      }
    </div>
  `,
})
export class SeatSelectorComponent implements OnInit, OnDestroy, OnChanges {
  @Input() seats: Seat[] = [];
  @Input() eventId: number | null = null;
  @Output() seatSelected = new EventEmitter<Seat | null>();

  selectedSeat: Seat | null = null;
  rows: number[] = [];
  cols: number[] = [];
  seatsByRow: Record<number, Seat[]> = {};
  wsConnected = false;

  readonly icons = { AlertTriangle, Wifi, WifiOff };
  private subs = new Subscription();

  constructor(private seatWs: SeatWsService) {}

  ngOnInit(): void {
    this.buildGrid();
    this.connectWs();
  }

  ngOnChanges(): void {
    this.buildGrid();
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
    this.seatWs.disconnect();
  }

  private buildGrid(): void {
    if (!this.seats.length) return;
    const maxRow = Math.max(...this.seats.map(s => s.row));
    const maxCol = Math.max(...this.seats.map(s => s.col));
    this.rows = Array.from({ length: maxRow }, (_, i) => i + 1);
    this.cols = Array.from({ length: maxCol }, (_, i) => i + 1);
    this.seatsByRow = {};
    for (const row of this.rows) {
      this.seatsByRow[row] = this.seats.filter(s => s.row === row).sort((a, b) => a.col - b.col);
    }
  }

  private connectWs(): void {
    if (!this.eventId) return;

    this.seatWs.connect(this.eventId);

    // Snapshot → replace seats array (full refresh on reconnect)
    this.subs.add(
      this.seatWs.snapshots$.subscribe(msg => {
        this.seats = msg.seats;
        this.buildGrid();
        this.wsConnected = true;
        // Deselect if our seat was grabbed by someone else
        if (this.selectedSeat) {
          const fresh = this.seats.find(s => s.id === this.selectedSeat!.id);
          if (fresh && !fresh.is_available) {
            this.selectedSeat = null;
            this.seatSelected.emit(null);
          }
        }
      })
    );

    // Individual update → patch single seat in place
    this.subs.add(
      this.seatWs.seatUpdates$.subscribe((upd: WsSeatUpdate) => {
        this.wsConnected = true;
        const seat = this.seats.find(s => s.id === upd.seat_id);
        if (seat) {
          seat.is_available = upd.is_available;
          // If our selected seat just became unavailable → deselect
          if (this.selectedSeat?.id === upd.seat_id && !upd.is_available) {
            this.selectedSeat = null;
            this.seatSelected.emit(null);
          }
        }
      })
    );
  }

  seatClass(seat: Seat): string {
    const base = 'w-7 h-7 rounded border-2 flex items-center justify-center transition-all duration-150';
    if (!seat.is_available) {
      return `${base} bg-gray-200 border-gray-300 text-gray-400 cursor-not-allowed`;
    }
    if (this.selectedSeat?.id === seat.id) {
      return `${base} bg-primary/20 border-primary text-primary font-bold scale-110 shadow-sm`;
    }
    if (seat.price_zone === 'vip') {
      return `${base} bg-blue-50 border-blue-300 text-blue-700 hover:bg-blue-100 hover:scale-110 cursor-pointer`;
    }
    if (seat.price_zone === 'premium') {
      return `${base} bg-purple-50 border-purple-300 text-purple-700 hover:bg-purple-100 hover:scale-110 cursor-pointer`;
    }
    return `${base} bg-[color:var(--pine-50)] border-emerald-400 text-[color:var(--pine-600)] hover:bg-[color:var(--pine-50)] hover:scale-110 cursor-pointer`;
  }

  selectSeat(seat: Seat): void {
    if (!seat.is_available) return;
    this.selectedSeat = seat;
    this.seatSelected.emit(seat);
  }

  deselect(): void {
    this.selectedSeat = null;
    this.seatSelected.emit(null);
  }
}
