import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import type { components, operations } from '../api/openapi';

/**
 * The organizer dashboard API (docs/ORGANIZER_DASHBOARD.md): totals over every
 * managed event, a paged/filtered/sorted event list with its numbers, and the
 * real activity feed. Types come from the backend's OpenAPI schema.
 */
type Schemas = components['schemas'];
type EventsQuery = NonNullable<operations['organizer_events_list']['parameters']['query']>;
type SalesQuery = NonNullable<operations['organizer_sales_retrieve']['parameters']['query']>;

export type DashboardSummary = Schemas['DashboardSummary'];
export type DashboardTabs = Schemas['DashboardTabs'];
export type DashboardRevenue = Schemas['DashboardRevenue'];
export type OrganizerEvent = Schemas['OrganizerEvent'];
export type OrganizerEventStats = Schemas['OrganizerEventStats'];
/** One page of the list (the standard DRF page: count, next, previous, results). */
export type OrganizerEventPage = Schemas['PaginatedOrganizerEventList'];
export type ActivityFeed = Schemas['ActivityFeed'];
export type ActivityItem = Schemas['ActivityItem'];
export type ActivityType = Schemas['ActivityItemTypeEnum'];
export type DashboardTab = NonNullable<EventsQuery['tab']>;
export type DashboardOrdering = NonNullable<EventsQuery['ordering']>;
export type SalesRange = NonNullable<SalesQuery['range']>;
export type SalesChart = Schemas['Sales'];
export type SalesDay = Schemas['SalesDay'];
export type SalesRevenueSeries = Schemas['SalesRevenueSeries'];
export type SalesRevenueDay = Schemas['SalesRevenueDay'];
export type SalesMarker = Schemas['SalesMarker'];
export type TodayBlock = Schemas['Today'];
export type TodayEvent = Schemas['TodayEvent'];
export type ReviewsSummary = Schemas['ReviewsSummary'];
export type RecentReview = Schemas['RecentReview'];

/** The windows of the sales chart, in the order the toggle shows them. */
export const SALES_RANGES: readonly SalesRange[] = ['7d', '30d', '90d'];
/** What the server draws when `range` is omitted. */
export const DEFAULT_SALES_RANGE: SalesRange = '30d';

export const DASHBOARD_TABS: readonly DashboardTab[] = ['upcoming', 'past', 'drafts', 'inactive'];

/** Every ordering the list accepts, in the order the sort menu shows them. */
export const DASHBOARD_ORDERINGS: readonly DashboardOrdering[] = [
  'date',
  '-date',
  '-tickets_sold',
  '-checkin_rate',
  '-sold_through',
];

/** What the server sorts by when `ordering` is omitted (upcoming: soonest first). */
export const DEFAULT_ORDERING: Readonly<Record<DashboardTab, DashboardOrdering>> = {
  upcoming: 'date',
  past: '-date',
  drafts: '-date',
  inactive: '-date',
};

export const DASHBOARD_PAGE_SIZE = 20;
export const SEARCH_MAX_LENGTH = 100;

export interface DashboardEventsParams {
  tab?: DashboardTab;
  search?: string;
  ordering?: DashboardOrdering;
  page?: number;
  pageSize?: number;
}

export interface DashboardActivityParams {
  limit?: number;
  cursor?: string | null;
}

@Injectable({ providedIn: 'root' })
export class OrganizerDashboardService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = `${environment.apiUrl}/organizer`;

  getSummary(): Observable<DashboardSummary> {
    return this.http.get<DashboardSummary>(`${this.apiUrl}/dashboard/`);
  }

  /** Empty parameters are left out, so the server's defaults apply. */
  getEvents(params: DashboardEventsParams = {}): Observable<OrganizerEventPage> {
    let httpParams = new HttpParams();
    const search = params.search?.trim().slice(0, SEARCH_MAX_LENGTH);
    if (params.tab) httpParams = httpParams.set('tab', params.tab);
    if (search) httpParams = httpParams.set('search', search);
    if (params.ordering) httpParams = httpParams.set('ordering', params.ordering);
    if (params.page) httpParams = httpParams.set('page', params.page);
    if (params.pageSize) httpParams = httpParams.set('page_size', params.pageSize);
    return this.http.get<OrganizerEventPage>(`${this.apiUrl}/events/`, { params: httpParams });
  }

  getActivity(params: DashboardActivityParams = {}): Observable<ActivityFeed> {
    let httpParams = new HttpParams();
    if (params.limit) httpParams = httpParams.set('limit', params.limit);
    if (params.cursor) httpParams = httpParams.set('cursor', params.cursor);
    return this.http.get<ActivityFeed>(`${this.apiUrl}/activity/`, { params: httpParams });
  }

  /** Tickets and net revenue per day (zero-filled), revenue per currency, and event markers. */
  getSales(range: SalesRange = DEFAULT_SALES_RANGE): Observable<SalesChart> {
    const params = new HttpParams().set('range', range);
    return this.http.get<SalesChart>(`${this.apiUrl}/sales/`, { params });
  }

  /** Managed events in progress or starting within 7 days (at most 10) and how many more there are. */
  getToday(): Observable<TodayBlock> {
    return this.http.get<TodayBlock>(`${this.apiUrl}/today/`);
  }

  /** Rating summary and the 5 latest reviews over every managed event. */
  getReviews(): Observable<ReviewsSummary> {
    return this.http.get<ReviewsSummary>(`${this.apiUrl}/reviews/`);
  }
}
