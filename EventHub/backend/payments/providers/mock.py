"""Mock provider: payments confirmed without charging anyone.

Replaces the `STRIPE_MOCK_MODE` switch (ADR 0001). The checkout redirects
straight to the frontend success page on the current origin and reports
`paid` synchronously (`CheckoutResult.immediate`); refunds succeed at once.
Session, payment and refund ids are derived from the idempotency keys, so a
retried call returns the same ids like a real provider.

It refuses to work unless DEBUG or the test runner is on; settings.py also
refuses to start a DEBUG=0 deployment that enables it.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.http import JsonResponse

from .base import (
    CallbackKind,
    CallbackResult,
    CheckoutResult,
    InvalidCallback,
    PaymentOrder,
    PaymentProvider,
    ProviderRejected,
    RefundResult,
    StatusResult,
)
from .registry import register

MAX_CALLBACK_BYTES = 16 * 1024


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def _allowed() -> bool:
    return bool(getattr(settings, 'DEBUG', False) or getattr(settings, 'TESTING', False))


def _with_query(url: str, **params: str) -> str:
    """`url` reduced to path + query (same origin, keeps the auth token in
    localStorage) with `params` added."""
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True) + list(params.items())
    return urlunsplit(('', '', parts.path or '/', urlencode(query), ''))


@register
class MockProvider(PaymentProvider):
    code = 'mock'
    supported_currencies = None

    def is_configured(self) -> bool:
        return _allowed()

    def _require_allowed(self) -> None:
        if not _allowed():
            raise ProviderRejected('the mock payment provider only works with DEBUG on', provider=self.code)

    def create_payment(self, order: PaymentOrder) -> CheckoutResult:
        self._require_allowed()
        session_id = f'mock_sess_{_digest(order.idempotency_key)}'
        payment_id = f'mock_pay_{_digest(order.idempotency_key)}'
        paid = CallbackResult(
            provider=self.code,
            event_id=f'{session_id}:paid',
            kind=CallbackKind.PAID,
            reference=order.reference,
            provider_session_id=session_id,
            provider_payment_id=payment_id,
            amount=order.amount,
            currency=order.currency,
            raw={'mock': True},
        )
        return CheckoutResult(
            provider=self.code,
            session_id=session_id,
            redirect_url=_with_query(order.success_url, session_id=session_id),
            expires_at=order.expires_at,
            payment_id=payment_id,
            immediate=paid,
        )

    def handle_callback(self, request) -> CallbackResult:
        """A simulated provider notification, for exercising failure paths
        in development: a JSON object with `event_id`, `kind` and optionally
        `reference`, `session_id`, `payment_id`, `amount`, `currency`."""
        if not _allowed():
            raise InvalidCallback('the mock payment provider only works with DEBUG on', provider=self.code)
        body = request.body
        if len(body) > MAX_CALLBACK_BYTES:
            raise InvalidCallback('callback too large', provider=self.code)
        try:
            data = json.loads(body)
        except (UnicodeDecodeError, ValueError) as exc:
            raise InvalidCallback('callback is not JSON', provider=self.code) from exc
        if not isinstance(data, dict):
            raise InvalidCallback('callback must be a JSON object', provider=self.code)
        amount = data.get('amount')
        try:
            amount = Decimal(str(amount)) if amount is not None else None
            return CallbackResult(
                provider=self.code,
                event_id=str(data.get('event_id') or ''),
                kind=str(data.get('kind') or ''),
                reference=str(data.get('reference') or ''),
                provider_session_id=str(data.get('session_id') or ''),
                provider_payment_id=str(data.get('payment_id') or ''),
                amount=amount,
                currency=str(data.get('currency') or '').upper(),
                raw={key: data[key] for key in ('event_id', 'kind', 'reference') if key in data},
            )
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise InvalidCallback(f'malformed callback: {exc}', provider=self.code) from exc

    def callback_response(self, result: CallbackResult, outcome: str) -> JsonResponse:
        return JsonResponse({'received': True, 'outcome': outcome})

    def refund(self, payment, amount: Decimal, *, idempotency_key: str, reason: str) -> RefundResult:
        self._require_allowed()
        if amount <= 0 or amount > payment.amount:
            raise ProviderRejected(f'cannot refund {amount} of {payment.amount}', provider=self.code)
        return RefundResult(
            provider_refund_id=f'mock_re_{_digest(idempotency_key)}',
            status='succeeded',
            amount=amount,
            currency=payment.currency.upper(),
            raw={'mock': True, 'reason': reason},
        )

    def get_status(self, payment) -> StatusResult:
        self._require_allowed()
        # A mock session is paid the moment it exists.
        state = CallbackKind.PAID if payment.provider_session_id else StatusResult.PENDING
        return StatusResult(
            provider=self.code,
            state=state,
            provider_session_id=payment.provider_session_id,
            provider_payment_id=payment.provider_payment_id,
            amount=payment.amount,
            currency=payment.currency.upper(),
        )

    def cancel_session(self, payment) -> None:
        return None
