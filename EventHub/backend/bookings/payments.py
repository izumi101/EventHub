"""
Checkout for a whole group booking.

Mirrors the single-seat payment flow (payments.views.CreateCheckoutSessionView):
  - KZT event with Freedom Pay enabled → one Freedom Pay payment for the whole
    group (payments.freedompay_flow) with a QR code of the payment page. Mock
    mode does not shortcut it: the gateway (or its emulator) is always called.
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


def create_booking_checkout(booking: Booking) -> dict:
    """Open the payment of a holding booking; the answer has the shape of
    `schema.BookingCheckoutResponseSerializer`.

    Raises ValueError (not payable), a PaymentProviderError (Freedom Pay
    unavailable) or a Stripe error.
    """
    from payments import freedompay_flow

    release_expired_bookings(booking.event)
    # Routing reads without a lock; start_checkout validates again under its
    # own locks. A booking with nothing to pay keeps the legacy path.
    if freedompay_flow.provider_for(booking) == freedompay_flow.PROVIDER and booking_amount(booking) > 0:
        # Not inside a transaction: the gateway is called with no row locked.
        checkout = freedompay_flow.start_checkout(booking)
        return {
            'checkout_url': checkout.result.redirect_url,
            'mock': False,
            'session_id': checkout.result.session_id,
            'provider': freedompay_flow.PROVIDER,
            'payment_id': checkout.payment.pk,
            'qr_code': checkout.qr_data_url,
            'amount': str(checkout.payment.amount),
            'currency': checkout.payment.currency.upper(),
        }
    return _legacy_checkout(booking)


@transaction.atomic
def _legacy_checkout(booking: Booking) -> dict:
    """Mock or Stripe Checkout (every currency Freedom Pay does not take)."""
    booking = Booking.objects.select_for_update().select_related('event').get(pk=booking.pk)
    if booking.status != Booking.Status.HOLDING:
        raise ValueError('This booking is not awaiting payment.')
    if not booking.seats.exists():
        raise ValueError('This booking has no seats.')
    currency = event_currency(booking.event)
    amount = booking_amount(booking)
    summary = {'payment_id': None, 'qr_code': None, 'amount': str(amount), 'currency': currency}

    # ── Mock mode: simulate instant success ──
    if settings.STRIPE_MOCK_MODE:
        booking.stripe_session_id = f'mock_booking_{booking.id}_{int(time.time())}'
        booking.save(update_fields=['stripe_session_id'])
        confirm_booking(booking, amount_paid=amount)
        return {
            'checkout_url': _success_url(booking),
            'mock': True,
            'session_id': booking.stripe_session_id,
            'provider': 'mock',
            **summary,
        }

    # ── Real Stripe ──
    line_items = []
    for bs in booking.seats.select_related('seat', 'booking__event'):
        line_items.append(
            {
                'price_data': {
                    'currency': currency.lower(),
                    'product_data': {
                        'name': f'{booking.event.title} — Seat {bs.seat.row}-{bs.seat.col}',
                        'description': f'{bs.seat.price_zone.title()} zone',
                    },
                    'unit_amount': to_minor_units(seat_total(bs), currency),
                },
                'quantity': 1,
            }
        )

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
    return {'checkout_url': session.url, 'mock': False, 'session_id': session.id, 'provider': 'stripe', **summary}


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
