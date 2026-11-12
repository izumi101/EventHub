"""The payment provider interface (ADR 0001, section 3).

Everything outside a provider module speaks in these types: money is a
`Decimal` in major units with at most two decimal places (the precision of
the ledger), currencies are upper-case ISO 4217 codes, and provider answers
are normalised into `CallbackKind` values. Each provider owns its own unit
conversion, signature checks and error mapping.

Providers never touch the database and never hold a transaction: the
orchestration layer calls them outside row locks and applies their results.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Protocol

from common.choices import PaymentCallbackKind as CallbackKind

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

__all__ = [
    'CallbackKind',
    'CallbackResult',
    'CheckoutResult',
    'InvalidCallback',
    'OrderLine',
    'PaymentOrder',
    'PaymentProvider',
    'PaymentProviderError',
    'PaymentRef',
    'ProviderRejected',
    'ProviderUnavailable',
    'RefundResult',
    'StatusResult',
]

_CURRENCY = re.compile(r'^[A-Z]{3}$')
_EMPTY: Mapping[str, object] = MappingProxyType({})


# ───────────────────────── errors ─────────────────────────


class PaymentProviderError(Exception):
    """Base class of the provider errors; `provider` is the provider code."""

    def __init__(self, message: str, *, provider: str = '', code: str = ''):
        super().__init__(message)
        self.provider = provider
        self.code = code


class ProviderUnavailable(PaymentProviderError):
    """Network error, timeout, rate limit or 5xx: the request may be retried
    (with the same idempotency key) and counts against the provider's
    health."""


class ProviderRejected(PaymentProviderError):
    """The provider understood the request and refused it (4xx): retrying
    the same request will not help."""


class InvalidCallback(PaymentProviderError):
    """A callback that is not authentic (bad signature, replayed) or cannot
    be parsed. Answered with 400 and never applied."""


# ───────────────────────── values ─────────────────────────


def _check_money(value, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError(f'{name} must be a finite Decimal, got {value!r}')
    if value.as_tuple().exponent < -2:
        raise ValueError(f'{name} has more than two decimal places: {value}')


def _check_currency(value: str) -> None:
    if not isinstance(value, str) or not _CURRENCY.match(value):
        raise ValueError(f'currency must be an upper-case ISO 4217 code, got {value!r}')


def _freeze(mapping) -> Mapping:
    return MappingProxyType(dict(mapping or {}))


@dataclass(frozen=True)
class OrderLine:
    """One line of the provider's payment page (e.g. one seat)."""

    name: str
    unit_amount: Decimal
    quantity: int = 1
    description: str = ''

    def __post_init__(self):
        _check_money(self.unit_amount, 'unit_amount')
        if self.unit_amount <= 0:
            raise ValueError('unit_amount must be positive')
        if not isinstance(self.quantity, int) or self.quantity < 1:
            raise ValueError('quantity must be a positive integer')

    @property
    def total(self) -> Decimal:
        return self.unit_amount * self.quantity


@dataclass(frozen=True)
class PaymentOrder:
    """What to charge for one payment attempt.

    `reference` is our Payment id as a string; providers echo it back so a
    callback can be matched even without the session id. `idempotency_key`
    (`payment-<id>-attempt-<n>`) makes a retried create return the same
    provider session. `success_url` / `cancel_url` are plain frontend URLs:
    each provider adds its own placeholders (Stripe: `session_id`).
    """

    reference: str
    amount: Decimal
    currency: str
    description: str
    success_url: str
    cancel_url: str
    expires_at: datetime
    idempotency_key: str
    lines: tuple[OrderLine, ...] = ()
    customer_email: str = ''
    customer_phone: str = ''
    locale: str = ''
    metadata: Mapping[str, str] = field(default_factory=lambda: _EMPTY)

    def __post_init__(self):
        if not self.reference:
            raise ValueError('reference is required')
        if not self.idempotency_key:
            raise ValueError('idempotency_key is required')
        _check_money(self.amount, 'amount')
        if self.amount <= 0:
            raise ValueError('amount must be positive')
        _check_currency(self.currency)
        if self.expires_at.tzinfo is None:
            raise ValueError('expires_at must be timezone-aware')
        object.__setattr__(self, 'lines', tuple(self.lines))
        if self.lines and sum((line.total for line in self.lines), Decimal('0')) != self.amount:
            raise ValueError('the lines do not add up to the amount')
        object.__setattr__(self, 'metadata', _freeze(self.metadata))


@dataclass(frozen=True)
class CallbackResult:
    """A provider notification, normalised.

    `event_id` is the provider's event id (or a stable hash of the callback
    for providers without one) and is the dedupe key of PaymentEvent.
    `amount` / `currency` are what the provider reports, for comparison with
    the Payment; None / '' when the event carries no amount. `raw` is the
    sanitised payload (never secrets or card data).
    """

    provider: str
    event_id: str
    kind: str
    reference: str = ''
    provider_session_id: str = ''
    provider_payment_id: str = ''
    amount: Decimal | None = None
    currency: str = ''
    raw: Mapping[str, object] = field(default_factory=lambda: _EMPTY)

    def __post_init__(self):
        if not self.event_id:
            raise ValueError('event_id is required')
        if self.kind not in CallbackKind.values:
            raise ValueError(f'unknown callback kind {self.kind!r}')
        if self.amount is not None:
            _check_money(self.amount, 'amount')
        if self.currency:
            _check_currency(self.currency)
        object.__setattr__(self, 'raw', _freeze(self.raw))


@dataclass(frozen=True)
class CheckoutResult:
    """A created provider session: send the buyer to `redirect_url`.

    `immediate` is set by providers that settle synchronously (the mock
    provider): the caller applies it exactly like a callback.
    """

    provider: str
    session_id: str
    redirect_url: str
    expires_at: datetime | None = None
    payment_id: str = ''
    immediate: CallbackResult | None = None
    raw: Mapping[str, object] = field(default_factory=lambda: _EMPTY)

    def __post_init__(self):
        if not self.session_id or not self.redirect_url:
            raise ValueError('session_id and redirect_url are required')
        object.__setattr__(self, 'raw', _freeze(self.raw))


@dataclass(frozen=True)
class RefundResult:
    """The provider's answer to a refund request. `status` is one of the
    Refund.Status values (`pending` when the provider settles it later)."""

    provider_refund_id: str
    status: str
    amount: Decimal
    currency: str
    raw: Mapping[str, object] = field(default_factory=lambda: _EMPTY)

    STATUSES: ClassVar[frozenset[str]] = frozenset({'pending', 'succeeded', 'failed'})

    def __post_init__(self):
        if self.status not in self.STATUSES:
            raise ValueError(f'unknown refund status {self.status!r}')
        _check_money(self.amount, 'amount')
        _check_currency(self.currency)
        object.__setattr__(self, 'raw', _freeze(self.raw))


@dataclass(frozen=True)
class StatusResult:
    """What the provider says about a payment right now.

    `state` is `pending` while the buyer can still pay, else the
    CallbackKind the state corresponds to (`paid`, `failed`, `expired`,
    `refunded`, ...). `as_callback()` turns it into a CallbackResult so a
    status poll is settled through the same path as a callback.
    """

    provider: str
    state: str
    provider_session_id: str = ''
    provider_payment_id: str = ''
    amount: Decimal | None = None
    currency: str = ''
    raw: Mapping[str, object] = field(default_factory=lambda: _EMPTY)

    PENDING: ClassVar[str] = 'pending'

    def __post_init__(self):
        if self.state != self.PENDING and self.state not in CallbackKind.values:
            raise ValueError(f'unknown payment state {self.state!r}')
        if self.amount is not None:
            _check_money(self.amount, 'amount')
        if self.currency:
            _check_currency(self.currency)
        object.__setattr__(self, 'raw', _freeze(self.raw))

    def as_callback(self, *, reference: str = '') -> CallbackResult:
        kind = CallbackKind.IGNORED if self.state == self.PENDING else self.state
        ids = self.provider_payment_id or self.provider_session_id
        return CallbackResult(
            provider=self.provider,
            event_id=f'status:{ids}:{self.state}',
            kind=kind,
            reference=reference,
            provider_session_id=self.provider_session_id,
            provider_payment_id=self.provider_payment_id,
            amount=self.amount,
            currency=self.currency,
            raw=self.raw,
        )


class PaymentRef(Protocol):
    """What a provider reads from a payment (a `payments.Payment` row, or a
    stand-in for an orphan refund that has no row)."""

    pk: object
    provider_session_id: str
    provider_payment_id: str
    amount: Decimal
    currency: str


# ───────────────────────── interface ─────────────────────────


class PaymentProvider(ABC):
    code: ClassVar[str]
    #: Upper-case ISO codes this provider can charge; None means any.
    supported_currencies: ClassVar[frozenset[str] | None] = None

    def supports_currency(self, currency: str) -> bool:
        return self.supported_currencies is None or currency.upper() in self.supported_currencies

    @abstractmethod
    def is_configured(self) -> bool:
        """True when every setting the provider needs is present."""

    @abstractmethod
    def create_payment(self, order: PaymentOrder) -> CheckoutResult:
        """Open a provider session for `order`. Raises ProviderUnavailable /
        ProviderRejected."""

    @abstractmethod
    def handle_callback(self, request: HttpRequest) -> CallbackResult:
        """Authenticate and normalise a provider notification. Raises
        InvalidCallback for anything not provably from the provider."""

    @abstractmethod
    def callback_response(self, result: CallbackResult, outcome: str) -> HttpResponse:
        """The acknowledgement the provider expects (also for re-deliveries)."""

    @abstractmethod
    def refund(self, payment: PaymentRef, amount: Decimal, *, idempotency_key: str, reason: str) -> RefundResult:
        """Return `amount` of `payment` to the buyer."""

    @abstractmethod
    def get_status(self, payment: PaymentRef) -> StatusResult:
        """Ask the provider for the current state of `payment`."""

    @abstractmethod
    def cancel_session(self, payment: PaymentRef) -> None:
        """Close the payment page of `payment` if it is still open. Best
        effort: never raises."""
