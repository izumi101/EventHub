"""
Group-booking business logic.

All seat-state mutations happen here, inside DB transactions with row locks so
two buyers can never grab the same seat. Every change broadcasts over WebSocket.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from events.models import Event, EventSeat
from events.seat_pricing import seat_price
from events.services import broadcast_seat_update

from .models import Booking, BookingSeat

logger = logging.getLogger(__name__)

MAX_GROUP_SEATS = 8
HOLD_MINUTES = 10


# ───────────────────────── expiry ─────────────────────────

@transaction.atomic
def release_expired_bookings(event=None):
    """Release seats from holding bookings whose 10-min hold has elapsed."""
    now = timezone.now()
    qs = (
        Booking.objects
        # skip_locked: a booking being confirmed right now keeps its seats.
        .select_for_update(skip_locked=True)
        .filter(status=Booking.Status.HOLDING, hold_expires_at__lt=now)
    )
    if event is not None:
        qs = qs.filter(event=event)

    for booking in qs:
        _release_booking_seats(booking)
        booking.status = Booking.Status.EXPIRED
        booking.save(update_fields=['status'])
        logger.info('Booking %s expired, seats released', booking.id)


def _release_booking_seats(booking):
    """Free every seat in a booking and broadcast, then delete the rows."""
    freed = []
    for bs in booking.seats.select_related('seat', 'seat__seat_map'):
        seat = bs.seat
        EventSeat.objects.filter(pk=seat.id).update(is_available=True)
        seat.is_available = True
        freed.append(seat)
    booking.seats.all().delete()
    if freed:
        transaction.on_commit(lambda: [broadcast_seat_update(s) for s in freed])


# ───────────────────────── create ─────────────────────────

@transaction.atomic
def create_booking(*, user, event, seat_ids):
    """Hold a group of seats for a user. Returns the Booking."""
    from events.services import ensure_attendee_can_buy, ensure_event_on_sale
    from events.models import WaitlistEntry

    # Same lock order as single registrations (event → seats) so the two
    # flows serialise on capacity instead of overselling each other.
    event = Event.objects.select_for_update().get(pk=event.pk)
    ensure_attendee_can_buy(user, event)
    ensure_event_on_sale(event)

    release_expired_bookings(event)

    seat_ids = list(dict.fromkeys(seat_ids))  # dedupe, keep order
    if not seat_ids:
        raise ValueError('Select at least one seat.')
    if len(seat_ids) > MAX_GROUP_SEATS:
        raise ValueError(f'You can book at most {MAX_GROUP_SEATS} seats at once.')

    # One unpaid group hold per buyer per event — otherwise a single account
    # could keep the whole hall on hold by chaining 8-seat bookings.
    if Booking.objects.filter(owner=user, event=event, status=Booking.Status.HOLDING).exists():
        raise ValueError('You already have a group booking awaiting payment for this event.')

    outstanding_offers = WaitlistEntry.objects.filter(
        event=event, status=WaitlistEntry.STATUS_OFFERED,
    ).exclude(user=user).count()
    if event.available_spots - outstanding_offers < len(seat_ids):
        raise ValueError('Not enough spots left for this many seats.')

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
    transaction.on_commit(lambda: [broadcast_seat_update(s) for s in seats])

    logger.info('Booking %s created with %s seats', booking.id, len(seats))
    return booking


# ───────────────────────── claim ─────────────────────────

@transaction.atomic
def claim_seat(*, booking, seat_id, attendee_name, user=None):
    """A friend (or the owner) claims a specific seat in the booking.

    Allowed while the booking is holding AND after it is paid — friends
    usually put their names on the tickets after the owner has checked out.
    A claimed seat can't be taken over by someone else (only the owner may
    reassign seats), and a friend claims at most one seat per booking.
    """
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    if booking.status not in (Booking.Status.HOLDING, Booking.Status.CONFIRMED):
        raise ValueError('This booking is no longer open for claims.')
    if booking.is_expired:
        raise ValueError('This booking hold has expired.')

    try:
        bs = booking.seats.select_related('seat').get(seat_id=seat_id)
    except BookingSeat.DoesNotExist:
        raise ValueError('That seat is not part of this booking.')

    is_auth = user is not None and user.is_authenticated
    is_owner = is_auth and user.id == booking.owner_id

    if not is_owner:
        already_claimed = bs.claimed_by_id is not None or bool(bs.attendee_name)
        if already_claimed and not (is_auth and bs.claimed_by_id == user.id):
            raise ValueError('This seat has already been claimed.')
        if is_auth and booking.seats.filter(claimed_by=user).exclude(pk=bs.pk).exists():
            raise ValueError('You have already claimed a seat in this booking.')

    bs.attendee_name = (attendee_name or '').strip()[:120]
    if is_auth and not is_owner:
        bs.claimed_by = user
    bs.save(update_fields=['attendee_name', 'claimed_by'])
    return bs


# ───────────────────────── confirm / cancel ─────────────────────────

@transaction.atomic
def confirm_booking(booking, *, payment_intent_id='', amount_paid=None):
    """Mark a booking paid. Seats become permanent, tickets are live.

    If the hold already ended (expired → seats released, or cancelled) the
    payment is refunded instead: those seats may already belong to someone else.
    """
    booking = Booking.objects.select_for_update().select_related('event', 'owner').get(pk=booking.pk)

    if booking.status == Booking.Status.CONFIRMED:
        if payment_intent_id and booking.stripe_payment_intent_id \
                and payment_intent_id != booking.stripe_payment_intent_id:
            from payments.services import _refund_payment_intent
            _refund_payment_intent(payment_intent_id, key=f'booking-duplicate-refund-{payment_intent_id}')
        return booking

    if booking.status != Booking.Status.HOLDING:
        logger.warning('Payment for booking %s arrived in status %s — refunding', booking.id, booking.status)
        from payments.services import _refund_payment_intent
        _refund_payment_intent(payment_intent_id, key=f'booking-late-refund-{payment_intent_id}')
        owner, event = booking.owner, booking.event

        def notify_late():
            from events.notify import notify
            notify(owner, 'payment_failed', f'💸 Payment refunded: {event.title}',
                   'Your group payment arrived after the seat hold expired, so it was refunded '
                   'automatically. Please book again.', event)

        transaction.on_commit(notify_late)
        return booking

    booking.status = Booking.Status.CONFIRMED
    booking.hold_expires_at = None
    booking.stripe_payment_intent_id = payment_intent_id or booking.stripe_payment_intent_id
    if amount_paid is not None:
        booking.amount_paid = amount_paid
    booking.save(update_fields=['status', 'hold_expires_at', 'stripe_payment_intent_id', 'amount_paid'])
    logger.info('Booking %s confirmed', booking.id)

    owner, event, count = booking.owner, booking.event, booking.seat_count

    def notify_confirmed():
        from events.notify import notify
        notify(
            owner, 'ticket_purchased',
            f'🎫 {count} tickets confirmed: {event.title}',
            'Your group booking is confirmed. Tickets are in My Tickets.',
            event,
        )

    transaction.on_commit(notify_confirmed)
    return booking


@transaction.atomic
def refund_booking(booking, *, actor, reason='', event_cancelled=False):
    """Organizer refunds a paid group booking in full: the money goes back
    through Stripe, the seats return to sale and the QR tickets stop working."""
    from common.permissions import can_manage_event
    from payments.services import _refund_payment_intent

    booking = Booking.objects.select_for_update().select_related('event', 'owner').get(pk=booking.pk)
    if not can_manage_event(booking.event, actor):
        raise PermissionError('Only the event team can refund group bookings.')
    if booking.status != Booking.Status.CONFIRMED:
        raise ValueError('Only a paid booking can be refunded.')
    if not event_cancelled and booking.seats.filter(is_checked_in=True).exists():
        raise ValueError('Some of these tickets were already used for entry.')

    if booking.stripe_payment_intent_id:
        # Idempotent: a retry after a crash can't refund twice.
        _refund_payment_intent(booking.stripe_payment_intent_id, key=f'booking-refund-{booking.pk}')
    if booking.amount_paid is None:
        from .payments import booking_amount
        booking.amount_paid = booking_amount(booking)

    _release_booking_seats(booking)
    booking.status = Booking.Status.REFUNDED
    booking.refunded_at = timezone.now()
    booking.refund_reason = (reason or '')[:255]
    booking.save(update_fields=['status', 'refunded_at', 'refund_reason', 'amount_paid'])

    from events.notify import notify
    notify(booking.owner, 'payment_failed', f'💸 Group booking refunded: {booking.event.title}',
           'Your group booking was refunded by the organizer.' + (f' Reason: {reason}' if reason else ''),
           booking.event)
    from events.webhooks import fire
    fire(booking.event, 'refund_issued', {
        'booking_id': str(booking.pk),
        'user': booking.owner.username,
        'refunded_amount': str(booking.amount_paid),
        'full_refund': True,
    })
    logger.info('Booking %s refunded by %s', booking.pk, actor.pk)
    return booking


@transaction.atomic
def cancel_booking(booking):
    """Owner releases a holding booking before payment."""
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    if booking.status not in (Booking.Status.HOLDING,):
        raise ValueError('Only a holding booking can be cancelled.')
    _release_booking_seats(booking)
    booking.status = Booking.Status.CANCELLED
    booking.save(update_fields=['status'])
    return booking
