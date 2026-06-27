"""
Group-booking business logic.

All seat-state mutations happen here, inside DB transactions with row locks so
two buyers can never grab the same seat. Every change broadcasts over WebSocket.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from events.models import EventSeat
from events.seat_pricing import seat_price
from events.services import broadcast_seat_update

from .models import Booking, BookingSeat

logger = logging.getLogger(__name__)

MAX_GROUP_SEATS = 8
HOLD_MINUTES = 10


# ───────────────────────── expiry (lazy) ─────────────────────────

def release_expired_bookings(event=None):
    """Release seats from holding bookings whose 10-min hold has elapsed."""
    now = timezone.now()
    qs = Booking.objects.filter(status=Booking.Status.HOLDING, hold_expires_at__lt=now)
    if event is not None:
        qs = qs.filter(event=event)

    for booking in qs.prefetch_related('seats__seat__seat_map'):
        _release_booking_seats(booking)
        booking.status = Booking.Status.EXPIRED
        booking.save(update_fields=['status'])
        logger.info('Booking %s expired, seats released', booking.id)


def _release_booking_seats(booking):
    """Free every seat in a booking and broadcast, then delete the rows."""
    for bs in booking.seats.select_related('seat', 'seat__seat_map'):
        seat = bs.seat
        EventSeat.objects.filter(pk=seat.id).update(is_available=True)
        seat.is_available = True
        broadcast_seat_update(seat)
    booking.seats.all().delete()


# ───────────────────────── create ─────────────────────────

@transaction.atomic
def create_booking(*, user, event, seat_ids):
    """Hold a group of seats for a user. Returns the Booking."""
    from events.services import ensure_attendee_can_buy
    ensure_attendee_can_buy(user)

    release_expired_bookings(event)

    seat_ids = list(dict.fromkeys(seat_ids))  # dedupe, keep order
    if not seat_ids:
        raise ValueError('Select at least one seat.')
    if len(seat_ids) > MAX_GROUP_SEATS:
        raise ValueError(f'You can book at most {MAX_GROUP_SEATS} seats at once.')

    # Lock the seat rows so concurrent bookings serialise.
    seats = list(
        EventSeat.objects.select_for_update()
        .filter(id__in=seat_ids, seat_map__event=event)
        .select_related('seat_map')
    )
    if len(seats) != len(seat_ids):
        raise ValueError('One or more seats were not found for this event.')

    for seat in seats:
        if not seat.is_available:
            raise ValueError(f'Seat {seat.row}-{seat.col} is no longer available.')

    booking = Booking.objects.create(
        owner=user,
        event=event,
        status=Booking.Status.HOLDING,
        hold_expires_at=timezone.now() + timedelta(minutes=HOLD_MINUTES),
    )

    for seat in seats:
        BookingSeat.objects.create(
            booking=booking,
            seat=seat,
            price=seat_price(event, seat),
        )
        seat.is_available = False
        seat.save(update_fields=['is_available'])
        broadcast_seat_update(seat)

    logger.info('Booking %s created with %s seats', booking.id, len(seats))
    return booking


# ───────────────────────── claim ─────────────────────────

@transaction.atomic
def claim_seat(*, booking, seat_id, attendee_name, user=None):
    """A friend (or the owner) claims a specific seat in the booking.

    Allowed while the booking is holding AND after it is paid — friends
    usually put their names on the tickets after the owner has checked out.
    """
    if booking.status not in (Booking.Status.HOLDING, Booking.Status.CONFIRMED):
        raise ValueError('This booking is no longer open for claims.')
    if booking.is_expired:
        raise ValueError('This booking hold has expired.')

    try:
        bs = booking.seats.select_related('seat').get(seat_id=seat_id)
    except BookingSeat.DoesNotExist:
        raise ValueError('That seat is not part of this booking.')

    bs.attendee_name = (attendee_name or '').strip()[:120]
    if user is not None and user.is_authenticated:
        bs.claimed_by = user
    bs.save(update_fields=['attendee_name', 'claimed_by'])
    return bs


# ───────────────────────── confirm / cancel ─────────────────────────

@transaction.atomic
def confirm_booking(booking):
    """Mark a booking paid. Seats become permanent, tickets are live."""
    if booking.status == Booking.Status.CONFIRMED:
        return booking
    booking.status = Booking.Status.CONFIRMED
    booking.hold_expires_at = None
    booking.save(update_fields=['status', 'hold_expires_at'])
    logger.info('Booking %s confirmed', booking.id)

    try:
        from events.notify import notify
        notify(
            booking.owner, 'ticket_purchased',
            f'🎫 {booking.seat_count} tickets confirmed: {booking.event.title}',
            'Your group booking is confirmed. Tickets are in My Tickets.',
            booking.event,
        )
    except Exception:
        pass
    return booking


@transaction.atomic
def cancel_booking(booking):
    """Owner releases a holding booking before payment."""
    if booking.status not in (Booking.Status.HOLDING,):
        raise ValueError('Only a holding booking can be cancelled.')
    _release_booking_seats(booking)
    booking.status = Booking.Status.CANCELLED
    booking.save(update_fields=['status'])
    return booking
