"""Seat-hold expiry and paid-registration reconciliation.

These keep the seat pool accurate lazily (on read paths) instead of
relying on a background worker.
"""

from django.utils import timezone

from common.choices import RegistrationStatusChoices

from ..models import Event, EventSeat, Registration
from .realtime import broadcast_seat_update

# How long a seat / spot is held for an unpaid registration before it is
# automatically released back to the pool.
SEAT_HOLD_MINUTES = 10


def release_expired_seat_holds(event: Event = None):
    """Lazily release seats/spots from unpaid registrations whose hold expired.

    Called on read (seat map) and before a new registration so the pool is
    always accurate without needing a background worker.
    """
    # A paid registration must never be released as an "expired hold" — confirm
    # it first so the loop below only touches genuinely unpaid, expired holds.
    reconcile_paid_registrations(event=event)

    now = timezone.now()
    qs = Registration.objects.filter(
        status=RegistrationStatusChoices.PENDING,
        seat_held_until__isnull=False,
        seat_held_until__lt=now,
    ).exclude(payment__status='completed')
    if event is not None:
        qs = qs.filter(event=event)

    freed_events = set()
    for registration in qs.select_related('seat', 'seat__seat_map'):
        freed_seat = registration.seat
        if freed_seat:
            EventSeat.objects.filter(pk=registration.seat_id).update(is_available=True)
            freed_seat.is_available = True  # reflect in-memory for broadcast
        registration.status = RegistrationStatusChoices.CANCELLED
        registration.seat = None
        registration.seat_held_until = None
        registration.save(update_fields=['status', 'seat', 'seat_held_until'])
        if freed_seat:
            broadcast_seat_update(freed_seat)
        freed_events.add(registration.event_id)

    # Offer the freed spots to anyone waiting.
    if freed_events:
        try:
            from ..waitlist import promote_waitlist
            for ev in Event.objects.filter(id__in=freed_events):
                promote_waitlist(ev)
        except Exception:
            pass


def reconcile_paid_registrations(*, user=None, event=None):
    """Confirm any pending registration whose payment already completed.

    Guards against a stuck state where the payment succeeded (Stripe webhook or
    mock checkout) but the registration status was never advanced to confirmed.
    Such a registration is broken from the attendee's side: 'Complete payment'
    is refused ("already completed") and 'Release seat' is refused ("paid
    tickets need a refund"), so the seat stays held forever. Idempotent and
    cheap — safe to call on read paths (my-registrations, event detail).
    """
    from common.choices import PaymentStatusChoices

    qs = Registration.objects.filter(
        status=RegistrationStatusChoices.PENDING,
        payment__status=PaymentStatusChoices.COMPLETED,
    )
    if user is not None:
        qs = qs.filter(user=user)
    if event is not None:
        qs = qs.filter(event=event)

    for registration in qs:
        registration.status = RegistrationStatusChoices.CONFIRMED
        registration.seat_held_until = None
        registration.save(update_fields=['status', 'seat_held_until'])
