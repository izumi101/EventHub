"""The 2-hour reminder next to the 24-hour one, and the review request
email after the event."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from events.models import Notification, Registration, Review

from . import types
from .models import NotificationPreference, SentReminder
from .reminders import send_due_reminders, send_due_review_requests
from .tests import WorldMixin, email_jobs


class TwoHourReminderTests(WorldMixin, TestCase):
    def setUp(self):
        self.make_world()
        self.now = timezone.now()

    def event_in(self, delta, **extra):
        event = self.make_event(**extra)
        event.date = self.now + delta
        event.save(update_fields=['date'])
        return event

    def reminders(self, user):
        return Notification.objects.filter(user=user, type=types.EVENT_REMINDER)

    def test_a_ticket_bought_an_hour_before_gets_only_the_2_hour_reminder(self):
        event = self.event_in(timedelta(hours=1))
        self.confirmed(self.alice, event=event)
        self.assertEqual(send_due_reminders(self.now), 1)
        self.assertEqual(send_due_reminders(self.now), 0)
        self.assertEqual(list(SentReminder.objects.values_list('kind', flat=True)), [SentReminder.KIND_2H])
        notification = self.reminders(self.alice).get()
        self.assertIn('in less than 2 hours', notification.body)
        payload = email_jobs(self.alice).get().payload
        self.assertTrue(payload['subject'].startswith('Starting in 2 hours: Almaty Product Conference at '))

    def test_the_message_names_the_local_start_time(self):
        from datetime import UTC, datetime

        with override_settings(NOTIFICATION_TIME_ZONE='Asia/Almaty'):
            now = datetime(2026, 12, 5, 12, 30, tzinfo=UTC)
            event = self.make_event()
            event.date = datetime(2026, 12, 5, 14, 0, tzinfo=UTC)  # 19:00 in Almaty
            event.save(update_fields=['date'])
            self.confirmed(self.alice, event=event)
            send_due_reminders(now)
        self.assertEqual(
            email_jobs(self.alice).get().payload['subject'], 'Starting in 2 hours: Almaty Product Conference at 19:00'
        )
        self.assertEqual(self.reminders(self.alice).get().title, '⏰ Starting soon: Almaty Product Conference at 19:00')

    def test_the_windows_split_at_two_hours(self):
        early = self.event_in(timedelta(hours=2, minutes=1), title='Just over two hours')
        edge = self.event_in(timedelta(hours=2), title='Exactly two hours')
        later = self.event_in(timedelta(hours=24, minutes=1), title='Over a day')
        for event in (early, edge, later):
            self.confirmed(self.alice, event=event)
        self.assertEqual(send_due_reminders(self.now), 2)
        kinds = dict(SentReminder.objects.values_list('event__title', 'kind'))
        self.assertEqual(
            kinds, {'Just over two hours': SentReminder.KIND_24H, 'Exactly two hours': SentReminder.KIND_2H}
        )

    def test_a_ticket_bought_the_day_before_gets_both_once(self):
        event = self.event_in(timedelta(hours=20))
        self.confirmed(self.alice, event=event)
        self.assertEqual(send_due_reminders(self.now), 1)  # 24-hour
        self.assertEqual(send_due_reminders(self.now + timedelta(hours=10)), 0)
        self.assertEqual(send_due_reminders(self.now + timedelta(hours=18, minutes=30)), 1)  # 2-hour
        self.assertEqual(send_due_reminders(self.now + timedelta(hours=19)), 0)
        self.assertEqual(
            sorted(SentReminder.objects.values_list('kind', flat=True)), [SentReminder.KIND_24H, SentReminder.KIND_2H]
        )
        self.assertEqual(self.reminders(self.alice).count(), 2)
        self.assertEqual(email_jobs(self.alice).count(), 2)

    def test_two_maintenance_passes_send_one_2_hour_reminder(self):
        event = self.event_in(timedelta(minutes=90))
        self.confirmed(self.alice, event=event)
        call_command('run_maintenance')
        call_command('run_maintenance')
        self.assertEqual(self.reminders(self.alice).count(), 1)
        self.assertEqual(SentReminder.objects.get().kind, SentReminder.KIND_2H)

    def test_started_events_get_no_reminder(self):
        event = self.event_in(timedelta(minutes=-5))
        self.confirmed(self.alice, event=event)
        self.assertEqual(send_due_reminders(self.now), 0)

    def test_the_opt_out_covers_both_reminders(self):
        NotificationPreference.objects.create(user=self.alice, email_disabled=[types.EVENT_REMINDER])
        event = self.event_in(timedelta(hours=1))
        self.confirmed(self.alice, event=event)
        send_due_reminders(self.now)
        self.assertEqual(self.reminders(self.alice).count(), 1)
        self.assertFalse(email_jobs(self.alice).exists())


@override_settings(EVENT_DEFAULT_DURATION_HOURS=3)
class ReviewRequestTests(WorldMixin, TestCase):
    def setUp(self):
        self.make_world()
        self.now = timezone.now()
        # Started 5 hours ago, ended 3 hours ago.
        self.ended = self.past_event(start=timedelta(hours=5), end=timedelta(hours=3), title='Last night')
        self.confirmed(self.alice, event=self.ended)

    def past_event(self, *, start, end=None, status='completed', title='Past event'):
        event = self.make_event(title=title)
        event.date = self.now - start
        event.end_date = self.now - end if end is not None else None
        event.status = status
        event.save(update_fields=['date', 'end_date', 'status'])
        return event

    def requests(self, user=None):
        notifications = Notification.objects.filter(type=types.REVIEW_REMINDER)
        return notifications.filter(user=user) if user else notifications

    def test_attendees_are_asked_once_by_email(self):
        self.assertEqual(send_due_review_requests(self.now), 1)
        self.assertEqual(send_due_review_requests(self.now), 0)
        self.assertEqual(send_due_review_requests(self.now + timedelta(hours=1)), 0)
        notification = self.requests(self.alice).get()
        self.assertEqual(notification.title, '⭐ How was Last night?')
        payload = email_jobs(self.alice).get().payload
        self.assertEqual(payload['subject'], 'How was Last night?')
        self.assertIn('Leave a review', payload['body'])
        self.assertIn(f'/events/{self.ended.pk}', payload['body'])
        self.assertIn('List-Unsubscribe', payload['headers'])  # optional email
        record = SentReminder.objects.get()
        self.assertEqual((record.kind, record.user, record.event), (SentReminder.KIND_REVIEW, self.alice, self.ended))

    def test_only_users_the_review_rules_allow_are_asked(self):
        from events.services import review_refusal

        Registration.objects.create(user=self.bob, event=self.ended, status='cancelled')
        reviewer = self.make_user('carol')
        self.confirmed(reviewer, event=self.ended)
        Review.objects.create(user=reviewer, event=self.ended, rating=5, comment='Great')
        holder = self.make_user('dave')  # a pending (unpaid) registration
        Registration.objects.create(user=holder, event=self.ended, status='pending')
        send_due_review_requests(self.now)
        self.assertEqual(list(self.requests().values_list('user__username', flat=True)), ['alice'])
        # The same rule the review API applies.
        self.assertIsNone(review_refusal(self.ended, self.alice, self.now))
        for user in (self.bob, reviewer, holder):
            self.assertIsNotNone(review_refusal(self.ended, user, self.now))

    def make_user(self, name):
        from django.contrib.auth.models import User

        return User.objects.create_user(name, f'{name}@example.com', 'password123')

    def test_the_window_is_two_to_forty_eight_hours_after_the_end(self):
        too_fresh = self.past_event(start=timedelta(hours=3), end=timedelta(hours=1), title='Just ended')
        too_old = self.past_event(start=timedelta(days=3, hours=2), end=timedelta(days=3), title='Long ago')
        running = self.past_event(start=timedelta(hours=1), end=timedelta(hours=-2), status='published', title='Now')
        for event in (too_fresh, too_old, running):
            self.confirmed(self.bob, event=event)
        self.assertEqual(send_due_review_requests(self.now), 1)
        self.assertFalse(self.requests(self.bob).exists())
        # Later, the fresh one enters the window; the old one never does.
        self.assertEqual(send_due_review_requests(self.now + timedelta(hours=1, minutes=1)), 1)
        self.assertEqual(list(self.requests(self.bob).values_list('event__title', flat=True)), ['Just ended'])

    def test_an_event_without_an_end_uses_the_default_duration(self):
        ended = self.past_event(start=timedelta(hours=6), title='No end, ended 3 h ago')
        not_yet = self.past_event(start=timedelta(hours=4), title='No end, ended 1 h ago')
        self.confirmed(self.bob, event=ended)
        self.confirmed(self.bob, event=not_yet)
        send_due_review_requests(self.now)
        self.assertEqual(
            list(self.requests(self.bob).values_list('event__title', flat=True)), ['No end, ended 3 h ago']
        )

    def test_cancelled_and_unpublished_events_are_skipped(self):
        for status in ('cancelled', 'draft', 'pending', 'rejected'):
            event = self.past_event(start=timedelta(hours=5), end=timedelta(hours=3), status=status, title=status)
            self.confirmed(self.bob, event=event)
        send_due_review_requests(self.now)
        self.assertFalse(self.requests(self.bob).exists())

    def test_an_ended_event_still_marked_published_is_included(self):
        event = self.past_event(start=timedelta(hours=5), end=timedelta(hours=3), status='published', title='Open')
        self.confirmed(self.bob, event=event)
        send_due_review_requests(self.now)
        self.assertTrue(self.requests(self.bob).exists())

    def test_opted_out_users_get_the_in_app_request_only(self):
        NotificationPreference.objects.create(user=self.alice, email_disabled=[types.REVIEW_REMINDER])
        send_due_review_requests(self.now)
        self.assertTrue(self.requests(self.alice).exists())
        self.assertFalse(email_jobs(self.alice).exists())

    def test_it_runs_in_the_maintenance_pass_and_the_command(self):
        call_command('run_maintenance')
        call_command('run_maintenance')
        out = StringIO()
        call_command('send_event_reminders', stdout=out)
        self.assertIn('Sent 0 review request(s).', out.getvalue())
        self.assertEqual(self.requests(self.alice).count(), 1)

    def test_a_failure_is_retried_on_the_next_pass(self):
        from unittest.mock import patch

        with patch('notifications.reminders.notify', return_value=None), self.assertLogs('notifications', 'WARNING'):
            self.assertEqual(send_due_review_requests(self.now), 0)
        self.assertFalse(SentReminder.objects.exists())
        self.assertEqual(send_due_review_requests(self.now), 1)
