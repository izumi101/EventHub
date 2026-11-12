"""Stripe provider (ADR 0001): Checkout Sessions, webhooks, refunds.

Talks to Stripe through its own `stripe.StripeClient`, which carries the API
key, the pinned API version, the retry budget and the HTTP timeouts. Nothing
global is configured: the legacy services, which still use the module-level
`stripe` API until WP1b switches them, keep exactly their old behaviour.
Only the app info (part of the User-Agent) is global in the SDK and is set
the first time a client is built.

Stripe amounts are integers in the currency's minor unit; the tables and
the conversion live here (moved from events/billing.py, which re-exports
them for its existing callers).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache

import stripe
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

from . import conf
from .base import (
    CallbackKind,
    CallbackResult,
    CheckoutResult,
    InvalidCallback,
    PaymentOrder,
    PaymentProvider,
    ProviderRejected,
    ProviderUnavailable,
    RefundResult,
    StatusResult,
)
from .registry import register

logger = logging.getLogger(__name__)

# The API version this module is written against. It equals the version the
# pinned SDK (requirements.lock) was generated for; test_provider_stripe.py
# fails when an SDK upgrade changes it, so the bump is a reviewed change.
API_VERSION = '2026-09-30.endive'
MAX_NETWORK_RETRIES = 2
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 30
# Stripe refuses Checkout Sessions that expire sooner than 30 minutes or later
# than 24 hours after creation.
CHECKOUT_SESSION_MINUTES = 31
MAX_CHECKOUT_SESSION = timedelta(hours=23, minutes=55)
WEBHOOK_TOLERANCE_SECONDS = 300
MAX_WEBHOOK_BYTES = 512 * 1024

# Stripe amounts are integers in the currency's minor unit; these currencies
# have no minor unit (or a 3-digit one) and must not be multiplied by 100.
# https://docs.stripe.com/currencies#zero-decimal
ZERO_DECIMAL_CURRENCIES = {
    'BIF',
    'CLP',
    'DJF',
    'GNF',
    'JPY',
    'KMF',
    'KRW',
    'MGA',
    'PYG',
    'RWF',
    'UGX',
    'VND',
    'VUV',
    'XAF',
    'XOF',
    'XPF',
}
THREE_DECIMAL_CURRENCIES = {'BHD', 'JOD', 'KWD', 'OMR', 'TND'}

CHECKOUT_LOCALES = frozenset({'auto', 'en', 'ru', 'de', 'fr', 'es', 'it', 'pl', 'tr', 'zh', 'ja', 'ko'})

_SESSION_EVENTS = {
    'checkout.session.completed': CallbackKind.PAID,
    'checkout.session.async_payment_succeeded': CallbackKind.PAID,
    'checkout.session.async_payment_failed': CallbackKind.FAILED,
    'checkout.session.expired': CallbackKind.EXPIRED,
}
_DISPUTE_WON = frozenset({'won', 'warning_closed', 'prevented'})


def to_minor_units(amount, currency: str) -> int:
    """Convert a decimal amount to the integer Stripe expects for `currency`."""
    currency = (currency or 'USD').upper()
    amount = Decimal(str(amount))
    if currency in ZERO_DECIMAL_CURRENCIES:
        return int(amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    cents = int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    if currency in THREE_DECIMAL_CURRENCIES:
        # Stripe requires the last digit of 3-decimal amounts to be zero.
        return cents * 10
    return cents


def from_minor_units(amount_minor, currency: str) -> Decimal | None:
    """Stripe's integer amount as a ledger Decimal (two places at most).

    None when the value cannot be represented exactly (a 3-decimal amount
    whose last digit is not zero): money is never rounded silently.
    """
    if amount_minor is None or isinstance(amount_minor, bool):
        return None
    try:
        minor = int(amount_minor)
    except (TypeError, ValueError):
        return None
    currency = (currency or '').upper()
    if currency in ZERO_DECIMAL_CURRENCIES:
        return Decimal(minor)
    divisor = Decimal(1000) if currency in THREE_DECIMAL_CURRENCIES else Decimal(100)
    value = Decimal(minor) / divisor
    exact = value.quantize(Decimal('0.01'))
    return exact if exact == value else None


@lru_cache(maxsize=8)
def _client(api_key: str, api_base: str, max_network_retries: int) -> stripe.StripeClient:
    # Retries reuse the request's idempotency key, so they are safe for POSTs.
    stripe.set_app_info('EventHub')
    return stripe.StripeClient(
        api_key,
        stripe_version=API_VERSION,
        max_network_retries=max_network_retries,
        http_client=stripe.RequestsClient(timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)),
        base_addresses={'api': api_base} if api_base else None,
    )


def _error(exc: stripe.StripeError, action: str) -> Exception:
    """Map an SDK error to ProviderUnavailable (retry later) or
    ProviderRejected (retrying the same request cannot help)."""
    message = f'Stripe {action} failed: {exc.user_message or exc}'
    code = exc.code or ''
    status = exc.http_status or 0
    if isinstance(exc, (stripe.APIConnectionError, stripe.RateLimitError, stripe.APIError)) or status >= 500:
        return ProviderUnavailable(message, provider='stripe', code=code)
    return ProviderRejected(message, provider='stripe', code=code)


def _expandable_id(value) -> str:
    if isinstance(value, dict):
        return str(value.get('id') or '')
    return str(value or '')


def _with_session_placeholder(url: str) -> str:
    # The literal `{CHECKOUT_SESSION_ID}` is replaced by Stripe on redirect.
    return f'{url}{"&" if "?" in url else "?"}session_id={{CHECKOUT_SESSION_ID}}'


@register
class StripeProvider(PaymentProvider):
    code = 'stripe'
    supported_currencies = None

    # ── configuration ──

    def is_configured(self) -> bool:
        return not conf.missing_settings(self.code, lambda name: getattr(settings, name, ''))

    def _api(self) -> stripe.StripeClient:
        key = getattr(settings, 'STRIPE_SECRET_KEY', '')
        if conf.is_placeholder(key):
            raise ProviderRejected('STRIPE_SECRET_KEY is not set', provider=self.code, code='not_configured')
        return _client(
            key,
            getattr(settings, 'STRIPE_API_BASE', '') or '',
            int(getattr(settings, 'STRIPE_MAX_NETWORK_RETRIES', MAX_NETWORK_RETRIES)),
        )

    # ── checkout ──

    def _session_expiry(self, wanted: datetime) -> datetime:
        now = timezone.now()
        earliest = now + timedelta(minutes=CHECKOUT_SESSION_MINUTES)
        latest = now + MAX_CHECKOUT_SESSION
        return min(max(wanted, earliest), latest)

    def _line_items(self, order: PaymentOrder) -> list[dict]:
        currency = order.currency.lower()
        if not order.lines:
            return [
                {
                    'price_data': {
                        'currency': currency,
                        'product_data': {'name': order.description},
                        'unit_amount': to_minor_units(order.amount, order.currency),
                    },
                    'quantity': 1,
                }
            ]
        items = []
        for line in order.lines:
            product = {'name': line.name}
            if line.description:
                product['description'] = line.description
            items.append(
                {
                    'price_data': {
                        'currency': currency,
                        'product_data': product,
                        'unit_amount': to_minor_units(line.unit_amount, order.currency),
                    },
                    'quantity': line.quantity,
                }
            )
        return items

    def create_payment(self, order: PaymentOrder) -> CheckoutResult:
        expires_at = self._session_expiry(order.expires_at)
        metadata = {**order.metadata, 'payment_id': order.reference}
        params = {
            'mode': 'payment',
            'payment_method_types': ['card'],
            'line_items': self._line_items(order),
            'expires_at': int(expires_at.timestamp()),
            'success_url': _with_session_placeholder(order.success_url),
            'cancel_url': order.cancel_url,
            'client_reference_id': order.reference,
            'metadata': metadata,
            # Charges, refunds and disputes are reported on the payment
            # intent: give it the reference as well.
            'payment_intent_data': {'metadata': metadata},
        }
        if order.customer_email:
            params['customer_email'] = order.customer_email
        if order.locale in CHECKOUT_LOCALES:
            params['locale'] = order.locale
        try:
            session = (
                self._api()
                .v1.checkout.sessions.create(params=params, options={'idempotency_key': order.idempotency_key})
                .to_dict()
            )
        except stripe.StripeError as exc:
            logger.warning('Stripe Checkout Session for payment %s failed: %s', order.reference, exc)
            raise _error(exc, 'checkout') from exc
        stripe_expiry = session.get('expires_at')
        return CheckoutResult(
            provider=self.code,
            session_id=str(session.get('id') or ''),
            redirect_url=str(session.get('url') or ''),
            expires_at=datetime.fromtimestamp(stripe_expiry, UTC) if stripe_expiry else expires_at,
            payment_id=_expandable_id(session.get('payment_intent')),
            raw={'id': session.get('id'), 'status': session.get('status'), 'livemode': session.get('livemode')},
        )

    # ── callbacks ──

    def handle_callback(self, request) -> CallbackResult:
        payload = request.body
        if len(payload) > MAX_WEBHOOK_BYTES:
            raise InvalidCallback('webhook payload too large', provider=self.code)
        secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')
        if conf.is_placeholder(secret):
            raise InvalidCallback('STRIPE_WEBHOOK_SECRET is not set', provider=self.code, code='not_configured')
        signature = request.META.get('HTTP_STRIPE_SIGNATURE')
        try:
            stripe.Webhook.construct_event(payload, signature, secret, tolerance=WEBHOOK_TOLERANCE_SECONDS)
            event = json.loads(payload)
        except stripe.SignatureVerificationError as exc:
            raise InvalidCallback(f'bad Stripe signature: {exc}', provider=self.code, code='signature') from exc
        except ValueError as exc:  # also JSONDecodeError / UnicodeDecodeError
            raise InvalidCallback('Stripe webhook is not JSON', provider=self.code, code='malformed') from exc
        if not isinstance(event, dict) or not event.get('id') or not isinstance(event.get('data'), dict):
            raise InvalidCallback('Stripe webhook is not an event', provider=self.code, code='malformed')
        obj = event['data'].get('object')
        if not isinstance(obj, dict):
            raise InvalidCallback('Stripe event has no object', provider=self.code, code='malformed')
        try:
            return self._normalise(event, obj)
        except (TypeError, ValueError) as exc:
            raise InvalidCallback(f'malformed Stripe event: {exc}', provider=self.code, code='malformed') from exc

    def _normalise(self, event: dict, obj: dict) -> CallbackResult:
        event_type = str(event.get('type') or '')
        raw = {
            'type': event_type,
            'object': obj.get('object'),
            'object_id': obj.get('id'),
            'livemode': event.get('livemode'),
        }
        common = {'provider': self.code, 'event_id': str(event['id']), 'raw': raw}
        metadata = obj.get('metadata') if isinstance(obj.get('metadata'), dict) else {}
        currency = str(obj.get('currency') or '').upper()

        if event_type in _SESSION_EVENTS:
            kind = _SESSION_EVENTS[event_type]
            raw['payment_status'] = obj.get('payment_status')
            if event_type == 'checkout.session.completed' and obj.get('payment_status') == 'unpaid':
                # A delayed payment method: async_payment_succeeded / _failed follows.
                kind = CallbackKind.IGNORED
            return CallbackResult(
                kind=kind,
                reference=str(obj.get('client_reference_id') or metadata.get('payment_id') or ''),
                provider_session_id=str(obj.get('id') or ''),
                provider_payment_id=_expandable_id(obj.get('payment_intent')),
                amount=from_minor_units(obj.get('amount_total'), currency),
                currency=currency,
                **common,
            )

        if event_type == 'charge.refunded':
            raw.update(refunded=obj.get('refunded'), amount=obj.get('amount'))
            return CallbackResult(
                kind=CallbackKind.REFUNDED,
                reference=str(metadata.get('payment_id') or ''),
                provider_payment_id=_expandable_id(obj.get('payment_intent')),
                # The total refunded so far on this charge.
                amount=from_minor_units(obj.get('amount_refunded'), currency),
                currency=currency,
                **common,
            )

        if event_type in ('charge.dispute.created', 'charge.dispute.closed'):
            status = str(obj.get('status') or '')
            raw.update(status=status, reason=obj.get('reason'), charge=_expandable_id(obj.get('charge')))
            if event_type == 'charge.dispute.created':
                kind = CallbackKind.DISPUTE_OPENED
            elif status in _DISPUTE_WON:
                kind = CallbackKind.DISPUTE_WON
            elif status == 'lost':
                kind = CallbackKind.DISPUTE_LOST
            else:
                kind = CallbackKind.IGNORED
            return CallbackResult(
                kind=kind,
                reference=str(metadata.get('payment_id') or ''),
                provider_payment_id=_expandable_id(obj.get('payment_intent')),
                amount=from_minor_units(obj.get('amount'), currency),
                currency=currency,
                **common,
            )

        return CallbackResult(kind=CallbackKind.IGNORED, **common)

    def callback_response(self, result: CallbackResult, outcome: str) -> JsonResponse:
        # Stripe only looks at the status code; any 2xx stops the retries.
        return JsonResponse({'received': True})

    # ── refunds ──

    def refund(self, payment, amount: Decimal | None, *, idempotency_key: str, reason: str) -> RefundResult:
        """Refund `amount` (None: everything that is left) of the payment
        intent. Stripe dedupes on `idempotency_key` for 24 hours."""
        if not payment.provider_payment_id:
            raise ProviderRejected('the payment has no Stripe payment intent', provider=self.code, code='no_intent')
        currency = payment.currency.upper()
        params = {
            'payment_intent': payment.provider_payment_id,
            'metadata': {'payment_id': str(payment.pk), 'reason': (reason or '')[:500]},
        }
        if amount is not None:
            params['amount'] = to_minor_units(amount, currency)
        try:
            refund = (
                self._api().v1.refunds.create(params=params, options={'idempotency_key': idempotency_key}).to_dict()
            )
        except stripe.StripeError as exc:
            logger.warning('Stripe refund for payment %s failed: %s', payment.pk, exc)
            raise _error(exc, 'refund') from exc
        refund_currency = str(refund.get('currency') or currency).upper()
        refunded = from_minor_units(refund.get('amount'), refund_currency)
        if refunded is None or not refund.get('id'):
            raise ProviderRejected(f'unexpected Stripe refund answer {refund.get("id")!r}', provider=self.code)
        stripe_status = refund.get('status')
        return RefundResult(
            provider_refund_id=str(refund['id']),
            status={'succeeded': 'succeeded', 'failed': 'failed', 'canceled': 'failed'}.get(stripe_status, 'pending'),
            amount=refunded,
            currency=refund_currency,
            raw={'id': refund['id'], 'status': stripe_status, 'failure_reason': refund.get('failure_reason')},
        )

    # ── status ──

    def get_status(self, payment) -> StatusResult:
        """The Checkout Session (if any) and its payment intent, with the
        latest charge to see refunds and disputes."""
        api = self._api()
        session: dict | None = None
        intent: dict | None = None
        intent_id = payment.provider_payment_id
        try:
            if payment.provider_session_id:
                session = api.v1.checkout.sessions.retrieve(payment.provider_session_id).to_dict()
                intent_id = intent_id or _expandable_id(session.get('payment_intent'))
            if intent_id:
                intent = api.v1.payment_intents.retrieve(intent_id, params={'expand': ['latest_charge']}).to_dict()
        except stripe.StripeError as exc:
            raise _error(exc, 'status') from exc
        if session is None and intent is None:
            raise ProviderRejected('the payment has no Stripe session or payment intent', provider=self.code)
        session = session or {}
        intent = intent or {}
        charge = intent.get('latest_charge') if isinstance(intent.get('latest_charge'), dict) else {}

        state = StatusResult.PENDING
        if intent.get('status') == 'succeeded':
            if charge.get('refunded'):
                state = CallbackKind.REFUNDED
            elif charge.get('disputed'):
                state = CallbackKind.DISPUTE_OPENED
            else:
                state = CallbackKind.PAID
        elif session.get('status') == 'expired':
            state = CallbackKind.EXPIRED
        elif intent.get('status') == 'canceled':
            state = CallbackKind.FAILED
        elif session.get('status') == 'complete' and session.get('payment_status') == 'paid':
            state = CallbackKind.PAID

        source = session or intent
        currency = str(source.get('currency') or '').upper()
        amount = from_minor_units(source.get('amount_total') if session else intent.get('amount'), currency)
        return StatusResult(
            provider=self.code,
            state=state,
            provider_session_id=str(session.get('id') or payment.provider_session_id),
            provider_payment_id=intent_id or '',
            amount=amount,
            currency=currency,
            raw={
                'session_status': session.get('status'),
                'payment_status': session.get('payment_status'),
                'intent_status': intent.get('status'),
            },
        )

    def cancel_session(self, payment) -> None:
        session_id = payment.provider_session_id
        if not session_id.startswith('cs_'):
            return
        try:
            self._api().v1.checkout.sessions.expire(session_id)
        except Exception as exc:  # already completed / expired: the webhook handles it
            logger.info('Could not expire Stripe session %s: %s', session_id, exc)
