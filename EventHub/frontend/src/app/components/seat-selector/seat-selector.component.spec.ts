import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { SeatSelectorComponent, summariseZones } from './seat-selector.component';
import { SeatWsService, WsSeatUpdate, WsSnapshot } from '../../services/seat-ws.service';
import type { Seat } from '../../models/models';
import { cheapestZonePrice } from '../event-detail/event-detail.component';
import { I18nTestingModule } from '../../i18n/testing';

const seat = (id: number, zone: string, price: string, available = true): Seat =>
  ({ id, row: 1, col: id, price_zone: zone, price, is_available: available }) as unknown as Seat;

function setup(seats: Seat[]) {
  const snapshots$ = new Subject<WsSnapshot>();
  const seatUpdates$ = new Subject<WsSeatUpdate>();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, SeatSelectorComponent],
    providers: [
      {
        provide: SeatWsService,
        useValue: { snapshots$, seatUpdates$, connect: vi.fn(), disconnect: vi.fn() },
      },
    ],
  });
  const fixture = TestBed.createComponent(SeatSelectorComponent);
  fixture.componentRef.setInput('seats', seats);
  fixture.componentRef.setInput('eventId', 7);
  fixture.detectChanges();
  return { cmp: fixture.componentInstance, snapshots$ };
}

describe('SeatSelectorComponent live snapshot', () => {
  it('keeps every seat price when a snapshot refreshes availability', () => {
    const { cmp, snapshots$ } = setup([seat(1, 'vip', '16000.00'), seat(2, 'standard', '8000.00')]);
    // The socket sends availability only, without prices.
    snapshots$.next({
      type: 'snapshot',
      seats: [
        { id: 1, is_available: true } as unknown as Seat,
        { id: 2, is_available: false } as unknown as Seat,
      ],
    });
    expect(cmp.seats.map((s) => [s.id, s.price, s.is_available])).toEqual([
      [1, '16000.00', true],
      [2, '8000.00', false],
    ]);
  });

  it('a seat chosen after a snapshot carries its zone price to the checkout', () => {
    const { cmp, snapshots$ } = setup([seat(1, 'vip', '16000.00')]);
    const emitted: (Seat | null)[] = [];
    cmp.seatSelected.subscribe((s) => emitted.push(s));
    snapshots$.next({
      type: 'snapshot',
      seats: [{ id: 1, is_available: true } as unknown as Seat],
    });
    cmp.selectSeat(cmp.seats[0]);
    expect(emitted[0]?.price).toBe('16000.00');
  });
});

describe('cheapestZonePrice', () => {
  it('returns the lowest zone price, or null without zones', () => {
    expect(
      cheapestZonePrice([
        { zone: 'vip', multiplier: 2, price: '16000.00' },
        { zone: 'standard', multiplier: 1, price: '8000.00' },
        { zone: 'premium', multiplier: 3, price: '24000.00' },
      ]),
    ).toBe('8000.00');
    expect(cheapestZonePrice([])).toBeNull();
    expect(cheapestZonePrice(undefined)).toBeNull();
  });
});

describe('summariseZones', () => {
  it('lists the real zones in hall order with their rows and prices', () => {
    const at = (row: number, zone: string, price: string) =>
      ({
        id: row * 100,
        row,
        col: 1,
        price_zone: zone,
        price,
        is_available: true,
      }) as unknown as Seat;
    const zones = summariseZones([
      at(4, 'standard', '8000.00'),
      at(2, 'vip', '16000.00'),
      at(1, 'premium', '24000.00'),
      at(3, 'vip', '16000.00'),
      at(5, 'standard', '8000.00'),
    ]);
    expect(zones.map((z) => `${z.rows}: ${z.label} ${z.price}`)).toEqual([
      'Row 1: Premium 24000.00',
      'Rows 2–3: VIP 16000.00',
      'Rows 4–5: Standard 8000.00',
    ]);
  });
});
