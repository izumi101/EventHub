"""Revenue is counted on the day the money arrived (`Payment.paid_at`,
`Booking.confirmed_at`), not on the day the checkout or the hold started."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from bookings.models import Booking
from events import sales_chart
from events.analytics import event_analytics
from events.business_time import local_date, local_today
from events.models import Registration
from events.test_organizer_batch_a import BatchABase, utc
from payments.models import Payment
from payments.services import mark_offline_paid


class SalesRevenueDayTests(BatchABase):
    NOW = utc(11, 15, 12)  # 17:00 on 15 Nov in Almaty

    def series(self):
        return sales_chart.sales_series(self.organizer, '7d', now=self.NOW)

    def test_an_offline_payment_created_on_day_1_and_marked_paid_on_day_3_counts_on_day_3(self):
        event = self.ev(currency='KZT')
        created = timezone.now() - timedelta(days=2)
        registration = self.reg(event, status='pending', at=created)
        payment = Payment.objects.create(registration=registration, amount=Decimal('999'), currency='kzt')
        Payment.objects.filter(pk=payment.pk).update(created_at=created)

        mark_offline_paid(registration=registration, amount='250')

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'completed')
        self.assertEqual(payment.created_at, created)
        self.assertGreater(payment.paid_at, created + timedelta(days=1, hours=23))
        self.login()
        data = self.sales(range='7d').data
        money = self.revenue_by_day(data, 'KZT')
        today, started = local_today(), local_date(created)
        self.assertEqual(money[today.isoformat()], Decimal('250.00'))
        self.assertEqual(money[started.isoformat()], Decimal('0.00'))
        self.assertEqual(sum(money.values()), Decimal('250.00'))
        # The ticket (a registration) is still counted on the day it was made.
        self.assertEqual(self.tickets_by_day(data)[started.isoformat()], 1)
        self.assertEqual(self.tickets_by_day(data)[today.isoformat()], 0)

    def test_a_checkout_spanning_midnight_counts_on_the_paying_day(self):
        event = self.ev(currency='KZT')
        started = utc(11, 10, 18, 55)  # 23:55 on the 10th in Almaty
        paid = utc(11, 10, 19, 5)  # 00:05 on the 11th
        registration = self.reg(event, at=started)
        self.pay_at(registration, 300, started, paid_at=paid, currency='kzt')
        data = self.series()
        money = {day: amount for day, amount in self.revenue_by_day(data, 'KZT').items() if amount}
        self.assertEqual(money, {'2026-11-11': Decimal('300.00')})
        self.assertEqual(self.tickets_by_day(data)['2026-11-10'], 1)

    def test_a_payment_that_never_arrived_has_no_revenue_day(self):
        event = self.ev(currency='KZT')
        registration = self.reg(event, status='pending', at=utc(11, 12, 8))
        self.pay_at(registration, 300, utc(11, 12, 8), status='pending', currency='kzt')
        self.assertEqual(self.series()['revenue'], [])

    def test_a_group_booking_confirmed_after_midnight_counts_on_the_confirmation_day(self):
        event = self.ev(currency='KZT')
        seats = self.seat_map(event, 2)
        self.booking(
            event,
            seats,
            amount_paid=Decimal('80'),
            at=utc(11, 10, 18, 55),  # held at 23:55 on the 10th
            confirmed_at=utc(11, 10, 19, 5),  # paid at 00:05 on the 11th
        )
        data = self.series()
        self.assertEqual(self.tickets_by_day(data)['2026-11-10'], 2)
        money = {day: amount for day, amount in self.revenue_by_day(data, 'KZT').items() if amount}
        self.assertEqual(money, {'2026-11-11': Decimal('80.00')})

    def test_an_unpriced_booking_is_dated_by_its_confirmation_too(self):
        event = self.ev(currency='KZT')
        self.booking(
            event,
            self.seat_map(event, 1),
            amount_paid=None,
            price=100,
            at=utc(11, 10, 18, 55),
            confirmed_at=utc(11, 11, 8),
        )
        money = {day: amount for day, amount in self.revenue_by_day(self.series(), 'KZT').items() if amount}
        self.assertEqual(money, {'2026-11-11': Decimal('100.00')})

    def test_a_booking_that_is_still_holding_has_no_money(self):
        event = self.ev(currency='KZT')
        self.booking(event, self.seat_map(event, 1), status='holding', amount_paid=Decimal('80'), at=utc(11, 12, 8))
        self.assertEqual(self.series()['revenue'], [])


class TimelineRevenueDayTests(BatchABase):
    def test_timeline_money_follows_paid_at_and_tickets_follow_registered_at(self):
        event = self.ev(currency='KZT')
        today = local_today()
        registered = timezone.now() - timedelta(days=3)
        paid = timezone.now() - timedelta(hours=1)
        registration = self.reg(event, at=registered)
        self.pay_at(registration, 400, registered, paid_at=paid, currency='kzt')
        timeline = {d['date']: d for d in event_analytics(event)['timeline']}
        day_registered, day_paid = local_date(registered).isoformat(), local_date(paid).isoformat()
        self.assertEqual((timeline[day_registered]['tickets'], timeline[day_registered]['revenue']), (1, 0.0))
        self.assertEqual(timeline[day_paid]['revenue'], 400.0)
        self.assertEqual(sum(d['revenue'] for d in timeline.values()), 400.0)
        self.assertEqual(today.isoformat(), max(timeline))

    def test_timeline_booking_money_is_dated_by_confirmation(self):
        event = self.ev(currency='KZT')
        created = timezone.now() - timedelta(days=4)
        confirmed = timezone.now() - timedelta(days=2)
        self.booking(event, self.seat_map(event, 2), amount_paid=Decimal('70'), at=created, confirmed_at=confirmed)
        timeline = {d['date']: d for d in event_analytics(event)['timeline']}
        self.assertEqual(timeline[local_date(created).isoformat()]['tickets'], 2)
        self.assertEqual(timeline[local_date(created).isoformat()]['revenue'], 0.0)
        self.assertEqual(timeline[local_date(confirmed).isoformat()]['revenue'], 70.0)

    def test_an_unpaid_payment_adds_no_timeline_money(self):
        event = self.ev(currency='KZT')
        registration = self.reg(event)
        Payment.objects.create(registration=registration, amount=Decimal('50'), currency='kzt')  # pending
        self.assertEqual(sum(d['revenue'] for d in event_analytics(event)['timeline']), 0.0)
        self.assertEqual(Registration.objects.filter(event=event).count(), 1)


class RollbackToleranceTests(BatchABase):
    """Old code (a code-only rollback) completes payments and confirms bookings
    without the new columns; revenue must still count them, on `created_at`."""

    NOW = utc(11, 15, 12)

    def series(self):
        return sales_chart.sales_series(self.organizer, '7d', now=self.NOW)

    def test_a_completed_payment_without_paid_at_counts_on_its_created_at_day(self):
        event = self.ev(currency='KZT')
        for status in ('completed', 'refunded'):
            registration = self.reg(event, at=utc(11, 12, 8))
            payment = self.pay_at(registration, 300, utc(11, 12, 8), status=status, currency='kzt')
            Payment.objects.filter(pk=payment.pk).update(paid_at=None)  # written by the previous release
        money = {day: amount for day, amount in self.revenue_by_day(self.series(), 'KZT').items() if amount}
        self.assertEqual(money, {'2026-11-12': Decimal('600.00')})

    def test_a_paid_at_wins_over_created_at(self):
        event = self.ev(currency='KZT')
        registration = self.reg(event, at=utc(11, 10, 8))
        self.pay_at(registration, 300, utc(11, 10, 8), paid_at=utc(11, 13, 8), currency='kzt')
        money = {day: amount for day, amount in self.revenue_by_day(self.series(), 'KZT').items() if amount}
        self.assertEqual(money, {'2026-11-13': Decimal('300.00')})

    def test_a_confirmed_booking_without_confirmed_at_counts_on_its_created_at_day(self):
        event = self.ev(currency='KZT')
        seats = self.seat_map(event, 2)
        booking = self.booking(event, seats[:1], amount_paid=Decimal('80'), at=utc(11, 12, 8))
        unpriced = self.booking(event, seats[1:], amount_paid=None, price=100, at=utc(11, 13, 8))
        Booking.objects.filter(pk__in=[booking.pk, unpriced.pk]).update(confirmed_at=None)
        money = {day: amount for day, amount in self.revenue_by_day(self.series(), 'KZT').items() if amount}
        self.assertEqual(money, {'2026-11-12': Decimal('80.00'), '2026-11-13': Decimal('100.00')})

    def test_the_timeline_tolerates_the_missing_columns_too(self):
        event = self.ev(currency='KZT')
        when = timezone.now() - timedelta(days=2)
        payment = self.pay_at(self.reg(event, at=when), 400, when, currency='kzt')
        Payment.objects.filter(pk=payment.pk).update(paid_at=None)
        booking = self.booking(event, self.seat_map(event, 1), amount_paid=Decimal('70'), at=when)
        Booking.objects.filter(pk=booking.pk).update(confirmed_at=None)
        timeline = {d['date']: d for d in event_analytics(event)['timeline']}
        self.assertEqual(timeline[local_date(when).isoformat()]['revenue'], 470.0)
