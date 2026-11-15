"""The 2-hour reminder next to the 24-hour one."""

from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from events.models import Notification

from . import types
from .models import NotificationPreference, SentReminder
from .reminders import send_due_reminders
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
