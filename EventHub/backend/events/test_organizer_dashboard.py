"""Organizer dashboard API, clone and stats fix (docs/ORGANIZER_DASHBOARD.md)."""

import base64
import json
from datetime import timedelta
from decimal import Decimal
from itertools import chain
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from bookings.models import Booking, BookingSeat
from events import dashboard
from events.billing import event_currency
from events.models import (
    CheckInList,
    Event,
    EventQuestion,
    EventSeat,
    EventStaff,
    PromoCode,
    Registration,
    SeatMap,
    TicketType,
)
from events.test_regressions import Base
from mfa.testing import authenticate_with_recent_mfa
from payments.models import Payment, Refund

DASHBOARD = '/api/v1/organizer/dashboard/'
EVENTS = '/api/v1/organizer/events/'
ACTIVITY = '/api/v1/organizer/activity/'


class DashboardBase(Base):
    def setUp(self):
        super().setUp()
        self.event.delete()  # these tests build their own events
        self.now = timezone.now()
        self._users = 0

    # ── builders ──
    def login(self, user=None):
        authenticate_with_recent_mfa(self.client, user or self.organizer)

    def ev(self, title='E', days=3, **kw):
        kw.setdefault('date', timezone.now() + timedelta(days=days))
        return self.make_event(title=title, **kw)

    def new_user(self, **kw):
        self._users += 1
        return User.objects.create_user(f'buyer{self._users}', f'buyer{self._users}@example.com', 'x', **kw)

    def reg(self, event, status='confirmed', checked_in=False, at=None, user=None, checked_at=None):
        registration = Registration.objects.create(
            user=user or self.new_user(),
            event=event,
            status=status,
            is_checked_in=checked_in,
            checked_in_at=(checked_at or timezone.now()) if checked_in else None,
        )
        if at is not None:
            Registration.objects.filter(pk=registration.pk).update(registered_at=at)
            registration.refresh_from_db()
        return registration

    def pay(self, registration, amount, status='completed', refunded=0, currency='kzt'):
        return Payment.objects.create(
            registration=registration,
            amount=Decimal(str(amount)),
            currency=currency,
            status=status,
            refunded_amount=Decimal(str(refunded)),
        )

    def seat_map(self, event, count=12):
        seat_map = SeatMap.objects.create(event=event, rows=count, cols=1)
        return [
            EventSeat.objects.create(seat_map=seat_map, row=r, col=1, price_zone='standard')
            for r in range(1, count + 1)
        ]

    def booking(self, event, seats, status='confirmed', amount_paid=None, checked=0, at=None, owner=None, price=10):
        booking = Booking.objects.create(
            owner=owner or self.new_user(), event=event, status=status, amount_paid=amount_paid
        )
        for i, seat in enumerate(seats):
            BookingSeat.objects.create(
                booking=booking,
                seat=seat,
                price=price,
                is_checked_in=i < checked,
                checked_in_at=timezone.now() if i < checked else None,
            )
        if at is not None:
            Booking.objects.filter(pk=booking.pk).update(created_at=at)
        return booking

    def get(self, url, **params):
        return self.client.get(url, params)

    def titles(self, response):
        return [e['title'] for e in response.data['results']]


class PermissionTests(DashboardBase):
    def test_anonymous_gets_401(self):
        for url in (DASHBOARD, EVENTS, ACTIVITY):
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_attendee_gets_403(self):
        self.login(self.attendee)
        for url in (DASHBOARD, EVENTS, ACTIVITY):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_check_in_staff_only_gets_403(self):
        EventStaff.objects.create(event=self.ev(), user=self.attendee, role=EventStaff.ROLE_CHECK_IN)
        self.login(self.attendee)
        self.assertEqual(self.client.get(EVENTS).status_code, 403)

    def test_organizer_without_events_gets_zeros(self):
        self.login()
        summary = self.get(DASHBOARD).data
        self.assertEqual(summary['tabs'], {'upcoming': 0, 'past': 0, 'drafts': 0, 'inactive': 0})
        self.assertEqual(summary['revenue'], [])
        self.assertEqual(summary['checkin_rate_pct'], 0)
        self.assertEqual(self.get(EVENTS).data['count'], 0)
        self.assertEqual(self.get(ACTIVITY).data, {'results': [], 'next_cursor': None})

    def test_co_organizer_sees_co_organized_events_as_not_owner(self):
        mine = self.ev('Mine')
        theirs = self.make_event(title='Theirs', organizer=self.make_user('org2', role='organizer'), status='published')
        EventStaff.objects.create(event=theirs, user=self.attendee, role=EventStaff.ROLE_CO_ORGANIZER)

        self.login(self.attendee)  # an attendee account with a co-organizer seat
        response = self.get(EVENTS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.titles(response), ['Theirs'])
        self.assertFalse(response.data['results'][0]['is_owner'])
        self.assertEqual(self.get(DASHBOARD).data['tabs']['upcoming'], 1)

        self.login()
        response = self.get(EVENTS)
        self.assertEqual(self.titles(response), ['Mine'])
        self.assertTrue(response.data['results'][0]['is_owner'])
        self.assertNotIn(theirs.title, self.titles(response))
        self.assertEqual(mine.organizer_id, self.organizer.id)

    def test_other_organizers_events_never_leak(self):
        other_org = self.make_user('org2', role='organizer')
        foreign = self.make_event(title='Foreign', organizer=other_org, status='published')
        buyer = self.reg(foreign)
        self.pay(buyer, 500)
        self.ev('Mine')

        self.login()
        self.assertEqual(self.titles(self.get(EVENTS)), ['Mine'])
        summary = self.get(DASHBOARD).data
        self.assertEqual(summary['tickets_sold'], 0)
        self.assertEqual(summary['revenue'], [])
        self.assertEqual(self.get(ACTIVITY).data['results'], [])

    def test_superuser_dashboard_lists_only_own_events(self):
        admin = User.objects.create_superuser('root', 'root@example.com', 'x')
        self.ev('Not admin')
        authenticate_with_recent_mfa(self.client, admin)
        self.assertEqual(self.get(EVENTS).data['count'], 0)
        self.assertEqual(self.get(DASHBOARD).status_code, 200)


class TabTests(DashboardBase):
    def setUp(self):
        super().setUp()
        now = self.now
        day = timedelta(days=1)
        self.ev('upcoming published', days=2)
        self.ev('upcoming pending', days=2, status='pending')
        self.ev('in progress', date=now - day, end_date=now + day)
        self.ev('ended with end date', date=now - 3 * day, end_date=now - day)
        self.ev('ended without end date', date=now - day)
        self.ev('completed', date=now + day, status='completed')
        self.ev('draft', days=9, status='draft')
        self.ev('old draft', date=now - day, status='draft')
        self.ev('cancelled', days=2, status='cancelled')
        self.ev('rejected', days=2, status='rejected')
        self.ev('expired pending', date=now - 2 * day, end_date=now - day, status='pending')
        self.login()

    def test_each_tab_has_its_events(self):
        expected = {
            'upcoming': {'upcoming published', 'upcoming pending', 'in progress'},
            'past': {'ended with end date', 'ended without end date', 'completed'},
            'drafts': {'draft', 'old draft'},
            'inactive': {'cancelled', 'rejected', 'expired pending'},
        }
        for tab, titles in expected.items():
            response = self.get(EVENTS, tab=tab)
            self.assertEqual(response.status_code, 200, tab)
            self.assertEqual(set(self.titles(response)), titles, tab)

    def test_tab_is_upcoming_by_default(self):
        self.assertEqual(self.get(EVENTS).data['count'], 3)

    def test_every_event_is_in_exactly_one_tab(self):
        seen = []
        for tab in dashboard.TABS:
            seen += self.titles(self.get(EVENTS, tab=tab))
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(len(seen), Event.objects.count())

    def test_summary_counts_match_tabs(self):
        summary = self.get(DASHBOARD).data
        self.assertEqual(summary['tabs'], {'upcoming': 3, 'past': 3, 'drafts': 2, 'inactive': 3})
        # The expired pending event can no longer be published: not awaiting approval.
        self.assertEqual(summary['pending_approval'], 1)

    def test_default_ordering_per_tab(self):
        self.assertEqual(self.titles(self.get(EVENTS, tab='upcoming'))[0], 'in progress')
        self.assertEqual(
            self.titles(self.get(EVENTS, tab='past')), ['completed', 'ended without end date', 'ended with end date']
        )
        self.assertEqual(self.titles(self.get(EVENTS, tab='drafts')), ['draft', 'old draft'])

    def test_invalid_tab_is_400(self):
        response = self.get(EVENTS, tab='everything')
        self.assertEqual(response.status_code, 400)
        self.assertIn('tab', response.data)


class SummaryTests(DashboardBase):
    def test_upcoming_next_7_days_counts_upcoming_tab_events_starting_soon(self):
        self.ev('soon', days=2)
        self.ev('soon pending', days=6, status='pending')
        self.ev('later', days=8)
        self.ev('in progress', date=self.now - timedelta(days=1), end_date=self.now + timedelta(days=1))
        self.ev('soon draft', days=2, status='draft')
        self.login()
        summary = self.get(DASHBOARD).data
        self.assertEqual(summary['upcoming_next_7_days'], 2)
        self.assertEqual(summary['tabs']['upcoming'], 4)

    def test_totals_and_revenue_per_currency(self):
        kzt = self.ev('KZT', currency='KZT', max_participants=50)
        usd = self.ev('USD', currency='USD', max_participants=50)
        past = self.ev('Past', date=self.now - timedelta(days=9), currency='KZT', status='completed')
        a = self.reg(kzt, checked_in=True)
        self.pay(a, 1000, currency='kzt')
        b = self.reg(kzt)
        self.pay(b, 500, refunded=100, currency='kzt')
        self.reg(kzt, status='pending')
        self.reg(kzt, status='cancelled')
        c = self.reg(usd, checked_in=True)
        self.pay(c, 30, currency='usd')
        d = self.reg(past, checked_in=True)
        self.pay(d, 200, currency='kzt')
        seats = self.seat_map(kzt)
        self.booking(kzt, seats[:3], amount_paid=Decimal('3000'), checked=2)

        self.login()
        summary = self.get(DASHBOARD).data
        self.assertEqual(summary['tickets_sold'], 2 + 3 + 1 + 1)
        self.assertEqual(summary['checked_in'], 1 + 2 + 1 + 1)
        self.assertEqual(summary['checkin_rate_pct'], round(5 / 7 * 100, 1))
        self.assertEqual(
            summary['revenue'],
            [
                {'currency': 'KZT', 'net_revenue': '4600.00'},  # 1000 + 400 + 200 + 3000
                {'currency': 'USD', 'net_revenue': '30.00'},
            ],
        )

    def test_zero_revenue_currencies_are_left_out(self):
        usd = self.ev('USD', currency='USD')
        self.pay(self.reg(usd), 40, currency='usd', status='refunded', refunded=40)
        self.login()
        self.assertEqual(self.get(DASHBOARD).data['revenue'], [])

    def test_sales_windows_boundaries(self):
        event = self.ev('Sales')
        now = self.now
        week, two_weeks = timedelta(days=7), timedelta(days=14)
        self.reg(event, at=now - timedelta(minutes=1))  # last
        self.reg(event, at=now - week)  # last: lower bound is inclusive
        self.reg(event, at=now - week - timedelta(microseconds=1))  # previous
        self.reg(event, at=now - two_weeks)  # previous: lower bound is inclusive
        self.reg(event, at=now - two_weeks - timedelta(microseconds=1))  # neither
        self.reg(event, at=now + timedelta(minutes=1))  # not yet: neither
        self.reg(event, status='pending', at=now - timedelta(hours=1))  # not a sale
        seats = self.seat_map(event)
        self.booking(event, seats[:3], at=now - timedelta(days=2))  # 3 last
        self.booking(event, seats[3:5], at=now - timedelta(days=10))  # 2 previous
        self.booking(event, seats[5:6], status='holding', at=now - timedelta(days=1))  # not a sale
        self.booking(event, seats[6:8], status='refunded', at=now - timedelta(days=1))  # not a sale

        summary = dashboard.dashboard_summary(self.organizer, now=now)
        self.assertEqual(summary['sales_last_7_days'], 2 + 3)
        self.assertEqual(summary['sales_previous_7_days'], 2 + 2)

    def test_summary_ignores_other_organizers_sales(self):
        mine = self.ev('Mine')
        self.reg(mine)
        foreign = self.make_event(title='Foreign', organizer=self.make_user('org2', role='organizer'))
        self.reg(foreign)
        self.reg(foreign)
        self.login()
        summary = self.get(DASHBOARD).data
        self.assertEqual(summary['tickets_sold'], 1)
        self.assertEqual(summary['sales_last_7_days'], 1)


class EventListTests(DashboardBase):
    def setUp(self):
        super().setUp()
        self.a = self.ev('Alpha', days=3, location='Almaty Arena', max_participants=10)
        self.b = self.ev('Bravo', days=2, location='Astana Hall', max_participants=100)
        self.c = self.ev('Charlie', days=4, location='Shymkent Hub', max_participants=4)
        for _ in range(2):
            self.reg(self.a)
        for i in range(5):
            self.reg(self.b, checked_in=i < 4)
        for i in range(3):
            self.reg(self.c, checked_in=i < 1)
        self.login()

    def order(self, ordering):
        response = self.get(EVENTS, ordering=ordering)
        self.assertEqual(response.status_code, 200, ordering)
        return self.titles(response)

    def test_orderings(self):
        self.assertEqual(self.order('date'), ['Bravo', 'Alpha', 'Charlie'])
        self.assertEqual(self.order('-date'), ['Charlie', 'Alpha', 'Bravo'])
        self.assertEqual(self.order('-tickets_sold'), ['Bravo', 'Charlie', 'Alpha'])
        self.assertEqual(self.order('-checkin_rate'), ['Bravo', 'Charlie', 'Alpha'])
        self.assertEqual(self.order('-sold_through'), ['Charlie', 'Alpha', 'Bravo'])

    def test_default_ordering_is_soonest_first(self):
        self.assertEqual(self.titles(self.get(EVENTS)), ['Bravo', 'Alpha', 'Charlie'])

    def test_ordering_by_numbers_uses_the_displayed_numbers(self):
        response = self.get(EVENTS, ordering='-sold_through')
        shown = [e['stats']['sold_through_pct'] for e in response.data['results']]
        self.assertEqual(shown, [75.0, 20.0, 5.0])
        response = self.get(EVENTS, ordering='-checkin_rate')
        shown = [e['stats']['checkin_rate_pct'] for e in response.data['results']]
        self.assertEqual(shown, [80.0, 33.3, 0.0])

    def test_group_booking_seats_count_in_sort_keys(self):
        seats = self.seat_map(self.a)
        self.booking(self.a, seats[:6], checked=6)  # Alpha: 2 + 6 sold, 6 checked in
        self.assertEqual(self.order('-tickets_sold'), ['Alpha', 'Bravo', 'Charlie'])
        self.assertEqual(self.order('-checkin_rate'), ['Bravo', 'Alpha', 'Charlie'])  # 80%, 75%, 33.3%

    def test_invalid_ordering_is_400(self):
        for value in ('title', 'tickets_sold', '-price', 'date,-date'):
            response = self.get(EVENTS, ordering=value)
            self.assertEqual(response.status_code, 400, value)
            self.assertIn('ordering', response.data)

    def test_search_matches_title_and_location_case_insensitively(self):
        self.assertEqual(self.titles(self.get(EVENTS, search='bRaV')), ['Bravo'])
        self.assertEqual(self.titles(self.get(EVENTS, search='ALMATY')), ['Alpha'])
        self.assertEqual(self.titles(self.get(EVENTS, search='  hall ')), ['Bravo'])
        self.assertEqual(self.titles(self.get(EVENTS, search='zzz')), [])
        self.assertEqual(self.get(EVENTS, search='a').data['count'], 3)

    def test_search_is_scoped_to_the_tab(self):
        self.ev('Alpha draft', status='draft')
        self.assertEqual(self.titles(self.get(EVENTS, search='alpha')), ['Alpha'])
        self.assertEqual(self.titles(self.get(EVENTS, tab='drafts', search='alpha')), ['Alpha draft'])

    def test_search_longer_than_100_chars_is_400(self):
        self.assertEqual(self.get(EVENTS, search='x' * 100).status_code, 200)
        response = self.get(EVENTS, search='x' * 101)
        self.assertEqual(response.status_code, 400)
        self.assertIn('search', response.data)

    def test_payload_is_the_event_list_payload_plus_stats(self):
        response = self.get(EVENTS, search='Bravo')
        item = response.data['results'][0]
        self.assertEqual(item['id'], self.b.id)
        for key in ('title', 'location', 'ticket_types', 'available_spots', 'registered_count', 'organizer'):
            self.assertIn(key, item)
        self.assertEqual(
            item['stats'],
            {
                'tickets_sold': 5,
                'checked_in': 4,
                'checkin_rate_pct': 80.0,
                'capacity': 100,
                'sold_through_pct': 5.0,
                'pending': 0,
                'net_revenue': '0.00',
                'currency': 'USD',
            },
        )

    def test_online_link_is_shown_to_co_organizers(self):
        other_org = self.make_user('org2', role='organizer')
        theirs = self.make_event(
            title='Theirs', organizer=other_org, is_online=True, online_link='https://meet.example.com/x'
        )
        EventStaff.objects.create(event=theirs, user=self.attendee, role=EventStaff.ROLE_CO_ORGANIZER)
        self.login(self.attendee)
        self.assertEqual(self.get(EVENTS).data['results'][0]['online_link'], 'https://meet.example.com/x')


class PaginationTests(DashboardBase):
    def setUp(self):
        super().setUp()
        Event.objects.bulk_create(
            [
                Event(
                    title=f'Bulk {i:02d}',
                    description='d',
                    organizer=self.organizer,
                    date=self.now + timedelta(days=1, minutes=i),
                    location='Hall',
                    status='published',
                )
                for i in range(55)
            ]
        )
        self.login()

    def test_default_page_size_is_20(self):
        response = self.get(EVENTS)
        self.assertEqual(response.data['count'], 55)
        self.assertEqual(len(response.data['results']), 20)
        self.assertIsNotNone(response.data['next'])
        self.assertIsNone(response.data['previous'])
        self.assertEqual(len(self.get(EVENTS, page=3).data['results']), 15)
        self.assertEqual(self.get(EVENTS, page=4).status_code, 404)

    def test_pages_do_not_overlap_and_cover_everything(self):
        seen = []
        for page in (1, 2, 3):
            seen += self.titles(self.get(EVENTS, page=page))
        self.assertEqual(seen, [f'Bulk {i:02d}' for i in range(55)])

    def test_page_size_param_and_cap(self):
        self.assertEqual(len(self.get(EVENTS, page_size=5).data['results']), 5)
        self.assertEqual(self.get(EVENTS, page_size=5).data['count'], 55)
        self.assertEqual(len(self.get(EVENTS, page_size=50).data['results']), 50)
        self.assertEqual(len(self.get(EVENTS, page_size=500).data['results']), 50)
        self.assertEqual(len(self.get(EVENTS, page_size=50, page=2).data['results']), 5)


class QueryCountTests(DashboardBase):
    """The number of queries does not depend on the number of events."""

    def populate(self, count):
        seat_events = []
        for i in range(count):
            event = self.ev(f'Event {i}', days=2 + i, currency='KZT' if i % 2 else 'USD', max_participants=40)
            TicketType.objects.create(event=event, name='GA', price=Decimal('10'), quantity=20)
            for j in range(3):
                registration = self.reg(event, checked_in=j == 0)
                self.pay(registration, 100, refunded=10 * j)
            self.reg(event, status='pending')
            seats = self.seat_map(event, 4)
            self.booking(event, seats[:2], amount_paid=Decimal('50') if i % 2 else None, checked=1)
            seat_events.append(event)
        theirs = self.make_event(title='Theirs', organizer=self.make_user(f'o{count}', role='organizer'))
        EventStaff.objects.create(event=theirs, user=self.organizer, role=EventStaff.ROLE_CO_ORGANIZER)

    def queries(self, url, **params):
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get(url, params).status_code, 200)
        return len(ctx)

    def measure(self):
        return {
            'list': self.queries(EVENTS),
            'list_by_sales': self.queries(EVENTS, ordering='-checkin_rate', page_size=50),
            'summary': self.queries(DASHBOARD),
            'activity': self.queries(ACTIVITY, limit=50),
        }

    def test_query_count_is_independent_of_event_count(self):
        self.login()
        self.populate(5)
        few = self.measure()
        self.populate(10)
        many = self.measure()
        self.assertEqual(many, few)
        self.assertEqual(self.get(EVENTS, page_size=50).data['count'], 15 + 2)


class StatsConsistencyTests(DashboardBase):
    """For every event the list shows what the analytics page shows."""

    def build_events(self):
        events = []

        confirmed = self.ev('Mixed regs', max_participants=8, currency='KZT')
        events += [confirmed]
        for i in range(3):
            self.pay(self.reg(confirmed, checked_in=i < 2), 1000, currency='kzt')
        self.reg(confirmed, status='pending')
        self.reg(confirmed, status='pending')
        cancelled = self.reg(confirmed, status='cancelled', checked_in=True)
        self.pay(cancelled, 1000, status='refunded', refunded=1000, currency='kzt')
        self.reg(confirmed, status='rejected')

        partial = self.ev('Partial refund', max_participants=20, currency='KZT')
        events += [partial]
        self.pay(self.reg(partial), 2000, refunded=500, currency='kzt')
        self.pay(self.reg(partial, checked_in=True), 2000, currency='kzt')
        self.pay(self.reg(partial, status='pending'), 2000, status='pending', currency='kzt')

        groups = self.ev('Groups', max_participants=10, currency='USD', tax_percent=Decimal('12'))
        events += [groups]
        seats = self.seat_map(groups)
        self.booking(groups, seats[:3], amount_paid=Decimal('45.50'), checked=2)  # confirmed, priced
        self.booking(groups, seats[3:5], amount_paid=None, checked=1, price=100)  # confirmed, priced from seats
        self.booking(groups, seats[5:7], status='refunded', amount_paid=Decimal('20'), checked=2)
        self.booking(groups, seats[7:8], status='holding')
        self.reg(groups, checked_in=True)

        free = self.ev('Free and empty', max_participants=0, price=0, currency='')
        events += [free]

        over = self.ev('Overbooked', max_participants=2, currency='EUR')
        events += [over]
        for _ in range(4):
            self.reg(over)
        return events

    def test_list_stats_equal_analytics_kpis(self):
        events = self.build_events()
        self.login()
        listed = {e['id']: e for e in self.get(EVENTS, page_size=50).data['results']}
        self.assertEqual(set(listed), {e.id for e in events})
        for event in events:
            stats = listed[event.id]['stats']
            analytics = self.client.get(f'/api/v1/events/{event.id}/analytics/')
            self.assertEqual(analytics.status_code, 200)
            kpis = analytics.data['kpis']
            for key in ('tickets_sold', 'checked_in', 'checkin_rate_pct', 'capacity', 'sold_through_pct', 'pending'):
                self.assertEqual(stats[key], kpis[key], f'{event.title}: {key}')
            self.assertEqual(Decimal(stats['net_revenue']), Decimal(str(kpis['net_revenue'])).quantize(Decimal('0.01')))
            self.assertEqual(stats['currency'], analytics.data['currency'], event.title)

    def test_known_values(self):
        events = {e.title: e for e in self.build_events()}
        stats = dashboard.bulk_event_stats(Event.objects.filter(pk__in=[e.pk for e in events.values()]))
        mixed = stats[events['Mixed regs'].pk]
        self.assertEqual(mixed['tickets_sold'], 3)
        self.assertEqual(mixed['checked_in'], 2)  # the cancelled, checked-in ticket is not counted
        self.assertEqual(mixed['pending'], 2)
        self.assertEqual(mixed['net_revenue'], '3000.00')
        self.assertEqual(stats[events['Partial refund'].pk]['net_revenue'], '3500.00')
        groups = stats[events['Groups'].pk]
        self.assertEqual(groups['tickets_sold'], 3 + 2 + 1)
        self.assertEqual(groups['checked_in'], 2 + 1 + 1)
        # 45.50 + 2 seats of 100 + 12% tax each = 224.00; refunded booking nets to zero.
        self.assertEqual(groups['net_revenue'], '269.50')
        empty = stats[events['Free and empty'].pk]
        self.assertEqual((empty['sold_through_pct'], empty['checkin_rate_pct']), (0.0, 0.0))
        self.assertEqual(empty['currency'], 'USD')
        self.assertEqual(stats[events['Overbooked'].pk]['sold_through_pct'], 200.0)

    def test_summary_equals_sum_of_event_stats(self):
        events = self.build_events()
        self.login()
        summary = self.get(DASHBOARD).data
        total_sold = total_checked = 0
        for event in events:
            kpis = self.client.get(f'/api/v1/events/{event.id}/analytics/').data['kpis']
            total_sold += kpis['tickets_sold']
            total_checked += kpis['checked_in']
        self.assertEqual(summary['tickets_sold'], total_sold)
        self.assertEqual(summary['checked_in'], total_checked)
        by_currency = {r['currency']: Decimal(r['net_revenue']) for r in summary['revenue']}
        self.assertEqual(by_currency['KZT'], Decimal('6500.00'))
        self.assertEqual(by_currency['USD'], Decimal('269.50'))


class ActivityTests(DashboardBase):
    def setUp(self):
        super().setUp()
        self.event = self.ev('Stand-up Almaty')
        self.login()

    def feed(self, **params):
        response = self.get(ACTIVITY, **params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    def test_registration(self):
        user = self.new_user(first_name='Dias', last_name='A.')
        registration = self.reg(self.event, user=user, at=self.now - timedelta(hours=1))
        item = self.feed()['results'][0]
        self.assertEqual(item['id'], f'registration:{registration.id}')
        self.assertEqual(item['type'], 'registration')
        self.assertEqual(item['event_id'], self.event.id)
        self.assertEqual(item['event_title'], 'Stand-up Almaty')
        self.assertEqual(item['attendee_name'], 'Dias A.')
        self.assertEqual((item['quantity'], item['amount'], item['currency']), (1, None, None))

    def test_only_confirmed_registrations_are_listed(self):
        self.reg(self.event, status='pending')
        self.reg(self.event, status='cancelled')
        self.assertEqual(self.feed()['results'], [])

    def test_attendee_name_falls_back_to_username(self):
        self.reg(self.event, user=self.new_user())
        self.assertEqual(self.feed()['results'][0]['attendee_name'], 'buyer1')

    def test_group_booking(self):
        owner = self.new_user(first_name='Aigerim', last_name='K.')
        seats = self.seat_map(self.event)
        booking = self.booking(self.event, seats[:4], owner=owner, at=self.now - timedelta(hours=2))
        self.booking(self.event, seats[4:6], status='holding')
        item = self.feed()['results'][0]
        self.assertEqual(item['id'], f'group_booking:{booking.id}')
        self.assertEqual(item['type'], 'group_booking')
        self.assertEqual(item['quantity'], 4)
        self.assertEqual(item['attendee_name'], 'Aigerim K.')
        self.assertEqual(len(self.feed()['results']), 1)

    def test_check_ins_of_registrations_and_seats(self):
        registration = self.reg(
            self.event, checked_in=True, at=self.now - timedelta(days=2), checked_at=self.now - timedelta(minutes=5)
        )
        booking = self.booking(self.event, self.seat_map(self.event)[:2], checked=1, at=self.now - timedelta(days=3))
        seat = booking.seats.get(is_checked_in=True)
        BookingSeat.objects.filter(pk=seat.pk).update(
            checked_in_at=self.now - timedelta(minutes=10), attendee_name='Guest Name'
        )
        check_ins = [i for i in self.feed()['results'] if i['type'] == 'check_in']
        self.assertEqual(
            [(i['id'], i['attendee_name']) for i in check_ins],
            [
                (f'check_in:registration:{registration.id}', registration.user.username),
                (f'check_in:booking_seat:{seat.id}', 'Guest Name'),
            ],
        )

    def test_refunds_only_when_processed(self):
        registration = self.reg(self.event, user=self.new_user(first_name='Ruslan', last_name='B.'))
        payment = self.pay(registration, 1000, status='completed', refunded=300, currency='kzt')

        def refund(status, amount, processed_at):
            return Refund.objects.create(
                payment=payment,
                amount=Decimal(amount),
                currency='KZT',
                kind=Refund.Kind.ORGANIZER,
                status=status,
                processed_at=processed_at,
            )

        done = refund(Refund.Status.SUCCEEDED, '300.00', self.now - timedelta(minutes=1))
        refund(Refund.Status.PENDING, '100.00', None)
        refund(Refund.Status.FAILED, '50.00', self.now - timedelta(minutes=2))

        booking = self.booking(self.event, self.seat_map(self.event)[:1], owner=self.new_user(first_name='Zhan'))
        booking_payment = Payment.objects.create(
            booking=booking, amount=Decimal('10'), currency='kzt', status='refunded'
        )
        booking_refund = Refund.objects.create(
            payment=booking_payment,
            amount=Decimal('10'),
            currency='KZT',
            kind=Refund.Kind.ORGANIZER,
            status=Refund.Status.SUCCEEDED,
            processed_at=self.now - timedelta(minutes=30),
        )
        refunds = [i for i in self.feed()['results'] if i['type'] == 'refund']
        self.assertEqual([i['id'] for i in refunds], [f'refund:{done.id}', f'refund:{booking_refund.id}'])
        self.assertEqual((refunds[0]['amount'], refunds[0]['currency']), ('300.00', 'KZT'))
        self.assertEqual(refunds[0]['attendee_name'], 'Ruslan B.')
        self.assertEqual(refunds[0]['event_title'], 'Stand-up Almaty')
        self.assertEqual(refunds[1]['attendee_name'], 'Zhan')

    def test_thirty_day_window(self):
        self.reg(self.event, at=self.now - timedelta(days=29, hours=23))
        self.reg(self.event, at=self.now - timedelta(days=30, hours=1))
        self.assertEqual(len(self.feed()['results']), 1)

    def test_newest_first_across_types(self):
        old = self.reg(self.event, at=self.now - timedelta(hours=5))
        booking = self.booking(self.event, self.seat_map(self.event)[:1], at=self.now - timedelta(hours=3))
        newest = self.reg(self.event, at=self.now - timedelta(hours=1))
        ids = [i['id'] for i in self.feed()['results']]
        self.assertEqual(ids, [f'registration:{newest.id}', f'group_booking:{booking.id}', f'registration:{old.id}'])
        times = [i['occurred_at'] for i in self.feed()['results']]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_limit_and_next_cursor(self):
        for hours in range(1, 6):
            self.reg(self.event, at=self.now - timedelta(hours=hours))
        page = self.feed(limit=2)
        self.assertEqual(len(page['results']), 2)
        self.assertIsNotNone(page['next_cursor'])
        self.assertEqual(len(self.feed()['results']), 5)  # default limit 20
        self.assertIsNone(self.feed()['next_cursor'])
        self.assertIsNone(self.feed(limit=5)['next_cursor'])  # exactly everything: nothing older

    def walk(self, limit):
        """Every page of the feed, as lists of ids."""
        pages, cursor = [], None
        for _ in range(100):
            params = {'limit': limit}
            if cursor:
                params['cursor'] = cursor
            page = self.feed(**params)
            pages.append([i['id'] for i in page['results']])
            cursor = page['next_cursor']
            if cursor is None:
                return pages
        self.fail('paging does not end')

    def test_paging_with_cursor_covers_every_item_once(self):
        for hours in range(1, 8):
            self.reg(self.event, at=self.now - timedelta(hours=hours))
        self.booking(self.event, self.seat_map(self.event)[:2], at=self.now - timedelta(hours=3, minutes=30))
        self.reg(
            self.event,
            checked_in=True,
            at=self.now - timedelta(days=1),
            checked_at=self.now - timedelta(hours=4, minutes=30),
        )
        everything = [i['id'] for i in self.feed(limit=50)['results']]
        self.assertEqual(len(everything), 7 + 1 + 1 + 1)
        for limit in (1, 2, 3, 4, 10):
            self.assertEqual(list(chain.from_iterable(self.walk(limit))), everything, limit)

    def test_items_sharing_one_timestamp_are_never_skipped_or_repeated(self):
        stamp = self.now - timedelta(hours=1)
        regs = [self.reg(self.event, at=stamp) for _ in range(13)]
        bookings = [self.booking(self.event, [], at=stamp) for _ in range(12)]
        expected = [f'group_booking:{b.id}' for b in sorted(bookings, key=lambda b: b.id, reverse=True)] + [
            f'registration:{r.id}' for r in sorted(regs, key=lambda r: r.id, reverse=True)
        ]  # (time, rank, pk) descending: bookings outrank registrations
        pages = self.walk(10)
        self.assertEqual([len(p) for p in pages], [10, 10, 5])
        self.assertEqual(list(chain.from_iterable(pages)), expected)
        self.assertEqual(list(chain.from_iterable(self.walk(7))), expected)

    def test_group_check_in_stamping_every_seat_at_once_pages_cleanly(self):
        stamp = self.now - timedelta(minutes=10)
        seats = self.seat_map(self.event)
        booking = self.booking(self.event, seats[:9], at=self.now - timedelta(days=1))
        BookingSeat.objects.filter(booking=booking).update(is_checked_in=True, checked_in_at=stamp)
        regs = [
            self.reg(self.event, checked_in=True, at=self.now - timedelta(days=2), checked_at=stamp) for _ in range(4)
        ]
        payment = self.pay(self.reg(self.event, at=self.now - timedelta(days=2)), 10, status='refunded', refunded=10)
        refunds = [
            Refund.objects.create(
                payment=payment,
                amount=Decimal('1'),
                currency='KZT',
                kind=Refund.Kind.ORGANIZER,
                status=Refund.Status.SUCCEEDED,
                processed_at=stamp,
            )
            for _ in range(3)
        ]
        everything = [i['id'] for i in self.feed(limit=50)['results']]
        self.assertEqual(
            len(everything),
            9 + 1 + 4 + 4 + 1 + 3,  # seat check-ins, booking, reg check-ins, their regs, a reg, refunds
        )
        self.assertEqual(len(set(everything)), len(everything))
        # Same timestamp: refunds first, then seat check-ins, then registration check-ins.
        top = everything[: 3 + 9 + 4]
        self.assertEqual(set(top[:3]), {f'refund:{r.id}' for r in refunds})
        self.assertTrue(all(i.startswith('check_in:booking_seat:') for i in top[3:12]))
        self.assertEqual(set(top[12:]), {f'check_in:registration:{r.id}' for r in regs})
        for limit in (1, 2, 5, 7):
            self.assertEqual(list(chain.from_iterable(self.walk(limit))), everything, limit)

    def test_uuid_ordering_agrees_between_database_and_python(self):
        for _ in range(30):
            self.booking(self.event, [])
        from_db = list(Booking.objects.order_by('-pk').values_list('pk', flat=True))
        self.assertEqual(from_db, sorted(from_db, reverse=True))
        self.assertEqual(
            list(Booking.objects.filter(pk__lt=from_db[10]).order_by('-pk').values_list('pk', flat=True)),
            from_db[11:],
        )

    def test_cursor_is_opaque_and_malformed_ones_are_400(self):
        self.reg(self.event)
        self.reg(self.event)
        cursor = self.feed(limit=1)['next_cursor']
        self.assertEqual(self.get(ACTIVITY, cursor=cursor).status_code, 200)

        def forge(**fields):
            data = {'t': self.now.isoformat(), 'r': 1, 'k': '1', **fields}
            return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()

        bad = [
            'garbage',
            '!!!!',
            base64.urlsafe_b64encode(b'not json').decode(),
            base64.urlsafe_b64encode(b'[1, 2]').decode(),
            base64.urlsafe_b64encode(b'{}').decode(),
            forge(r=9),
            forge(r=0),
            forge(r='1'),
            forge(r=True),
            forge(k='abc'),
            forge(r=2, k='1'),  # a booking cursor needs a UUID
            forge(t='yesterday'),
            forge(t='2026-01-01T00:00:00'),  # no timezone
            forge(t=None),
        ]
        for value in bad:
            response = self.get(ACTIVITY, cursor=value)
            self.assertEqual(response.status_code, 400, value)
            self.assertIn('cursor', response.data, value)

    def test_invalid_params_are_400(self):
        for params in ({'limit': 0}, {'limit': 51}, {'limit': 'x'}, {'cursor': 'yesterday'}):
            response = self.get(ACTIVITY, **params)
            self.assertEqual(response.status_code, 400, params)
            self.assertTrue(set(response.data) & {'limit', 'cursor'}, params)

    def test_no_other_organizers_data(self):
        foreign_organizer = self.make_user('org2', role='organizer')
        foreign = self.make_event(title='Foreign', organizer=foreign_organizer)
        registration = self.reg(foreign, checked_in=True)
        self.pay(registration, 10, status='refunded', refunded=10)
        Refund.objects.create(
            payment=registration.payment,
            amount=Decimal('10'),
            currency='KZT',
            kind=Refund.Kind.ORGANIZER,
            status=Refund.Status.SUCCEEDED,
            processed_at=self.now,
        )
        self.booking(foreign, self.seat_map(foreign)[:2], checked=1)
        mine = self.reg(self.event)
        self.assertEqual([i['id'] for i in self.feed()['results']], [f'registration:{mine.id}'])

    def test_co_organized_event_activity_is_listed(self):
        foreign = self.make_event(title='Theirs', organizer=self.make_user('org2', role='organizer'))
        registration = self.reg(foreign)
        EventStaff.objects.create(event=foreign, user=self.organizer, role=EventStaff.ROLE_CO_ORGANIZER)
        self.assertEqual([i['id'] for i in self.feed()['results']], [f'registration:{registration.id}'])

    def test_no_email_address_in_the_payload(self):
        # A username that is an email address must not leak through the display name.
        leaky = User.objects.create_user('leaky.person@example.com', 'leaky.person@example.com', 'x')
        self.reg(self.event, user=leaky, checked_in=True)
        owner = User.objects.create_user('owner@example.org', 'owner@example.org', 'x')
        self.booking(self.event, self.seat_map(self.event)[:1], owner=owner, checked=1)
        response = self.get(ACTIVITY)
        body = response.content.decode()
        self.assertNotIn('@', body)
        self.assertNotIn('example', body)
        names = {i['attendee_name'] for i in response.data['results']}
        self.assertEqual(names, {'leaky.person', 'owner'})
        for item in response.data['results']:
            self.assertEqual(
                set(item),
                {
                    'id',
                    'type',
                    'occurred_at',
                    'event_id',
                    'event_title',
                    'attendee_name',
                    'quantity',
                    'amount',
                    'currency',
                },
            )


class CloneTests(DashboardBase):
    def setUp(self):
        super().setUp()
        self.src = self.ev('Summit', days=20, status='published', max_participants=77, currency='KZT')
        self.url = f'/api/v1/events/{self.src.id}/clone/'
        self.login()

    def clone(self, body=None, **kw):
        return self.client.post(self.url, body, format='json', **kw)

    def test_default_title_keeps_the_copy_suffix(self):
        response = self.clone()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['title'], 'Summit (Copy)')
        self.assertEqual(response.data['status'], 'draft')
        self.assertEqual(response.data['max_participants'], 77)

    def test_default_title_is_cut_to_fit_the_column(self):
        self.src.title = 'x' * 200
        self.src.save()
        response = self.clone()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['title'], 'x' * 193 + ' (Copy)')

    def test_title_param_is_used_and_trimmed(self):
        response = self.clone({'title': '  Саммит (копия)  '})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['title'], 'Саммит (копия)')
        self.assertEqual(Event.objects.get(pk=response.data['id']).title, 'Саммит (копия)')

    def test_title_of_200_chars_is_accepted(self):
        self.assertEqual(self.clone({'title': 'y' * 200}).status_code, 201)

    def test_invalid_titles_are_400_and_create_nothing(self):
        for body in ({'title': ''}, {'title': '   '}, {'title': 'y' * 201}, {'title': None}, {'title': ['a']}):
            response = self.clone(body)
            self.assertEqual(response.status_code, 400, body)
            self.assertIn('title', response.data, body)
        self.assertEqual(Event.objects.count(), 1)

    def test_clone_without_a_body_still_works(self):
        self.assertEqual(self.client.post(self.url).status_code, 201)

    def test_check_in_lists_are_copied_independently(self):
        main = CheckInList.objects.create(
            event=self.src, name='Main', description='Front door', color='#112233', is_default=True
        )
        vip = CheckInList.objects.create(event=self.src, name='VIP', color='#445566')
        response = self.clone({'title': 'Copy'})
        copy = Event.objects.get(pk=response.data['id'])
        copied = list(copy.checkin_lists.order_by('created_at', 'id'))
        self.assertEqual(
            [(c.name, c.description, c.color, c.is_default) for c in copied],
            [('Main', 'Front door', '#112233', True), ('VIP', '', '#445566', False)],
        )
        self.assertFalse({c.pk for c in copied} & {main.pk, vip.pk})
        self.assertEqual(self.src.checkin_lists.count(), 2)

    def test_everything_else_is_still_copied_and_nothing_sold_is(self):
        TicketType.objects.create(event=self.src, name='GA', price=Decimal('10'), quantity=5)
        EventQuestion.objects.create(event=self.src, label='Diet?')
        PromoCode.objects.create(event=self.src, code='SAVE', discount_type='percent', discount_value=10)
        self.seat_map(self.src, 3)
        self.reg(self.src)
        EventStaff.objects.create(event=self.src, user=self.attendee, role=EventStaff.ROLE_CHECK_IN)

        copy = Event.objects.get(pk=self.clone().data['id'])
        self.assertEqual(copy.ticket_types.count(), 1)
        self.assertNotEqual(copy.ticket_types.get().pk, self.src.ticket_types.get().pk)
        self.assertEqual(copy.questions.count(), 1)
        self.assertEqual(copy.promo_codes.count(), 1)
        self.assertEqual(copy.seat_map.seats.count(), 3)
        self.assertEqual(copy.registrations.count(), 0)
        self.assertEqual(copy.staff.count(), 0)

    def test_the_copy_is_indexed_for_search_like_a_created_event(self):
        with patch('events.search.index_event_async') as index:
            response = self.clone({'title': 'Indexed'})
        self.assertEqual(response.status_code, 201)
        index.assert_called_once()
        self.assertEqual(index.call_args.args[0].pk, response.data['id'])

    def test_nothing_is_indexed_when_the_request_is_refused(self):
        with patch('events.search.index_event_async') as index:
            self.assertEqual(self.clone({'title': ''}).status_code, 400)
            self.login(self.attendee)
            self.assertEqual(self.clone({'title': 'X'}).status_code, 403)
        index.assert_not_called()

    def test_the_copy_enqueues_an_index_job(self):
        from jobs.models import Job

        with patch('events.search.semantic_search_installed', return_value=True):
            response = self.clone()
        self.assertTrue(Job.objects.filter(kind='index_event', payload={'event_id': response.data['id']}).exists())

    def test_attendee_cannot_clone_a_visible_event(self):
        self.login(self.attendee)
        response = self.clone({'title': 'Mine now'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Event.objects.count(), 1)

    def test_events_the_caller_cannot_see_are_404(self):
        self.src.status = 'draft'
        self.src.save()
        self.login(self.attendee)
        self.assertEqual(self.clone().status_code, 404)

    def test_anonymous_gets_401(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.clone().status_code, 401)

    def test_a_co_organizer_can_clone_and_owns_the_copy(self):
        EventStaff.objects.create(event=self.src, user=self.attendee, role=EventStaff.ROLE_CO_ORGANIZER)
        self.login(self.attendee)
        response = self.clone({'title': 'By co-org'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Event.objects.get(pk=response.data['id']).organizer_id, self.attendee.id)


class StatsEndpointTests(DashboardBase):
    def test_checked_in_counts_confirmed_registrations_only(self):
        event = self.ev('Stats')
        self.reg(event, checked_in=True)
        self.reg(event)
        self.reg(event, status='cancelled', checked_in=True)  # e.g. checked in, then refunded
        self.reg(event, status='pending', checked_in=True)
        self.login()
        data = self.client.get(f'/api/v1/events/{event.id}/stats/').data
        self.assertEqual(data['total_registrations'], 2)
        self.assertEqual(data['checked_in'], 1)
        self.assertEqual(data['remaining'], 1)
        self.assertEqual(data['check_in_rate'], 50)

    def test_rate_never_passes_100(self):
        event = self.ev('Stats')
        self.reg(event, checked_in=True)
        self.reg(event, status='cancelled', checked_in=True)
        self.login()
        self.assertLessEqual(self.client.get(f'/api/v1/events/{event.id}/stats/').data['check_in_rate'], 100)


class CurrencyConsistencyTests(DashboardBase):
    def test_list_stats_and_summary_agree_on_the_currency_code(self):
        event = self.ev('Lowercase', currency='kzt')
        self.pay(self.reg(event), 700, currency='kzt')
        self.login()
        item = self.get(EVENTS).data['results'][0]
        revenue = self.get(DASHBOARD).data['revenue']
        self.assertEqual(item['stats']['currency'], 'KZT')
        self.assertEqual([r['currency'] for r in revenue], [item['stats']['currency']])
        self.assertEqual(dashboard.bulk_event_stats([event])[event.pk]['currency'], event_currency(event))

    def test_blank_currency_means_usd_in_both(self):
        event = self.ev('Blank', currency='')
        self.pay(self.reg(event), 5, currency='usd')
        self.login()
        self.assertEqual(self.get(EVENTS).data['results'][0]['stats']['currency'], 'USD')
        self.assertEqual(self.get(DASHBOARD).data['revenue'], [{'currency': 'USD', 'net_revenue': '5.00'}])


class RetryAfterCorsTests(DashboardBase):
    """Cross-origin scripts (the SPA on another origin) can read Retry-After."""

    ORIGIN = 'http://localhost:4200'

    def test_throttled_cross_origin_response_exposes_retry_after(self):
        from django.core.cache import cache
        from rest_framework.throttling import UserRateThrottle

        from events.views import OrganizerDashboardView

        cache.clear()
        self.addCleanup(cache.clear)
        self.login()
        with (
            patch.object(OrganizerDashboardView, 'throttle_classes', [UserRateThrottle]),
            patch.object(UserRateThrottle, 'THROTTLE_RATES', {'user': '1/min'}),
        ):
            first = self.client.get(DASHBOARD, HTTP_ORIGIN=self.ORIGIN)
            second = self.client.get(DASHBOARD, HTTP_ORIGIN=self.ORIGIN)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertTrue(second['Retry-After'].isdigit())
        self.assertEqual(second['Access-Control-Allow-Origin'], self.ORIGIN)
        exposed = [h.strip().lower() for h in second['Access-Control-Expose-Headers'].split(',')]
        self.assertIn('retry-after', exposed)

    def test_expose_headers_setting_keeps_retry_after(self):
        from django.conf import settings

        self.assertIn('Retry-After', settings.CORS_EXPOSE_HEADERS)
