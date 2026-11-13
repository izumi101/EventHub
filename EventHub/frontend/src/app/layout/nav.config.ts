import {
  Search,
  Ticket,
  Heart,
  LayoutDashboard,
  CalendarDays,
  Plus,
  ScanLine,
  Users,
  Tag,
  MessageSquare,
  ClipboardList,
  Settings,
  SquarePen,
  Shield,
  ChevronLeft,
  Clock,
  ChartColumn,
  Armchair,
  type LucideIconData,
} from 'lucide-angular';

// attendee = logged-in && NOT organizer (pure attendees only)
// organizer = is_staff || is_superuser || profile.role === 'organizer'
// admin     = is_superuser
export type Role = 'public' | 'auth' | 'attendee' | 'organizer' | 'admin';

export type LucideIcon = LucideIconData;

export interface NavItem {
  /** Translation key of the item label. */
  labelKey: string;
  icon: LucideIcon;
  route?: string;
  routeFn?: (eventId: string) => string;
  exact?: boolean;
  roles: Role[];
}

export interface NavSection {
  id: string;
  /** Translation key of the section heading. */
  titleKey?: string;
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
      { labelKey: 'nav.discover', icon: Search, route: '/', exact: true, roles: ['public'] },
      // Anyone signed in can buy tickets for other people's events.
      { labelKey: 'nav.myTickets', icon: Ticket, route: '/my-registrations', roles: ['auth'] },
      { labelKey: 'nav.myBookings', icon: Armchair, route: '/my-bookings', roles: ['auth'] },
      { labelKey: 'nav.favorites', icon: Heart, route: '/favorites', roles: ['auth'] },
    ],
  },
  {
    id: 'organize',
    titleKey: 'nav.sectionOrganize',
    roles: ['organizer'],
    items: [
      {
        labelKey: 'nav.dashboard',
        icon: LayoutDashboard,
        route: '/organizer/dashboard',
        roles: ['organizer'],
      },
      { labelKey: 'nav.myEvents', icon: CalendarDays, route: '/my-events', roles: ['organizer'] },
      { labelKey: 'nav.createEvent', icon: Plus, route: '/create-event', roles: ['organizer'] },
      { labelKey: 'nav.scanTickets', icon: ScanLine, route: '/scan', roles: ['organizer'] },
    ],
  },
  {
    id: 'event-context',
    titleKey: 'nav.event',
    roles: ['organizer'],
    context: 'event',
    collapsible: true,
    defaultOpen: true,
    items: [
      {
        labelKey: 'nav.attendees',
        icon: Users,
        routeFn: (id) => `/organizer/events/${id}/attendees`,
        roles: ['organizer'],
      },
      {
        labelKey: 'nav.analytics',
        icon: ChartColumn,
        routeFn: (id) => `/organizer/events/${id}/analytics`,
        roles: ['organizer'],
      },
      {
        labelKey: 'nav.tickets',
        icon: Ticket,
        routeFn: (id) => `/organizer/events/${id}/ticket-types`,
        roles: ['organizer'],
      },
      {
        labelKey: 'nav.promoCodes',
        icon: Tag,
        routeFn: (id) => `/organizer/events/${id}/promo-codes`,
        roles: ['organizer'],
      },
      {
        labelKey: 'nav.questions',
        icon: MessageSquare,
        routeFn: (id) => `/organizer/events/${id}/questions`,
        roles: ['organizer'],
      },
      {
        labelKey: 'nav.checkinLists',
        icon: ClipboardList,
        routeFn: (id) => `/organizer/events/${id}/checkin-lists`,
        roles: ['organizer'],
      },
      {
        labelKey: 'nav.waitlist',
        icon: Clock,
        routeFn: (id) => `/organizer/events/${id}/waitlist`,
        roles: ['organizer'],
      },
      {
        labelKey: 'nav.settings',
        icon: Settings,
        routeFn: (id) => `/organizer/events/${id}/settings`,
        roles: ['organizer'],
      },
      {
        labelKey: 'nav.editEvent',
        icon: SquarePen,
        routeFn: (id) => `/edit-event/${id}`,
        roles: ['organizer'],
      },
      {
        labelKey: 'nav.allEvents',
        icon: ChevronLeft,
        route: '/organizer/dashboard',
        roles: ['organizer'],
      },
    ],
  },
  {
    id: 'admin',
    titleKey: 'nav.sectionAdmin',
    roles: ['admin'],
    items: [
      { labelKey: 'nav.moderation', icon: Shield, route: '/admin/moderation', roles: ['admin'] },
    ],
  },
];
