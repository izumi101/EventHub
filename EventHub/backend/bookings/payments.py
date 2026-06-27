"""
Checkout for a whole group booking.

Mirrors the single-seat payment flow:
  - Mock mode (no real Stripe key) → confirm instantly, return success URL.
  - Real mode → one Stripe Checkout Session with N line items.
"""

import logging
import time

import stripe
from django.conf import settings

from .models import Booking
from .services import confirm_booking

logger = logging.getLogger(__name__)


def _success_url(booking) -> str:
    # Relative → stays on the current origin, keeps the auth token.
    return f'/payment/success?booking_id={booking.id}'


def create_booking_checkout(booking: Booking) -> dict:
    """Return {checkout_url, mock} for a holding booking."""
    if booking.status != Booking.Status.HOLDING:
        raise ValueError('This booking is not awaiting payment.')

    # ── Mock mode: simulate instant success ──
    if settings.STRIPE_MOCK_MODE:
        booking.stripe_session_id = f'mock_booking_{booking.id}_{int(time.time())}'
        booking.save(update_fields=['stripe_session_id'])
        confirm_booking(booking)
        return {'checkout_url': _success_url(booking), 'mock': True}

    # ── Real Stripe ──
    stripe.api_key = settings.STRIPE_SECRET_KEY
    line_items = []
    for bs in booking.seats.select_related('seat'):
        line_items.append({
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': f'{booking.event.title} — Seat {bs.seat.row}-{bs.seat.col}',
                    'description': f'{bs.seat.price_zone.title()} zone',
                },
                'unit_amount': int(bs.price * 100),
            },
            'quantity': 1,
        })

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=line_items,
        mode='payment',
        success_url=f'{settings.FRONTEND_URL}/payment/success?booking_id={booking.id}&session_id={{CHECKOUT_SESSION_ID}}',
        cancel_url=f'{settings.FRONTEND_URL}/payment/cancel',
        metadata={'booking_id': str(booking.id)},
    )
    booking.stripe_session_id = session.id
    booking.save(update_fields=['stripe_session_id'])
    return {'checkout_url': session.url, 'mock': False, 'session_id': session.id}


def confirm_booking_by_session(session_id: str):
    """Used by the Stripe webhook / success-page verify to confirm a booking."""
    try:
        booking = Booking.objects.get(stripe_session_id=session_id)
    except Booking.DoesNotExist:
        return None
    return confirm_booking(booking)
