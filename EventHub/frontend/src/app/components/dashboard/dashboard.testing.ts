import type { EventAnalytics } from '../../services/event.service';
import type {
  ActivityItem,
  DashboardSummary,
  OrganizerEvent,
  OrganizerEventPage,
  OrganizerEventStats,
  RecentReview,
  ReviewsSummary,
  SalesChart,
  SalesRevenueSeries,
  TodayBlock,
  TodayEvent,
} from '../../services/organizer-dashboard.service';

/** Test factories for the dashboard specs (plain API payloads, no mocks). */
export function stats(overrides: Partial<OrganizerEventStats> = {}): OrganizerEventStats {
  return {
    tickets_sold: 3,
    checked_in: 1,
    checkin_rate_pct: 33.3,
    capacity: 100,
    sold_through_pct: 3,
    pending: 2,
    net_revenue: '45000.00',
    currency: 'KZT',
    ...overrides,
  };
}

export function organizerEvent(
  id: number,
  overrides: Partial<Omit<OrganizerEvent, 'stats'>> & { stats?: Partial<OrganizerEventStats> } = {},
): OrganizerEvent {
  const { stats: statsOverrides, ...rest } = overrides;
  return {
    id,
    title: `Event ${id}`,
    description: '',
    organizer: { id: 1, username: 'org', first_name: '', last_name: '' },
    category: { id: 1, name: 'Music', description: '', icon: 'music' },
    date: '2026-12-11T19:00:00Z',
    end_date: null,
    location: 'Almaty',
    address: '',
    image: null,
    price: '5000.00',
    max_participants: 100,
    status: 'published',
    is_online: false,
    online_link: '',
    available_spots: 97,
    is_free: false,
    has_ticket_types: false,
    price_from: '5000.00',
    ticket_types: [],
    tax_percent: '0.00',
    service_fee_percent: '0.00',
    fees_passed_to_buyer: false,
    currency: 'KZT',
    refundable: true,
    registered_count: 3,
    created_at: '2026-11-01T10:00:00Z',
    seo_title: '',
    seo_description: '',
    is_owner: true,
    ...rest,
    stats: stats(statsOverrides),
  };
}

export function eventPage(
  results: OrganizerEvent[],
  count = results.length,
  next: string | null = null,
): OrganizerEventPage {
  return { count, next, previous: null, results };
}

export function summary(overrides: Partial<DashboardSummary> = {}): DashboardSummary {
  return {
    tabs: { upcoming: 15, past: 2, drafts: 1, inactive: 0 },
    pending_approval: 0,
    upcoming_next_7_days: 0,
    tickets_sold: 9,
    checked_in: 3,
    checkin_rate_pct: 33.3,
    revenue: [{ currency: 'KZT', net_revenue: '124000.00' }],
    sales_last_7_days: 0,
    sales_previous_7_days: 0,
    ...overrides,
  };
}

export function activityItem(
  type: ActivityItem['type'],
  id: number,
  overrides: Partial<ActivityItem> = {},
): ActivityItem {
  return {
    id: `${type}:${id}`,
    type,
    occurred_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    event_id: 13,
    event_title: 'Stand-up Almaty',
    attendee_name: 'Dias A.',
    quantity: 1,
    amount: null,
    currency: null,
    ...overrides,
  };
}

/** `count` consecutive dates from `start` (YYYY-MM-DD). */
export function dates(start: string, count: number): string[] {
  const first = new Date(`${start}T00:00:00Z`).getTime();
  return Array.from({ length: count }, (_, i) =>
    new Date(first + i * 86_400_000).toISOString().slice(0, 10),
  );
}

/** A revenue series: one amount per day, from `start`. */
export function revenueSeries(
  currency: string,
  start: string,
  amounts: number[],
): SalesRevenueSeries {
  return {
    currency,
    days: dates(start, amounts.length).map((date, i) => ({
      date,
      net_revenue: amounts[i].toFixed(2),
    })),
  };
}

/** A week of sales: 12 tickets, 120 000 KZT, no markers. */
export function salesChart(overrides: Partial<SalesChart> = {}): SalesChart {
  const tickets = [0, 2, 0, 5, 1, 0, 4];
  return {
    time_zone: 'Asia/Almaty',
    start: '2026-11-15',
    end: '2026-11-21',
    days: dates('2026-11-15', tickets.length).map((date, i) => ({ date, tickets: tickets[i] })),
    revenue: [revenueSeries('KZT', '2026-11-15', [0, 20000, 0, 50000, 10000, 0, 40000])],
    markers: [],
    ...overrides,
  };
}

/** A range of `count` days with no sale at all. */
export function emptySales(count = 30): SalesChart {
  const days = dates('2026-10-23', count);
  return {
    time_zone: 'Asia/Almaty',
    start: days[0],
    end: days[count - 1],
    days: days.map((date) => ({ date, tickets: 0 })),
    revenue: [],
    markers: [],
  };
}

export function todayEvent(
  id: number,
  overrides: Partial<Omit<TodayEvent, 'stats'>> & { stats?: Partial<TodayEvent['stats']> } = {},
): TodayEvent {
  const { stats: statsOverrides, ...rest } = overrides;
  return {
    id,
    title: `Today ${id}`,
    date: new Date(Date.now() + 3 * 3_600_000 + 5 * 60_000).toISOString(),
    end_date: null,
    location: 'Almaty, Abay Ave 1',
    status: 'published',
    is_owner: true,
    in_progress: false,
    ...rest,
    stats: { tickets_sold: 3, checked_in: 1, capacity: 120, ...statsOverrides },
  };
}

export function todayBlock(results: TodayEvent[], more = 0): TodayBlock {
  return { results, more };
}

export function recentReview(index: number, overrides: Partial<RecentReview> = {}): RecentReview {
  return {
    event_id: 13,
    event_title: 'Stand-up Almaty',
    rating: 5,
    comment: `Great evening ${index}`,
    created_at: new Date(Date.now() - 2 * 3_600_000).toISOString(),
    author: 'Dias A.',
    ...overrides,
  };
}

/** 12 reviews, 4.42 on average. */
export function reviewsSummary(overrides: Partial<ReviewsSummary> = {}): ReviewsSummary {
  return {
    count: 12,
    average: 4.42,
    distribution: { 1: 0, 2: 1, 3: 1, 4: 2, 5: 8 },
    recent: [recentReview(1), recentReview(2, { rating: 4, author: 'Aigerim K.' })],
    ...overrides,
  };
}

export function eventAnalytics(overrides: Partial<EventAnalytics> = {}): EventAnalytics {
  return {
    currency: 'KZT',
    kpis: {
      net_revenue: 90000,
      gross_revenue: 90000,
      refunded: 0,
      tickets_sold: 9,
      paid_orders: 9,
      avg_order_value: 10000,
      capacity: 100,
      sold_through_pct: 9,
      checked_in: 2,
      checkin_rate_pct: 22.2,
      pending: 0,
      group_bookings: 0,
      group_seats: 0,
    },
    timeline: [],
    by_ticket_type: [
      { name: 'Standard', count: 6, revenue: 60000, quantity: 10, remaining: 4 },
      { name: 'General', count: 3, revenue: 30000, quantity: null, remaining: null },
    ],
    by_affiliate: [],
    ...overrides,
  };
}
