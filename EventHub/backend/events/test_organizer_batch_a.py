"""Organizer dashboard, batch A (docs/ORGANIZER_DASHBOARD_PHASE2.md): the sales
chart, the ticket-type breakdown, today / next 7 days and the reviews summary.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from bookings.models import Booking
from events import dashboard, sales_chart
from events.analytics import event_analytics
from events.business_time import business_tz, day_start, local_today
from events.models import EventStaff, Review, TicketType
from events.test_organizer_dashboard import DashboardBase
from payments.models import Payment, Refund

SALES = '/api/v1/organizer/sales/'
TODAY = '/api/v1/organizer/today/'
REVIEWS = '/api/v1/organizer/reviews/'
UTC = UTC


def utc(month, day, hour=0, minute=0, second=0):
    return datetime(2026, month, day, hour, minute, second, tzinfo=UTC)


@override_settings(NOTIFICATION_TIME_ZONE='Asia/Almaty')
class BatchABase(DashboardBase):
    def pay_at(self, registration, amount, at, paid_at=None, **kw):
        """A payment started at `at` and (when it is paid) paid at `paid_at`, default `at`."""
        payment = self.pay(registration, amount, **kw)
        paid = (paid_at or at) if payment.paid_at is not None else None
        Payment.objects.filter(pk=payment.pk).update(created_at=at, paid_at=paid)
        payment.refresh_from_db()
        return payment

    def booking(self, *args, confirmed_at=None, at=None, **kwargs):
        """As the base helper; a confirmed or refunded booking is confirmed at
        `confirmed_at`, default the moment it was created (`at`)."""
        booking = super().booking(*args, at=at, **kwargs)
        stamp = confirmed_at or at
        if stamp is not None and booking.confirmed_at is not None:
            Booking.objects.filter(pk=booking.pk).update(confirmed_at=stamp)
            booking.refresh_from_db()
        return booking

    def refund(self, payment, amount, processed_at, status=Refund.Status.SUCCEEDED):
        return Refund.objects.create(
            payment=payment,
            amount=Decimal(str(amount)),
            currency=payment.currency.upper(),
            kind=Refund.Kind.ORGANIZER,
            status=status,
            processed_at=processed_at,
        )

    def sales(self, **params):
        return self.get(SALES, **params)

    @staticmethod
    def tickets_by_day(data):
        return {d['date']: d['tickets'] for d in data['days']}

    @staticmethod
    def revenue_by_day(data, currency):
        series = next(s for s in data['revenue'] if s['currency'] == currency)
        return {d['date']: Decimal(d['net_revenue']) for d in series['days']}


class PermissionTests(BatchABase):
    URLS = (SALES, TODAY, REVIEWS)

    def test_anonymous_gets_401(self):
        for url in self.URLS:
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_attendee_gets_403(self):
        self.login(self.attendee)
        for url in self.URLS:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_organizer_without_events_gets_empty_answers(self):
        self.login()
        sales = self.sales().data
        self.assertEqual(sales['revenue'], [])
        self.assertEqual(sum(d['tickets'] for d in sales['days']), 0)
        self.assertEqual(self.get(TODAY).data, {'results': [], 'more': 0})
        self.assertEqual(
            self.get(REVIEWS).data,
            {'count': 0, 'average': None, 'distribution': {'1': 0, '2': 0, '3': 0, '4': 0, '5': 0}, 'recent': []},
        )

    def test_co_organizer_sees_co_organized_events_and_other_organizers_never_leak(self):
        other = self.make_user('org2', role='organizer')
        theirs = self.make_event(
            title='Theirs', organizer=other, status='published', date=timezone.now() + timedelta(days=2)
        )
        foreign = self.make_event(
            title='Foreign', organizer=other, status='published', date=timezone.now() + timedelta(days=2)
        )
        EventStaff.objects.create(event=theirs, user=self.attendee, role=EventStaff.ROLE_CO_ORGANIZER)
        for event in (theirs, foreign):
            buyer = self.reg(event)
            self.pay(buyer, 500)
            Review.objects.create(user=self.new_user(), event=event, rating=4, comment=event.title)
        self.ev('Mine')

        self.login(self.attendee)  # an attendee account with a co-organizer seat
        self.assertEqual(sum(d['tickets'] for d in self.sales().data['days']), 1)
        self.assertEqual([e['title'] for e in self.get(TODAY).data['results']], ['Theirs'])
        self.assertFalse(self.get(TODAY).data['results'][0]['is_owner'])
        reviews = self.get(REVIEWS).data
        self.assertEqual([r['comment'] for r in reviews['recent']], ['Theirs'])

        self.login()  # the owner of 'Mine' sees none of it
        self.assertEqual(sum(d['tickets'] for d in self.sales().data['days']), 0)
        self.assertEqual(self.sales().data['revenue'], [])
        self.assertEqual([e['title'] for e in self.get(TODAY).data['results']], ['Mine'])
        self.assertEqual(self.get(REVIEWS).data['count'], 0)


class SalesShapeTests(BatchABase):
    def setUp(self):
        super().setUp()
        self.login()

    def test_default_range_is_30_days_ending_today_in_the_business_time_zone(self):
        data = self.sales().data
        today = local_today()
        self.assertEqual(data['time_zone'], 'Asia/Almaty')
        self.assertEqual(data['end'], today.isoformat())
        self.assertEqual(data['start'], (today - timedelta(days=29)).isoformat())
        self.assertEqual(len(data['days']), 30)
        self.assertEqual((data['days'][0]['date'], data['days'][-1]['date']), (data['start'], data['end']))

    def test_ranges(self):
        for key, length in (('7d', 7), ('30d', 30), ('90d', 90)):
            data = self.sales(range=key).data
            self.assertEqual(len(data['days']), length, key)
            dates = [d['date'] for d in data['days']]
            self.assertEqual(dates, sorted(set(dates)))

    def test_invalid_range_is_a_field_error(self):
        for value in ('1d', '365d', 'week', '30'):
            response = self.sales(range=value)
            self.assertEqual(response.status_code, 400, value)
            self.assertIn('range', response.data, value)

    def test_blank_range_means_the_default(self):
        # Like a blank `ordering` on organizer/events: DRF treats an empty
        # query value as omitted, so the default window applies.
        response = self.sales(range='')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['days']), 30)

    def test_every_day_is_zero_filled(self):
        event = self.ev()
        self.reg(event)
        self.pay(self.reg(event), 100)
        data = self.sales(range='7d').data
        self.assertEqual(len(data['days']), 7)
        self.assertEqual(sum(d['tickets'] for d in data['days']), 2)
        self.assertEqual(sorted(d['tickets'] for d in data['days']), [0, 0, 0, 0, 0, 0, 2])
        series = data['revenue'][0]
        self.assertEqual(len(series['days']), 7)
        self.assertEqual(sum(Decimal(d['net_revenue']) for d in series['days']), Decimal('100.00'))
        self.assertEqual(sorted(d['net_revenue'] for d in series['days'])[:6], ['0.00'] * 6)

    def test_markers_are_empty_until_events_have_a_publication_time(self):
        self.ev()
        self.assertEqual(self.sales().data['markers'], [])

    def test_only_confirmed_tickets_count(self):
        event = self.ev()
        self.reg(event)
        self.reg(event, status='pending')
        self.reg(event, status='cancelled')
        self.reg(event, status='rejected')
        seats = self.seat_map(event, 4)
        self.booking(event, seats[:2])
        self.booking(event, seats[2:3], status='holding')
        self.booking(event, seats[3:4], status='cancelled')
        self.assertEqual(sum(d['tickets'] for d in self.sales().data['days']), 3)

    def test_unpaid_failed_and_pending_payments_bring_no_money(self):
        event = self.ev(currency='KZT')
        for status in ('pending', 'failed', 'expired'):
            self.pay(self.reg(event, status='pending'), 100, status=status)
        self.assertEqual(self.sales().data['revenue'], [])

    def test_a_refund_that_did_not_succeed_is_not_deducted(self):
        event = self.ev(currency='KZT')
        payment = self.pay(self.reg(event), 1000)
        self.refund(payment, 300, timezone.now(), status=Refund.Status.PENDING)
        self.refund(payment, 200, timezone.now(), status=Refund.Status.FAILED)
        data = self.sales().data
        self.assertEqual(sum(self.revenue_by_day(data, 'KZT').values()), Decimal('1000.00'))


class SalesDayBoundaryTests(BatchABase):
    """Days are Almaty days (UTC+5), not UTC days."""

    NOW = utc(11, 15, 12)  # 17:00 on 15 Nov in Almaty; the 7d range is 9..15 Nov

    def setUp(self):
        super().setUp()
        self.event = self.ev(currency='KZT')

    def series(self, **kw):
        return sales_chart.sales_series(self.organizer, '7d', now=self.NOW, **kw)

    def test_range_bounds(self):
        data = self.series()
        self.assertEqual((data['start'], data['end']), ('2026-11-09', '2026-11-15'))
        self.assertEqual([d['date'][-2:] for d in data['days']], ['09', '10', '11', '12', '13', '14', '15'])

    def test_tickets_around_almaty_midnight(self):
        moments = {
            utc(11, 8, 18, 59, 59): None,  # 23:59:59 on the 8th: before the range
            utc(11, 8, 19, 0, 0): '2026-11-09',  # 00:00 on the 9th: first day
            utc(11, 10, 18, 59, 59): '2026-11-10',  # 23:59:59
            utc(11, 10, 19, 0, 0): '2026-11-11',  # 00:00 next day, while UTC is still the 10th
            utc(11, 10, 23, 30): '2026-11-11',  # 04:30 on the 11th, 23:30 on the 10th UTC
            utc(11, 15, 18, 59, 59): '2026-11-15',  # last second of the last day
            utc(11, 15, 19, 0, 0): None,  # the 16th: after the range
        }
        for moment in moments:
            self.reg(self.event, at=moment)
        expected = {d['date']: 0 for d in self.series()['days']}
        for day in moments.values():
            if day:
                expected[day] += 1
        self.assertEqual(self.tickets_by_day(self.series()), expected)
        self.assertEqual(expected['2026-11-11'], 2)

    def test_group_booking_seats_sit_on_the_booking_day(self):
        seats = self.seat_map(self.event, 5)
        self.booking(self.event, seats[:3], at=utc(11, 10, 19, 0, 0))  # 11th
        self.booking(self.event, seats[3:], at=utc(11, 10, 18, 59, 59))  # 10th
        by_day = self.tickets_by_day(self.series())
        self.assertEqual((by_day['2026-11-10'], by_day['2026-11-11']), (2, 3))

    def test_payments_refunds_and_bookings_money_around_midnight(self):
        paid_late_on_10 = self.pay_at(self.reg(self.event), 100, utc(11, 10, 18, 59, 59))
        paid_early_on_11 = self.pay_at(self.reg(self.event), 200, utc(11, 10, 19, 0, 0))
        self.refund(paid_late_on_10, 30, utc(11, 11, 18, 59, 59))  # the 11th
        self.refund(paid_early_on_11, 50, utc(11, 11, 19, 0, 0))  # the 12th
        self.pay_at(self.reg(self.event), 7, utc(11, 8, 18, 59, 59))  # before the range
        seats = self.seat_map(self.event, 2)
        self.booking(self.event, seats[:1], amount_paid=Decimal('40'), at=utc(11, 12, 5))
        refunded = self.booking(self.event, seats[1:], status='refunded', amount_paid=Decimal('25'), at=utc(11, 12, 5))
        Booking.objects.filter(pk=refunded.pk).update(refunded_at=utc(11, 13, 19, 0, 0))  # the 14th

        money = self.revenue_by_day(self.series(), 'KZT')
        self.assertEqual(
            {day: amount for day, amount in money.items() if amount},
            {
                '2026-11-10': Decimal('100.00'),
                '2026-11-11': Decimal('200.00') - Decimal('30.00'),
                '2026-11-12': Decimal('40.00') + Decimal('25.00') - Decimal('50.00'),
                '2026-11-14': Decimal('-25.00'),
            },
        )

    def test_the_business_time_zone_setting_decides_the_day(self):
        self.reg(self.event, at=utc(11, 10, 23, 30))
        self.assertEqual(self.tickets_by_day(self.series())['2026-11-11'], 1)
        with override_settings(NOTIFICATION_TIME_ZONE='UTC'):
            data = self.series()
            self.assertEqual(data['time_zone'], 'UTC')
            self.assertEqual((data['start'], data['end']), ('2026-11-09', '2026-11-15'))
            self.assertEqual(self.tickets_by_day(data)['2026-11-10'], 1)
            self.assertEqual(self.tickets_by_day(data)['2026-11-11'], 0)

    def test_end_is_today_in_the_business_time_zone(self):
        # 20:00 UTC on the 15th is already the 16th in Almaty.
        data = sales_chart.sales_series(self.organizer, '7d', now=utc(11, 15, 20))
        self.assertEqual(data['end'], '2026-11-16')
        self.assertEqual(data['start'], '2026-11-10')


class SalesCurrencyTests(BatchABase):
    def test_money_is_never_summed_across_currencies(self):
        kzt = self.ev('KZT', currency='KZT')
        usd = self.ev('USD', currency='USD')
        blank = self.ev('Blank', currency='')  # priced in USD, like everywhere else
        eur = self.ev('EUR', currency='eur')
        self.pay(self.reg(kzt), 50000, currency='kzt')
        self.pay(self.reg(kzt), 10000, currency='kzt')
        self.pay(self.reg(usd), 100, currency='usd')
        self.pay(self.reg(blank), 20, currency='usd')
        self.pay(self.reg(eur), 9, currency='eur')
        self.login()

        data = self.sales().data
        self.assertEqual([s['currency'] for s in data['revenue']], ['EUR', 'KZT', 'USD'])
        totals = {s: sum(self.revenue_by_day(data, s).values()) for s in ('EUR', 'KZT', 'USD')}
        self.assertEqual(totals, {'EUR': Decimal('9.00'), 'KZT': Decimal('60000.00'), 'USD': Decimal('120.00')})
        self.assertEqual(sum(d['tickets'] for d in data['days']), 5)  # tickets have no currency

    def test_group_bookings_and_refunds_follow_the_event_currency(self):
        kzt = self.ev('KZT', currency='KZT')
        usd = self.ev('USD', currency='USD')
        seats = self.seat_map(kzt, 1) + self.seat_map(usd, 1)
        self.booking(kzt, seats[:1], amount_paid=Decimal('1000'))
        self.booking(usd, seats[1:], amount_paid=Decimal('12.50'))
        payment = self.pay(self.reg(usd), 40, currency='usd')
        self.refund(payment, 15, timezone.now())
        self.login()

        data = self.sales().data
        self.assertEqual(sum(self.revenue_by_day(data, 'KZT').values()), Decimal('1000.00'))
        self.assertEqual(sum(self.revenue_by_day(data, 'USD').values()), Decimal('37.50'))


class SalesReconciliationTests(BatchABase):
    """The range totals equal the per-event analytics for an event whose whole life is in the range."""

    def build(self):
        now = timezone.now()
        event = self.ev('Whole life', currency='KZT', max_participants=50, tax_percent=Decimal('12'))
        self.reg(event, at=now - timedelta(days=4))  # free ticket
        a = self.reg(event, at=now - timedelta(days=3))
        self.pay_at(a, 1000, now - timedelta(days=3), currency='kzt')
        b = self.reg(event, at=now - timedelta(days=3))
        partly = self.pay_at(b, 2000, now - timedelta(days=3), refunded=500, currency='kzt')
        self.refund(partly, 500, now - timedelta(days=1))
        c = self.reg(event, status='cancelled', at=now - timedelta(days=5))
        gone = self.pay_at(c, 700, now - timedelta(days=5), status='refunded', refunded=700, currency='kzt')
        self.refund(gone, 700, now - timedelta(days=2))
        pending = self.reg(event, status='pending', at=now - timedelta(days=1))
        self.pay_at(pending, 900, now - timedelta(days=1), status='pending', currency='kzt')

        seats = self.seat_map(event, 4)
        self.booking(event, seats[:2], amount_paid=Decimal('90'), at=now - timedelta(days=3))
        self.booking(event, seats[2:3], amount_paid=None, price=100, at=now - timedelta(days=2))  # 100 + 12% tax
        refunded = self.booking(
            event, seats[3:], status='refunded', amount_paid=Decimal('40'), at=now - timedelta(days=6)
        )
        Booking.objects.filter(pk=refunded.pk).update(refunded_at=now - timedelta(days=1))
        return event

    def test_totals_equal_event_analytics(self):
        event = self.build()
        self.login()
        kpis = self.client.get(f'/api/v1/events/{event.id}/analytics/').data['kpis']
        data = self.sales(range='30d').data

        self.assertEqual(kpis['tickets_sold'], 1 + 2 + 2 + 1)
        self.assertEqual(sum(d['tickets'] for d in data['days']), kpis['tickets_sold'])
        series = self.revenue_by_day(data, 'KZT')
        self.assertEqual(sum(series.values()), Decimal(str(kpis['net_revenue'])).quantize(Decimal('0.01')))
        self.assertEqual(sum(series.values()), Decimal('1000') + Decimal('1500') + Decimal('90') + Decimal('112'))
        # ... and the dashboard summary agrees too.
        summary = self.get('/api/v1/organizer/dashboard/').data
        self.assertEqual(
            {r['currency']: Decimal(r['net_revenue']) for r in summary['revenue']}, {'KZT': sum(series.values())}
        )
        self.assertEqual(summary['tickets_sold'], sum(d['tickets'] for d in data['days']))

    def test_a_longer_range_gives_the_same_totals(self):
        self.build()
        self.login()
        totals = {
            key: (
                sum(d['tickets'] for d in self.sales(range=key).data['days']),
                sum(self.revenue_by_day(self.sales(range=key).data, 'KZT').values()),
            )
            for key in ('30d', '90d')
        }
        self.assertEqual(totals['30d'], totals['90d'])

    def test_money_outside_the_range_is_left_out(self):
        event = self.ev(currency='KZT')
        old = timezone.now() - timedelta(days=20)
        self.pay_at(self.reg(event, at=old), 500, old, currency='kzt')
        self.login()
        self.assertEqual(sum(d['tickets'] for d in self.sales(range='7d').data['days']), 0)
        self.assertEqual(self.sales(range='7d').data['revenue'], [])
        self.assertEqual(sum(d['tickets'] for d in self.sales(range='30d').data['days']), 1)


class SalesQueryCountTests(BatchABase):
    def populate(self, count):
        now = timezone.now()
        for i in range(count):
            event = self.ev(f'Event {i}', days=2 + i % 5, currency='KZT' if i % 2 else 'USD', tax_percent=Decimal('12'))
            for j in range(2):
                payment = self.pay_at(self.reg(event), 100, now - timedelta(days=j), refunded=10 * j)
                if j:
                    self.refund(payment, 10, now)
            seats = self.seat_map(event, 4)
            self.booking(event, seats[:1], amount_paid=Decimal('50'))
            self.booking(event, seats[1:2], amount_paid=None)  # priced from the seat
            refunded = self.booking(event, seats[2:3], status='refunded', amount_paid=Decimal('30'))
            Booking.objects.filter(pk=refunded.pk).update(refunded_at=now)
            Review.objects.create(user=self.new_user(), event=event, rating=1 + i % 5, comment='ok')
        theirs = self.make_event(title='Theirs', organizer=self.make_user(f'o{count}', role='organizer'))
        EventStaff.objects.create(event=theirs, user=self.organizer, role=EventStaff.ROLE_CO_ORGANIZER)

    def queries(self, url, **params):
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get(url, params).status_code, 200)
        return len(ctx)

    def measure(self):
        return {
            'sales_30d': self.queries(SALES),
            'sales_90d': self.queries(SALES, range='90d'),
            'today': self.queries(TODAY),
            'reviews': self.queries(REVIEWS),
        }

    def test_query_count_is_independent_of_event_count(self):
        self.login()
        self.populate(3)
        few = self.measure()
        self.populate(9)  # 12 events
        many = self.measure()
        self.assertEqual(many, few)
        self.assertEqual(Booking.objects.count(), 36)
        with self.assertNumQueries(few['sales_30d']):
            self.client.get(SALES)
        with self.assertNumQueries(few['today']):
            self.client.get(TODAY)
        with self.assertNumQueries(few['reviews']):
            self.client.get(REVIEWS)


class TimelineFixTests(BatchABase):
    """`events/analytics.py` timeline: business time zone, zero-filled, sales older than the window are outside it."""

    def timeline(self, event):
        return {d['date']: d for d in event_analytics(event)['timeline']}

    def test_thirty_zero_filled_days_ending_today(self):
        event = self.ev(currency='KZT')
        today = local_today()
        timeline = event_analytics(event)['timeline']
        self.assertEqual(len(timeline), 30)
        self.assertEqual(timeline[-1]['date'], today.isoformat())
        self.assertEqual(timeline[0]['date'], (today - timedelta(days=29)).isoformat())
        self.assertTrue(all(d['tickets'] == 0 and d['revenue'] == 0 for d in timeline))
        self.assertEqual(set(timeline[0]), {'date', 'tickets', 'revenue'})

    def test_sales_older_than_the_window_are_not_piled_onto_its_first_day(self):
        event = self.ev(currency='KZT')
        today = local_today()
        for days_ago in (30, 45, 200):
            when = day_start(today - timedelta(days=days_ago)) + timedelta(hours=3)
            self.pay_at(self.reg(event, at=when), 100, when)
        when = day_start(today - timedelta(days=29)) + timedelta(hours=1)
        self.pay_at(self.reg(event, at=when), 70, when)
        timeline = event_analytics(event)['timeline']
        self.assertEqual(timeline[0]['tickets'], 1)  # only the sale of that very day
        self.assertEqual(timeline[0]['revenue'], 70.0)
        self.assertEqual(sum(d['tickets'] for d in timeline), 1)
        # The headline numbers still count everything.
        self.assertEqual(event_analytics(event)['kpis']['tickets_sold'], 4)

    def test_days_are_business_time_zone_days(self):
        event = self.ev(currency='KZT')
        today = local_today()
        midnight = day_start(today)
        self.reg(event, at=midnight - timedelta(seconds=1))  # last second of yesterday
        self.reg(event, at=midnight)  # first second of today
        self.reg(event, at=midnight + timedelta(hours=5))
        timeline = self.timeline(event)
        self.assertEqual(timeline[(today - timedelta(days=1)).isoformat()]['tickets'], 1)
        self.assertEqual(timeline[today.isoformat()]['tickets'], 2)
        self.assertEqual(business_tz().key, 'Asia/Almaty')

    def test_group_bookings_use_the_same_bucketing(self):
        event = self.ev(currency='KZT')
        today = local_today()
        seats = self.seat_map(event, 5)
        self.booking(event, seats[:2], amount_paid=Decimal('80'), at=day_start(today) + timedelta(minutes=1))
        self.booking(event, seats[2:3], amount_paid=Decimal('30'), at=day_start(today) - timedelta(seconds=1))
        self.booking(event, seats[3:], amount_paid=Decimal('99'), at=day_start(today - timedelta(days=60)))
        timeline = self.timeline(event)
        self.assertEqual((timeline[today.isoformat()]['tickets'], timeline[today.isoformat()]['revenue']), (2, 80.0))
        yesterday = timeline[(today - timedelta(days=1)).isoformat()]
        self.assertEqual((yesterday['tickets'], yesterday['revenue']), (1, 30.0))
        self.assertEqual(sum(d['tickets'] for d in timeline.values()), 3)

    def test_the_endpoint_serves_the_fixed_timeline(self):
        event = self.ev()
        self.reg(event, at=timezone.now() - timedelta(days=90))
        self.login()
        timeline = self.client.get(f'/api/v1/events/{event.id}/analytics/').data['timeline']
        self.assertEqual(len(timeline), 30)
        self.assertEqual(sum(d['tickets'] for d in timeline), 0)


class TicketTypeBreakdownTests(BatchABase):
    def rows(self, event):
        self.login()
        response = self.client.get(f'/api/v1/events/{event.id}/analytics/')
        self.assertEqual(response.status_code, 200)
        return {row['name']: row for row in response.data['by_ticket_type']}

    def test_quantity_and_remaining(self):
        event = self.ev(currency='KZT')
        limited = TicketType.objects.create(event=event, name='Limited', price=Decimal('10'), quantity=10)
        for status in ('confirmed', 'confirmed', 'confirmed', 'pending', 'cancelled', 'rejected'):
            registration = self.reg(event, status=status)
            registration.ticket_type = limited
            registration.save()
        row = self.rows(event)['Limited']
        self.assertEqual((row['count'], row['quantity'], row['remaining']), (3, 10, 6))  # 3 confirmed + 1 pending held
        self.assertEqual(row['remaining'], TicketType.objects.get(pk=limited.pk).available)

    def test_remaining_is_never_negative(self):
        event = self.ev()
        tight = TicketType.objects.create(event=event, name='Tight', price=Decimal('10'), quantity=2)
        for _ in range(4):
            registration = self.reg(event)
            registration.ticket_type = tight
            registration.save()
        row = self.rows(event)['Tight']
        self.assertEqual((row['quantity'], row['remaining']), (2, 0))

    def test_unlimited_tier_has_null_quantity_and_remaining(self):
        event = self.ev()
        free = TicketType.objects.create(event=event, name='Open', price=Decimal('0'), quantity=None)
        registration = self.reg(event)
        registration.ticket_type = free
        registration.save()
        row = self.rows(event)['Open']
        self.assertEqual((row['quantity'], row['remaining']), (None, None))

    def test_general_and_group_rows_have_nulls(self):
        event = self.ev(currency='KZT')
        self.pay(self.reg(event), 100)  # no tier
        self.booking(event, self.seat_map(event, 2), amount_paid=Decimal('60'))
        rows = self.rows(event)
        for name in ('General', 'Group booking'):
            self.assertEqual((rows[name]['quantity'], rows[name]['remaining']), (None, None), name)
        self.assertEqual(rows['Group booking']['count'], 2)
        self.assertEqual(set(rows['General']), {'name', 'count', 'revenue', 'quantity', 'remaining'})

    def test_two_tiers_sharing_a_name_are_two_rows(self):
        event = self.ev()
        first = TicketType.objects.create(event=event, name='Same', price=Decimal('1'), quantity=5)
        second = TicketType.objects.create(event=event, name='Same', price=Decimal('2'), quantity=8)
        for tier in (first, first, second):
            registration = self.reg(event)
            registration.ticket_type = tier
            registration.save()
        self.login()
        rows = self.client.get(f'/api/v1/events/{event.id}/analytics/').data['by_ticket_type']
        self.assertEqual(sorted((r['quantity'], r['remaining'], r['count']) for r in rows), [(5, 3, 2), (8, 7, 1)])


class TodayTests(BatchABase):
    def setUp(self):
        super().setUp()
        self.login()

    def titles_today(self):
        return [e['title'] for e in self.get(TODAY).data['results']]

    def test_selection_and_order(self):
        now = timezone.now()
        self.ev('Later', date=now + timedelta(days=6, hours=20))
        self.ev('Tomorrow', date=now + timedelta(days=1))
        self.ev('Running', date=now - timedelta(hours=1), end_date=now + timedelta(hours=2))
        self.ev('Pending soon', date=now + timedelta(hours=5), status='pending')
        self.ev('Beyond a week', date=now + timedelta(days=7, hours=2))
        self.ev('Over', date=now - timedelta(hours=5), end_date=now - timedelta(hours=1))
        self.ev('Started, no end', date=now - timedelta(hours=1))  # ends where it starts: over
        self.ev('Draft', date=now + timedelta(days=1), status='draft')
        self.ev('Cancelled', date=now + timedelta(days=1), status='cancelled')
        self.ev('Rejected', date=now + timedelta(days=1), status='rejected')
        self.ev('Completed', date=now - timedelta(hours=1), end_date=now + timedelta(hours=1), status='completed')
        self.assertEqual(self.titles_today(), ['Running', 'Pending soon', 'Tomorrow', 'Later'])

    def test_item_shape_and_numbers(self):
        now = timezone.now()
        running = self.ev(
            'Running', date=now - timedelta(hours=1), end_date=now + timedelta(hours=2), max_participants=120
        )
        self.reg(running, checked_in=True)
        self.reg(running)
        self.reg(running, status='pending')
        seats = self.seat_map(running, 3)
        self.booking(running, seats, checked=2)
        soon = self.ev('Soon', days=2, location='Hall 7')

        results = self.get(TODAY).data['results']
        self.assertEqual([r['id'] for r in results], [running.id, soon.id])
        first = results[0]
        self.assertEqual(
            set(first),
            {'id', 'title', 'date', 'end_date', 'location', 'status', 'is_owner', 'in_progress', 'stats'},
        )
        self.assertEqual(first['stats'], {'tickets_sold': 5, 'checked_in': 3, 'capacity': 120})
        self.assertEqual((first['status'], first['is_owner'], first['in_progress']), ('published', True, True))
        self.assertIsNotNone(first['end_date'])
        self.assertEqual(
            (results[1]['in_progress'], results[1]['end_date'], results[1]['location']), (False, None, 'Hall 7')
        )
        stats = dashboard.bulk_event_stats([running])[running.pk]
        self.assertEqual(first['stats']['tickets_sold'], stats['tickets_sold'])

    def test_the_seven_day_horizon(self):
        now = timezone.now()
        self.ev('Inside', date=now + timedelta(days=7) - timedelta(minutes=5))
        self.ev('Outside', date=now + timedelta(days=7) + timedelta(minutes=5))
        self.assertEqual(self.titles_today(), ['Inside'])

    def test_at_most_ten_and_more_counts_the_rest(self):
        now = timezone.now()
        for i in range(13):
            self.ev(f'E{i:02d}', date=now + timedelta(hours=1 + i))
        data = self.get(TODAY).data
        self.assertEqual([e['title'] for e in data['results']], [f'E{i:02d}' for i in range(10)])
        self.assertEqual(data['more'], 3)
        self.ev('E13', date=now + timedelta(hours=30))
        self.assertEqual(self.get(TODAY).data['more'], 4)

    def test_exactly_ten_has_no_more(self):
        now = timezone.now()
        for i in range(10):
            self.ev(f'E{i}', date=now + timedelta(hours=1 + i))
        data = self.get(TODAY).data
        self.assertEqual((len(data['results']), data['more']), (10, 0))

    def test_ties_are_ordered_by_id(self):
        date = timezone.now() + timedelta(days=1)
        first, second = self.ev('First', date=date), self.ev('Second', date=date)
        self.assertEqual([r['id'] for r in self.get(TODAY).data['results']], [first.id, second.id])


class ReviewsTests(BatchABase):
    def review(self, event, rating, comment='', user=None, at=None):
        review = Review.objects.create(user=user or self.new_user(), event=event, rating=rating, comment=comment)
        if at is not None:
            Review.objects.filter(pk=review.pk).update(created_at=at)
        return review

    def setUp(self):
        super().setUp()
        self.login()
        self.event = self.ev('Reviewed', days=-2)

    def test_count_average_and_distribution(self):
        for rating in (5, 5, 4, 3, 1):
            self.review(self.event, rating)
        data = self.get(REVIEWS).data
        self.assertEqual(data['count'], 5)
        self.assertEqual(data['average'], 3.6)
        self.assertEqual(data['distribution'], {'1': 1, '2': 0, '3': 1, '4': 1, '5': 2})

    def test_average_has_two_decimals(self):
        for rating in (5, 5, 4):
            self.review(self.event, rating)
        self.assertEqual(self.get(REVIEWS).data['average'], 4.67)
        other = self.ev('Other', days=-3)
        more = (5, 5, 5, 4, 4, 4, 4, 4, 5, 4, 4, 1)
        for rating in more:
            self.review(other, rating)
        data = self.get(REVIEWS).data
        self.assertEqual(data['count'], 15)
        self.assertEqual(data['average'], round((5 + 5 + 4 + sum(more)) / 15, 2))  # 4.2

    def test_the_five_keys_are_always_present(self):
        self.review(self.event, 2)
        self.assertEqual(list(self.get(REVIEWS).data['distribution']), ['1', '2', '3', '4', '5'])

    def test_recent_are_the_five_latest(self):
        now = timezone.now()
        for i in range(7):
            self.review(self.event, 1 + i % 5, comment=f'c{i}', at=now - timedelta(hours=7 - i))
        recent = self.get(REVIEWS).data['recent']
        self.assertEqual([r['comment'] for r in recent], ['c6', 'c5', 'c4', 'c3', 'c2'])
        self.assertEqual(self.get(REVIEWS).data['count'], 7)

    def test_recent_item_shape(self):
        author = self.new_user(first_name='Dias', last_name='A.')
        review = self.review(self.event, 5, comment='Great', user=author)
        item = self.get(REVIEWS).data['recent'][0]
        self.assertEqual(set(item), {'event_id', 'event_title', 'rating', 'comment', 'created_at', 'author'})
        self.assertEqual(
            (item['event_id'], item['event_title'], item['rating'], item['comment'], item['author']),
            (self.event.id, 'Reviewed', 5, 'Great', 'Dias A.'),
        )
        self.assertEqual(datetime.fromisoformat(item['created_at']), review.created_at)

    def test_author_is_never_an_email(self):
        by_username = self.new_user()
        by_username.username = 'someone@example.com'
        by_username.save()
        self.review(self.event, 4, user=by_username)
        self.review(self.event, 3, user=self.new_user(first_name='Zhan'))
        self.review(self.event, 2, user=self.new_user())  # username `buyerN`, email on file
        data = self.get(REVIEWS).data
        authors = {r['author'] for r in data['recent']}
        self.assertEqual(authors, {'someone', 'Zhan', 'buyer3'})
        self.assertNotIn('@', json.dumps(data))
        self.assertNotIn('example.com', json.dumps(data))

    def test_blank_comment_and_other_organizers_reviews(self):
        self.review(self.event, 3)
        foreign = self.make_event(title='Foreign', organizer=self.make_user('org2', role='organizer'))
        self.review(foreign, 1, comment='not mine')
        data = self.get(REVIEWS).data
        self.assertEqual(data['count'], 1)
        self.assertEqual([r['comment'] for r in data['recent']], [''])
        self.assertEqual(data['distribution']['1'], 0)

    def test_co_organized_event_reviews_are_included(self):
        foreign = self.make_event(title='Shared', organizer=self.make_user('org2', role='organizer'))
        EventStaff.objects.create(event=foreign, user=self.organizer, role=EventStaff.ROLE_CO_ORGANIZER)
        self.review(foreign, 5, comment='shared')
        self.assertEqual([r['comment'] for r in self.get(REVIEWS).data['recent']], ['shared'])
