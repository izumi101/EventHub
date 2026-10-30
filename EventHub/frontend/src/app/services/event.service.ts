import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  type AcceptsNumericDecimals,
  Category,
  CheckInAttendee,
  CheckInList,
  CheckInLogEntry,
  CheckInResponse,
  Event,
  EventActionResponse,
  EventAttendee,
  EventFormPayload,
  EventStatsResponse,
  PaginatedResponse,
  Registration,
  SeatMap,
} from '../models/models';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import type { components } from '../api/openapi';

@Injectable({ providedIn: 'root' })
export class EventService {
  private http = inject(HttpClient);

  private apiUrl = environment.apiUrl;

  getCategories(): Observable<Category[]> {
    return this.http
      .get<Category[] | PaginatedResponse<Category>>(`${this.apiUrl}/categories/`)
      .pipe(map((response) => (Array.isArray(response) ? response : response.results)));
  }

  getEvents(params?: {
    category?: number;
    search?: string;
    q?: string; // semantic search query
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
    return this.http.get<PaginatedResponse<Event>>(`${this.apiUrl}/events/`, {
      params: httpParams,
    });
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

  registerForEvent(
    eventId: number,
    payload: RegisterPayload | string = {},
  ): Observable<Registration> {
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
    return this.http.get<PaginatedResponse<Registration>>(`${this.apiUrl}/my-registrations/`, {
      params: httpParams,
    });
  }

  getSeatMap(eventId: number): Observable<SeatMap> {
    return this.http.get<SeatMap>(`${this.apiUrl}/events/${eventId}/seat_map/`);
  }

  getRecommendations(): Observable<PaginatedResponse<Event>> {
    return this.http.get<PaginatedResponse<Event>>(`${this.apiUrl}/recommendations/`);
  }

  getEventPricing(eventId: number): Observable<DynamicPrice> {
    return this.http.get<DynamicPrice>(`${this.apiUrl}/events/${eventId}/pricing/`);
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
  getEventRegistrations(eventId: number): Observable<EventAttendee[]> {
    return this.http.get<EventAttendee[]>(`${this.apiUrl}/events/${eventId}/registrations/`);
  }

  // ── Favorites ──
  getFavorites(): Observable<Favorite[]> {
    return this.http.get<ListResponse<Favorite>>(`${this.apiUrl}/favorites/`).pipe(map(listItems));
  }
  toggleFavorite(eventId: number): Observable<{ favorited: boolean }> {
    return this.http.post<{ favorited: boolean }>(`${this.apiUrl}/favorites/${eventId}/`, {});
  }
  getFavoriteStatus(eventId: number): Observable<{ favorited: boolean }> {
    return this.http.get<{ favorited: boolean }>(`${this.apiUrl}/favorites/${eventId}/`);
  }

  // ── Reviews ──
  getEventReviews(eventId: number): Observable<Review[]> {
    return this.http
      .get<ListResponse<Review>>(`${this.apiUrl}/events/${eventId}/reviews/`)
      .pipe(map(listItems));
  }
  createReview(eventId: number, rating: number, comment: string): Observable<ReviewCreate> {
    return this.http.post<ReviewCreate>(`${this.apiUrl}/events/${eventId}/reviews/`, {
      rating,
      comment,
    });
  }

  // ── Notifications ──
  getNotifications(): Observable<UserNotification[]> {
    return this.http
      .get<ListResponse<UserNotification>>(`${this.apiUrl}/notifications/`)
      .pipe(map(listItems));
  }
  markNotificationRead(id?: number): Observable<Ok> {
    const url = id
      ? `${this.apiUrl}/notifications/${id}/read/`
      : `${this.apiUrl}/notifications/read/`;
    return this.http.post<Ok>(url, {});
  }

  // ── Admin Dashboard ──
  getAdminDashboard(): Observable<AdminDashboard> {
    return this.http.get<AdminDashboard>(`${this.apiUrl}/admin-dashboard/`);
  }

  // ── Promo codes (public validate) ──
  validatePromo(
    eventId: number,
    code: string,
    ctx?: { ticket_type_id?: number; seat_id?: number },
  ): Observable<PromoQuote> {
    return this.http.post<PromoQuote>(`${this.apiUrl}/events/${eventId}/validate-promo/`, {
      code,
      ...(ctx ?? {}),
    });
  }

  // ── Promo codes (organizer CRUD) ──
  getPromoCodes(eventId: number): Observable<PromoCode[]> {
    return this.http
      .get<ListResponse<PromoCode>>(`${this.apiUrl}/events/${eventId}/promo-codes/`)
      .pipe(map(listItems));
  }
  createPromoCode(eventId: number, data: PromoCodeInput): Observable<PromoCode> {
    return this.http.post<PromoCode>(`${this.apiUrl}/events/${eventId}/promo-codes/`, data);
  }
  updatePromoCode(id: number, data: Partial<PromoCode>): Observable<PromoCode> {
    return this.http.patch<PromoCode>(`${this.apiUrl}/promo-codes/${id}/`, data);
  }
  deletePromoCode(id: number): Observable<null> {
    return this.http.delete<null>(`${this.apiUrl}/promo-codes/${id}/`);
  }

  // ── Event clone / lifecycle ──
  cloneEvent(eventId: number): Observable<Event> {
    return this.http.post<Event>(`${this.apiUrl}/events/${eventId}/clone/`, {});
  }
  submitEvent(eventId: number): Observable<EventActionResponse> {
    return this.http.post<EventActionResponse>(`${this.apiUrl}/events/${eventId}/submit/`, {});
  }
  cancelEvent(
    eventId: number,
  ): Observable<EventActionResponse & { notified?: number; refunded?: number }> {
    return this.http.post<EventActionResponse & { notified?: number; refunded?: number }>(
      `${this.apiUrl}/events/${eventId}/cancel-event/`,
      {},
    );
  }

  // ── Seat map management (organizer) ──
  createSeatMap(
    eventId: number,
    data: {
      rows: number;
      cols: number;
      vip_rows?: number;
      premium_rows?: number;
      sync_capacity?: boolean;
    },
  ): Observable<SeatMap> {
    return this.http.post<SeatMap>(`${this.apiUrl}/events/${eventId}/seat-map/create/`, data);
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
    return this.http
      .get<ListResponse<TicketType>>(`${this.apiUrl}/events/${eventId}/ticket-types/`)
      .pipe(map(listItems));
  }
  createTicketType(eventId: number, data: TicketTypeInput): Observable<TicketType> {
    return this.http.post<TicketType>(`${this.apiUrl}/events/${eventId}/ticket-types/`, data);
  }
  updateTicketType(id: number, data: Partial<TicketType>): Observable<TicketType> {
    return this.http.patch<TicketType>(`${this.apiUrl}/ticket-types/${id}/`, data);
  }
  deleteTicketType(id: number): Observable<null> {
    return this.http.delete<null>(`${this.apiUrl}/ticket-types/${id}/`);
  }

  // ── Custom questions ──
  getEventQuestions(eventId: number): Observable<EventQuestion[]> {
    return this.http
      .get<ListResponse<EventQuestion>>(`${this.apiUrl}/events/${eventId}/questions/`)
      .pipe(map(listItems));
  }
  createQuestion(eventId: number, data: Partial<EventQuestion>): Observable<EventQuestion> {
    return this.http.post<EventQuestion>(`${this.apiUrl}/events/${eventId}/questions/`, data);
  }
  updateQuestion(id: number, data: Partial<EventQuestion>): Observable<EventQuestion> {
    return this.http.patch<EventQuestion>(`${this.apiUrl}/questions/${id}/`, data);
  }
  deleteQuestion(id: number): Observable<null> {
    return this.http.delete<null>(`${this.apiUrl}/questions/${id}/`);
  }

  // ── Waitlist ──
  getWaitlistStatus(eventId: number): Observable<WaitlistStatus> {
    return this.http.get<WaitlistStatus>(`${this.apiUrl}/events/${eventId}/waitlist/`);
  }
  joinWaitlist(eventId: number): Observable<WaitlistStatus> {
    return this.http.post<WaitlistStatus>(`${this.apiUrl}/events/${eventId}/waitlist/`, {});
  }
  leaveWaitlist(eventId: number): Observable<WaitlistStatus> {
    return this.http.delete<WaitlistStatus>(`${this.apiUrl}/events/${eventId}/waitlist/`);
  }
  getEventWaitlist(eventId: number): Observable<WaitlistEntry[]> {
    return this.http
      .get<ListResponse<WaitlistEntry>>(`${this.apiUrl}/events/${eventId}/waitlist-entries/`)
      .pipe(map(listItems));
  }

  // ── Attendee CSV export (returns a Blob to trigger a download) ──
  exportAttendeesUrl(eventId: number): string {
    return `${this.apiUrl}/events/${eventId}/export-attendees/`;
  }
  exportAttendees(eventId: number): Observable<Blob> {
    return this.http.get(this.exportAttendeesUrl(eventId), { responseType: 'blob' });
  }

  // ── Refunds & offline payments (organizer) ──
  refundRegistration(
    registrationId: number,
    body: { amount?: string; reason?: string },
  ): Observable<RefundResult> {
    return this.http.post<RefundResult>(`${this.apiUrl}/payments/refund/${registrationId}/`, body);
  }
  markOfflinePaid(registrationId: number, amount?: string): Observable<OfflinePaymentResult> {
    return this.http.post<OfflinePaymentResult>(
      `${this.apiUrl}/payments/mark-offline/${registrationId}/`,
      {
        amount,
      },
    );
  }

  // ── Refund requests ──
  requestRefund(eventId: number, reason: string): Observable<RefundRequestCreated> {
    return this.http.post<RefundRequestCreated>(
      `${this.apiUrl}/events/${eventId}/request-refund/`,
      { reason },
    );
  }
  getRefundRequests(eventId: number): Observable<RefundRequest[]> {
    return this.http
      .get<ListResponse<RefundRequest>>(`${this.apiUrl}/events/${eventId}/refund-requests/`)
      .pipe(map(listItems));
  }
  resolveRefundRequest(id: number, approve: boolean, note = ''): Observable<RefundResolution> {
    return this.http.post<RefundResolution>(`${this.apiUrl}/refund-requests/${id}/resolve/`, {
      approve,
      note,
    });
  }

  // ── Team / roles ──
  getStaff(eventId: number): Observable<EventStaff[]> {
    return this.http
      .get<ListResponse<EventStaff>>(`${this.apiUrl}/events/${eventId}/staff/`)
      .pipe(map(listItems));
  }
  addStaff(eventId: number, invite_username: string, role: string): Observable<EventStaff> {
    return this.http.post<EventStaff>(`${this.apiUrl}/events/${eventId}/staff/`, {
      invite_username,
      role,
    });
  }
  removeStaff(id: number): Observable<null> {
    return this.http.delete<null>(`${this.apiUrl}/staff/${id}/`);
  }

  // ── Webhooks ──
  getWebhooks(eventId: number): Observable<Webhook[]> {
    return this.http
      .get<ListResponse<Webhook>>(`${this.apiUrl}/events/${eventId}/webhooks/`)
      .pipe(map(listItems));
  }
  createWebhook(eventId: number, data: Partial<Webhook>): Observable<Webhook> {
    return this.http.post<Webhook>(`${this.apiUrl}/events/${eventId}/webhooks/`, data);
  }
  updateWebhook(id: number, data: Partial<Webhook>): Observable<Webhook> {
    return this.http.patch<Webhook>(`${this.apiUrl}/webhooks/${id}/`, data);
  }
  deleteWebhook(id: number): Observable<null> {
    return this.http.delete<null>(`${this.apiUrl}/webhooks/${id}/`);
  }

  // ── Affiliates ──
  getAffiliates(eventId: number): Observable<Affiliate[]> {
    return this.http
      .get<ListResponse<Affiliate>>(`${this.apiUrl}/events/${eventId}/affiliates/`)
      .pipe(map(listItems));
  }
  createAffiliate(eventId: number, data: Partial<Affiliate>): Observable<Affiliate> {
    return this.http.post<Affiliate>(`${this.apiUrl}/events/${eventId}/affiliates/`, data);
  }
  deleteAffiliate(id: number): Observable<null> {
    return this.http.delete<null>(`${this.apiUrl}/affiliates/${id}/`);
  }
  trackAffiliateClick(eventId: number, code: string): Observable<Ok> {
    return this.http.post<Ok>(`${this.apiUrl}/events/${eventId}/affiliate-click/`, { code });
  }

  // ── Broadcast message to attendees ──
  broadcast(
    eventId: number,
    body: { subject: string; body: string; audience: string },
  ): Observable<BroadcastResult> {
    return this.http.post<BroadcastResult>(`${this.apiUrl}/events/${eventId}/broadcast/`, body);
  }

  // ── Invoice (fetched with the auth header, opened as a blob — no JWT in the URL) ──
  getInvoiceBlob(registrationId: number): Observable<Blob> {
    return this.http.get(`${this.apiUrl}/payments/invoice/${registrationId}/`, {
      responseType: 'blob',
    });
  }

  // ── Check-in Lists ──
  getCheckInLists(eventId: number): Observable<CheckInList[]> {
    return this.http
      .get<ListResponse<CheckInList>>(`${this.apiUrl}/events/${eventId}/checkin-lists/`)
      .pipe(map(listItems));
  }
  createCheckInList(
    eventId: number,
    data: { name: string; description?: string; color?: string },
  ): Observable<CheckInList> {
    return this.http.post<CheckInList>(`${this.apiUrl}/events/${eventId}/checkin-lists/`, data);
  }
  updateCheckInList(
    listId: number,
    data: Partial<{ name: string; description: string; color: string; is_default: boolean }>,
  ): Observable<CheckInList> {
    return this.http.patch<CheckInList>(`${this.apiUrl}/checkin-lists/${listId}/`, data);
  }
  deleteCheckInList(listId: number): Observable<null> {
    return this.http.delete<null>(`${this.apiUrl}/checkin-lists/${listId}/`);
  }
  getCheckInListAttendees(listId: number): Observable<CheckInAttendee[]> {
    return this.http
      .get<ListResponse<CheckInAttendee>>(`${this.apiUrl}/checkin-lists/${listId}/attendees/`)
      .pipe(map(listItems));
  }
  checkInByList(
    listId: number,
    ticketUuid: string,
    action: 'check_in' | 'undo' = 'check_in',
    note = '',
  ): Observable<CheckInScanResult> {
    return this.http.post<CheckInScanResult>(`${this.apiUrl}/checkin-lists/${listId}/check-in/`, {
      ticket_uuid: ticketUuid,
      action,
      note,
    });
  }
  getCheckInLogs(eventId: number): Observable<CheckInLogEntry[]> {
    return this.http
      .get<ListResponse<CheckInLogEntry>>(`${this.apiUrl}/events/${eventId}/checkin-logs/`)
      .pipe(map(listItems));
  }
}

// API shapes come from the backend's OpenAPI schema (see models/models.ts).
type Schemas = components['schemas'];

export type QueueStatus = Schemas['QueueStatus'];
export type EventAnalytics = Schemas['EventAnalytics'];
export type BroadcastResult = Schemas['BroadcastResult'];
export type RefundRequest = Schemas['RefundRequest'];
export type PriceBreakdown = Schemas['PriceBreakdown'];
export type PromoQuote = Schemas['PromoQuote'];
export type PromoCode = Schemas['PromoCode'];
export type DiscountType = Schemas['DiscountTypeEnum'];
export type PromoCodeInput = AcceptsNumericDecimals<Schemas['PromoCodeRequest'], 'discount_value'>;
export type TicketKind = Schemas['TicketKindEnum'];
export type SaleState = Schemas['SaleStateEnum'];
export type TicketType = Schemas['TicketType'];
export type TicketTypeInput = AcceptsNumericDecimals<Schemas['TicketTypeRequest'], 'price'>;
export type QuestionType = Schemas['QuestionTypeEnum'];
export type EventQuestion = Schemas['EventQuestion'];
export type WaitlistStatus = Schemas['WaitlistStatus'];
export type EventStaff = Schemas['EventStaff'];
export type WebhookTrigger = Schemas['WebhookTriggerEnum'];
export type Webhook = Schemas['Webhook'];
export type Affiliate = Schemas['Affiliate'];
/** POST /events/{id}/register/. The donation is sent as a JSON number, which
 *  DRF's DecimalField accepts just like the string the schema declares. */
export type RegisterPayload = Omit<Schemas['RegisterRequestRequest'], 'donation_amount'> & {
  donation_amount?: string | number | null;
};
export type DynamicPrice = Schemas['DynamicPrice'];
export type Favorite = Schemas['Favorite'];
export type Review = Schemas['Review'];
export type ReviewCreate = Schemas['ReviewCreate'];
export type UserNotification = Schemas['Notification'];
export type AdminDashboard = Schemas['AdminDashboard'];
export type WaitlistEntry = Schemas['WaitlistEntry'];
export type CheckInScanResult = Schemas['CheckInScanResult'];
export type RefundResult = Schemas['RefundResult'];
export type OfflinePaymentResult = Schemas['OfflinePaymentResult'];
export type RefundRequestCreated = Schemas['RefundRequestCreated'];
export type RefundResolution = Schemas['RefundResolution'];
type Ok = Schemas['Ok'];

/** List endpoints answer with a DRF page or, when unpaginated, a bare array. */
type ListResponse<T> = T[] | { results?: T[] };

function listItems<T>(response: ListResponse<T>): T[] {
  return Array.isArray(response) ? response : (response.results ?? []);
}
