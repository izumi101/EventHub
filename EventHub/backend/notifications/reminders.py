"""Event reminders, 24 hours before the start.

`send_due_reminders` runs every minute from `run_maintenance` (the worker)
and on demand via `manage.py send_event_reminders`. It is idempotent: each
(user, event start) reminder is recorded in `SentReminder` under a unique
constraint, in the same transaction as the notification and its email job,
so a reminder is sent at most once even when two passes overlap.
"""

import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import types
from .models import SentReminder
from .service import notify, ticket_holders

logger = logging.getLogger(__name__)

REMINDER_WINDOW = timedelta(hours=24)


def due_events(now=None):
    """Published events starting within the next 24 hours."""
    from common.choices import EventStatusChoices
    from events.models import Event

    now = now or timezone.now()
    return Event.objects.filter(
        status=EventStatusChoices.PUBLISHED,
        date__gt=now,
        date__lte=now + REMINDER_WINDOW,
    ).order_by('date', 'pk')


def _send_one(user, event) -> bool:
    """Record and send one reminder; False when it was already sent."""
    try:
        with transaction.atomic():
            SentReminder.objects.create(user=user, event=event, kind=SentReminder.KIND_24H, event_starts_at=event.date)
            if notify(user, types.EVENT_REMINDER, event=event) is None:
                # Roll the record back too: the next pass tries again.
                raise RuntimeError('notification failed')
    except IntegrityError:
        return False
    except RuntimeError:
        logger.warning('Reminder of event %s to user %s failed; will retry', event.pk, user.pk)
        return False
    return True


def send_due_reminders(now=None) -> int:
    """Send every reminder that is due and not sent yet. Returns the count."""
    sent = 0
    for event in due_events(now):
        already = set(
            SentReminder.objects.filter(
                event=event, kind=SentReminder.KIND_24H, event_starts_at=event.date
            ).values_list('user_id', flat=True)
        )
        for user in ticket_holders(event):
            if user.pk in already:
                continue
            if _send_one(user, event):
                sent += 1
    if sent:
        logger.info('Sent %s event reminders', sent)
    return sent
