"""Waitlist with automatic FIFO offers.

When an event fills up, attendees join a waitlist. The moment a spot frees
(cancellation, refund, expired hold) the next person in line is offered the
spot and notified. Offers have a TTL; if not claimed, the spot passes on.

Like the seat-hold system, this runs lazily — `promote_waitlist` is called
whenever a spot might have freed, so there is no background worker to babysit.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Event, WaitlistEntry
from .notify import notify

# How long an offered spot is reserved for one person before passing on.
OFFER_TTL_MINUTES = 30


@transaction.atomic
def join_waitlist(*, user, event: Event) -> WaitlistEntry:
    """Add `user` to the waitlist for `event` (idempotent)."""
    entry, created = WaitlistEntry.objects.get_or_create(
        user=user, event=event,
        defaults={'status': WaitlistEntry.STATUS_WAITING},
    )
    if not created and entry.status == WaitlistEntry.STATUS_EXPIRED:
        # Let an expired user rejoin at the back of the line.
        entry.status = WaitlistEntry.STATUS_WAITING
        entry.offered_at = None
        entry.offer_expires_at = None
        entry.created_at = timezone.now()
        entry.save()
    return entry


def leave_waitlist(*, user, event: Event):
    WaitlistEntry.objects.filter(user=user, event=event).delete()


def position(*, user, event: Event):
    """1-based queue position among people still waiting, or None."""
    try:
        entry = WaitlistEntry.objects.get(user=user, event=event)
    except WaitlistEntry.DoesNotExist:
        return None
    if entry.status == WaitlistEntry.STATUS_OFFERED:
        return {'status': 'offered', 'position': 0, 'offer_expires_at': entry.offer_expires_at}
    if entry.status != WaitlistEntry.STATUS_WAITING:
        return {'status': entry.status, 'position': None}
    ahead = WaitlistEntry.objects.filter(
        event=event, status=WaitlistEntry.STATUS_WAITING, created_at__lt=entry.created_at,
    ).count()
    return {'status': 'waiting', 'position': ahead + 1}


@transaction.atomic
def promote_waitlist(event: Event):
    """Expire stale offers, then offer any free spots to the next in line.

    Safe to call often and concurrently — uses row locks on the entries.
    """
    now = timezone.now()

    # 1. Expire offers that timed out so their spot can pass on.
    WaitlistEntry.objects.filter(
        event=event, status=WaitlistEntry.STATUS_OFFERED, offer_expires_at__lt=now,
    ).update(status=WaitlistEntry.STATUS_EXPIRED)

    # 2. How many spots are genuinely free right now?
    free = event.available_spots
    # Outstanding (still valid) offers already claim some of those spots.
    outstanding = WaitlistEntry.objects.filter(
        event=event, status=WaitlistEntry.STATUS_OFFERED,
    ).count()
    open_spots = free - outstanding
    if open_spots <= 0:
        return 0

    # 3. Offer to the next waiting people, FIFO.
    next_up = list(
        WaitlistEntry.objects
        .select_for_update()
        .filter(event=event, status=WaitlistEntry.STATUS_WAITING)
        .order_by('created_at')[:open_spots]
    )
    for entry in next_up:
        entry.status = WaitlistEntry.STATUS_OFFERED
        entry.offered_at = now
        entry.offer_expires_at = now + timedelta(minutes=OFFER_TTL_MINUTES)
        entry.save(update_fields=['status', 'offered_at', 'offer_expires_at'])
        notify(
            entry.user, 'seat_available',
            f'🎉 A spot opened up: {event.title}',
            f'You have {OFFER_TTL_MINUTES} minutes to grab your ticket before it passes to the next person.',
            event=event,
        )
    return len(next_up)


def mark_converted(*, user, event: Event):
    """Call after a waitlisted user successfully registers."""
    WaitlistEntry.objects.filter(user=user, event=event).update(
        status=WaitlistEntry.STATUS_CONVERTED,
    )
