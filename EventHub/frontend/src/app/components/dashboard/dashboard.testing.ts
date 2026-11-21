import type {
  ActivityItem,
  DashboardSummary,
  OrganizerEvent,
  OrganizerEventPage,
  OrganizerEventStats,
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
