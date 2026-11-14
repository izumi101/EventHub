"""The one entry point for user notifications.

    from notifications.service import notify
    notify(user, types.TICKET_PURCHASED, event=event, registration=reg, amount=..., currency=...)

`notify` writes the in-app row (events.Notification) and — when the user
has an email address and has not switched that type off — the `send_email`
outbox job, both in the caller's transaction. So a notification exists if
and only if the business change that caused it was committed: a rollback
leaves neither the row nor the email.
"""

import logging

from django.db import transaction

from . import types
from .emails import render_email
from .messages import build_message
from .models import NotificationPreference

logger = logging.getLogger(__name__)


def email_enabled(user, type_key: str) -> bool:
    spec = types.get(type_key)
    if not spec.sends_email:
        return False
    if not spec.email_optional:
        return True
    try:
        preference = user.notification_preference
    except NotificationPreference.DoesNotExist:
        return True
    return preference.email_enabled(type_key)


def notify(user, type_key: str, *, event=None, **data):
    """Notify `user`; returns the in-app Notification (None if it failed),
    whose `email_queued` attribute says whether an email was queued.

    Never raises: a notification must not break the business flow that
    triggered it. The writes run in a savepoint, so a failure here rolls
    back only the notification, never the caller's transaction; failures
    are logged.
    """
    from events.models import Notification
    from jobs.handlers import enqueue_email

    try:
        with transaction.atomic():
            message = build_message(type_key, user, event, data)
            notification = Notification.objects.create(
                user=user,
                type=type_key,
                title=message.title[:200],
                body=message.body,
                event=event,
            )
            notification.email_queued = bool(user.email) and email_enabled(user, type_key)
            if notification.email_queued:
                email = render_email(type_key, message)
                enqueue_email(
                    email['subject'],
                    email['body'],
                    user.email,
                    html_body=email['html_body'],
                    attachments=email['attachments'],
                    headers=email['headers'],
                )
            return notification
    except Exception:
        logger.exception('Could not create %s notification for user %s', type_key, getattr(user, 'pk', None))
        return None


def notify_many(users, type_key: str, *, event=None, **data) -> int:
    """Notify each distinct user once. Returns how many were notified."""
    seen = set()
    sent = 0
    for user in users:
        if user is None or user.pk in seen:
            continue
        seen.add(user.pk)
        if notify(user, type_key, event=event, **data) is not None:
            sent += 1
    return sent


def ticket_holders(event) -> list:
    """Users holding a valid ticket for `event`: confirmed registrations,
    owners of confirmed group bookings and friends who claimed a seat in
    one. Each user once, in a stable order."""
    from django.contrib.auth.models import User

    from bookings.models import Booking, BookingSeat
    from common.choices import RegistrationStatusChoices

    user_ids = set(
        event.registrations.filter(status=RegistrationStatusChoices.CONFIRMED).values_list('user_id', flat=True)
    )
    user_ids |= set(
        Booking.objects.filter(event=event, status=Booking.Status.CONFIRMED).values_list('owner_id', flat=True)
    )
    user_ids |= set(
        BookingSeat.objects.filter(
            booking__event=event, booking__status=Booking.Status.CONFIRMED, claimed_by__isnull=False
        ).values_list('claimed_by_id', flat=True)
    )
    return list(User.objects.filter(pk__in=user_ids).select_related('notification_preference').order_by('pk'))
