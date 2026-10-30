"""Periodic housekeeping that used to run lazily inside GET requests.

Run it every minute (the `scheduler` service in docker-compose does):
    python manage.py run_maintenance            # one pass
    python manage.py run_maintenance --loop 60  # forever, every 60 s
"""

import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from common.choices import EventStatusChoices

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Release expired seat holds and group bookings, advance waitlists, complete past events.'

    def add_arguments(self, parser):
        parser.add_argument('--loop', type=int, default=0, help='Repeat every N seconds instead of running once.')

    def handle(self, *args, **options):
        interval = options['loop']
        while True:
            try:
                self.run_once()
            except Exception:
                # Keep the scheduler alive; the next pass retries.
                logger.exception('Maintenance pass failed')
            if not interval:
                return
            close_old_connections()
            time.sleep(interval)

    def run_once(self):
        from bookings.services import release_expired_bookings
        from events.models import Event, WaitlistEntry
        from events.services import release_expired_seat_holds
        from events.waitlist import promote_waitlist

        release_expired_seat_holds()
        release_expired_bookings()

        # Offers that timed out pass to the next person in line.
        waiting_events = (
            WaitlistEntry.objects.filter(status__in=[WaitlistEntry.STATUS_WAITING, WaitlistEntry.STATUS_OFFERED])
            .values_list('event_id', flat=True)
            .distinct()
        )
        for event in Event.objects.filter(id__in=list(waiting_events), status=EventStatusChoices.PUBLISHED):
            promote_waitlist(event)

        # Published events whose end has passed become "completed".
        now = timezone.now()
        Event.objects.filter(status=EventStatusChoices.PUBLISHED, end_date__lt=now).update(
            status=EventStatusChoices.COMPLETED,
        )
        Event.objects.filter(status=EventStatusChoices.PUBLISHED, end_date__isnull=True, date__lt=now).update(
            status=EventStatusChoices.COMPLETED,
        )
