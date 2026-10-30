import { Injectable, OnDestroy, inject } from '@angular/core';
import { Observable, Subject, timer } from 'rxjs';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { retry, takeUntil } from 'rxjs/operators';
import { Seat } from '../models/models';
import { AuthService } from './auth.service';

/** Reconnect with exponential backoff (1 s, 2 s, 4 s … capped at 30 s) and give
 *  up after this many attempts — the HTTP seat map still works without WS. */
const MAX_RECONNECTS = 8;

export interface WsSeatUpdate {
  type: 'seat_update';
  seat_id: number;
  is_available: boolean;
  price_zone: string;
}

export interface WsSnapshot {
  type: 'snapshot';
  seats: Seat[];
}

export type WsMessage = WsSeatUpdate | WsSnapshot;

@Injectable({ providedIn: 'root' })
export class SeatWsService implements OnDestroy {
  private auth = inject(AuthService);
  private socket$: WebSocketSubject<WsMessage> | null = null;
  private destroy$ = new Subject<void>();

  /** Emits individual seat updates (is_available flipped) */
  private updates$ = new Subject<WsSeatUpdate>();

  /** Emits full snapshots on connect/reconnect */
  private snapshot$ = new Subject<WsSnapshot>();

  connect(eventId: number): void {
    if (this.socket$) this.disconnect();

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    // Same origin as the page: nginx (and the dev-server proxy) forward /ws/
    // to Daphne, so this works over HTTPS and without exposing port 8000.
    const wsUrl = `${protocol}://${window.location.host}/ws/seats/${eventId}/`;

    // Browsers can't send headers with a WebSocket and URLs end up in logs,
    // so the access token travels as the second subprotocol (events/ws_auth.py).
    const token = this.auth.getToken();
    this.socket$ = webSocket<WsMessage>({
      url: wsUrl,
      protocol: token ? ['eventhub.jwt', token] : undefined,
    });

    this.socket$
      .pipe(
        retry({
          count: MAX_RECONNECTS,
          delay: (_err, attempt) => timer(Math.min(1000 * 2 ** (attempt - 1), 30_000)),
          resetOnSuccess: true,
        }),
        takeUntil(this.destroy$),
      )
      .subscribe({
        next: (msg) => {
          if (msg.type === 'snapshot') this.snapshot$.next(msg as WsSnapshot);
          if (msg.type === 'seat_update') this.updates$.next(msg as WsSeatUpdate);
        },
        // Live updates are a progressive enhancement; the page keeps working.
        error: () => {
          this.socket$ = null;
        },
      });
  }

  disconnect(): void {
    this.socket$?.complete();
    this.socket$ = null;
  }

  get seatUpdates$(): Observable<WsSeatUpdate> {
    return this.updates$.asObservable();
  }

  get snapshots$(): Observable<WsSnapshot> {
    return this.snapshot$.asObservable();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    this.disconnect();
  }
}
