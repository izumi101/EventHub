import logging
import time

import stripe
from django.conf import settings
from django.db import transaction

from common.choices import PaymentStatusChoices, RegistrationStatusChoices
from .models import Payment

logger = logging.getLogger(__name__)


@transaction.atomic
def create_mock_checkout_session(*, registration):
    """Simulate a successful Stripe checkout for local development.

    Used only when STRIPE_MOCK_MODE is on (no real Stripe key). Confirms the
    registration immediately and returns a fake session whose `url` points at
    the frontend success page, so the UX is identical to the real flow.
    """
    mock_session_id = f'mock_sess_{registration.id}_{int(time.time())}'

    from events.billing import registration_amount
    amount = registration_amount(registration)

    payment, _ = Payment.objects.get_or_create(
        registration=registration,
        defaults={'amount': amount},
    )
    payment.stripe_checkout_session_id = mock_session_id
    payment.amount = amount
    payment.status = PaymentStatusChoices.COMPLETED
    payment.save(update_fields=['stripe_checkout_session_id', 'amount', 'status'])

    registration.status = RegistrationStatusChoices.CONFIRMED
    registration.seat_held_until = None
    registration.save(update_fields=['status', 'seat_held_until'])

    _consume_promo(registration)
    _fire_ticket_sold(registration, amount)

    logger.info('[MOCK] Payment auto-confirmed for registration %s', registration.id)

    try:
        from events.notify import notify_ticket_purchased
        notify_ticket_purchased(registration.user, registration.event)
    except Exception:
        pass

    # Relative URL so the SPA stays on the current origin (http://localhost:4200
    # or https://localhost) — avoids a cross-origin redirect that would drop the
    # auth token stored in localStorage.
    success_url = f'/payment/success?session_id={mock_session_id}'
    return success_url, payment


def _consume_promo(registration):
    """Atomically increment the used-count of the registration's promo code."""
    if not registration.promo_code_id:
        return
    from django.db.models import F
    from events.models import PromoCode
    PromoCode.objects.filter(pk=registration.promo_code_id).update(times_used=F('times_used') + 1)


def _fire_ticket_sold(registration, amount):
    """Notify webhooks that a paid ticket completed."""
    try:
        from events.webhooks import fire
        fire(registration.event, 'ticket_sold', {
            'registration_id': registration.id,
            'user': registration.user.username,
            'amount': str(amount),
            'ticket_type': registration.ticket_type.name if registration.ticket_type_id else None,
        })
    except Exception:
        pass


def create_checkout_session(*, registration):
    from events.billing import registration_amount
    amount = registration_amount(registration)

    label = registration.event.title
    if registration.promo_code_id:
        label += f' (promo {registration.promo_code.code})'

    checkout_session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': label,
                    'description': f'Registration for {registration.event.title}',
                },
                'unit_amount': int(amount * 100),
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=f'{settings.FRONTEND_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}',
        cancel_url=f'{settings.FRONTEND_URL}/payment/cancel',
        metadata={'registration_id': registration.id},
    )

    payment, created = Payment.objects.get_or_create(
        registration=registration,
        defaults={
            'amount': amount,
            'stripe_checkout_session_id': checkout_session.id,
        },
    )
    if not created:
        payment.stripe_checkout_session_id = checkout_session.id
        payment.amount = amount
        payment.save(update_fields=['stripe_checkout_session_id', 'amount'])

    return checkout_session, payment


@transaction.atomic
def confirm_stripe_checkout_session(session):
    payment = Payment.objects.get(stripe_checkout_session_id=session['id'])

    # Idempotent: webhook and success-page verification can both call this.
    if payment.status == PaymentStatusChoices.COMPLETED:
        return payment

    payment.status = PaymentStatusChoices.COMPLETED
    payment.stripe_payment_intent_id = session.get('payment_intent', '') or ''
    payment.save(update_fields=['status', 'stripe_payment_intent_id'])

    registration = payment.registration
    registration.status = RegistrationStatusChoices.CONFIRMED
    # Payment succeeded — the seat is now permanent, clear the hold timer.
    registration.seat_held_until = None
    registration.save(update_fields=['status', 'seat_held_until'])
    _consume_promo(registration)
    _fire_ticket_sold(registration, payment.amount)
    logger.info('Payment completed for registration %s', registration.id)

    # Fire in-app notification
    try:
        from events.notify import notify_ticket_purchased
        notify_ticket_purchased(registration.user, registration.event)
    except Exception:
        pass

    return payment


@transaction.atomic
def refund_payment(*, payment, amount=None, reason='', notify_user=True):
    """Refund a completed payment, fully or partially.

    `amount` None → full refund of the remaining refundable balance.
    Releases the seat and cancels the registration only on a full refund.
    In mock mode the Stripe call is skipped but the books are still updated.

    `notify_user` False suppresses the "Refund issued" attendee notification —
    used when the caller (e.g. refund-request approval) sends its own, so the
    attendee doesn't receive two notifications for one refund.
    """
    from decimal import Decimal
    from django.utils import timezone

    if payment.status not in (PaymentStatusChoices.COMPLETED,):
        raise ValueError('Only completed payments can be refunded.')

    remaining = payment.amount - payment.refunded_amount
    if remaining <= 0:
        raise ValueError('This payment has already been fully refunded.')

    refund_amount = remaining if amount is None else Decimal(str(amount))
    if refund_amount <= 0:
        raise ValueError('Refund amount must be greater than zero.')
    if refund_amount > remaining:
        raise ValueError(f'Cannot refund more than the remaining ${remaining}.')

    # Issue the Stripe refund unless we're in mock mode.
    if not getattr(settings, 'STRIPE_MOCK_MODE', False) and payment.stripe_payment_intent_id:
        try:
            stripe.Refund.create(
                payment_intent=payment.stripe_payment_intent_id,
                amount=int(refund_amount * 100),
            )
        except stripe.error.StripeError as exc:
            logger.error('Stripe refund failed for payment %s: %s', payment.id, exc)
            raise ValueError(f'Stripe refund failed: {exc}')

    payment.refunded_amount = payment.refunded_amount + refund_amount
    payment.refund_reason = reason or payment.refund_reason
    payment.refunded_at = timezone.now()

    is_full = payment.refunded_amount >= payment.amount
    if is_full:
        payment.status = PaymentStatusChoices.REFUNDED
    payment.save(update_fields=['refunded_amount', 'refund_reason', 'refunded_at', 'status'])

    registration = payment.registration
    if is_full:
        # Release the seat and cancel the registration on a full refund.
        from events.services import cancel_registration
        try:
            cancel_registration(user=registration.user, event=registration.event)
        except Exception as exc:
            logger.warning('Seat release after refund failed: %s', exc)

    # Notify the attendee (unless the caller will send its own message).
    if notify_user:
        try:
            from events.notify import notify
            notify(
                registration.user, 'payment_failed',
                f'💸 Refund issued: {registration.event.title}',
                f'You were refunded ${refund_amount}.' + (f' Reason: {reason}' if reason else ''),
                event=registration.event,
            )
        except Exception:
            pass

    # Fire the refund webhook.
    try:
        from events.webhooks import fire
        fire(registration.event, 'refund_issued', {
            'registration_id': registration.id,
            'user': registration.user.username,
            'refunded_amount': str(refund_amount),
            'full_refund': is_full,
        })
    except Exception:
        pass

    logger.info('Refunded $%s on payment %s (full=%s)', refund_amount, payment.id, is_full)
    return payment


@transaction.atomic
def mark_offline_paid(*, registration, amount=None):
    """Organizer manually confirms a cash / bank-transfer payment."""
    if amount is None:
        # The real amount owed — tier / seat zone / promo / tax & fees —
        # not the bare event price.
        from events.billing import registration_amount
        amt = registration_amount(registration)
    else:
        amt = amount
    payment, _ = Payment.objects.get_or_create(
        registration=registration,
        defaults={'amount': amt},
    )
    payment.amount = amt
    payment.method = Payment.METHOD_OFFLINE
    payment.status = PaymentStatusChoices.COMPLETED
    payment.save(update_fields=['amount', 'method', 'status'])

    registration.status = RegistrationStatusChoices.CONFIRMED
    registration.seat_held_until = None
    registration.save(update_fields=['status', 'seat_held_until'])

    try:
        from events.notify import notify_ticket_purchased
        notify_ticket_purchased(registration.user, registration.event)
    except Exception:
        pass
    return payment


def verify_payment(session_id: str):
    """Return the payment for a session, confirming it if Stripe says it's paid.

    The Stripe webhook is the source of truth in production, but in local
    development webhooks are often not forwarded. Actively retrieving the
    session here lets the success page confirm the registration on its own.
    """
    payment = Payment.objects.get(stripe_checkout_session_id=session_id)

    if payment.status != PaymentStatusChoices.COMPLETED:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            if session.get('payment_status') == 'paid':
                confirm_stripe_checkout_session(session)
                payment.refresh_from_db()
        except stripe.error.StripeError as exc:
            logger.warning('Could not retrieve Stripe session %s: %s', session_id, exc)

    return payment
