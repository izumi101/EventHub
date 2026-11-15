"""Event reminders, 24 hours and 2 hours before the start.

`send_due_reminders` runs every minute from `run_maintenance` (the worker)
and on demand via `manage.py send_event_reminders`. It is idempotent: each notification is recorded in
`SentReminder` under a unique (user, event, kind, event start) constraint,
in the same transaction as the notification and its email job, so it is sent
at most once even when two passes overlap.

Reminder windows, by time left until the start:

- (2 h, 24 h]: the 24-hour reminder;
- (0, 2 h]:    the 2-hour reminder.

So a ticket bought an hour before the start gets only the 2-hour reminder,
and one bought the day before gets both.
"""

import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import types
from .models import SentReminder
from .service import notify, ticket_holders

logger = logging.getLogger(__name__)

# kind → (lower, upper] bound of the time left until the start.
REMINDER_WINDOWS = {
    SentReminder.KIND_24H: (timedelta(hours=2), timedelta(hours=24)),
    SentReminder.KIND_2H: (timedelta(0), timedelta(hours=2)),
}

def due_events(now=None, kind=SentReminder.KIND_24H):
    """Published events whose start falls in the window of `kind`."""
    from common.choices import EventStatusChoices
    from events.models import Event

    now = now or timezone.now()
    lower, upper = REMINDER_WINDOWS[kind]
    return Event.objects.filter(
        status=EventStatusChoices.PUBLISHED,
        date__gt=now + lower,
        date__lte=now + upper,
    ).order_by('date', 'pk')


def _send_once(user, event, kind: str, type_key: str, **data) -> bool:
    """Record and send one notification; False when it was already sent."""
    try:
        with transaction.atomic():
            SentReminder.objects.create(user=user, event=event, kind=kind, event_starts_at=event.date)
            if notify(user, type_key, event=event, **data) is None:
                # Roll the record back too: the next pass tries again.
                raise RuntimeError('notification failed')
    except IntegrityError:
        return False
    except RuntimeError:
        logger.warning('%s notification of event %s to user %s failed; will retry', kind, event.pk, user.pk)
        return False
    return True


def _send_one(user, event, kind=SentReminder.KIND_24H) -> bool:
    return _send_once(user, event, kind, types.EVENT_REMINDER, window=kind)


def _already_sent(event, kind: str) -> set[int]:
    return set(
        SentReminder.objects.filter(event=event, kind=kind, event_starts_at=event.date).values_list(
            'user_id', flat=True
        )
    )


def send_due_reminders(now=None) -> int:
    """Send every reminder that is due and not sent yet. Returns the count."""
    now = now or timezone.now()
    sent = 0
    for kind in REMINDER_WINDOWS:
        for event in due_events(now, kind):
            already = _already_sent(event, kind)
            for user in ticket_holders(event):
                if user.pk not in already and _send_one(user, event, kind):
                    sent += 1
    if sent:
        logger.info('Sent %s event reminders', sent)
    return sent
