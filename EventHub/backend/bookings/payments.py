"""
Checkout for a whole group booking.

Mirrors the single-seat payment flow:
  - Mock mode (explicit dev opt-in) → confirm instantly, return success URL.
  - Real mode → one Stripe Checkout Session with N line items.
"""

import logging
import time
from datetime import timedelta
from decimal import Decimal

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from events.billing import event_currency, quote_breakdown, to_minor_units

from .models import Booking
from .services import confirm_booking, release_expired_bookings

logger = logging.getLogger(__name__)

# Stripe's minimum Checkout Session lifetime is 30 minutes.
CHECKOUT_SESSION_MINUTES = 31


def _success_url(booking) -> str:
    # Relative → stays on the current origin, keeps the auth token.
    return f'/payment/success?booking_id={booking.id}'


def seat_total(booking_seat) -> Decimal:
    """What one seat of the group really costs: zone price + tax & fees,
    computed exactly like a single ticket (events.billing)."""
    return Decimal(quote_breakdown(booking_seat.booking.event, booking_seat.price)['total'])


def booking_amount(booking) -> Decimal:
    return sum((seat_total(bs) for bs in booking.seats.select_related('booking__event')), Decimal('0.00'))


@transaction.atomic
def create_booking_checkout(booking: Booking) -> dict:
    """Return {checkout_url, mock} for a holding booking."""
    release_expired_bookings(booking.event)
    booking = Booking.objects.select_for_update().select_related('event').get(pk=booking.pk)
    if booking.status != Booking.Status.HOLDING:
        raise ValueError('This booking is not awaiting payment.')
    if not booking.seats.exists():
        raise ValueError('This booking has no seats.')

    # ── Mock mode: simulate instant success ──
    if settings.STRIPE_MOCK_MODE:
        booking.stripe_session_id = f'mock_booking_{booking.id}_{int(time.time())}'
        booking.save(update_fields=['stripe_session_id'])
        confirm_booking(booking, amount_paid=booking_amount(booking))
        return {'checkout_url': _success_url(booking), 'mock': True}

    # ── Real Stripe ──
    currency = event_currency(booking.event)
    line_items = []
    for bs in booking.seats.select_related('seat', 'booking__event'):
        line_items.append({
            'price_data': {
                'currency': currency.lower(),
                'product_data': {
                    'name': f'{booking.event.title} — Seat {bs.seat.row}-{bs.seat.col}',
                    'description': f'{bs.seat.price_zone.title()} zone',
                },
                'unit_amount': to_minor_units(seat_total(bs), currency),
            },
            'quantity': 1,
        })

    # Keep the seats held for as long as the Stripe page stays payable.
    expires_at = timezone.now() + timedelta(minutes=CHECKOUT_SESSION_MINUTES)
    booking.hold_expires_at = max(booking.hold_expires_at or expires_at, expires_at + timedelta(minutes=1))

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=line_items,
        mode='payment',
        expires_at=int(expires_at.timestamp()),
        success_url=f'{settings.FRONTEND_URL}/payment/success?booking_id={booking.id}&session_id={{CHECKOUT_SESSION_ID}}',
        cancel_url=f'{settings.FRONTEND_URL}/payment/cancel',
        client_reference_id=str(booking.id),
        metadata={'booking_id': str(booking.id)},
    )
    booking.stripe_session_id = session.id
    booking.save(update_fields=['stripe_session_id', 'hold_expires_at'])
    return {'checkout_url': session.url, 'mock': False, 'session_id': session.id}


def confirm_booking_by_session(session):
    """Used by the Stripe webhook / success-page verify to confirm a booking."""
    booking_id = (session.get('metadata') or {}).get('booking_id')
    booking = Booking.objects.filter(stripe_session_id=session['id']).first()
    if booking is None and booking_id:
        booking = Booking.objects.filter(pk=booking_id).first()
    intent = session.get('payment_intent', '') or ''
    if booking is None:
        from payments.services import _refund_payment_intent
        logger.error('Paid Stripe session %s matches no booking — refunding', session['id'])
        _refund_payment_intent(intent, key=f'orphan-booking-refund-{session["id"]}')
        return None
    amount_total = session.get('amount_total')
    amount_paid = None
    if amount_total is not None:
        minor_per_unit = to_minor_units(1, event_currency(booking.event))
        amount_paid = (Decimal(amount_total) / minor_per_unit).quantize(Decimal('0.01'))
    return confirm_booking(booking, payment_intent_id=intent, amount_paid=amount_paid)
