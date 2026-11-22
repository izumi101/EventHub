"""seed_demo_kz on a public demo deployment (docs/DEMO_DATA.md): the content, its
consistency with the app's own numbers, the demo-mode guards, removal, and the
safety of refunding demo payments with the payment mocks off.
"""

# ruff: noqa: RUF001 - the review comments are checked in Russian and Kazakh
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import textwrap
from collections import Counter
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import UserProfile
from bookings.models import Booking, BookingSeat
from common import demo_seed
from common.sql_checks import DjangoConnectionExecutor, load_checks, run_checks
from events import dashboard
from events.demo_kz_data import CITIES, EVENTS, KZ_TZ, ORGANIZERS, PHONE_PREFIXES, STAFF, TITLES
from events.management.commands import seed_showcase
from events.models import (
    Affiliate,
    Category,
    CheckInList,
    CheckInLog,
    Event,
    EventSeat,
    EventStaff,
    Notification,
    PromoCode,
    RefundRequest,
    Registration,
    Review,
    SeatMap,
    TicketType,
    WaitlistEntry,
)
from events.services.lifecycle import cancel_event
from events.services.refunds import resolve_refund_request
from jobs.models import Job
from mfa.testing import authenticate_with_recent_mfa
from notifications import types
from notifications.service import notify
from payments.models import Payment, Refund

OWNER = 'real_owner'


def run_demo(*args, **kwargs):
    out, err = StringIO(), StringIO()
    call_command('seed_demo_kz', *args, stdout=out, stderr=err, **kwargs)
    return out.getvalue(), err.getvalue()


def critical_findings():
    results = run_checks(load_checks(), DjangoConnectionExecutor())
    return {
        r.check.name: (r.error or r.rows[:3]) for r in results if (r.rows or r.error) and r.check.severity == 'CRITICAL'
    }


def all_findings():
    results = run_checks(load_checks(), DjangoConnectionExecutor())
    return {r.check.name: (r.error or r.rows[:3]) for r in results if r.rows or r.error}


def model_counts(*models):
    return {model.__name__: model.objects.count() for model in models}


class SpecTests(SimpleTestCase):
    """The 60 hand-written events, as data."""

    def test_sixty_events_with_unique_keys_and_titles(self):
        self.assertEqual(len(EVENTS), 60)
        self.assertEqual(len({s['key'] for s in EVENTS}), 60)
        self.assertEqual(len(TITLES), 60)

    def test_titles_never_reuse_another_seed_commands_titles(self):
        showcase = {spec.title for spec in seed_showcase.EVENTS}
        self.assertEqual(len(showcase), 18)
        self.assertEqual(TITLES & showcase, set())
        # seed_data's four events.
        self.assertEqual(
            TITLES
            & {
                'Angular Meetup Almaty',
                'Startup Pitch Night',
                'Online Django REST Workshop',
                'Almaty Product Conference',
            },
            set(),
        )

    def test_the_time_and_status_table_of_the_doc(self):
        def group(spec):
            status = spec.get('status')
            if status:
                return status
            if 'offset_minutes' in spec:
                return 'today'
            return 'past' if spec['days'] < 0 else 'upcoming'

        counts = Counter(group(s) for s in EVENTS)
        self.assertEqual(
            counts,
            {'past': 25, 'today': 3, 'upcoming': 22, 'draft': 3, 'pending': 3, 'rejected': 2, 'cancelled': 2},
        )
        for spec in EVENTS:
            if 'days' in spec:
                self.assertLessEqual(spec['days'], 100)  # nothing further than a few months out

    def test_a_third_of_the_events_belong_to_the_organizer_and_two_are_co_organized(self):
        self.assertEqual(sum(1 for s in EVENTS if s.get('mine')), 20)
        self.assertEqual(sum(1 for s in EVENTS if s.get('owner_coorg')), 2)
        for spec in EVENTS:
            self.assertFalse(spec.get('mine') and spec.get('owner_coorg'))
            # Demo accounts never get power over the real organizer's events.
            self.assertFalse(spec.get('mine') and spec.get('coorg'))

    def test_every_format_of_the_doc_is_covered(self):
        layouts = {s['layout'] for s in EVENTS}
        self.assertEqual(layouts, {'seated', 'chamber', 'tiers', 'ga', 'free'})
        kinds = {t['kind'] for s in EVENTS for t in s.get('tiers', [])}
        self.assertEqual(kinds, {'paid', 'free', 'donation'})
        self.assertTrue(any(t['sale_end_days'] for s in EVENTS for t in s.get('tiers', [])))  # early bird
        self.assertTrue(any(s.get('online') for s in EVENTS))
        self.assertTrue(any(s.get('bookings') for s in EVENTS))
        self.assertTrue(any(s.get('promo') for s in EVENTS))
        self.assertTrue(any(s.get('affiliate') for s in EVENTS))
        self.assertTrue(any(s.get('waitlist') for s in EVENTS))
        self.assertEqual(
            {s['city'] for s in EVENTS if not s.get('online')} - {'Almaty', 'Astana', 'Shymkent', 'Karaganda'}, set()
        )
        self.assertEqual(
            {s['category'] for s in EVENTS}, {'Music', 'Technology', 'Business', 'Education', 'Sports', 'Theatre'}
        )


@override_settings(DEBUG=True)
class SeededDemoTests(TestCase):
    """One full seed (DEBUG=1, with `--organizer`), then everything the contract says about it."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(OWNER, 'owner@example.com', 'Real-owner-pass-1!')
        cls.owner.profile.role = 'organizer'
        cls.owner.profile.save()
        cls.real_att = User.objects.create_user('real_attendee', 'att@example.com', 'Real-att-pass-1!')
        cls.admin = User.objects.create_superuser('real_admin', 'admin@example.com', 'Real-admin-pass-1!')
        category = Category.objects.create(name='Real category')
        cls.real_event = Event.objects.create(
            title='Real Owner Event',
            description='Not demo data.',
            organizer=cls.owner,
            category=category,
            date=timezone.now() + timedelta(days=9),
            location='Real hall',
            price=Decimal('1000.00'),
            currency='KZT',
            max_participants=10,
            status='published',
        )
        cls.real_reg = Registration.objects.create(user=cls.real_att, event=cls.real_event, status='confirmed')
        cls.real_payment = Payment.objects.create(
            registration=cls.real_reg,
            amount=Decimal('1000.00'),
            currency='kzt',
            status='completed',
            provider='freedompay',
            provider_session_id='real-session',
            provider_payment_id='real-pay-1',
        )
        EventStaff.objects.create(event=cls.real_event, user=cls.real_att, role='check_in')
        cls.now = timezone.now()
        cls.output, _ = run_demo('--organizer', OWNER)
        cls.demo_users = User.objects.filter(username__startswith='kz_')

    # ------------------------------------------------------------ people ---- #

    def test_the_accounts(self):
        organizers = User.objects.filter(profile__role='organizer', username__startswith='kz_')
        self.assertEqual(organizers.count(), len(ORGANIZERS))
        staff = User.objects.filter(username__startswith='kz_staff.')
        self.assertEqual(staff.count(), len(STAFF))
        attendees = self.demo_users.exclude(pk__in=organizers).exclude(pk__in=staff)
        self.assertEqual(attendees.count(), 760)
        for user in self.demo_users:
            self.assertTrue(user.email.endswith('@demo.eventhub.local'))
            self.assertTrue(user.check_password('password123'))  # DEBUG=1 keeps the development password
        self.assertEqual(
            set(UserProfile.objects.filter(user__in=attendees).values_list('role', flat=True)), {'attendee'}
        )

    def test_cities_phones_and_signup_dates(self):
        attendees = UserProfile.objects.filter(user__username__startswith='kz_', role='attendee').exclude(
            user__username__startswith='kz_staff.'
        )
        cities = Counter(attendees.values_list('location', flat=True))
        self.assertEqual(set(cities), {name for name, _ in CITIES})
        self.assertEqual(cities.most_common(1)[0][0], 'Almaty')
        self.assertGreater(cities['Almaty'], cities['Astana'])
        self.assertGreater(cities['Astana'], cities['Shymkent'])
        for phone in attendees.values_list('phone', flat=True):
            self.assertRegex(phone, r'^\+7 \d{3} \d{3} \d{2} \d{2}$')
            self.assertIn(phone.split()[1], PHONE_PREFIXES)
        joined = list(User.objects.filter(profile__in=attendees).values_list('date_joined', flat=True))
        self.assertLessEqual(max(self.now - d for d in joined), timedelta(days=430))
        self.assertGreater(max(self.now - d for d in joined), timedelta(days=330))  # over a year of sign-ups
        recent = sum(1 for d in joined if self.now - d < timedelta(days=183))
        self.assertGreater(recent / len(joined), 0.55)  # a growing platform
        # A profile is as old as its account.
        profile = attendees.select_related('user').first()
        self.assertEqual(profile.created_at, profile.user.date_joined)

    def test_names_have_matching_surname_forms(self):
        from events.demo_kz_data import FEMALE_FIRST, MALE_FIRST, SURNAMES

        female_last = {f for _, f in SURNAMES}
        male_last = {m for m, _ in SURNAMES}
        people = self.demo_users.exclude(username__startswith='kz_staff.')
        for user in people.filter(first_name__in=FEMALE_FIRST)[:200]:
            self.assertIn(user.last_name, female_last)
        for user in people.filter(first_name__in=MALE_FIRST)[:200]:
            self.assertIn(user.last_name, male_last)
        self.assertEqual(set(FEMALE_FIRST) & set(MALE_FIRST), set())

    # ------------------------------------------------------------ events ---- #

    def test_sixty_events_in_the_time_and_status_table(self):
        events = Event.objects.filter(title__in=TITLES)
        self.assertEqual(events.count(), 60)
        by_status = Counter(events.values_list('status', flat=True))
        now = timezone.now()
        today = events.filter(status='published', date__lt=now + timedelta(days=1)).count()
        upcoming = events.filter(status='published', date__gte=now + timedelta(days=1)).count()
        self.assertEqual(by_status['completed'], 25)
        self.assertEqual(today, 3)
        self.assertEqual(upcoming, 22)
        self.assertEqual((by_status['draft'], by_status['pending'], by_status['rejected']), (3, 3, 2))
        self.assertEqual(by_status['cancelled'], 2)
        # None left "published" after its end: the worker would complete it within a minute.
        self.assertFalse(events.filter(status='published', end_date__lt=now).exists())
        self.assertEqual(events.filter(status='published', date__lt=now, end_date__gt=now).count(), 2)  # in progress
        far = events.filter(status='published').order_by('-date').first()
        self.assertLess(far.date - now, timedelta(days=91))
        # Every event is in tenge and has an address, except the online ones.
        self.assertEqual(set(events.values_list('currency', flat=True)), {'KZT'})
        for event in events.filter(is_online=False):
            self.assertTrue(event.address, event.title)
        self.assertEqual(events.filter(is_online=True).count(), sum(1 for s in EVENTS if s.get('online')))

    def test_the_organizer_owns_a_third_and_co_organizes_two(self):
        mine = Event.objects.filter(organizer=self.owner, title__in=TITLES)
        self.assertEqual(mine.count(), 20)
        self.assertEqual(set(mine.values_list('title', flat=True)), {s['title'] for s in EVENTS if s.get('mine')})
        co = EventStaff.objects.filter(user=self.owner, role='co_organizer')
        self.assertEqual(co.count(), 2)
        for row in co.select_related('event__organizer'):
            self.assertTrue(row.event.organizer.username.startswith('kz_'))
        # The real event of the organizer is untouched.
        self.real_event.refresh_from_db()
        self.assertEqual(self.real_event.title, 'Real Owner Event')
        self.assertEqual(Event.objects.filter(organizer=self.owner).count(), 21)
        self.assertEqual(
            sorted(dashboard.managed_events(self.owner).filter(title__in=TITLES).values_list('pk', flat=True)),
            sorted(set(mine.values_list('pk', flat=True)) | set(co.values_list('event_id', flat=True))),
        )

    def test_the_organizer_never_holds_a_ticket_scans_or_reviews(self):
        owner = self.owner
        self.assertFalse(Registration.objects.filter(user=owner).exists())
        self.assertFalse(Booking.objects.filter(owner=owner).exists())
        self.assertFalse(BookingSeat.objects.filter(claimed_by=owner).exists())
        self.assertFalse(Review.objects.filter(user=owner).exists())
        self.assertFalse(WaitlistEntry.objects.filter(user=owner).exists())
        self.assertFalse(CheckInLog.objects.filter(scanned_by=owner).exists())
        self.assertFalse(EventStaff.objects.filter(user=owner, role='check_in').exists())
        self.assertEqual(critical_findings(), {})  # includes organizer_ticket_for_own_event

    def test_demo_organizers_never_hold_tickets_or_run_events_of_the_real_organizer(self):
        organizers = User.objects.filter(profile__role='organizer', username__startswith='kz_')
        ids = list(organizers.values_list('pk', flat=True))  # ids first: a subquery plans badly on fresh data
        self.assertFalse(Registration.objects.filter(user_id__in=ids).exists())
        self.assertFalse(Booking.objects.filter(owner_id__in=ids).exists())
        # Check-in staff scan at the organizer's events, but no demo account co-runs them.
        self.assertFalse(
            EventStaff.objects.filter(
                event__organizer=self.owner, user__in=self.demo_users, role='co_organizer'
            ).exists()
        )

    def test_gates_and_check_in_staff(self):
        lists = CheckInList.objects.filter(event__title__in=TITLES)
        self.assertGreater(lists.values('event').distinct().count(), 30)
        for event_id in lists.values_list('event_id', flat=True).distinct():
            staff = EventStaff.objects.filter(event_id=event_id, role='check_in')
            self.assertGreaterEqual(staff.count(), 2, event_id)
            for row in staff.select_related('user'):
                self.assertTrue(row.user.username.startswith('kz_staff.'))
        self.assertFalse(
            CheckInList.objects.filter(event__status__in=['cancelled', 'draft', 'pending', 'rejected']).exists()
        )
        # Every scan is logged with someone who may scan at that event.
        allowed = 0
        staff_of = set(EventStaff.objects.filter(role='check_in').values_list('event_id', 'user_id'))
        for log in CheckInLog.objects.select_related('checkin_list__event', 'registration')[:3000]:
            event = log.checkin_list.event
            self.assertEqual(log.registration.event_id, event.id)
            self.assertTrue(
                log.scanned_by_id == event.organizer_id or (event.id, log.scanned_by_id) in staff_of,
                (event.title, log.scanned_by_id),
            )
            allowed += 1
        self.assertGreater(allowed, 1000)
        scanners = CheckInLog.objects.values('scanned_by').distinct().count()
        self.assertGreater(scanners, 8)

    def test_every_event_has_a_main_gate_and_a_vip_gate_where_it_has_vip_tickets(self):
        for event in Event.objects.filter(title__in=TITLES, status__in=['published', 'completed']):
            if not event.registrations.exists() and not event.bookings.exists():
                continue
            self.assertEqual(event.checkin_lists.filter(is_default=True).count(), 1, event.title)

    # -------------------------------------------------------- consistency ---- #

    def test_data_checks_report_nothing(self):
        self.assertEqual(critical_findings(), {})
        self.assertEqual(all_findings(), {})

    def test_no_jobs_and_no_notifications_are_created(self):
        self.assertEqual(Job.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_dashboard_numbers_equal_the_event_analytics(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        events = list(
            Event.objects.filter(title__in=TITLES, status__in=['published', 'completed', 'cancelled'])
            .exclude(registrations=None)
            .order_by('pk')
        )
        sample = events[::3]
        self.assertGreaterEqual(len(sample), 15)
        stats = dashboard.bulk_event_stats(sample)
        for event in sample:
            kpis = client.get(f'/api/v1/events/{event.id}/analytics/').data['kpis']
            row = stats[event.pk]
            self.assertEqual(row['tickets_sold'], kpis['tickets_sold'], event.title)
            self.assertEqual(row['checked_in'], kpis['checked_in'], event.title)
            self.assertEqual(row['pending'], kpis['pending'], event.title)
            self.assertEqual(row['capacity'], kpis['capacity'], event.title)
            self.assertEqual(row['sold_through_pct'], kpis['sold_through_pct'], event.title)
            self.assertEqual(row['checkin_rate_pct'], kpis['checkin_rate_pct'], event.title)
            self.assertEqual(
                Decimal(row['net_revenue']), Decimal(str(kpis['net_revenue'])).quantize(Decimal('0.01')), event.title
            )

    def test_the_organizers_dashboard_adds_up_over_its_events(self):
        summary = dashboard.dashboard_summary(self.owner)
        managed = list(dashboard.managed_events(self.owner))
        stats = dashboard.bulk_event_stats(managed)
        self.assertEqual(summary['tickets_sold'], sum(s['tickets_sold'] for s in stats.values()))
        self.assertEqual(summary['checked_in'], sum(s['checked_in'] for s in stats.values()))
        self.assertEqual(len(managed), 20 + 2 + 1)  # own demo events, co-organized ones, the real event
        self.assertGreater(summary['tickets_sold'], 500)

    def test_a_second_run_creates_nothing(self):
        models = (
            User, UserProfile, Event, EventSeat, SeatMap, TicketType, Registration, Payment, Refund, RefundRequest,
            Booking, BookingSeat, CheckInList, CheckInLog, EventStaff, Review, WaitlistEntry, PromoCode, Affiliate,
            Category, Job, Notification,
        )  # fmt: skip
        before = model_counts(*models)
        output, _ = run_demo('--organizer', OWNER)
        self.assertEqual(model_counts(*models), before)
        self.assertIn('0 events created, 60 already present', output)

    def test_a_run_without_the_organizer_after_one_with_it_creates_no_duplicates(self):
        before = Event.objects.count()
        run_demo()
        self.assertEqual(Event.objects.count(), before)

    # ----------------------------------------------------- sales and money ---- #

    def test_the_volume(self):
        self.assertGreater(Registration.objects.filter(event__title__in=TITLES).count(), 4000)
        self.assertEqual(
            set(Registration.objects.values_list('status', flat=True).distinct()), {'pending', 'confirmed', 'cancelled'}
        )
        self.assertGreater(Booking.objects.count(), 30)
        self.assertEqual(
            set(Booking.objects.values_list('status', flat=True)), {'confirmed', 'holding', 'expired', 'refunded'}
        )

    def test_payment_outcomes(self):
        payments = Payment.objects.filter(provider='mock')
        statuses = Counter(payments.values_list('status', flat=True))
        self.assertEqual(set(statuses), {'completed', 'pending', 'failed', 'expired', 'refunded', 'disputed'})
        self.assertEqual(Payment.objects.exclude(provider__in=['mock', 'freedompay']).count(), 0)
        self.assertTrue(payments.filter(status='completed', refunded_amount__gt=0).exists())  # partial refunds
        self.assertGreaterEqual(statuses['disputed'], 3)
        self.assertLessEqual(statuses['disputed'], 10)  # a handful
        reasons = Counter(
            p['failure'] for p in payments.filter(status='failed').values_list('provider_payload', flat=True)
        )
        self.assertEqual(set(reasons), {'card_declined', 'insufficient_funds'})
        self.assertGreater(reasons['card_declined'], reasons['insufficient_funds'])
        # Money arrived the day the payment says it did.
        for payment in payments.filter(status__in=['completed', 'refunded', 'disputed'])[:500]:
            self.assertIsNotNone(payment.paid_at)
            self.assertGreaterEqual(payment.paid_at, payment.created_at)
        for booking in Booking.objects.filter(status__in=['confirmed', 'refunded']):
            self.assertIsNotNone(booking.confirmed_at)

    def test_refund_requests_in_every_state(self):
        states = Counter(RefundRequest.objects.values_list('status', flat=True))
        self.assertEqual(set(states), {'pending', 'approved', 'rejected'})
        self.assertGreaterEqual(states['pending'], 5)
        for request in RefundRequest.objects.select_related('registration__payment', 'registration__event'):
            registration = request.registration
            if request.status == 'pending':
                self.assertEqual(registration.status in ('pending', 'confirmed'), True)
                self.assertGreater(registration.event.date, timezone.now())  # only for upcoming events
                self.assertFalse(registration.is_checked_in)
            elif request.status == 'approved':
                self.assertEqual(registration.status, 'cancelled')
                self.assertEqual(registration.payment.status, 'refunded')
                self.assertIsNotNone(request.resolved_at)
            else:
                self.assertEqual(registration.status, 'confirmed')
                self.assertIsNotNone(request.resolved_at)
                self.assertGreater(request.resolved_at, request.created_at)

    def test_cancelled_events_refunded_every_buyer(self):
        for event in Event.objects.filter(status='cancelled', title__in=TITLES):
            regs = event.registrations.all()
            self.assertTrue(regs.exists())
            self.assertFalse(regs.exclude(status='cancelled').exists())
            paid = Payment.objects.filter(registration__event=event)
            self.assertTrue(paid.exists())
            self.assertEqual(set(paid.values_list('status', flat=True)), {'refunded'})
            self.assertEqual(
                set(Refund.objects.filter(payment__in=paid).values_list('kind', flat=True)), {'event_cancelled'}
            )

    def test_pending_holds_exist_only_for_upcoming_events_and_are_short_lived(self):
        now = timezone.now()
        holds = Registration.objects.filter(status='pending')
        self.assertTrue(holds.exists())
        self.assertLessEqual(holds.count(), 12)
        for hold in holds.select_related('event'):
            self.assertEqual(hold.event.status, 'published')
            self.assertGreater(hold.event.date, now)
            self.assertLess(now - hold.registered_at, timedelta(minutes=10))
            self.assertGreater(hold.seat_held_until, now - timedelta(minutes=1))
        for booking in Booking.objects.filter(status='holding'):
            self.assertGreater(booking.event.date, now)
            self.assertLess(now - booking.created_at, timedelta(minutes=10))
        self.assertEqual(
            Payment.objects.filter(status='pending', registration__status='pending').count(), holds.count()
        )

    def test_sales_follow_the_calendar(self):
        """An early-bird burst, a quiet middle, a rise in the last week, a few on the day; evenings and lunch busy."""
        past = Event.objects.filter(status='completed', title__in=TITLES, registrations__isnull=False).distinct()
        first_week = middle_week = last_week = week_before = on_the_day = total = 0
        for event in past:
            times = sorted(event.registrations.exclude(status='pending').values_list('registered_at', flat=True))
            if len(times) < 60 or (event.date - times[0]) < timedelta(days=40):
                continue
            opened = times[0]
            first_week += sum(1 for t in times if t < opened + timedelta(days=7))
            middle_week += sum(1 for t in times if opened + timedelta(days=21) <= t < opened + timedelta(days=28))
            last_week += sum(1 for t in times if event.date - timedelta(days=7) <= t < event.date)
            week_before += sum(
                1 for t in times if event.date - timedelta(days=14) <= t < event.date - timedelta(days=7)
            )
            on_the_day += sum(1 for t in times if t.astimezone(KZ_TZ).date() == event.date.astimezone(KZ_TZ).date())
            total += len(times)
        self.assertGreater(total, 1000)
        self.assertGreater(first_week, 2 * middle_week)
        self.assertGreater(last_week, 2 * week_before)
        self.assertGreater(on_the_day / total, 0.005)
        self.assertLess(on_the_day / total, 0.2)

        hours = Counter(
            t.astimezone(KZ_TZ).hour
            for t in Registration.objects.exclude(status='pending').values_list('registered_at', flat=True)
        )
        everything = sum(hours.values())
        night = sum(hours[h] for h in range(6))
        busy = sum(hours[h] for h in (12, 13, 14, 18, 19, 20, 21, 22))
        self.assertLess(night / everything, 0.05)
        self.assertGreater(busy / everything, 0.5)

    def test_early_bird_tickets_were_sold_inside_their_window(self):
        for ticket_type in TicketType.objects.filter(sale_end__isnull=False, event__title__in=TITLES):
            regs = ticket_type.registrations.all()
            self.assertTrue(regs.exists(), ticket_type)
            self.assertFalse(regs.filter(registered_at__gt=ticket_type.sale_end).exists(), ticket_type)
            self.assertLess(ticket_type.sale_end, ticket_type.event.date)

    def test_nobody_buys_before_signing_up(self):
        for registration in Registration.objects.filter(event__title__in=TITLES).select_related('user')[:6000]:
            self.assertGreaterEqual(registration.registered_at, registration.user.date_joined)

    def test_reviews_come_from_attendees_of_past_events(self):
        reviews = Review.objects.all()
        self.assertGreater(reviews.count(), 200)
        ratings = Counter(reviews.values_list('rating', flat=True))
        self.assertGreater((ratings[4] + ratings[5]) / reviews.count(), 0.75)  # mostly 4-5 stars
        self.assertTrue(all(ratings[star] for star in (1, 2, 3)))  # a few critical ones
        now = timezone.now()
        for review in reviews.select_related('event', 'user')[:1500]:
            self.assertLess(review.event.end_date, now)
            self.assertGreaterEqual(review.created_at, review.event.end_date)
            self.assertTrue(
                Registration.objects.filter(
                    user=review.user, event=review.event, status='confirmed', is_checked_in=True
                ).exists()
            )
        comments = ' '.join(reviews.values_list('comment', flat=True))
        self.assertRegex(comments, r'[А-Яа-я]')  # Russian
        self.assertRegex(comments, r'[әғқңөұүһіӘҒҚҢӨҰҮҺІ]')  # Kazakh
        self.assertRegex(comments, r'[A-Za-z]{4}')  # English

    def test_group_bookings_promo_codes_affiliates_and_waitlists(self):
        self.assertTrue(PromoCode.objects.filter(times_used__gt=0).exists())
        self.assertTrue(Affiliate.objects.filter(registrations__isnull=False).exists())
        self.assertEqual(
            set(WaitlistEntry.objects.values_list('status', flat=True)), {'waiting', 'expired', 'offered', 'converted'}
        )
        for entry in WaitlistEntry.objects.select_related('user'):
            self.assertGreaterEqual(entry.created_at, entry.user.date_joined)
        self.assertTrue(Event.objects.filter(waitlist__isnull=False, title__in=TITLES).exists())

    # ----------------------------------------------------------- removal ---- #

    def snapshot_of_real_data(self):
        return {
            'users': sorted(
                User.objects.exclude(username__startswith='kz_').values_list('pk', 'username', 'password', 'email')
            ),
            'event': list(Event.objects.filter(pk=self.real_event.pk).values()),
            'registration': list(Registration.objects.filter(pk=self.real_reg.pk).values()),
            'payment': list(Payment.objects.filter(pk=self.real_payment.pk).values()),
            'staff': list(EventStaff.objects.filter(event=self.real_event).values()),
        }

    # Models the seed fills and nothing real puts rows in (in these tests).
    DEMO_ONLY = (
        EventSeat, SeatMap, TicketType, Refund, RefundRequest, Booking, BookingSeat, CheckInList, CheckInLog,
        Review, WaitlistEntry, PromoCode, Affiliate,
    )  # fmt: skip
    ALL = (
        User, Event, EventSeat, SeatMap, TicketType, Registration, Payment, Refund, RefundRequest, Booking,
        BookingSeat, CheckInList, CheckInLog, EventStaff, Review, WaitlistEntry, PromoCode, Affiliate, Category,
    )  # fmt: skip

    def test_remove_dry_run_prints_the_counts_and_deletes_nothing(self):
        before = model_counts(*self.ALL)
        output, _ = run_demo('--remove', '--dry-run', '--organizer', OWNER)
        self.assertEqual(model_counts(*self.ALL), before)
        self.assertIn('Would delete:', output)
        self.assertIn(f'  events: {Event.objects.filter(title__in=TITLES).count()}', output)
        self.assertIn(f'  registrations: {Registration.objects.filter(event__title__in=TITLES).count()}', output)
        labels = ('payments', 'refunds', 'booking seats', 'bookings', 'check-in logs', 'waitlist entries', 'reviews')
        labels += ('promo codes', 'affiliates', 'event staff', 'ticket types', 'seat maps', 'users')
        for label in labels:
            self.assertRegex(output, rf'  {label}: \d+')
        self.assertIn('Dry run: nothing was deleted.', output)

    def test_remove_deletes_every_demo_row_and_nothing_else(self):
        real = self.snapshot_of_real_data()
        categories = Category.objects.count()
        output, _ = run_demo('--remove', '--organizer', OWNER)
        self.assertIn('Deleted:', output)
        self.assertEqual(self.snapshot_of_real_data(), real)
        self.assertEqual(Category.objects.count(), categories)  # shared: kept
        self.assertEqual(User.objects.filter(username__startswith='kz_').count(), 0)
        self.assertEqual(User.objects.filter(email__endswith='@demo.eventhub.local').count(), 0)
        self.assertEqual(Event.objects.filter(title__in=TITLES).count(), 0)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(model_counts(*self.DEMO_ONLY), dict.fromkeys((m.__name__ for m in self.DEMO_ONLY), 0))
        self.assertEqual(Registration.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(EventStaff.objects.count(), 1)  # the real one; the organizer's co-organizer rows are gone
        self.assertFalse(EventStaff.objects.filter(user=self.owner).exists())
        self.assertEqual(Job.objects.count(), 0)
        self.assertEqual(all_findings(), {})
        # And the seed can run again.
        run_demo('--organizer', OWNER, '--attendees', '30')
        self.assertEqual(Event.objects.filter(title__in=TITLES).count(), 60)

    def test_remove_without_the_organizer_keeps_the_organizers_events_and_says_so(self):
        output, _ = run_demo('--remove')
        self.assertIn('20 events with demo titles belong to other accounts', output)
        self.assertEqual(Event.objects.filter(organizer=self.owner, title__in=TITLES).count(), 20)
        self.assertEqual(Event.objects.filter(title__in=TITLES).count(), 20)
        # Demo users who hold tickets at the organizer's events stay: those events are not removed.
        self.assertIn('Kept ', output)
        self.assertGreater(User.objects.filter(username__startswith='kz_').count(), 0)
        # Co-organizer rows went with their events.
        self.assertFalse(EventStaff.objects.filter(user=self.owner).exists())

    def test_an_event_real_accounts_bought_tickets_for_is_kept(self):
        event = Event.objects.get(title='Almaty Jazz Festival 2026')
        reg = Registration.objects.create(user=self.real_att, event=event, status='confirmed')
        paid = Payment.objects.create(
            registration=reg, amount=Decimal('18000'), currency='kzt', status='completed', provider='freedompay',
            provider_session_id='real-bought', provider_payment_id='real-pay-2',
        )  # fmt: skip
        output, _ = run_demo('--remove', '--organizer', OWNER)
        self.assertIn('Kept 1 demo events that real accounts bought tickets for.', output)
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())
        self.assertTrue(Payment.objects.filter(pk=paid.pk, status='completed').exists())
        self.assertEqual(Event.objects.filter(title__in=TITLES).count(), 1)
        # The demo buyers of that event stay with it.
        self.assertTrue(User.objects.filter(registrations__event=event, username__startswith='kz_').exists())

    def test_remove_runs_in_one_transaction(self):
        from events import demo_kz_remove

        before = model_counts(*self.ALL)
        real_build_plan = demo_kz_remove.build_plan

        class Failing:
            def count(self):
                return 1

            def delete(self):
                raise RuntimeError('boom')

        def failing_plan(owner):
            steps, notes = real_build_plan(owner)
            return [*steps, ('failing step', Failing())], notes

        with patch.object(demo_kz_remove, 'build_plan', failing_plan), self.assertRaisesMessage(RuntimeError, 'boom'):
            run_demo('--remove', '--organizer', OWNER)
        self.assertEqual(model_counts(*self.ALL), before)

    def test_remove_needs_a_real_organizer_account(self):
        with self.assertRaisesMessage(CommandError, 'does not exist'):
            run_demo('--remove', '--organizer', 'nobody')
        with self.assertRaisesMessage(CommandError, 'is a demo account'):
            run_demo('--remove', '--organizer', 'kz_dana.abenova')
        with self.assertRaisesMessage(CommandError, 'is not an organizer'):
            run_demo('--remove', '--organizer', 'real_attendee')
        with self.assertRaisesMessage(CommandError, '--dry-run only works with --remove'):
            run_demo('--dry-run')

    # --------------------------------------------- refunds without mocks ---- #

    def organizer_client(self, event):
        client = APIClient()
        authenticate_with_recent_mfa(client, User.objects.get(pk=event.organizer_id))
        return client

    def refund_settings(self):
        return override_settings(
            DEBUG=False,
            PAYMENTS_MOCK_MODE=False,
            STRIPE_MOCK_MODE=False,
            PAYMENT_PROVIDERS_ENABLED=['stripe', 'freedompay'],
        )

    def no_gateway(self):
        """Every way to reach Stripe or Freedom Pay fails the test."""
        from contextlib import ExitStack

        stack = ExitStack()
        self.stripe_refund = stack.enter_context(patch('stripe.Refund.create', side_effect=AssertionError('Stripe')))
        stack.enter_context(patch('payments.freedompay_flow.provider', side_effect=AssertionError('Freedom Pay')))
        stack.enter_context(patch('payments.providers.registry.get', side_effect=AssertionError('registry')))
        self.addCleanup(stack.close)

    def a_confirmed_paid_ticket(self):
        payment = (
            Payment.objects.filter(
                provider='mock',
                status='completed',
                refunded_amount=0,
                registration__status='confirmed',
                registration__is_checked_in=False,
                registration__event__status='published',
                registration__event__date__gt=timezone.now() + timedelta(days=2),
                registration__refund_request__isnull=True,
            )
            .select_related('registration__event')
            .order_by('pk')
            .first()
        )
        self.assertIsNotNone(payment)
        return payment

    def test_the_organizer_refunds_a_demo_payment_with_the_mocks_off(self):
        payment = self.a_confirmed_paid_ticket()
        registration, event = payment.registration, payment.registration.event
        self.assertEqual(payment.provider, 'mock')
        client = self.organizer_client(event)
        with self.refund_settings():
            self.no_gateway()
            half = (payment.amount / 2).quantize(Decimal('0.01'))
            partial = client.post(f'/api/v1/payments/refund/{registration.id}/', {'amount': str(half)})
            self.assertEqual(partial.status_code, 200, partial.data)
            full = client.post(f'/api/v1/payments/refund/{registration.id}/')
            self.assertEqual(full.status_code, 200, full.data)
        self.stripe_refund.assert_not_called()
        payment.refresh_from_db()
        registration.refresh_from_db()
        self.assertEqual((payment.status, payment.refunded_amount), ('refunded', payment.amount))
        self.assertEqual(registration.status, 'cancelled')
        ledger = Refund.objects.filter(payment=payment)
        self.assertEqual([r.amount for r in ledger], [half, payment.amount - half])
        self.assertEqual({(r.provider, r.status) for r in ledger}, {('mock', 'succeeded')})
        self.assertEqual(Job.objects.filter(kind='send_email').count(), 0)  # nothing to an undeliverable address
        self.assertEqual(critical_findings(), {})
        self.assertEqual(all_findings(), {})

    def test_the_organizer_refunds_a_demo_group_booking_with_the_mocks_off(self):
        booking = (
            Booking.objects.filter(
                status='confirmed',
                payment__provider='mock',
                payment__status='completed',
                event__status='published',
                event__date__gt=timezone.now() + timedelta(days=2),
            )
            .select_related('event', 'payment')
            .order_by('pk')
            .first()
        )
        self.assertIsNotNone(booking)
        client = self.organizer_client(booking.event)
        with self.refund_settings():
            self.no_gateway()
            response = client.post(f'/api/v1/bookings/{booking.pk}/refund/', {'reason': 'Venue change'})
        self.assertEqual(response.status_code, 200, response.data)
        self.stripe_refund.assert_not_called()
        booking.refresh_from_db()
        payment = Payment.objects.get(booking=booking)
        self.assertEqual(booking.status, 'refunded')
        self.assertEqual((payment.status, payment.refunded_amount), ('refunded', payment.amount))
        self.assertEqual(Refund.objects.filter(payment=payment, status='succeeded').count(), 1)
        self.assertEqual(critical_findings(), {})
        self.assertEqual(all_findings(), {})

    def test_approving_a_refund_request_with_the_mocks_off(self):
        request = (
            RefundRequest.objects.filter(status='pending').select_related('registration__event').order_by('pk').first()
        )
        self.assertIsNotNone(request)
        event = request.registration.event
        with self.refund_settings():
            self.no_gateway()
            resolve_refund_request(
                refund_request=request, actor=User.objects.get(pk=event.organizer_id), approve=True, note='ok'
            )
        request.refresh_from_db()
        payment = request.registration.payment
        payment.refresh_from_db()
        self.assertEqual((request.status, payment.status), ('approved', 'refunded'))
        self.assertEqual(critical_findings(), {})

    def test_cancelling_a_seeded_event_with_the_mocks_off(self):
        event = (
            Event.objects.filter(
                title__in=TITLES,
                status='published',
                date__gt=timezone.now() + timedelta(days=2),
                registrations__payment__status='completed',
                bookings__status='confirmed',
            )
            .distinct()
            .order_by('pk')
            .first()
        )
        self.assertIsNotNone(event)
        paid_before = Payment.objects.filter(registration__event=event, status='completed').count()
        with self.refund_settings():
            self.no_gateway()
            result = cancel_event(event=event, actor=User.objects.get(pk=event.organizer_id))
        self.stripe_refund.assert_not_called()
        self.assertEqual(result['refund_failed'], 0, result)
        self.assertGreaterEqual(result['refunded'], paid_before)
        self.assertFalse(Payment.objects.filter(registration__event=event, status='completed').exists())
        self.assertFalse(Payment.objects.filter(booking__event=event, status='completed').exists())
        # In-app notices, but no email job: the demo addresses are undeliverable.
        self.assertGreater(Notification.objects.count(), 0)
        self.assertEqual(Job.objects.filter(kind='send_email').count(), 0)
        self.assertEqual(critical_findings(), {})
        # cancel_event leaves open refund requests of the voided tickets as they are (a WARNING of the
        # refund_request_inconsistent check, not of the seed): only the money must balance.
        self.assertEqual(set(all_findings()) - {'refund_request_inconsistent'}, set())


class DemoAddressesGetNoEmailTests(TestCase):
    def test_notify_keeps_the_in_app_row_but_queues_no_email_for_a_demo_address(self):
        demo = User.objects.create_user('kz_someone', 'kz_someone@demo.eventhub.local', 'x')
        real = User.objects.create_user('someone', 'someone@example.com', 'x')
        event = Event.objects.create(
            title='Any event',
            description='d',
            organizer=real,
            date=timezone.now() + timedelta(days=3),
            location='Hall',
            status='published',
        )
        for user in (demo, real):
            notify(user, types.PAYMENT_REFUNDED, event=event, amount=Decimal('10'), currency='KZT', reason='test')
        self.assertEqual(Notification.objects.filter(user=demo).count(), 1)
        self.assertEqual(Notification.objects.filter(user=real).count(), 1)
        recipients = [to for job in Job.objects.filter(kind='send_email') for to in job.payload['to']]
        self.assertEqual(recipients, ['someone@example.com'])


class DemoModeTests(TestCase):
    """DJANGO_DEBUG=0: the flag, the credentials file, random passwords."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, 'credentials.txt')

    def run_small(self, *extra, path=None):
        return run_demo('--i-know-this-is-a-demo', '--attendees', '40', '--credentials-file', path or self.path, *extra)

    @override_settings(DEBUG=False)
    def test_refused_without_the_flag(self):
        with self.assertRaisesMessage(CommandError, '--i-know-this-is-a-demo'):
            run_demo('--credentials-file', self.path)
        self.assertFalse(os.path.exists(self.path))
        self.assertFalse(User.objects.exists())

    @override_settings(DEBUG=False)
    def test_refused_without_the_credentials_file(self):
        with self.assertRaisesMessage(CommandError, '--credentials-file'):
            run_demo('--i-know-this-is-a-demo')
        self.assertFalse(User.objects.exists())

    @override_settings(DEBUG=False)
    def test_refuses_an_existing_file_and_keeps_it_as_it_is(self):
        with open(self.path, 'w') as handle:
            handle.write('earlier passwords\n')
        with self.assertRaisesMessage(CommandError, 'already exists'):
            self.run_small()
        with open(self.path) as handle:
            self.assertEqual(handle.read(), 'earlier passwords\n')
        self.assertFalse(User.objects.exists())

    @override_settings(DEBUG=True)
    def test_debug_mode_keeps_the_development_password_and_needs_no_file(self):
        run_demo('--attendees', '30')
        self.assertTrue(User.objects.get(username='kz_dana.abenova').check_password('password123'))
        with self.assertRaisesMessage(CommandError, 'only used with DJANGO_DEBUG=0'):
            run_demo('--credentials-file', self.path)

    @override_settings(DEBUG=False)
    def test_every_account_gets_its_own_strong_password_in_a_0600_file(self):
        output, errors = self.run_small()
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(mode, 0o600)
        with open(self.path) as handle:
            lines = handle.read().splitlines()
        rows = [line.split('\t') for line in lines]
        self.assertEqual(len(rows), len(ORGANIZERS) + len(STAFF) + 40)
        self.assertTrue(all(len(row) == 3 for row in rows))
        roles = [row[2] for row in rows]
        self.assertEqual(roles[: len(ORGANIZERS)], ['organizer'] * len(ORGANIZERS))  # organizers first
        self.assertEqual(Counter(roles), {'organizer': 6, 'check_in': len(STAFF), 'attendee': 40})
        passwords = [row[1] for row in rows]
        self.assertEqual(len(set(passwords)), len(passwords))
        hashes = set()
        for username, password, _role in rows:
            self.assertEqual(len(password), 20)
            self.assertTrue(re.search(r'[A-Z]', password) and re.search(r'[a-z]', password))
            self.assertTrue(re.search(r'\d', password) and re.search(r'[^A-Za-z0-9]', password))
            validate_password(password)
            self.assertNotEqual(password, 'password123')
            user = User.objects.get(username=username)
            self.assertTrue(user.check_password(password))
            self.assertFalse(user.check_password('password123'))
            hashes.add(user.password)
        self.assertEqual(len(hashes), len(rows))  # every account has its own salt
        # Nothing secret on stdout or stderr: only counts and the path.
        for password in passwords:
            self.assertNotIn(password, output)
            self.assertNotIn(password, errors)
        self.assertNotIn('password123', output + errors)
        self.assertIn(self.path, output)
        self.assertIn(f'Passwords for {len(rows)} new accounts', output)

    @override_settings(DEBUG=False)
    def test_a_second_run_creates_no_account_and_the_event_data_is_the_same(self):
        self.run_small()
        counts = model_counts(User, Event, Registration, Payment)
        second = os.path.join(self.dir.name, 'second.txt')
        output, _ = self.run_small(path=second)
        self.assertEqual(model_counts(User, Event, Registration, Payment), counts)
        self.assertEqual(os.path.getsize(second), 0)
        self.assertIn('Passwords for 0 new accounts', output)

    @override_settings(DEBUG=False)
    def test_a_failed_run_leaves_no_empty_file_behind(self):
        with self.assertRaises(CommandError):
            run_demo(
                '--i-know-this-is-a-demo', '--credentials-file', self.path, '--attendees', '5', '--organizer', 'nobody'
            )
        self.assertFalse(os.path.exists(self.path))

    @override_settings(DEBUG=False)
    def test_an_existing_real_account_with_a_demo_user_name_is_never_reused(self):
        User.objects.create_user('kz_dana.abenova', 'dana@example.com', 'Real-pass-1234!')
        with self.assertRaisesMessage(CommandError, 'not a demo account'):
            self.run_small()
        self.assertTrue(User.objects.get(username='kz_dana.abenova').check_password('Real-pass-1234!'))
        self.assertFalse(os.path.exists(self.path) and os.path.getsize(self.path))

    @override_settings(DEBUG=False)
    def test_remove_needs_the_flag_but_no_file(self):
        with self.assertRaisesMessage(CommandError, '--i-know-this-is-a-demo'):
            run_demo('--remove')
        self.run_small()
        output, _ = run_demo('--i-know-this-is-a-demo', '--remove')
        self.assertIn('Deleted:', output)
        self.assertEqual(User.objects.filter(username__startswith='kz_').count(), 0)

    @override_settings(DEBUG=False)
    def test_the_organizer_must_be_an_organizer(self):
        User.objects.create_user('plain', 'plain@example.com', 'Real-pass-1234!')
        with self.assertRaisesMessage(CommandError, 'is not an organizer'):
            self.run_small('--organizer', 'plain')
        self.assertFalse(os.path.exists(self.path))


class PasswordHelperTests(SimpleTestCase):
    def test_generated_passwords_are_random_and_valid(self):
        passwords = {demo_seed.generate_password() for _ in range(200)}
        self.assertEqual(len(passwords), 200)
        for password in passwords:
            self.assertEqual(len(password), demo_seed.GENERATED_PASSWORD_LENGTH)
            validate_password(password)

    def test_hashing_gives_each_password_its_own_hash_with_or_without_a_pool(self):
        passwords = [demo_seed.generate_password() for _ in range(12)]
        with patch.object(demo_seed, 'POOL_THRESHOLD_SECONDS', -1):  # always try the process pool
            pooled = demo_seed.hash_passwords(passwords, workers=2)
        sequential = demo_seed.hash_passwords(passwords, workers=1)
        for password, one, two in zip(passwords, pooled, sequential, strict=True):
            self.assertTrue(demo_seed.make_password(password) != one)  # salted
            from django.contrib.auth.hashers import check_password

            self.assertTrue(check_password(password, one))
            self.assertTrue(check_password(password, two))
        self.assertEqual(len(set(pooled)), 12)

    def test_progress_counts_are_reported(self):
        seen = []
        demo_seed.hash_passwords(['a-Password-1!'] * 5, progress=lambda done, total: seen.append((done, total)))
        self.assertEqual(seen[-1], (5, 5))

    def test_a_real_process_pool_hashes_with_the_production_hasher(self):
        """In a fresh interpreter (not a daemonic test worker): the pool starts and every hash verifies."""
        code = textwrap.dedent(
            """
            import concurrent.futures, json
            from django.conf import settings
            from django.contrib.auth.hashers import check_password
            from common import demo_seed

            started = []
            real = concurrent.futures.ProcessPoolExecutor

            class Counting(real):
                def __init__(self, *args, **kwargs):
                    started.append(1)
                    super().__init__(*args, **kwargs)

            concurrent.futures.ProcessPoolExecutor = Counting
            demo_seed.POOL_THRESHOLD_SECONDS = -1
            passwords = [demo_seed.generate_password() for _ in range(6)]
            hashes = demo_seed.hash_passwords(passwords, workers=2)
            print(json.dumps({
                'hasher': settings.PASSWORD_HASHERS[0].rsplit('.', 1)[-1],
                'pool': bool(started),
                'verified': all(check_password(p, h) for p, h in zip(passwords, hashes)),
                'distinct': len(set(hashes)),
            }))
            """
        )
        env = {**os.environ, 'DJANGO_DEBUG': '1', 'DJANGO_SETTINGS_MODULE': 'eventhub_backend.settings'}
        env.pop('PYTHONPATH', None)
        run = subprocess.run(  # noqa: S603 - our own interpreter and code
            [sys.executable, '-c', 'import django; django.setup()\n' + code],
            cwd=settings.BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(run.returncode, 0, run.stderr[-2000:])
        result = json.loads(run.stdout.strip().splitlines()[-1])
        self.assertEqual(result, {'hasher': 'PBKDF2PasswordHasher', 'pool': True, 'verified': True, 'distinct': 6})

    def test_the_credentials_file_is_created_exclusively_with_mode_0600(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'c.txt')
            handle = demo_seed.open_credentials_file(path)
            demo_seed.write_credentials(handle, [('u', 'p', 'attendee')])
            handle.close()
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            with open(path) as written:
                self.assertEqual(written.read(), 'u\tp\tattendee\n')
            with self.assertRaises(CommandError):
                demo_seed.open_credentials_file(path)
