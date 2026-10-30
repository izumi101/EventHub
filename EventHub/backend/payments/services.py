import logging
import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from common.choices import PaymentStatusChoices, RegistrationStatusChoices
from events.models import Registration

from .models import Payment

logger = logging.getLogger(__name__)

# Stripe refuses Checkout Sessions that expire sooner than 30 minutes after
# creation; the seat hold is stretched to cover the session's lifetime.
CHECKOUT_SESSION_MINUTES = 31


def stripe_to_dict(obj) -> dict:
    """Plain dict from a Stripe object. Since stripe-python 15, StripeObject is
    no longer a dict: `.get()` raises AttributeError, so convert at the edge."""
    return obj.to_dict() if hasattr(obj, 'to_dict') else dict(obj)


def _lock_registration(registration_id, **filters):
    return (
        Registration.objects.select_for_update(of=('self',))
        .select_related('event', 'user', 'payment', 'ticket_type', 'seat', 'promo_code')
        .get(pk=registration_id, **filters)
    )


def ensure_registration_payable(registration):
    """Raise ValueError unless `registration` is an unpaid ticket whose hold
    is still alive. Call it with a row-locked registration."""
    payment = getattr(registration, 'payment', None)
    if payment and payment.status == PaymentStatusChoices.COMPLETED:
        raise ValueError('Payment already completed')
    if registration.status != RegistrationStatusChoices.PENDING:
        raise ValueError('This registration is no longer awaiting payment. Please register again.')
    held_until = registration.seat_held_until
    if held_until is not None and held_until < timezone.now():
        raise ValueError('Your hold on this ticket has expired. Please register again.')


def _parse_money(value, field='amount') -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f'Invalid {field}.') from None
    if not amount.is_finite():
        raise ValueError(f'Invalid {field}.')
    return amount.quantize(Decimal('0.01'))


def _currency_of(registration) -> str:
    from events.billing import event_currency

    return event_currency(registration.event)


def _confirm_paid_registration(registration, payment):
    registration.status = RegistrationStatusChoices.CONFIRMED
    # Payment succeeded — the seat is now permanent, clear the hold timer.
    registration.seat_held_until = None
    registration.save(update_fields=['status', 'seat_held_until'])

    # Webhook job + in-app notification are rows in this same transaction.
    _fire_ticket_sold(registration, payment.amount)
    from events.notify import notify_ticket_purchased

    notify_ticket_purchased(registration.user, registration.event)


@transaction.atomic
def create_mock_checkout_session(*, registration):
    """Simulate a successful Stripe checkout for local development.

    Used only when STRIPE_MOCK_MODE is on (explicit opt-in, DEBUG only).
    Confirms the registration immediately and returns a fake session whose
    `url` points at the frontend success page, so the UX matches the real flow.
    """
    registration = _lock_registration(registration.pk)
    ensure_registration_payable(registration)

    mock_session_id = f'mock_sess_{registration.id}_{int(time.time())}'

    from events.billing import registration_amount

    amount = registration_amount(registration)

    payment, _ = Payment.objects.get_or_create(
        registration=registration,
        defaults={'amount': amount, 'currency': _currency_of(registration).lower()},
    )
    payment.stripe_checkout_session_id = mock_session_id
    payment.amount = amount
    payment.currency = _currency_of(registration).lower()
    payment.status = PaymentStatusChoices.COMPLETED
    payment.save(update_fields=['stripe_checkout_session_id', 'amount', 'currency', 'status'])

    _confirm_paid_registration(registration, payment)
    logger.info('[MOCK] Payment auto-confirmed for registration %s', registration.id)

    # Relative URL so the SPA stays on the current origin (http://localhost:4200
    # or https://localhost) — avoids a cross-origin redirect that would drop the
    # auth token stored in localStorage.
    success_url = f'/payment/success?session_id={mock_session_id}'
    return success_url, payment


def _fire_ticket_sold(registration, amount):
    """Notify webhooks that a paid ticket completed."""
    from events.webhooks import fire

    fire(
        registration.event,
        'ticket_sold',
        {
            'registration_id': registration.id,
            'user': registration.user.username,
            'amount': str(amount),
            'currency': _currency_of(registration),
            'ticket_type': registration.ticket_type.name if registration.ticket_type_id else None,
        },
    )


@transaction.atomic
def create_checkout_session(*, registration):
    from events.billing import registration_amount, to_minor_units

    registration = _lock_registration(registration.pk)
    ensure_registration_payable(registration)

    amount = registration_amount(registration)
    currency = _currency_of(registration)

    label = registration.event.title
    if registration.promo_code_id:
        label += f' (promo {registration.promo_code.code})'

    # Keep the seat for as long as the Stripe page stays payable, so a buyer
    # who pays on minute 15 doesn't find their seat already resold.
    expires_at = timezone.now() + timedelta(minutes=CHECKOUT_SESSION_MINUTES)
    if registration.seat_held_until is None or registration.seat_held_until < expires_at:
        registration.seat_held_until = expires_at + timedelta(minutes=1)
        registration.save(update_fields=['seat_held_until'])

    params = {
        'payment_method_types': ['card'],
        'line_items': [
            {
                'price_data': {
                    'currency': currency.lower(),
                    'product_data': {
                        'name': label,
                        'description': f'Registration for {registration.event.title}',
                    },
                    'unit_amount': to_minor_units(amount, currency),
                },
                'quantity': 1,
            }
        ],
        'mode': 'payment',
        'expires_at': int(expires_at.timestamp()),
        'success_url': f'{settings.FRONTEND_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}',
        'cancel_url': f'{settings.FRONTEND_URL}/payment/cancel',
        'client_reference_id': str(registration.id),
        'metadata': {'registration_id': str(registration.id)},
    }
    if registration.user.email:
        params['customer_email'] = registration.user.email
    checkout_session = stripe.checkout.Session.create(**params)

    payment = getattr(registration, 'payment', None)
    previous_session_id = payment.stripe_checkout_session_id if payment else ''
    if payment is None:
        payment = Payment.objects.create(
            registration=registration,
            amount=amount,
            currency=currency.lower(),
            stripe_checkout_session_id=checkout_session.id,
        )
    else:
        payment.stripe_checkout_session_id = checkout_session.id
        payment.amount = amount
        payment.currency = currency.lower()
        payment.save(update_fields=['stripe_checkout_session_id', 'amount', 'currency'])

    # Only one payable Stripe page per ticket: close the previous one.
    if previous_session_id and previous_session_id.startswith('cs_'):
        transaction.on_commit(lambda: _expire_session_quietly(previous_session_id))

    return checkout_session, payment


def _expire_session_quietly(session_id):
    try:
        stripe.checkout.Session.expire(session_id)
    except Exception as exc:  # already completed / expired — the webhook handles it
        logger.info('Could not expire Stripe session %s: %s', session_id, exc)


def _refund_payment_intent(payment_intent_id, *, key, amount_minor=None):
    """Return money to the buyer. Raises on failure so the caller's
    transaction rolls back and Stripe retries the webhook later."""
    if not payment_intent_id or getattr(settings, 'STRIPE_MOCK_MODE', False):
        return
    params = {'payment_intent': payment_intent_id, 'idempotency_key': key}
    if amount_minor is not None:
        params['amount'] = amount_minor
    stripe.Refund.create(**params)


@transaction.atomic
def confirm_stripe_checkout_session(session):
    """Apply a paid Checkout Session (webhook or success-page verification).

    Idempotent. If the ticket is no longer awaiting payment when the money
    arrives (hold expired and the seat was released, cancelled, already paid
    through another session) the payment is refunded automatically instead of
    confirming a ticket that no longer has a seat.
    """
    session_id = session['id']
    intent = session.get('payment_intent', '') or ''

    payment = Payment.objects.select_for_update().filter(stripe_checkout_session_id=session_id).first()
    if payment is None:
        # An older session of the same ticket (the id was overwritten when
        # the buyer reopened checkout) — find the ticket through metadata.
        reg_id = (session.get('metadata') or {}).get('registration_id')
        if reg_id:
            payment = Payment.objects.select_for_update().filter(registration_id=reg_id).first()
    if payment is None:
        logger.error('Paid Stripe session %s matches no ticket — refunding', session_id)
        _refund_payment_intent(intent, key=f'orphan-refund-{session_id}')
        return None

    registration = _lock_registration(payment.registration_id)

    if payment.status == PaymentStatusChoices.COMPLETED:
        if intent and payment.stripe_payment_intent_id and intent != payment.stripe_payment_intent_id:
            logger.warning(
                'Second paid session %s for registration %s — refunding the duplicate', session_id, registration.id
            )
            _refund_payment_intent(intent, key=f'duplicate-refund-{session_id}')
        return payment

    if registration.status != RegistrationStatusChoices.PENDING:
        logger.warning(
            'Payment for registration %s arrived in status %s — refunding automatically',
            registration.id,
            registration.status,
        )
        _refund_payment_intent(intent, key=f'late-refund-{session_id}')
        payment.status = PaymentStatusChoices.REFUNDED
        payment.stripe_payment_intent_id = intent
        payment.stripe_checkout_session_id = session_id
        payment.refunded_amount = payment.amount
        payment.refunded_at = timezone.now()
        payment.refund_reason = 'Automatic refund: the ticket hold had ended before the payment arrived.'
        payment.save(
            update_fields=[
                'status',
                'stripe_payment_intent_id',
                'stripe_checkout_session_id',
                'refunded_amount',
                'refunded_at',
                'refund_reason',
            ]
        )
        from events.notify import notify

        notify(
            registration.user,
            'payment_failed',
            f'💸 Payment refunded: {registration.event.title}',
            'Your payment arrived after the ticket hold expired, so it was refunded automatically. Please book again.',
            event=registration.event,
        )
        return payment

    payment.status = PaymentStatusChoices.COMPLETED
    payment.stripe_payment_intent_id = intent
    payment.stripe_checkout_session_id = session_id
    payment.save(update_fields=['status', 'stripe_payment_intent_id', 'stripe_checkout_session_id'])
    _confirm_paid_registration(registration, payment)
    logger.info('Payment completed for registration %s', registration.id)
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
    from events.billing import to_minor_units

    # Lock the row: two concurrent refunds (or approve + refund) can't both
    # see the same remaining balance.
    payment = Payment.objects.select_for_update().get(pk=payment.pk)

    if payment.status != PaymentStatusChoices.COMPLETED:
        raise ValueError('Only completed payments can be refunded.')

    remaining = payment.amount - payment.refunded_amount
    if remaining <= 0:
        raise ValueError('This payment has already been fully refunded.')

    refund_amount = remaining if amount in (None, '') else _parse_money(amount, 'refund amount')
    if refund_amount <= 0:
        raise ValueError('Refund amount must be greater than zero.')
    if refund_amount > remaining:
        raise ValueError(f'Cannot refund more than the remaining {remaining}.')

    registration = payment.registration
    currency = (payment.currency or _currency_of(registration)).upper()

    if not getattr(settings, 'STRIPE_MOCK_MODE', False) and payment.stripe_payment_intent_id:
        try:
            # The key is derived from the balance before this refund, so a
            # retry after a crash can't refund twice.
            _refund_payment_intent(
                payment.stripe_payment_intent_id,
                key=f'refund-{payment.pk}-{payment.refunded_amount}-{refund_amount}',
                amount_minor=to_minor_units(refund_amount, currency),
            )
        except stripe.error.StripeError as exc:
            logger.error('Stripe refund failed for payment %s: %s', payment.id, exc)
            raise ValueError(f'Stripe refund failed: {exc.user_message or exc}') from exc

    payment.refunded_amount = payment.refunded_amount + refund_amount
    payment.refund_reason = (reason or payment.refund_reason)[:255]
    payment.refunded_at = timezone.now()

    is_full = payment.refunded_amount >= payment.amount
    if is_full:
        payment.status = PaymentStatusChoices.REFUNDED
    payment.save(update_fields=['refunded_amount', 'refund_reason', 'refunded_at', 'status'])

    if is_full:
        # Release the seat and cancel the registration on a full refund.
        from events.services import cancel_registration

        cancel_registration(registration=registration)

    event, user = registration.event, registration.user
    if notify_user:
        from events.notify import notify

        notify(
            user,
            'payment_failed',
            f'💸 Refund issued: {event.title}',
            f'You were refunded {refund_amount} {currency}.' + (f' Reason: {reason}' if reason else ''),
            event=event,
        )
    from events.webhooks import fire

    fire(
        event,
        'refund_issued',
        {
            'registration_id': registration.id,
            'user': user.username,
            'refunded_amount': str(refund_amount),
            'currency': currency,
            'full_refund': is_full,
        },
    )

    logger.info('Refunded %s %s on payment %s (full=%s)', refund_amount, currency, payment.id, is_full)
    return payment


@transaction.atomic
def mark_offline_paid(*, registration, amount=None):
    """Organizer manually confirms a cash / bank-transfer payment."""
    registration = _lock_registration(registration.pk)
    payment = getattr(registration, 'payment', None)
    if payment and payment.status == PaymentStatusChoices.COMPLETED:
        raise ValueError('This ticket is already paid.')
    if registration.status != RegistrationStatusChoices.PENDING:
        raise ValueError('Only a ticket that is awaiting payment can be marked as paid.')

    if amount in (None, ''):
        # The real amount owed — tier / seat zone / promo / tax & fees —
        # not the bare event price.
        from events.billing import registration_amount

        amt = registration_amount(registration)
    else:
        amt = _parse_money(amount)
        if amt < 0:
            raise ValueError('Amount cannot be negative.')

    currency = _currency_of(registration).lower()
    if payment is None:
        payment = Payment(registration=registration)
    payment.amount = amt
    payment.currency = currency
    payment.method = Payment.METHOD_OFFLINE
    payment.status = PaymentStatusChoices.COMPLETED
    payment.save()

    _confirm_paid_registration(registration, payment)
    return payment


def verify_payment(session_id: str, user):
    """Return the user's payment for a session, confirming it if Stripe says
    it's paid.

    The Stripe webhook is the source of truth in production, but in local
    development webhooks are often not forwarded. Actively retrieving the
    session here lets the success page confirm the registration on its own.
    """
    payment = Payment.objects.select_related('registration__event').get(
        stripe_checkout_session_id=session_id,
        registration__user=user,
    )

    if payment.status not in (PaymentStatusChoices.COMPLETED, PaymentStatusChoices.REFUNDED) and not getattr(
        settings, 'STRIPE_MOCK_MODE', False
    ):
        try:
            session = stripe_to_dict(stripe.checkout.Session.retrieve(session_id))
            if session.get('payment_status') == 'paid':
                confirm_stripe_checkout_session(session)
                payment.refresh_from_db()
        except stripe.error.StripeError as exc:
            logger.warning('Could not retrieve Stripe session %s: %s', session_id, exc)

    return payment
