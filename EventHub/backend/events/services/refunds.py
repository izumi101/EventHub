"""Refund requests: attendee submission and organizer resolution."""

from django.db import transaction
from django.shortcuts import get_object_or_404

from ..models import Event, Registration


@transaction.atomic
def request_refund(*, user, event: Event, reason: str = ''):
    """Attendee asks the organizer to refund their paid ticket."""
    from ..models import RefundRequest

    registration = get_object_or_404(Registration, user=user, event=event)

    # A scanned ticket means the attendee entered the event — the service
    # was delivered, so the refund window is closed for good.
    if registration.is_checked_in:
        raise ValueError('This ticket has already been used for entry — it can no longer be refunded.')

    if not event.refundable:
        raise ValueError('Tickets for this event are non-refundable.')

    payment = getattr(registration, 'payment', None)
    if not payment or not payment.is_refundable:
        raise ValueError('No refundable payment found for this ticket.')

    existing = getattr(registration, 'refund_request', None)
    if existing and existing.status == RefundRequest.STATUS_PENDING:
        raise ValueError('You already have a pending refund request.')
    if existing and existing.status == RefundRequest.STATUS_APPROVED:
        raise ValueError('This ticket has already been refunded.')

    if existing:
        # Allow re-requesting after a rejection.
        existing.status = RefundRequest.STATUS_PENDING
        existing.reason = reason
        existing.organizer_note = ''
        existing.resolved_at = None
        existing.save()
        req = existing
    else:
        req = RefundRequest.objects.create(registration=registration, reason=reason)

    # Notify the organizer in-app.
    try:
        from ..notify import notify
        notify(
            event.organizer, 'event_updated',
            f'💸 Refund requested: {event.title}',
            f'{user.username} requested a refund of ${payment.net_amount}.'
            + (f' Reason: {reason}' if reason else ''),
            event=event,
        )
    except Exception:
        pass

    return req


@transaction.atomic
def resolve_refund_request(*, refund_request, actor, approve: bool, note: str = ''):
    """Organizer approves or rejects a refund request."""
    from django.utils import timezone as _tz
    from ..models import RefundRequest

    registration = refund_request.registration
    event = registration.event

    from common.permissions import can_manage_event
    if not can_manage_event(event, actor):
        raise PermissionError('Only the organizer can resolve refund requests.')

    if refund_request.status != RefundRequest.STATUS_PENDING:
        raise ValueError('This request has already been resolved.')

    if approve:
        payment = getattr(registration, 'payment', None)
        if payment and payment.is_refundable:
            from payments.services import refund_payment
            # Suppress the low-level "Refund issued" notice — we send the
            # user-facing "Refund approved" message below, avoiding duplicates.
            refund_payment(
                payment=payment,
                reason=f'Refund request approved: {note}'.strip(': '),
                notify_user=False,
            )
        refund_request.status = RefundRequest.STATUS_APPROVED
        notify_type, title = 'ticket_purchased', f'✅ Refund approved: {event.title}'
        body = 'Your refund has been approved and processed.'
    else:
        # Rejection means "no refund" — the attendee keeps their paid ticket,
        # so the registration stays confirmed.
        refund_request.status = RefundRequest.STATUS_REJECTED
        notify_type, title = 'payment_failed', f'❌ Refund rejected: {event.title}'
        body = 'Your refund request was declined — your ticket remains valid.'

    refund_request.organizer_note = note
    refund_request.resolved_at = _tz.now()
    refund_request.save(update_fields=['status', 'organizer_note', 'resolved_at'])

    try:
        from ..notify import notify
        notify(registration.user, notify_type, title,
               body + (f' Note: {note}' if note else ''), event=event)
    except Exception:
        pass

    return refund_request
