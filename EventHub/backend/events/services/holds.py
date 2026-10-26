"""Seat-hold expiry and paid-registration reconciliation.

`run_maintenance` (management command, run by the scheduler container) calls
these periodically; write paths that need an exact seat count (registration,
checkout) also call them for the event they touch. Read-only endpoints don't.
"""

from django.db import transaction
from django.utils import timezone

from common.choices import PaymentStatusChoices, RegistrationStatusChoices

from ..models import Event, EventSeat, Registration
from .realtime import broadcast_seat_update

# How long a seat / spot is held for an unpaid registration before it is
# automatically released back to the pool.
SEAT_HOLD_MINUTES = 10


@transaction.atomic
def release_expired_seat_holds(event: Event = None):
    """Release seats/spots from unpaid registrations whose hold expired."""
    # A paid registration must never be released as an "expired hold" — confirm
    # it first so the loop below only touches genuinely unpaid, expired holds.
    reconcile_paid_registrations(event=event)

    now = timezone.now()
    qs = (
        Registration.objects
        # skip_locked: a registration whose payment is being confirmed right
        # now is row-locked by the confirmation and must not be released.
        .select_for_update(skip_locked=True, of=('self',))
        .filter(
            status=RegistrationStatusChoices.PENDING,
            seat_held_until__isnull=False,
            seat_held_until__lt=now,
        )
        .exclude(payment__status=PaymentStatusChoices.COMPLETED)
        .select_related('seat', 'seat__seat_map')
    )
    if event is not None:
        qs = qs.filter(event=event)

    from ..promo import release_promo

    freed_events = set()
    freed_seats = []
    for registration in qs:
        freed_seat = registration.seat
        if freed_seat:
            EventSeat.objects.filter(pk=registration.seat_id).update(is_available=True)
            freed_seat.is_available = True  # reflect in-memory for broadcast
            freed_seats.append(freed_seat)
        registration.status = RegistrationStatusChoices.CANCELLED
        registration.seat = None
        registration.seat_held_until = None
        registration.save(update_fields=['status', 'seat', 'seat_held_until'])
        release_promo(registration)
        freed_events.add(registration.event_id)

    if freed_seats:
        transaction.on_commit(lambda: [broadcast_seat_update(s) for s in freed_seats])

    # Offer the freed spots to anyone waiting.
    if freed_events:
        from ..waitlist import promote_waitlist
        for ev in Event.objects.filter(id__in=freed_events):
            promote_waitlist(ev)
    return len(freed_events)


def reconcile_paid_registrations(*, user=None, event=None):
    """Confirm any pending registration whose payment already completed.

    Guards against a stuck state where the payment succeeded but the
    registration status was never advanced to confirmed. Idempotent.
    """
    qs = Registration.objects.filter(
        status=RegistrationStatusChoices.PENDING,
        payment__status=PaymentStatusChoices.COMPLETED,
    )
    if user is not None:
        qs = qs.filter(user=user)
    if event is not None:
        qs = qs.filter(event=event)
    return Registration.objects.filter(pk__in=list(qs.values_list('pk', flat=True))).update(
        status=RegistrationStatusChoices.CONFIRMED,
        seat_held_until=None,
    )
