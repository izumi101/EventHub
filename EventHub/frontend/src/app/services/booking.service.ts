import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface BookingSeatDto {
  id: number;
  seat_id: number;
  row: number;
  col: number;
  zone: string;
  price: string;
  attendee_name: string;
  claimed: boolean;
  /** True when the signed-in viewer claimed this seat. */
  claimed_by_me: boolean;
  /** The QR ticket — only sent to the booking owner and to whoever claimed the seat. */
  ticket_uuid: string | null;
  is_checked_in: boolean;
}

export interface BookingDto {
  id: string;
  status: 'holding' | 'confirmed' | 'cancelled' | 'expired';
  /** Only returned to the owner (and to visitors of the share link itself). */
  share_token: string | null;
  hold_expires_at: string | null;
  event_id: number;
  event_title: string;
  event_date: string;
  event_location: string;
  owner_username: string;
  seats: BookingSeatDto[];
  seat_count: number;
  /** Sum of seat prices, before tax & service fee. */
  total_price: string;
  /** What checkout charges: seat prices plus tax & fees. */
  total_due: string;
  currency: string;
  is_owner: boolean;
  is_expired: boolean;
  created_at: string;
}

@Injectable({ providedIn: 'root' })
export class BookingService {
  private api = `${environment.apiUrl}/bookings`;

  constructor(private http: HttpClient) {}

  create(eventId: number, seatIds: number[]): Observable<BookingDto> {
    return this.http.post<BookingDto>(`${this.api}/`, { event: eventId, seat_ids: seatIds });
  }

  get(id: string): Observable<BookingDto> {
    return this.http.get<BookingDto>(`${this.api}/${id}/`);
  }

  getShared(token: string): Observable<BookingDto> {
    return this.http.get<BookingDto>(`${this.api}/shared/${token}/`);
  }

  claimSeat(token: string, seatId: number, name: string): Observable<BookingDto> {
    return this.http.post<BookingDto>(`${this.api}/shared/${token}/claim/`, { seat_id: seatId, name });
  }

  checkout(id: string): Observable<{ checkout_url: string; mock?: boolean }> {
    return this.http.post<{ checkout_url: string; mock?: boolean }>(`${this.api}/${id}/checkout/`, {});
  }

  cancel(id: string): Observable<any> {
    return this.http.post<any>(`${this.api}/${id}/cancel/`, {});
  }

  mine(): Observable<BookingDto[]> {
    return this.http.get<BookingDto[]>(`${this.api}/mine/`);
  }

  verify(sessionId: string): Observable<BookingDto> {
    return this.http.get<BookingDto>(`${this.api}/verify/`, { params: { session_id: sessionId } });
  }
}
