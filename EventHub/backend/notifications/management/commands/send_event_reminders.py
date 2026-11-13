"""Send the 24-hour event reminders that are due.

The worker already runs this every minute (inside `run_maintenance`); the
command is for cron-style deployments and manual runs. Safe to run any
number of times: a reminder is never sent twice.

    python manage.py send_event_reminders
"""

from django.core.management.base import BaseCommand

from notifications.reminders import send_due_reminders


class Command(BaseCommand):
    help = 'Send 24-hour reminders for upcoming events (idempotent).'

    def handle(self, *args, **options):
        sent = send_due_reminders()
        self.stdout.write(f'Sent {sent} event reminder(s).')
