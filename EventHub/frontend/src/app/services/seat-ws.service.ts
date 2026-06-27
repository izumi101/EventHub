import { Injectable, OnDestroy } from '@angular/core';
import { Observable, Subject, BehaviorSubject, timer, EMPTY } from 'rxjs';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { catchError, switchMap, tap, retryWhen, delay, takeUntil } from 'rxjs/operators';
import { Seat } from '../models/models';

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
  private socket$: WebSocketSubject<WsMessage> | null = null;
  private destroy$ = new Subject<void>();
  private reconnectDelay = 2000;

  /** Emits individual seat updates (is_available flipped) */
  private updates$ = new Subject<WsSeatUpdate>();

  /** Emits full snapshots on connect/reconnect */
  private snapshot$ = new Subject<WsSnapshot>();

  connect(eventId: number): void {
    if (this.socket$) this.disconnect();

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    // In dev: backend is on port 8000, frontend proxy passes /ws/ → backend
    const wsUrl = `${protocol}://${window.location.hostname}:8000/ws/seats/${eventId}/`;

    this.socket$ = webSocket<WsMessage>({
      url: wsUrl,
      openObserver: { next: () => console.log(`[SeatWS] Connected event=${eventId}`) },
      closeObserver: { next: () => console.log(`[SeatWS] Disconnected event=${eventId}`) },
    });

    this.socket$.pipe(
      retryWhen(errors => errors.pipe(delay(this.reconnectDelay))),
      takeUntil(this.destroy$),
    ).subscribe({
      next: msg => {
        if (msg.type === 'snapshot') this.snapshot$.next(msg as WsSnapshot);
        if (msg.type === 'seat_update') this.updates$.next(msg as WsSeatUpdate);
      },
      error: err => console.warn('[SeatWS] Error', err),
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
