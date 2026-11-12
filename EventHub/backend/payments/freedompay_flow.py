"""Freedom Pay for single tickets: checkout, notifications, status polling
and refunds (ADR 0001, section 4).

Rules kept here:

- Lock order is Payment, then its Registration.
- No provider network call happens inside a transaction that holds a row
  lock: checkout is lock/validate -> call the gateway -> store the session;
  a `paid` notification is confirmed with `get_status3.php` before the
  locked transaction; refunds are a `Refund` row plus an outbox job whose
  gateway call runs outside any transaction.
- A notification is applied once: `PaymentEvent` (provider, event_id) is
  inserted in the transaction that applies it, and a re-delivery gets the
  stored outcome back (so the reply is identical, S4).
- Confirmation goes through `services._confirm_paid_registration`, exactly
  like the Stripe path (ticket, seat, webhook, notification).

Group bookings stay on their existing (Stripe) path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from common.choices import EventStatusChoices, PaymentStatusChoices, RegistrationStatusChoices

from .models import Payment, PaymentEvent, Refund
from .providers import registry
from .providers.base import (
    CallbackKind,
    CallbackResult,
    CheckoutResult,
    PaymentOrder,
    PaymentProviderError,
    ProviderRejected,
    ProviderUnavailable,
    StatusResult,
)
from .providers.freedompay import lifetime_seconds, payment_id_ref
from .services import _confirm_paid_registration, _lock_registration, ensure_registration_payable
from .state import transition

logger = logging.getLogger(__name__)

PROVIDER = 'freedompay'
REFUND_JOB = 'process_payment_refund'
# A pending payment is re-checked with the gateway once it is this old, and
# at most once per STATUS_REFRESH_EVERY_SECONDS (polling clients).
STATUS_REFRESH_AFTER = timedelta(seconds=15)
STATUS_REFRESH_EVERY_SECONDS = 5
MAX_KNOWN_PAYMENT_IDS = 20
Outcome = PaymentEvent.Outcome


class PaymentNotConfirmed(Exception):
    """The gateway does not (yet) confirm what a notification claims: the
    notification is answered with `error` and the gateway retries it."""


@dataclass(frozen=True)
class Checkout:
    payment: Payment
    result: CheckoutResult

    @property
    def qr_data_url(self) -> str | None:
        qr = self.result.raw.get('redirect_qr')
        return f'data:image/png;base64,{qr}' if qr else None


def provider():
    return registry.get(PROVIDER, require_enabled=False)


def provider_for(registration) -> str:
    """`freedompay` for a KZT event when Freedom Pay is enabled and
    configured; otherwise `stripe` (the legacy path, real or mock)."""
    from events.billing import event_currency

    if event_currency(registration.event) == 'KZT' and any(p.code == PROVIDER for p in registry.for_currency('KZT')):
        return PROVIDER
    return 'stripe'


def known_payment_ids(payment: Payment) -> set[str]:
    """Every gateway payment id one of this payment's attempts created."""
    ids = {payment.provider_session_id, payment.provider_payment_id}
    ids.update(str(value) for value in (payment.provider_payload or {}).get('pg_payment_ids', []))
    ids.discard('')
    return ids


# ───────────────────────── checkout ─────────────────────────


def _lock_payment_and_registration(registration_id):
    """Payment first, then the registration (ADR lock order). A payment that
    does not exist yet is created under the registration lock."""
    payment = Payment.objects.select_for_update().filter(registration_id=registration_id).first()
    registration = _lock_registration(registration_id)
    if payment is None:
        payment = Payment.objects.select_for_update().filter(registration_id=registration_id).first()
    return payment, registration


def start_checkout(registration) -> Checkout:
    """Open a Freedom Pay payment page for an unpaid ticket.

    Raises ValueError (not payable) or a PaymentProviderError (gateway).
    """
    from events.billing import event_currency, registration_amount
    from events.services.holds import SEAT_HOLD_MINUTES

    gateway = provider()
    # (1) Short transaction: validate, create or reuse the pending payment,
    # make the seat hold cover the payment page's lifetime.
    with transaction.atomic():
        payment, registration = _lock_payment_and_registration(registration.pk)
        ensure_registration_payable(registration)
        amount = registration_amount(registration)
        currency = event_currency(registration.event)
        if payment is None:
            payment = Payment.objects.create(
                registration=registration, amount=amount, currency=currency.lower(), provider=PROVIDER
            )
        elif payment.status in (PaymentStatusChoices.FAILED, PaymentStatusChoices.EXPIRED):
            transition(payment, PaymentStatusChoices.PENDING, reason='new Freedom Pay attempt')
        elif payment.status != PaymentStatusChoices.PENDING:
            raise ValueError('This ticket can no longer be paid.')

        now = timezone.now()
        hold = registration.seat_held_until or now + timedelta(minutes=SEAT_HOLD_MINUTES)
        page_expires = now + timedelta(seconds=lifetime_seconds(hold, now))
        if registration.seat_held_until is None or registration.seat_held_until < page_expires + timedelta(minutes=1):
            registration.seat_held_until = page_expires + timedelta(minutes=1)
            registration.save(update_fields=['seat_held_until'])

        payment.provider = PROVIDER
        payment.amount = amount
        payment.currency = currency.lower()
        payment.method = Payment.METHOD_CARD
        payment.attempt += 1
        payment.save(update_fields=['provider', 'amount', 'currency', 'method', 'attempt', 'updated_at'])

        label = registration.event.title
        if registration.promo_code_id:
            label += f' (promo {registration.promo_code.code})'
        query = f'provider={PROVIDER}&payment={payment.pk}'
        order = PaymentOrder(
            reference=str(payment.pk),
            amount=amount,
            currency=currency,
            description=f'Ticket: {label}',
            success_url=f'{settings.FRONTEND_URL}/payment/success?{query}',
            cancel_url=f'{settings.FRONTEND_URL}/payment/cancel?{query}',
            expires_at=page_expires,
            # Unique per merchant for good: the payment's creation time keeps
            # the key unique even if a database is reset and ids repeat.
            idempotency_key=f'payment-{payment.pk}-{int(payment.created_at.timestamp())}-attempt-{payment.attempt}',
            customer_email=registration.user.email or '',
        )

    # (2) The gateway call, outside any transaction. On failure the payment
    # stays pending without a new session and the buyer can retry.
    result = gateway.create_payment(order)

    # (3) Short transaction: remember the session.
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == PaymentStatusChoices.COMPLETED:
            raise ValueError('Payment already completed')
        payload = dict(payment.provider_payload or {})
        ids = [str(i) for i in payload.get('pg_payment_ids', []) if str(i) != result.session_id]
        payload['pg_payment_ids'] = [*ids[-(MAX_KNOWN_PAYMENT_IDS - 1) :], result.session_id]
        payment.provider = PROVIDER
        payment.provider_session_id = result.session_id
        payment.provider_payload = payload
        payment.save(update_fields=['provider', 'provider_session_id', 'provider_payload', 'updated_at'])
    logger.info('Freedom Pay payment %s opened for payment %s', result.session_id, payment.pk)
    return Checkout(payment=payment, result=result)


# ───────────────────────── notifications ─────────────────────────


def _find_payment(result: CallbackResult) -> Payment | None:
    payment = None
    if result.reference.isdigit():
        payment = Payment.objects.filter(
            pk=int(result.reference), provider=PROVIDER, registration__isnull=False
        ).first()
    if payment is None and result.provider_payment_id:
        payment = Payment.objects.filter(provider=PROVIDER, provider_session_id=result.provider_payment_id).first()
    if payment is not None and result.provider_payment_id not in known_payment_ids(payment):
        # Same order number, but not a gateway payment we created for it
        # (e.g. a stale callback from another database): treat as unknown.
        logger.error('Freedom Pay payment %s is not an attempt of payment %s', result.provider_payment_id, payment.pk)
        return None
    return payment


def _confirm_with_gateway(gateway, result: CallbackResult) -> str | None:
    """Ask `get_status3.php` about a `paid` notification (MD5 signatures are
    weak). None when confirmed, else the gateway's contradicting state.
    Raises PaymentNotConfirmed while the gateway cannot answer or still
    reports the payment as pending."""
    try:
        status = gateway.get_status(payment_id_ref(result.provider_payment_id))
    except PaymentProviderError as exc:
        raise PaymentNotConfirmed(f'status check failed: {exc}') from exc
    if status.state == StatusResult.PENDING:
        raise PaymentNotConfirmed('the gateway still reports the payment as pending')
    if status.state != CallbackKind.PAID:
        return str(status.state)
    if status.amount != result.amount or status.currency != result.currency:
        return f'status reports {status.amount} {status.currency}'
    return None


def _new_refund(payment, *, kind, amount: Decimal, currency: str, provider_payment_id: str, reason: str) -> Refund:
    return Refund.objects.create(
        payment=payment,
        amount=amount,
        currency=currency.upper(),
        kind=kind,
        reason=reason[:255],
        provider=PROVIDER,
        provider_payment_id=provider_payment_id,
    )


def _apply_paid(result: CallbackResult, payment: Payment | None, registration) -> tuple[str, list[Refund]]:
    pg_id = result.provider_payment_id
    if result.amount is None or result.amount <= 0 or not result.currency:
        logger.error('Freedom Pay payment %s reported without a usable amount: not applied', pg_id)
        return Outcome.REJECTED, []
    if payment is None:
        logger.error('Freedom Pay payment %s matches no order (%r): refunding', pg_id, result.reference)
        refund = _new_refund(
            None,
            kind=Refund.Kind.ORPHAN,
            amount=result.amount,
            currency=result.currency,
            provider_payment_id=pg_id,
            reason='Automatic refund: the payment matches no order.',
        )
        return Outcome.ORPHAN, [refund]

    if payment.status in (PaymentStatusChoices.COMPLETED, PaymentStatusChoices.REFUNDED, PaymentStatusChoices.DISPUTED):
        if payment.provider_payment_id == pg_id:
            return Outcome.IGNORED, []
        logger.warning('Second Freedom Pay payment %s for payment %s: refunding the duplicate', pg_id, payment.pk)
        refund = _new_refund(
            payment,
            kind=Refund.Kind.DUPLICATE,
            amount=result.amount,
            currency=result.currency,
            provider_payment_id=pg_id,
            reason='Automatic refund: the ticket was already paid.',
        )
        return Outcome.DUPLICATE_PAYMENT, [refund]

    if result.amount != payment.amount or result.currency.upper() != payment.currency.upper():
        logger.critical(
            'Freedom Pay payment %s reports %s %s, payment %s expects %s %s: not confirming, refunding',
            pg_id,
            result.amount,
            result.currency,
            payment.pk,
            payment.amount,
            payment.currency.upper(),
        )
        if payment.status == PaymentStatusChoices.PENDING:
            transition(payment, PaymentStatusChoices.FAILED, reason='amount or currency mismatch')
        refund = _new_refund(
            payment,
            kind=Refund.Kind.AMOUNT_MISMATCH,
            amount=result.amount,
            currency=result.currency,
            provider_payment_id=pg_id,
            reason='Automatic refund: the paid amount differs from the order.',
        )
        return Outcome.AMOUNT_MISMATCH, [refund]

    # The money for this order really arrived.
    transition(payment, PaymentStatusChoices.COMPLETED, reason=f'Freedom Pay payment {pg_id}')
    payment.provider_payment_id = pg_id
    payment.save(update_fields=['provider_payment_id', 'updated_at'])

    if (
        registration.status != RegistrationStatusChoices.PENDING
        or registration.event.status != EventStatusChoices.PUBLISHED
    ):
        logger.warning(
            'Freedom Pay payment for registration %s arrived in status %s (event %s): refunding automatically',
            registration.pk,
            registration.status,
            registration.event.status,
        )
        refund = _new_refund(
            payment,
            kind=Refund.Kind.LATE_PAYMENT,
            amount=payment.amount,
            currency=payment.currency,
            provider_payment_id=pg_id,
            reason='Automatic refund: the ticket hold had ended before the payment arrived.',
        )
        from events.notify import notify

        notify(
            registration.user,
            'payment_failed',
            f'💸 Payment refunded: {registration.event.title}',
            'Your payment arrived after the ticket hold expired, so it is being refunded automatically. '
            'Please book again.',
            event=registration.event,
        )
        return Outcome.LATE_PAYMENT, [refund]

    _confirm_paid_registration(registration, payment)
    logger.info('Freedom Pay payment %s completed registration %s', pg_id, registration.pk)
    return Outcome.PROCESSED, []


def _apply(result: CallbackResult, payment_pk) -> tuple[Payment | None, str, list[Refund]]:
    payment = registration = None
    if payment_pk is not None:
        payment = Payment.objects.select_for_update().get(pk=payment_pk)
        registration = _lock_registration(payment.registration_id)
    if result.kind == CallbackKind.PAID:
        return (payment, *_apply_paid(result, payment, registration))
    # Only the current attempt can fail the payment; the hold expires on its own.
    if (
        result.kind in (CallbackKind.FAILED, CallbackKind.EXPIRED)
        and payment is not None
        and payment.status == PaymentStatusChoices.PENDING
        and payment.provider_session_id == result.provider_payment_id
    ):
        target = PaymentStatusChoices.FAILED if result.kind == CallbackKind.FAILED else PaymentStatusChoices.EXPIRED
        transition(payment, target, reason=f'Freedom Pay payment {result.provider_payment_id} {result.kind}')
        return payment, Outcome.PROCESSED, []
    return payment, Outcome.IGNORED, []


def _payload(result: CallbackResult) -> dict:
    return {key: value for key, value in result.raw.items() if key not in ('reply_salt', 'script')}


def handle_notification(gateway, result: CallbackResult, *, confirm: bool = True) -> str:
    """Apply a Result notification (or a status poll as one). Returns the
    PaymentEvent outcome; a re-delivery returns the stored outcome.

    Raises PaymentNotConfirmed when a `paid` notification cannot be
    confirmed with the gateway yet (nothing is recorded: the retry is
    processed normally).
    """
    stored = PaymentEvent.objects.filter(provider=PROVIDER, event_id=result.event_id).values_list('outcome', flat=True)
    if stored:
        return stored[0] or Outcome.IGNORED

    payment = _find_payment(result)
    contradiction = None
    if result.kind == CallbackKind.PAID and confirm:
        contradiction = _confirm_with_gateway(gateway, result)

    with transaction.atomic():
        try:
            with transaction.atomic():
                event = PaymentEvent.objects.create(
                    provider=PROVIDER, event_id=result.event_id, kind=result.kind, payload=_payload(result)
                )
        except IntegrityError:
            # Delivered twice at the same moment: the other one applied it.
            outcome = (
                PaymentEvent.objects.filter(provider=PROVIDER, event_id=result.event_id)
                .values_list('outcome', flat=True)
                .first()
            )
            return outcome or Outcome.IGNORED

        if contradiction is not None:
            logger.critical(
                'Freedom Pay notification says payment %s is paid but get_status3 says %s: ignored',
                result.provider_payment_id,
                contradiction,
            )
            locked, outcome, refunds = payment, Outcome.REJECTED, []
        else:
            locked, outcome, refunds = _apply(result, payment.pk if payment else None)
        event.payment = locked
        event.outcome = outcome
        event.processed_at = timezone.now()
        event.save(update_fields=['payment', 'outcome', 'processed_at'])
        for refund in refunds:
            _enqueue_refund(refund)
    return outcome


# ───────────────────────── status polling ─────────────────────────


def refresh_status(payment: Payment) -> Payment:
    """Settle a Freedom Pay payment that is still pending by asking the
    gateway, at most once per few seconds and only once it is older than
    STATUS_REFRESH_AFTER (the Result notification normally comes first)."""
    if (
        payment.provider != PROVIDER
        or payment.status != PaymentStatusChoices.PENDING
        or not payment.provider_session_id
        or timezone.now() - payment.updated_at < STATUS_REFRESH_AFTER
    ):
        return payment
    if not cache.add(f'freedompay:status:{payment.pk}', 1, timeout=STATUS_REFRESH_EVERY_SECONDS):
        return payment
    gateway = provider()
    try:
        status = gateway.get_status(payment)
        if status.state != StatusResult.PENDING:
            handle_notification(gateway, status.as_callback(reference=str(payment.pk)), confirm=False)
    except (PaymentProviderError, PaymentNotConfirmed) as exc:
        logger.warning('Freedom Pay status check of payment %s failed: %s', payment.pk, exc)
        return payment
    payment.refresh_from_db()
    return payment


# ───────────────────────── refunds ─────────────────────────


def _enqueue_refund(refund: Refund) -> None:
    """Outbox: the job row commits with the refund row. Also tried right
    after the commit (outside the transaction) so the buyer does not wait
    for the worker; the job's lease makes the two never run together."""
    from jobs.queue import enqueue, run_job

    job = enqueue(REFUND_JOB, {'refund_id': str(refund.pk)}, max_attempts=8)
    if not getattr(settings, 'JOBS_RUN_INLINE', False):
        transaction.on_commit(lambda: run_job(job.pk))


def process_refund_job(refund_id: str) -> None:
    """Job handler: perform a pending refund with the gateway, then record
    the answer. Safe to run again: the gateway dedupes on the refund's
    idempotency key and a finished refund is left alone."""
    from jobs.queue import PermanentJobError

    refund = Refund.objects.filter(pk=refund_id).first()
    if refund is None or refund.status != Refund.Status.PENDING:
        return
    gateway = registry.get(refund.provider, require_enabled=False)
    target = payment_id_ref(
        refund.provider_payment_id, pk=refund.payment_id or '', amount=refund.amount, currency=refund.currency
    )
    try:
        answer = gateway.refund(target, refund.amount, idempotency_key=refund.idempotency_key, reason=refund.reason)
    except ProviderUnavailable as exc:
        Refund.objects.filter(pk=refund.pk, status=Refund.Status.PENDING).update(
            attempts=F('attempts') + 1, error=str(exc)[:2000]
        )
        raise
    except ProviderRejected as exc:
        _finish_refund(refund.pk, Refund.Status.FAILED, error=str(exc))
        raise PermanentJobError(str(exc)) from exc
    _finish_refund(refund.pk, answer.status, provider_refund_id=answer.provider_refund_id)
    if answer.status == Refund.Status.PENDING:
        raise ProviderUnavailable('refund still pending at the gateway', provider=refund.provider)


def _finish_refund(refund_id, status: str, *, provider_refund_id: str = '', error: str = '') -> None:
    if status == Refund.Status.PENDING:
        return
    with transaction.atomic():
        payment_id = Refund.objects.filter(pk=refund_id).values_list('payment_id', flat=True).first()
        payment = Payment.objects.select_for_update().get(pk=payment_id) if payment_id else None
        refund = Refund.objects.select_for_update().get(pk=refund_id)
        if refund.status != Refund.Status.PENDING:
            return
        now = timezone.now()
        refund.status = status
        refund.provider_refund_id = provider_refund_id or refund.provider_refund_id
        refund.error = error[:2000]
        refund.attempts += 1
        refund.processed_at = now
        refund.save(update_fields=['status', 'provider_refund_id', 'error', 'attempts', 'processed_at'])
        if status == Refund.Status.FAILED:
            logger.error(
                'Refund %s (%s) of %s %s failed: %s', refund.pk, refund.kind, refund.amount, refund.currency, error
            )
            return
        # Only a late payment's refund returns this payment's own money;
        # duplicates, mismatches and orphans are other gateway payments.
        if (
            payment is not None
            and refund.kind == Refund.Kind.LATE_PAYMENT
            and refund.provider_payment_id == payment.provider_payment_id
        ):
            payment.refunded_amount = min(payment.amount, payment.refunded_amount + refund.amount)
            payment.refunded_at = now
            payment.refund_reason = refund.reason[:255]
            payment.save(update_fields=['refunded_amount', 'refunded_at', 'refund_reason', 'updated_at'])
            if payment.refunded_amount >= payment.amount and payment.status == PaymentStatusChoices.COMPLETED:
                transition(payment, PaymentStatusChoices.REFUNDED, reason=f'refund {refund.pk}')
        logger.info('Refund %s (%s) of %s %s succeeded', refund.pk, refund.kind, refund.amount, refund.currency)


def refund_now(payment: Payment, amount: Decimal, reason: str, *, kind=Refund.Kind.ORGANIZER) -> Refund:
    """Synchronous refund for `services.refund_payment` (organizer refunds,
    approved refund requests, event cancellation). Runs inside the caller's
    transaction like the legacy Stripe refund does; WP1b moves it to the
    ledger job. Raises ValueError when the gateway does not refund."""
    # Derived from the gateway payment id (never reused) and the balance
    # before this refund: a retry after a lost answer reuses the key and
    # cannot refund twice.
    key = f'refund-{payment.provider_payment_id}-{payment.refunded_amount}-{amount}'
    refund = Refund.objects.create(
        payment=payment,
        amount=amount,
        currency=payment.currency.upper(),
        kind=kind,
        reason=(reason or '')[:255],
        provider=PROVIDER,
        provider_payment_id=payment.provider_payment_id,
        idempotency_key=key,
    )
    try:
        answer = provider().refund(payment, amount, idempotency_key=key, reason=reason or '')
    except PaymentProviderError as exc:
        logger.error('Freedom Pay refund failed for payment %s: %s', payment.pk, exc)
        raise ValueError(f'Freedom Pay refund failed: {exc}') from exc
    if answer.status != Refund.Status.SUCCEEDED:
        raise ValueError('Freedom Pay declined the refund.')
    refund.status = Refund.Status.SUCCEEDED
    refund.provider_refund_id = answer.provider_refund_id
    refund.attempts = 1
    refund.processed_at = timezone.now()
    refund.save(update_fields=['status', 'provider_refund_id', 'attempts', 'processed_at'])
    return refund
