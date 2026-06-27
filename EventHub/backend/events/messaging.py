"""Broadcast a message from an organizer to their attendees.

Delivery is dual: an in-app Notification (always) plus an email (when an SMTP
backend is configured). Audience can be narrowed to a status or a ticket tier
so organizers can, say, email only VIPs or only confirmed buyers.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail

from common.choices import RegistrationStatusChoices
from .models import Notification

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


def broadcast_to_attendees(*, event, subject: str, body: str, audience: str = 'all') -> dict:
    """Send `subject`/`body` to the chosen audience. Returns delivery counts."""
    regs = _audience_queryset(event, audience)

    # De-duplicate by user (a user has one registration per event anyway).
    seen_users = {}
    for r in regs:
        seen_users.setdefault(r.user_id, r.user)
    users = list(seen_users.values())

    # 1. In-app notifications (bulk insert).
    Notification.objects.bulk_create([
        Notification(
            user=u, type='event_updated',
            title=f'📣 {event.title}: {subject}',
            body=body, event=event,
        ) for u in users
    ])

    # 2. Email — best-effort, and only when SMTP is genuinely configured.
    # Without a real EMAIL_HOST the smtp backend would block on connection
    # timeouts for every recipient, so we skip it and rely on in-app delivery.
    emailed = 0
    recipients = [u.email for u in users if u.email]
    backend = getattr(settings, 'EMAIL_BACKEND', '')
    host = getattr(settings, 'EMAIL_HOST', '') or ''
    smtp_ready = 'smtp' in backend and host and host not in ('localhost', '127.0.0.1')
    non_smtp_ok = backend and 'smtp' not in backend and 'dummy' not in backend
    email_enabled = bool(recipients) and (smtp_ready or non_smtp_ok)

    if email_enabled:
        from_addr = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@eventhub.local')
        for addr in recipients:
            try:
                send_mail(
                    subject=f'{event.title}: {subject}',
                    message=body,
                    from_email=from_addr,
                    recipient_list=[addr],
                    fail_silently=True,
                )
                emailed += 1
            except Exception as exc:
                logger.warning('Bulk email failed for event %s: %s', event.id, exc)

    return {
        'recipients': len(users),
        'notified': len(users),
        'emailed': emailed,
        'email_enabled': email_enabled,
    }
