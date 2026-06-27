import {
  Search, Ticket, Heart, LayoutDashboard, CalendarDays, Plus, ScanLine,
  Users, Tag, MessageSquare, ClipboardList, Settings, Edit, Shield, ChevronLeft, Clock,
  BarChart3, Armchair,
} from 'lucide-angular';

// attendee = logged-in && NOT organizer (pure attendees only)
// organizer = is_staff || is_superuser || profile.role === 'organizer'
// admin     = is_superuser
export type Role = 'public' | 'auth' | 'attendee' | 'organizer' | 'admin';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type LucideIcon = any;

export interface NavItem {
  label: string;
  icon: LucideIcon;
  route?: string;
  routeFn?: (eventId: string) => string;
  exact?: boolean;
  roles: Role[];
}

export interface NavSection {
  id: string;
  title?: string;
  roles: Role[];
  collapsible?: boolean;
  defaultOpen?: boolean;
  context?: 'event';
  items: NavItem[];
}

export const NAV: NavSection[] = [
  {
    id: 'main',
    roles: ['public'],
    items: [
      { label: 'Discover',    icon: Search,          route: '/',                exact: true, roles: ['public']    },
      // Anyone signed in can buy tickets for other people's events.
      { label: 'My Tickets',  icon: Ticket,          route: '/my-registrations',              roles: ['auth']      },
      { label: 'My Bookings', icon: Armchair,        route: '/my-bookings',                   roles: ['auth']      },
      { label: 'Favorites',   icon: Heart,           route: '/favorites',                      roles: ['auth']      },
    ],
  },
  {
    id: 'organize',
    title: 'Organize',
    roles: ['organizer'],
    items: [
      { label: 'Dashboard',    icon: LayoutDashboard, route: '/organizer/dashboard', roles: ['organizer'] },
      { label: 'My Events',    icon: CalendarDays,    route: '/my-events',           roles: ['organizer'] },
      { label: 'Create Event', icon: Plus,            route: '/create-event',        roles: ['organizer'] },
      { label: 'Scan Tickets', icon: ScanLine,        route: '/scan',                roles: ['organizer'] },
    ],
  },
  {
    id: 'event-context',
    title: '',
    roles: ['organizer'],
    context: 'event',
    collapsible: true,
    defaultOpen: true,
    items: [
      { label: 'Attendees',      icon: Users,         routeFn: id => `/organizer/events/${id}/attendees`,    roles: ['organizer'] },
      { label: 'Analytics',      icon: BarChart3,     routeFn: id => `/organizer/events/${id}/analytics`,    roles: ['organizer'] },
      { label: 'Tickets',        icon: Ticket,        routeFn: id => `/organizer/events/${id}/ticket-types`, roles: ['organizer'] },
      { label: 'Promo Codes',    icon: Tag,           routeFn: id => `/organizer/events/${id}/promo-codes`,  roles: ['organizer'] },
      { label: 'Questions',      icon: MessageSquare, routeFn: id => `/organizer/events/${id}/questions`,    roles: ['organizer'] },
      { label: 'Check-in Lists', icon: ClipboardList, routeFn: id => `/organizer/events/${id}/checkin-lists`,roles: ['organizer'] },
      { label: 'Waitlist',       icon: Clock,         routeFn: id => `/organizer/events/${id}/waitlist`,     roles: ['organizer'] },
      { label: 'Settings',       icon: Settings,      routeFn: id => `/organizer/events/${id}/settings`,     roles: ['organizer'] },
      { label: 'Edit Event',     icon: Edit,          routeFn: id => `/edit-event/${id}`,                    roles: ['organizer'] },
      { label: 'All Events',     icon: ChevronLeft,   route:   '/organizer/dashboard',                       roles: ['organizer'] },
    ],
  },
  {
    id: 'admin',
    title: 'Admin',
    roles: ['admin'],
    items: [
      { label: 'Moderation', icon: Shield, route: '/admin/moderation', roles: ['admin'] },
    ],
  },
];
