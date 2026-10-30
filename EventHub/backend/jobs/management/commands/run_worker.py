"""Background worker: runs queued jobs (emails, webhooks, search indexing)
every few seconds and the periodic maintenance every minute.

    python manage.py run_worker                  # forever
    python manage.py run_worker --once           # one pass of both, then exit
"""

import logging
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from jobs.queue import purge_finished, run_due_jobs

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run background jobs and periodic maintenance.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='One pass, then exit.')
        parser.add_argument('--poll', type=float, default=2.0, help='Seconds between job polls.')
        parser.add_argument('--maintenance-every', type=float, default=60.0, help='Seconds between maintenance passes.')

    def handle(self, *args, **options):
        last_maintenance = 0.0
        while True:
            try:
                ran = run_due_jobs()
                if time.monotonic() - last_maintenance >= options['maintenance_every'] or options['once']:
                    call_command('run_maintenance')
                    purge_finished()
                    last_maintenance = time.monotonic()
            except Exception:
                # Keep the worker alive; the next pass retries.
                logger.exception('Worker pass failed')
                ran = 0
            if options['once']:
                return
            close_old_connections()
            if not ran:
                time.sleep(options['poll'])
