"""Broadcast a message from an organizer to their attendees.

Delivery is dual: an in-app Notification (always) plus an email (unless the
attendee switched organizer messages off), through notifications.service.
Audience can be narrowed to a status or a ticket tier so organizers can,
say, email only VIPs or only confirmed buyers.
"""

import logging

from django.db import transaction

from common.choices import RegistrationStatusChoices
from notifications import types
from notifications.service import notify

logger = logging.getLogger(__name__)


def _audience_queryset(event, audience: str):
    """Resolve an audience selector to the target registrations."""
    qs = event.registrations.exclude(
        status__in=[RegistrationStatusChoices.CANCELLED, RegistrationStatusChoices.REJECTED]
    ).select_related('user', 'ticket_type')

    if audience in (None, '', 'all'):
        return qs
    if audience == 'confirmed':
        return qs.filter(status=RegistrationStatusChoices.CONFIRMED)
    if audience == 'pending':
        return qs.filter(status=RegistrationStatusChoices.PENDING)
    if audience == 'checked_in':
        return qs.filter(is_checked_in=True)
    if str(audience).startswith('ticket:'):
        try:
            tt_id = int(str(audience).split(':', 1)[1])
            return qs.filter(ticket_type_id=tt_id)
        except (ValueError, IndexError):
            return qs
    return qs


@transaction.atomic
def broadcast_to_attendees(*, event, subject: str, body: str, audience: str = 'all') -> dict:
    """Send `subject`/`body` to the chosen audience. Returns delivery counts."""
    regs = _audience_queryset(event, audience)

    # De-duplicate by user (a user has one registration per event anyway).
    seen_users = {}
    for r in regs:
        seen_users.setdefault(r.user_id, r.user)
    users = list(seen_users.values())

    # In-app notification for everyone; an email (queued, sent by the worker)
    # to those with an address who did not switch these messages off.
    notified = emailed = 0
    for user in users:
        notification = notify(user, types.ORGANIZER_MESSAGE, event=event, subject=subject, text=body)
        if notification is not None:
            notified += 1
            emailed += int(notification.email_queued)

    return {
        'recipients': len(users),
        'notified': notified,
        'emailed': emailed,
        'email_enabled': emailed > 0,
    }
