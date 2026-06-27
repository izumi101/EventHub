import {
  Component, Input, Output, EventEmitter, OnInit, OnDestroy, OnChanges,
  ElementRef, ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { LucideAngularModule, Plus, Minus, Maximize, Wifi } from 'lucide-angular';
import { Subscription } from 'rxjs';
import { Seat, ZonePrice } from '../../models/models';
import { SeatWsService, WsSeatUpdate } from '../../services/seat-ws.service';

interface ViewBox { x: number; y: number; w: number; h: number; }

const SEAT = 22;   // seat size px
const GAP = 8;     // gap between seats
const CELL = SEAT + GAP;
const PAD = 24;    // padding around grid
const STAGE_H = 46;

@Component({
  selector: 'app-seat-map-svg',
  standalone: true,
  imports: [CommonModule, LucideAngularModule],
  template: `
    <div class="seat-map-wrap relative select-none">
      <!-- Toolbar -->
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-1.5 text-xs" [class]="wsConnected ? 'text-[color:var(--pine-600)]' : 'text-muted-foreground'">
          <span class="relative flex h-2 w-2">
            @if (wsConnected) {
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-2 w-2 bg-[color:var(--pine-50)]0"></span>
            } @else {
              <span class="relative inline-flex rounded-full h-2 w-2 bg-gray-300"></span>
            }
          </span>
          {{ wsConnected ? 'Live availability' : 'Connecting…' }}
        </div>
        <div class="flex items-center gap-1">
          <button (click)="zoomBy(0.8)" class="zoom-btn" title="Zoom out"><lucide-icon [img]="icons.Minus" class="w-4 h-4"></lucide-icon></button>
          <button (click)="resetView()" class="zoom-btn" title="Reset"><lucide-icon [img]="icons.Maximize" class="w-3.5 h-3.5"></lucide-icon></button>
          <button (click)="zoomBy(1.25)" class="zoom-btn" title="Zoom in"><lucide-icon [img]="icons.Plus" class="w-4 h-4"></lucide-icon></button>
        </div>
      </div>

      <!-- SVG canvas -->
      <div
        #canvas
        class="seat-canvas relative rounded-xl border border-border bg-muted/30 overflow-hidden touch-none"
        [style.height.px]="canvasHeight"
        (wheel)="onWheel($event)"
        (mousedown)="onPanStart($event)"
        (mousemove)="onPanMove($event)"
        (mouseup)="onPanEnd()"
        (mouseleave)="onPanEnd(); hovered = null"
        (touchstart)="onTouchStart($event)"
        (touchmove)="onTouchMove($event)"
        (touchend)="onPanEnd()"
      >
        <svg
          [attr.viewBox]="vb.x + ' ' + vb.y + ' ' + vb.w + ' ' + vb.h"
          width="100%" height="100%"
          [class.cursor-grabbing]="panning"
          [class.cursor-grab]="!panning"
        >
          <!-- Stage -->
          <rect [attr.x]="PAD" [attr.y]="PAD - 6" [attr.width]="gridWidth" [attr.height]="26" rx="6"
                fill="var(--secondary)" stroke="var(--border)" />
          <text [attr.x]="PAD + gridWidth / 2" [attr.y]="PAD + 11" text-anchor="middle"
                font-size="12" font-weight="700" letter-spacing="3"
                fill="var(--muted-foreground)">STAGE</text>

          <!-- Seats -->
          @for (s of seats; track s.id) {
            <g
              (click)="toggleSeat(s, $event)"
              (mouseenter)="hover(s, $event)"
              (mousemove)="moveTip($event)"
              [style.cursor]="s.is_available ? 'pointer' : 'not-allowed'"
            >
              <rect
                [attr.x]="seatX(s)" [attr.y]="seatY(s)"
                [attr.width]="SEAT" [attr.height]="SEAT" rx="5"
                [attr.fill]="seatFill(s)"
                [attr.stroke]="seatStroke(s)"
                stroke-width="1.5"
                [class.seat-selected]="isSelected(s)"
              />
              <text
                [attr.x]="seatX(s) + SEAT / 2" [attr.y]="seatY(s) + SEAT / 2 + 3.5"
                text-anchor="middle" font-size="9"
                [attr.fill]="seatTextColor(s)"
                pointer-events="none"
              >{{ s.col }}</text>
            </g>
          }

          <!-- Row labels -->
          @for (r of rows; track r) {
            <text [attr.x]="PAD - 10" [attr.y]="rowLabelY(r)" text-anchor="end" font-size="10"
                  fill="var(--muted-foreground)" pointer-events="none">{{ r }}</text>
          }
        </svg>

        <!-- Hover tooltip -->
        @if (hovered) {
          <div
            class="seat-tip absolute z-20 pointer-events-none px-2.5 py-1.5 rounded-lg bg-foreground text-background text-xs shadow-lg whitespace-nowrap"
            [style.left.px]="tipX" [style.top.px]="tipY"
          >
            <span class="font-semibold">Row {{ hovered.row }}, Seat {{ hovered.col }}</span>
            <span class="opacity-70 mx-1">·</span>
            <span class="capitalize">{{ hovered.zone || hovered.price_zone }}</span>
            @if (hovered.price) {
              <span class="opacity-70 mx-1">·</span>
              <span class="font-semibold">{{ '$' + hovered.price }}</span>
            }
            @if (!hovered.is_available) {
              <span class="ml-1 text-ember">· Taken</span>
            }
          </div>
        }

        <!-- Hint -->
        <div class="absolute bottom-2 left-2 text-[10px] text-muted-foreground bg-background/80 backdrop-blur px-2 py-0.5 rounded">
          Scroll to zoom · drag to pan
        </div>
      </div>

      <!-- Legend with prices -->
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1.5 mt-3 text-xs">
        @for (z of zonePrices; track z.zone) {
          <div class="flex items-center gap-1.5">
            <span class="w-3.5 h-3.5 rounded border-2" [style.background]="zoneFill(z.zone)" [style.border-color]="zoneStroke(z.zone)"></span>
            <span class="capitalize text-foreground">{{ z.zone }}</span>
            <span class="font-semibold text-foreground">{{ '$' + z.price }}</span>
          </div>
        }
        <div class="flex items-center gap-1.5">
          <span class="w-3.5 h-3.5 rounded bg-gray-300 border-2 border-gray-400"></span>
          <span class="text-muted-foreground">Taken</span>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .zoom-btn {
      width: 30px; height: 30px;
      display: flex; align-items: center; justify-content: center;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--card);
      color: var(--muted-foreground);
      transition: all .15s;
    }
    .zoom-btn:hover { background: var(--muted); color: var(--foreground); }
    .seat-selected { filter: drop-shadow(0 1px 3px rgba(79,70,229,.5)); }
    svg rect[rx="5"] { transition: fill .12s, stroke .12s; }
  `],
})
export class SeatMapSvgComponent implements OnInit, OnDestroy, OnChanges {
  @Input() seats: Seat[] = [];
  @Input() maxSelection = 1;
  @Input() eventId: number | null = null;
  @Input() zonePrices: ZonePrice[] = [];
  @Output() selectionChange = new EventEmitter<Seat[]>();

  @ViewChild('canvas') canvasRef!: ElementRef<HTMLDivElement>;

  readonly icons = { Plus, Minus, Maximize, Wifi };
  readonly SEAT = SEAT;
  readonly PAD = PAD;

  selectedIds = new Set<number>();
  rows: number[] = [];
  maxRow = 0;
  maxCol = 0;
  gridWidth = 0;
  gridHeight = 0;
  canvasHeight = 360;

  vb: ViewBox = { x: 0, y: 0, w: 100, h: 100 };
  private fullVb: ViewBox = { x: 0, y: 0, w: 100, h: 100 };

  panning = false;
  private panStart = { x: 0, y: 0 };
  private vbStart = { x: 0, y: 0 };

  hovered: (Seat & { zone?: string }) | null = null;
  tipX = 0; tipY = 0;

  wsConnected = false;
  private subs = new Subscription();

  constructor(private seatWs: SeatWsService) {}

  ngOnInit(): void {
    this.build();
    this.connectWs();
  }

  ngOnChanges(): void {
    this.build();
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
    this.seatWs.disconnect();
  }

  // ───────── geometry ─────────
  private build(): void {
    if (!this.seats.length) return;
    this.maxRow = Math.max(...this.seats.map(s => s.row));
    this.maxCol = Math.max(...this.seats.map(s => s.col));
    this.rows = Array.from({ length: this.maxRow }, (_, i) => i + 1);
    this.gridWidth = this.maxCol * CELL - GAP;
    this.gridHeight = this.maxRow * CELL - GAP;

    const totalW = this.gridWidth + PAD * 2;
    const totalH = this.gridHeight + PAD * 2 + STAGE_H;
    this.fullVb = { x: 0, y: 0, w: totalW, h: totalH };
    this.vb = { ...this.fullVb };

    // Fit canvas height to a sensible aspect (cap)
    this.canvasHeight = Math.min(460, Math.max(280, totalH * 0.9));
  }

  seatX(s: Seat): number { return PAD + (s.col - 1) * CELL; }
  seatY(s: Seat): number { return PAD + STAGE_H + (s.row - 1) * CELL; }
  rowLabelY(r: number): number { return PAD + STAGE_H + (r - 1) * CELL + SEAT / 2 + 3.5; }

  // ───────── colors ─────────
  zoneFill(zone: string): string {
    return { vip: '#dbeafe', premium: '#ede9fe', standard: '#d1fae5' }[zone] ?? '#d1fae5';
  }
  zoneStroke(zone: string): string {
    return { vip: '#60a5fa', premium: '#a78bfa', standard: '#34d399' }[zone] ?? '#34d399';
  }
  seatFill(s: Seat): string {
    if (!s.is_available) return '#d1d5db';
    if (this.isSelected(s)) return '#E8552D';
    return this.zoneFill(s.price_zone);
  }
  seatStroke(s: Seat): string {
    if (!s.is_available) return '#9ca3af';
    if (this.isSelected(s)) return '#C2410C';
    return this.zoneStroke(s.price_zone);
  }
  seatTextColor(s: Seat): string {
    if (this.isSelected(s)) return '#ffffff';
    if (!s.is_available) return '#6b7280';
    return '#374151';
  }

  // ───────── selection ─────────
  isSelected(s: Seat): boolean { return this.selectedIds.has(s.id); }

  toggleSeat(s: Seat, evt: MouseEvent): void {
    evt.stopPropagation();
    if (this.draggedDuringPress) return;   // ignore clicks that were drags
    if (!s.is_available) return;

    if (this.selectedIds.has(s.id)) {
      this.selectedIds.delete(s.id);
    } else {
      if (this.maxSelection === 1) {
        this.selectedIds.clear();
        this.selectedIds.add(s.id);
      } else if (this.selectedIds.size < this.maxSelection) {
        this.selectedIds.add(s.id);
      } else {
        return; // limit reached
      }
    }
    this.emit();
  }

  private emit(): void {
    const chosen = this.seats.filter(s => this.selectedIds.has(s.id));
    this.selectionChange.emit(chosen);
  }

  // ───────── zoom & pan ─────────
  zoomBy(factor: number, cx?: number, cy?: number): void {
    const newW = Math.min(this.fullVb.w, this.vb.w / factor);
    const newH = Math.min(this.fullVb.h, this.vb.h / factor);
    // zoom toward a focal point (default center)
    const fx = cx ?? this.vb.x + this.vb.w / 2;
    const fy = cy ?? this.vb.y + this.vb.h / 2;
    const dx = (fx - this.vb.x) * (1 - newW / this.vb.w);
    const dy = (fy - this.vb.y) * (1 - newH / this.vb.h);
    this.vb = this.clamp({ x: this.vb.x + dx, y: this.vb.y + dy, w: newW, h: newH });
  }

  onWheel(e: WheelEvent): void {
    e.preventDefault();
    const rect = this.canvasRef.nativeElement.getBoundingClientRect();
    const px = this.vb.x + ((e.clientX - rect.left) / rect.width) * this.vb.w;
    const py = this.vb.y + ((e.clientY - rect.top) / rect.height) * this.vb.h;
    this.zoomBy(e.deltaY < 0 ? 1.15 : 0.87, px, py);
  }

  resetView(): void { this.vb = { ...this.fullVb }; }

  private draggedDuringPress = false;

  onPanStart(e: MouseEvent): void {
    this.panning = true;
    this.draggedDuringPress = false;
    this.panStart = { x: e.clientX, y: e.clientY };
    this.vbStart = { x: this.vb.x, y: this.vb.y };
  }

  onPanMove(e: MouseEvent): void {
    if (!this.panning) return;
    const rect = this.canvasRef.nativeElement.getBoundingClientRect();
    const dx = ((e.clientX - this.panStart.x) / rect.width) * this.vb.w;
    const dy = ((e.clientY - this.panStart.y) / rect.height) * this.vb.h;
    if (Math.abs(e.clientX - this.panStart.x) > 3 || Math.abs(e.clientY - this.panStart.y) > 3) {
      this.draggedDuringPress = true;
    }
    this.vb = this.clamp({ ...this.vb, x: this.vbStart.x - dx, y: this.vbStart.y - dy });
  }

  onPanEnd(): void {
    this.panning = false;
    // reset drag flag after the click event has fired
    setTimeout(() => (this.draggedDuringPress = false), 0);
  }

  // touch (single-finger pan)
  onTouchStart(e: TouchEvent): void {
    if (e.touches.length === 1) {
      this.onPanStart({ clientX: e.touches[0].clientX, clientY: e.touches[0].clientY } as MouseEvent);
    }
  }
  onTouchMove(e: TouchEvent): void {
    if (e.touches.length === 1) {
      this.onPanMove({ clientX: e.touches[0].clientX, clientY: e.touches[0].clientY } as MouseEvent);
    }
  }

  private clamp(v: ViewBox): ViewBox {
    // keep viewBox inside the full content bounds
    const x = Math.max(this.fullVb.x, Math.min(v.x, this.fullVb.x + this.fullVb.w - v.w));
    const y = Math.max(this.fullVb.y, Math.min(v.y, this.fullVb.y + this.fullVb.h - v.h));
    return { x, y, w: v.w, h: v.h };
  }

  // ───────── tooltip ─────────
  hover(s: Seat, e: MouseEvent): void {
    this.hovered = { ...s, zone: s.price_zone };
    this.moveTip(e);
  }
  moveTip(e: MouseEvent): void {
    const rect = this.canvasRef?.nativeElement.getBoundingClientRect();
    if (!rect) return;
    this.tipX = e.clientX - rect.left + 12;
    this.tipY = e.clientY - rect.top + 12;
  }

  // ───────── live updates ─────────
  private connectWs(): void {
    if (!this.eventId) return;
    this.seatWs.connect(this.eventId);

    this.subs.add(this.seatWs.snapshots$.subscribe(msg => {
      this.wsConnected = true;
      // merge availability without losing local geometry
      const byId = new Map(msg.seats.map(s => [s.id, s]));
      this.seats = this.seats.map(s => byId.has(s.id) ? { ...s, is_available: byId.get(s.id)!.is_available } : s);
      this.dropTakenSelections();
    }));

    this.subs.add(this.seatWs.seatUpdates$.subscribe((u: WsSeatUpdate) => {
      this.wsConnected = true;
      const seat = this.seats.find(s => s.id === u.seat_id);
      if (seat) {
        seat.is_available = u.is_available;
        if (!u.is_available) this.dropTakenSelections();
      }
    }));
  }

  private dropTakenSelections(): void {
    let changed = false;
    for (const id of [...this.selectedIds]) {
      const seat = this.seats.find(s => s.id === id);
      if (seat && !seat.is_available) { this.selectedIds.delete(id); changed = true; }
    }
    if (changed) this.emit();
  }
}
