import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { Seat } from '../../models/models';
import { SeatWsService } from '../../services/seat-ws.service';
import { SeatMapSvgComponent } from './seat-map-svg.component';

const seat = (id: number, row: number, col: number, is_available = true): Seat => ({
  id,
  row,
  col,
  price_zone: 'standard',
  is_available,
  price: '10.00',
});

describe('SeatMapSvgComponent keyboard access', () => {
  function render(seats: Seat[], maxSelection = 2) {
    TestBed.configureTestingModule({
      providers: [
        {
          provide: SeatWsService,
          useValue: {
            connect: () => undefined,
            disconnect: () => undefined,
            snapshots$: new Subject(),
            seatUpdates$: new Subject(),
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(SeatMapSvgComponent);
    fixture.componentInstance.seats = seats;
    fixture.componentInstance.maxSelection = maxSelection;
    fixture.componentInstance.currency = 'EUR';
    fixture.detectChanges();
    return fixture;
  }
  const el = (root: HTMLElement, id: number) =>
    root.querySelector<SVGGElement>(`[data-seat-id="${id}"]`)!;
  const key = (target: Element, k: string) =>
    target.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true }));

  it('exposes seats as labelled checkboxes with a single tab stop', () => {
    const fixture = render([seat(1, 1, 1, false), seat(2, 1, 2), seat(3, 2, 1)]);
    const root = fixture.nativeElement as HTMLElement;
    expect(el(root, 1).getAttribute('aria-label')).toBe('Row 1, seat 1, standard, €10.00, taken');
    expect(el(root, 1).getAttribute('aria-disabled')).toBe('true');
    // The first available seat is the tab stop.
    expect([1, 2, 3].map((id) => el(root, id).getAttribute('tabindex'))).toEqual(['-1', '0', '-1']);
  });

  it('moves with arrows and selects with Space', () => {
    const fixture = render([seat(1, 1, 1), seat(2, 1, 2), seat(3, 2, 2)]);
    const root = fixture.nativeElement as HTMLElement;
    const picked: number[][] = [];
    fixture.componentInstance.selectionChange.subscribe((s) => picked.push(s.map((x) => x.id)));

    key(el(root, 1), 'ArrowRight');
    fixture.detectChanges();
    expect(document.activeElement).toBe(el(root, 2));
    key(el(root, 2), 'ArrowDown');
    fixture.detectChanges();
    expect(document.activeElement).toBe(el(root, 3));

    key(el(root, 3), ' ');
    fixture.detectChanges();
    expect(picked).toEqual([[3]]);
    expect(el(root, 3).getAttribute('aria-checked')).toBe('true');
  });
});
