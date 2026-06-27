export interface UserProfile {
  bio: string;
  phone: string;
  avatar: string | null;
  location: string;
  website: string;
  role?: 'attendee' | 'organizer';
}

export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  profile: UserProfile;
  is_superuser?: boolean;
  is_staff?: boolean;
}

export interface AuthResponse {
  user: User;
  tokens: {
    refresh: string;
    access: string;
  };
}

export interface RefreshTokenResponse {
  access: string;
}

export interface ApiMessageResponse {
  message: string;
}

export interface Category {
  id: number;
  name: string;
  description: string;
  icon: string;
  event_count: number;
}

export interface Event {
  id: number;
  title: string;
  description: string;
  organizer: {
    id: number;
    username: string;
    first_name: string;
    last_name: string;
  };
  category: Category;
  date: string;
  end_date: string | null;
  location: string;
  address: string;
  image: string | null;
  price: string;
  max_participants: number;
  status: string;
  is_online: boolean;
  online_link: string;
  available_spots: number;
  is_free: boolean;
  has_ticket_types?: boolean;
  price_from?: string;
  ticket_types?: import('../services/event.service').TicketType[];
  tax_percent?: string;
  service_fee_percent?: string;
  fees_passed_to_buyer?: boolean;
  currency?: string;
  refundable?: boolean;
  registered_count: number;
  created_at: string;
  seo_title?: string;
  seo_description?: string;
}

export interface CheckInList {
  id: number;
  name: string;
  description: string;
  color: string;
  is_default: boolean;
  log_count: number;
  checked_in_count: number;
  created_at: string;
}

export interface CheckInAttendee {
  id: number;
  ticket_uuid: string;
  username: string;
  full_name: string;
  email: string;
  status: string;
  is_checked_in: boolean;
  checked_in_at: string | null;
  scanned_by: string | null;
}

export interface CheckInLogEntry {
  id: number;
  action: 'check_in' | 'undo';
  attendee: { id: number; username: string; full_name: string };
  scanned_by_username: string;
  note: string;
  created_at: string;
}

export interface EventFormPayload {
  title: string;
  description: string;
  category_id: number;
  date: string;
  end_date?: string | null;
  location: string;
  address?: string;
  image?: File | string | null;
  price?: string | number;
  max_participants?: number;
  status?: string;
  is_online?: boolean;
  online_link?: string;
}

export interface Registration {
  id: number;
  event: Event;
  username: string;
  email?: string;
  full_name?: string;
  status: string;
  registered_at: string;
  notes: string;
  ticket_uuid: string;
  is_checked_in: boolean;
  checked_in_at: string | null;
  seat?: { id: number; row: number; col: number; zone: string } | null;
  payment?: {
    amount: string;
    status: string;
    method: string;
    refunded_amount: string;
    net_amount: string;
    is_refundable: boolean;
  } | null;
  promo?: { code: string } | null;
  ticket_type?: { id: number; name: string; kind: string } | null;
  answers?: { label: string; answer: string; type: string }[];
  refund_request?: { status: 'pending' | 'approved' | 'rejected'; reason: string; organizer_note: string; created_at: string } | null;
}

export interface EventActionResponse extends ApiMessageResponse {
  status?: string;
}

export interface CheckInResponse extends ApiMessageResponse {
  status: string;
  attendee: string;
  event?: string;
  checked_in_at?: string;
}

export interface EventStatsResponse {
  total_registrations: number;
  checked_in: number;
  remaining: number;
  check_in_rate: number;
}

export interface CheckoutSessionResponse {
  checkout_url: string;
  session_id: string;
}

export interface PaymentVerificationResponse {
  status: string;
  event_title: string;
  amount: string;
}

export interface PasswordResetTokenResponse extends ApiMessageResponse {
  reset_token: string;
}

export interface RegistrationCodeResponse extends ApiMessageResponse {
  /** Present in dev when email is not configured — show it to the user. */
  dev_code?: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Seat {
  id: number;
  row: number;
  col: number;
  price_zone: 'standard' | 'vip' | 'premium';
  is_available: boolean;
  price?: string | null;
}

export interface ZonePrice {
  zone: string;
  multiplier: number;
  price: string;
}

export interface SeatMap {
  id: number;
  rows: number;
  cols: number;
  layout?: Record<string, any>;
  seats: Seat[];
  zone_prices?: ZonePrice[];
}
