import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  Category,
  CheckInResponse,
  Event,
  EventActionResponse,
  EventFormPayload,
  EventStatsResponse,
  PaginatedResponse,
  Registration,
} from '../models/models';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class EventService {
  private apiUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  getCategories(): Observable<Category[]> {
    return this.http
      .get<Category[] | PaginatedResponse<Category>>(`${this.apiUrl}/categories/`)
      .pipe(map(response => Array.isArray(response) ? response : response.results));
  }

  getEvents(params?: {
    category?: number;
    search?: string;
    q?: string;          // semantic search query
    location?: string;
    ordering?: string;
    is_free?: boolean;
    is_online?: boolean;
    status?: string;
    page?: number;
    upcoming?: boolean;
  }): Observable<PaginatedResponse<Event>> {
    let httpParams = new HttpParams();
    if (params) {
      if (params.category) httpParams = httpParams.set('category', params.category.toString());
      if (params.search) httpParams = httpParams.set('search', params.search);
      if (params.q) httpParams = httpParams.set('q', params.q);
      if (params.location) httpParams = httpParams.set('location', params.location);
      if (params.ordering) httpParams = httpParams.set('ordering', params.ordering);
      if (params.is_free) httpParams = httpParams.set('is_free', 'true');
      if (params.is_online) httpParams = httpParams.set('is_online', 'true');
      if (params.status) httpParams = httpParams.set('status', params.status);
      if (params.page) httpParams = httpParams.set('page', params.page.toString());
      if (params.upcoming) httpParams = httpParams.set('upcoming', 'true');
    }
    return this.http.get<PaginatedResponse<Event>>(`${this.apiUrl}/events/`, { params: httpParams });
  }

  getEvent(id: number): Observable<Event> {
    return this.http.get<Event>(`${this.apiUrl}/events/${id}/`);
  }

  approveEvent(id: number): Observable<EventActionResponse> {
    return this.http.post<EventActionResponse>(`${this.apiUrl}/events/${id}/approve/`, {});
  }

  rejectEvent(id: number): Observable<EventActionResponse> {
    return this.http.post<EventActionResponse>(`${this.apiUrl}/events/${id}/reject/`, {});
  }

  createEvent(data: EventFormPayload | FormData): Observable<Event> {
    return this.http.post<Event>(`${this.apiUrl}/events/`, data);
  }

  updateEvent(id: number, data: Partial<EventFormPayload> | FormData): Observable<Event> {
    return this.http.put<Event>(`${this.apiUrl}/events/${id}/`, data);
  }

  deleteEvent(id: number): Observable<EventActionResponse> {
    return this.http.delete<EventActionResponse>(`${this.apiUrl}/events/${id}/`);
  }

  registerForEvent(eventId: number, payload: any = {}): Observable<Registration> {
    // Support both old string notes and new object payload
    const body = typeof payload === 'string' ? { notes: payload } : payload;
    return this.http.post<Registration>(`${this.apiUrl}/events/${eventId}/register/`, body);
  }

  cancelRegistration(eventId: number): Observable<EventActionResponse> {
    return this.http.post<EventActionResponse>(`${this.apiUrl}/events/${eventId}/cancel/`, {});
  }

  getMyEvents(): Observable<PaginatedResponse<Event>> {
    return this.http.get<PaginatedResponse<Event>>(`${this.apiUrl}/my-events/`);
  }

  getMyRegistrations(params?: { event?: number }): Observable<PaginatedResponse<Registration>> {
    let httpParams = new HttpParams();
    if (params?.event) httpParams = httpParams.set('event', params.event.toString());
    return this.http.get<PaginatedResponse<Registration>>(`${this.apiUrl}/my-registrations/`, { params: httpParams });
  }

  getSeatMap(eventId: number): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/events/${eventId}/seat_map/`);
  }

  getRecommendations(): Observable<PaginatedResponse<Event>> {
    return this.http.get<PaginatedResponse<Event>>(`${this.apiUrl}/recommendations/`);
  }

  getEventPricing(eventId: number): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/events/${eventId}/pricing/`);
  }

  // --- Organizer/Check-in Features ---

  /**
   * Validates a ticket by its unique UUID.
   * Can only be performed by the event organizer.
   */
  checkIn(uuid: string): Observable<CheckInResponse> {
    return this.http.post<CheckInResponse>(`${this.apiUrl}/registrations/check-in/${uuid}/`, {});
  }

  /**
   * Retrieves real-time statistics for an organized event.
   */
  getEventStats(eventId: number): Observable<EventStatsResponse> {
    return this.http.get<EventStatsResponse>(`${this.apiUrl}/events/${eventId}/stats/`);
  }

  /**
   * Retrieves all confirmed registrations for a specific event.
   */
  getEventRegistrations(eventId: number): Observable<Registration[]> {
    return this.http.get<Registration[]>(`${this.apiUrl}/events/${eventId}/registrations/`);
  }

  // ── Favorites ──
  getFavorites(): Observable<any[]> {
    return this.http.get<any>(`${this.apiUrl}/favorites/`).pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }
  toggleFavorite(eventId: number): Observable<{ favorited: boolean }> {
    return this.http.post<{ favorited: boolean }>(`${this.apiUrl}/favorites/${eventId}/`, {});
  }
  getFavoriteStatus(eventId: number): Observable<{ favorited: boolean }> {
    return this.http.get<{ favorited: boolean }>(`${this.apiUrl}/favorites/${eventId}/`);
  }

  // ── Reviews ──
  getEventReviews(eventId: number): Observable<any[]> {
    return this.http.get<any>(`${this.apiUrl}/events/${eventId}/reviews/`).pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }
  createReview(eventId: number, rating: number, comment: string): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/events/${eventId}/reviews/`, { rating, comment });
  }

  // ── Notifications ──
  getNotifications(): Observable<any[]> {
    return this.http.get<any>(`${this.apiUrl}/notifications/`).pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }
  markNotificationRead(id?: number): Observable<any> {
    const url = id ? `${this.apiUrl}/notifications/${id}/read/` : `${this.apiUrl}/notifications/read/`;
    return this.http.post<any>(url, {});
  }

  // ── Admin Dashboard ──
  getAdminDashboard(): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/admin-dashboard/`);
  }

  // ── Promo codes (public validate) ──
  validatePromo(eventId: number, code: string, ctx?: { ticket_type_id?: number; seat_id?: number }): Observable<PromoQuote> {
    return this.http.post<PromoQuote>(`${this.apiUrl}/events/${eventId}/validate-promo/`, { code, ...(ctx ?? {}) });
  }

  // ── Promo codes (organizer CRUD) ──
  getPromoCodes(eventId: number): Observable<PromoCode[]> {
    return this.http.get<any>(`${this.apiUrl}/events/${eventId}/promo-codes/`)
      .pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }
  createPromoCode(eventId: number, data: Partial<PromoCode>): Observable<PromoCode> {
    return this.http.post<PromoCode>(`${this.apiUrl}/events/${eventId}/promo-codes/`, data);
  }
  updatePromoCode(id: number, data: Partial<PromoCode>): Observable<PromoCode> {
    return this.http.patch<PromoCode>(`${this.apiUrl}/promo-codes/${id}/`, data);
  }
  deletePromoCode(id: number): Observable<any> {
    return this.http.delete<any>(`${this.apiUrl}/promo-codes/${id}/`);
  }

  // ── Event clone / lifecycle ──
  cloneEvent(eventId: number): Observable<Event> {
    return this.http.post<Event>(`${this.apiUrl}/events/${eventId}/clone/`, {});
  }
  submitEvent(eventId: number): Observable<EventActionResponse> {
    return this.http.post<EventActionResponse>(`${this.apiUrl}/events/${eventId}/submit/`, {});
  }
  cancelEvent(eventId: number): Observable<EventActionResponse & { notified?: number; refunded?: number }> {
    return this.http.post<EventActionResponse & { notified?: number; refunded?: number }>(`${this.apiUrl}/events/${eventId}/cancel-event/`, {});
  }

  // ── Seat map management (organizer) ──
  createSeatMap(eventId: number, data: { rows: number; cols: number; vip_rows?: number; premium_rows?: number; sync_capacity?: boolean }): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/events/${eventId}/seat-map/create/`, data);
  }

  // ── Analytics (organizer) ──
  getEventAnalytics(eventId: number): Observable<EventAnalytics> {
    return this.http.get<EventAnalytics>(`${this.apiUrl}/events/${eventId}/analytics/`);
  }

  // ── Virtual waiting queue ──
  queueJoin(eventId: number): Observable<QueueStatus> {
    return this.http.post<QueueStatus>(`${this.apiUrl}/events/${eventId}/queue_join/`, {});
  }
  queueStatus(eventId: number): Observable<QueueStatus> {
    return this.http.get<QueueStatus>(`${this.apiUrl}/events/${eventId}/queue_status/`);
  }

  // ── Ticket types ──
  getTicketTypes(eventId: number): Observable<TicketType[]> {
    return this.http.get<any>(`${this.apiUrl}/events/${eventId}/ticket-types/`)
      .pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }
  createTicketType(eventId: number, data: Partial<TicketType>): Observable<TicketType> {
    return this.http.post<TicketType>(`${this.apiUrl}/events/${eventId}/ticket-types/`, data);
  }
  updateTicketType(id: number, data: Partial<TicketType>): Observable<TicketType> {
    return this.http.patch<TicketType>(`${this.apiUrl}/ticket-types/${id}/`, data);
  }
  deleteTicketType(id: number): Observable<any> {
    return this.http.delete<any>(`${this.apiUrl}/ticket-types/${id}/`);
  }

  // ── Custom questions ──
  getEventQuestions(eventId: number): Observable<EventQuestion[]> {
    return this.http.get<any>(`${this.apiUrl}/events/${eventId}/questions/`)
      .pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }
  createQuestion(eventId: number, data: Partial<EventQuestion>): Observable<EventQuestion> {
    return this.http.post<EventQuestion>(`${this.apiUrl}/events/${eventId}/questions/`, data);
  }
  updateQuestion(id: number, data: Partial<EventQuestion>): Observable<EventQuestion> {
    return this.http.patch<EventQuestion>(`${this.apiUrl}/questions/${id}/`, data);
  }
  deleteQuestion(id: number): Observable<any> {
    return this.http.delete<any>(`${this.apiUrl}/questions/${id}/`);
  }

  // ── Waitlist ──
  getWaitlistStatus(eventId: number): Observable<WaitlistStatus> {
    return this.http.get<WaitlistStatus>(`${this.apiUrl}/events/${eventId}/waitlist/`);
  }
  joinWaitlist(eventId: number): Observable<WaitlistStatus> {
    return this.http.post<WaitlistStatus>(`${this.apiUrl}/events/${eventId}/waitlist/`, {});
  }
  leaveWaitlist(eventId: number): Observable<any> {
    return this.http.delete<any>(`${this.apiUrl}/events/${eventId}/waitlist/`);
  }
  getEventWaitlist(eventId: number): Observable<any[]> {
    return this.http.get<any>(`${this.apiUrl}/events/${eventId}/waitlist-entries/`)
      .pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }

  // ── Attendee CSV export (returns a Blob to trigger a download) ──
  exportAttendeesUrl(eventId: number): string {
    return `${this.apiUrl}/events/${eventId}/export-attendees/`;
  }
  exportAttendees(eventId: number): Observable<Blob> {
    return this.http.get(this.exportAttendeesUrl(eventId), { responseType: 'blob' });
  }

  // ── Refunds & offline payments (organizer) ──
  refundRegistration(registrationId: number, body: { amount?: string; reason?: string }): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/payments/refund/${registrationId}/`, body);
  }
  markOfflinePaid(registrationId: number, amount?: string): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/payments/mark-offline/${registrationId}/`, { amount });
  }

  // ── Refund requests ──
  requestRefund(eventId: number, reason: string): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/events/${eventId}/request-refund/`, { reason });
  }
  getRefundRequests(eventId: number): Observable<RefundRequest[]> {
    return this.http.get<any>(`${this.apiUrl}/events/${eventId}/refund-requests/`)
      .pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }
  resolveRefundRequest(id: number, approve: boolean, note = ''): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/refund-requests/${id}/resolve/`, { approve, note });
  }

  // ── Team / roles ──
  getStaff(eventId: number): Observable<EventStaff[]> {
    return this.http.get<any>(`${this.apiUrl}/events/${eventId}/staff/`)
      .pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }
  addStaff(eventId: number, invite_username: string, role: string): Observable<EventStaff> {
    return this.http.post<EventStaff>(`${this.apiUrl}/events/${eventId}/staff/`, { invite_username, role });
  }
  removeStaff(id: number): Observable<any> {
    return this.http.delete<any>(`${this.apiUrl}/staff/${id}/`);
  }

  // ── Webhooks ──
  getWebhooks(eventId: number): Observable<Webhook[]> {
    return this.http.get<any>(`${this.apiUrl}/events/${eventId}/webhooks/`)
      .pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }
  createWebhook(eventId: number, data: Partial<Webhook>): Observable<Webhook> {
    return this.http.post<Webhook>(`${this.apiUrl}/events/${eventId}/webhooks/`, data);
  }
  updateWebhook(id: number, data: Partial<Webhook>): Observable<Webhook> {
    return this.http.patch<Webhook>(`${this.apiUrl}/webhooks/${id}/`, data);
  }
  deleteWebhook(id: number): Observable<any> {
    return this.http.delete<any>(`${this.apiUrl}/webhooks/${id}/`);
  }

  // ── Affiliates ──
  getAffiliates(eventId: number): Observable<Affiliate[]> {
    return this.http.get<any>(`${this.apiUrl}/events/${eventId}/affiliates/`)
      .pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }
  createAffiliate(eventId: number, data: Partial<Affiliate>): Observable<Affiliate> {
    return this.http.post<Affiliate>(`${this.apiUrl}/events/${eventId}/affiliates/`, data);
  }
  deleteAffiliate(id: number): Observable<any> {
    return this.http.delete<any>(`${this.apiUrl}/affiliates/${id}/`);
  }
  trackAffiliateClick(eventId: number, code: string): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/events/${eventId}/affiliate-click/`, { code });
  }

  // ── Broadcast message to attendees ──
  broadcast(eventId: number, body: { subject: string; body: string; audience: string }): Observable<BroadcastResult> {
    return this.http.post<BroadcastResult>(`${this.apiUrl}/events/${eventId}/broadcast/`, body);
  }

  // ── Invoice (fetched with the auth header, opened as a blob — no JWT in the URL) ──
  getInvoiceBlob(registrationId: number): Observable<Blob> {
    return this.http.get(`${this.apiUrl}/payments/invoice/${registrationId}/`, { responseType: 'blob' });
  }

  // ── Check-in Lists ──
  getCheckInLists(eventId: number): Observable<any[]> {
    return this.http.get<any>(`${this.apiUrl}/events/${eventId}/checkin-lists/`)
      .pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }
  createCheckInList(eventId: number, data: { name: string; description?: string; color?: string }): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/events/${eventId}/checkin-lists/`, data);
  }
  updateCheckInList(listId: number, data: Partial<{ name: string; description: string; color: string; is_default: boolean }>): Observable<any> {
    return this.http.patch<any>(`${this.apiUrl}/checkin-lists/${listId}/`, data);
  }
  deleteCheckInList(listId: number): Observable<any> {
    return this.http.delete<any>(`${this.apiUrl}/checkin-lists/${listId}/`);
  }
  getCheckInListAttendees(listId: number): Observable<any[]> {
    return this.http.get<any>(`${this.apiUrl}/checkin-lists/${listId}/attendees/`)
      .pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }
  checkInByList(listId: number, ticketUuid: string, action: 'check_in' | 'undo' = 'check_in', note = ''): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/checkin-lists/${listId}/check-in/`, { ticket_uuid: ticketUuid, action, note });
  }
  getCheckInLogs(eventId: number): Observable<any[]> {
    return this.http.get<any>(`${this.apiUrl}/events/${eventId}/checkin-logs/`)
      .pipe(map((r: any) => Array.isArray(r) ? r : r.results ?? []));
  }
}

export interface QueueStatus {
  status: 'queued' | 'admitted' | 'not_in_queue' | 'not_needed';
  position?: number;
  total?: number;
  wait_minutes?: number;
  token?: string;
  expires_in?: number;
  message?: string;
}

export interface EventAnalytics {
  currency: string;
  kpis: {
    net_revenue: number;
    gross_revenue: number;
    refunded: number;
    tickets_sold: number;
    paid_orders: number;
    avg_order_value: number;
    capacity: number;
    sold_through_pct: number;
    checked_in: number;
    checkin_rate_pct: number;
    pending: number;
  };
  timeline: { date: string; tickets: number; revenue: number }[];
  by_ticket_type: { name: string; count: number; revenue: number }[];
  by_affiliate: { name: string; count: number; revenue: number }[];
}

export interface BroadcastResult {
  recipients: number;
  notified: number;
  emailed: number;
  email_enabled: boolean;
}

export interface RefundRequest {
  id: number;
  username: string;
  full_name: string;
  amount: string;
  ticket_type: string | null;
  status: 'pending' | 'approved' | 'rejected';
  reason: string;
  organizer_note: string;
  created_at: string;
  resolved_at: string | null;
}

export interface PriceBreakdown {
  subtotal: string;
  tax_percent: string;
  tax: string;
  fee_percent: string;
  fee: string;
  fees_passed_to_buyer: boolean;
  total: string;
  currency: string;
}

export interface PromoQuote {
  code: string;
  discount_type: 'percent' | 'fixed';
  discount_value: string;
  base_price: string;
  final_price: string;
  savings: string;
}

export interface PromoCode {
  id: number;
  code: string;
  discount_type: 'percent' | 'fixed';
  discount_value: string;
  max_uses: number | null;
  times_used: number;
  expires_at: string | null;
  is_active: boolean;
  created_at: string;
  is_valid: boolean;
  is_expired: boolean;
  is_exhausted: boolean;
}

export type TicketKind = 'paid' | 'free' | 'donation';
export type SaleState = 'on_sale' | 'sold_out' | 'scheduled' | 'ended' | 'inactive';

export interface TicketType {
  id: number;
  name: string;
  description: string;
  kind: TicketKind;
  price: string;
  quantity: number | null;
  min_per_order: number;
  max_per_order: number;
  sale_start: string | null;
  sale_end: string | null;
  is_active: boolean;
  order: number;
  sold: number;
  available: number | null;
  is_sold_out: boolean;
  on_sale: boolean;
  sale_state: SaleState;
}

export type QuestionType = 'text' | 'textarea' | 'dropdown' | 'checkbox' | 'date' | 'phone';

export interface EventQuestion {
  id: number;
  label: string;
  question_type: QuestionType;
  options: string[];
  is_required: boolean;
  order: number;
}

export interface WaitlistStatus {
  status: 'waiting' | 'offered' | 'converted' | 'expired' | 'not_joined' | 'spots_available' | 'left';
  position?: number | null;
  offer_expires_at?: string | null;
  message?: string;
}

export interface EventStaff {
  id: number;
  username: string;
  email: string;
  role: 'co_organizer' | 'check_in';
  created_at: string;
}

export type WebhookTrigger = 'ticket_sold' | 'registration_created' | 'refund_issued' | 'attendee_checked_in';

export interface Webhook {
  id: number;
  url: string;
  secret: string;
  triggers: WebhookTrigger[];
  is_active: boolean;
  created_at: string;
  last_triggered_at: string | null;
  last_status: number | null;
  deliveries_count: number;
}

export interface Affiliate {
  id: number;
  name: string;
  code: string;
  clicks: number;
  sales: number;
  revenue: string;
  is_active: boolean;
  created_at: string;
}
