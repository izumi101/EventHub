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
  ticket_uuid: string;
  is_checked_in: boolean;
}

export interface BookingDto {
  id: string;
  status: 'holding' | 'confirmed' | 'cancelled' | 'expired';
  share_token: string;
  hold_expires_at: string | null;
  event_id: number;
  event_title: string;
  event_date: string;
  event_location: string;
  owner_username: string;
  seats: BookingSeatDto[];
  seat_count: number;
  total_price: string;
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
