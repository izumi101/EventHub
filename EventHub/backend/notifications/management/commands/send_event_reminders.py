"""Send the event reminders (24 hours and 2 hours before the start) and the
review requests (after the event) that are due.

The worker already runs this every minute (inside `run_maintenance`); the
command is for cron-style deployments and manual runs. Safe to run any
number of times: nothing is sent twice.

    python manage.py send_event_reminders
"""

from django.core.management.base import BaseCommand

from notifications.reminders import send_due_reminders, send_due_review_requests


class Command(BaseCommand):
    help = 'Send due event reminders (24 h and 2 h before) and review requests (idempotent).'

    def handle(self, *args, **options):
        sent = send_due_reminders()
        self.stdout.write(f'Sent {sent} event reminder(s).')
        reviews = send_due_review_requests()
        self.stdout.write(f'Sent {reviews} review request(s).')
