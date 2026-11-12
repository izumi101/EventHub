"""Domain records: payments and their money operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

# pg_payment_status values (S7, S11).
NEW = 'new'
WAITING = 'waiting'
PROCESS = 'process'
SUCCESS = 'success'
ERROR = 'error'
PENDING_STATUSES = (NEW, WAITING, PROCESS)

TIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%f+00:00'


def iso(moment: datetime) -> str:
    """Fixed-width UTC timestamp, so stored values compare lexicographically."""
    return moment.astimezone(UTC).strftime(TIME_FORMAT)


def from_iso(text: str) -> datetime:
    return datetime.strptime(text, TIME_FORMAT).replace(tzinfo=UTC)


_DECIMALS = {'amount', 'clearing_amount'}
_TIMES = {'created_at', 'expires_at', 'paid_at', 'captured_at'}


@dataclass
class Payment:
    payment_id: int
    merchant_id: str
    customer: str
    amount: Decimal
    currency: str
    description: str
    created_at: datetime
    expires_at: datetime
    lifetime: int
    testing_mode: bool
    auto_clearing: bool
    order_id: str | None = None
    status: str = NEW
    check_url: str | None = None
    result_url: str | None = None
    request_method: str = 'POST'
    success_url: str | None = None
    success_url_method: str = 'GET'
    failure_url: str | None = None
    failure_url_method: str = 'GET'
    timeout_after_payment: int = 10
    language: str | None = None
    user_phone: str | None = None
    user_email: str | None = None
    user_ip: str | None = None
    user_id: str | None = None
    payment_method_filter: str | None = None
    custom_params: list[list[str]] = field(default_factory=list)
    pg_params: dict[str, str] = field(default_factory=dict)
    receipt_positions: Any = None
    idempotency_key: str | None = None
    redirect_qr: bool = False
    # Outcome
    scenario: dict[str, Any] | None = None
    challenge: dict[str, Any] | None = None
    payment_method: str = 'none'
    card: dict[str, str] | None = None
    reference: str | None = None
    auth_code: str | None = None
    failure_code: str | None = None
    failure_description: str | None = None
    paid_at: datetime | None = None
    captured: bool = False
    captured_at: datetime | None = None
    clearing_amount: Decimal = Decimal('0')
    can_reject: bool = False
    merchant_rejected: bool = False
    merchant_reply_description: str | None = None
    auto_processed: str | None = None

    @property
    def is_final(self) -> bool:
        return self.status in (SUCCESS, ERROR)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for name in _DECIMALS:
            data[name] = str(data[name])
        for name in _TIMES:
            data[name] = iso(data[name]) if data[name] is not None else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Payment:
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        for name in _DECIMALS:
            values[name] = Decimal(values[name])
        for name in _TIMES:
            if values.get(name) is not None:
                values[name] = from_iso(values[name])
        return cls(**values)


# Operation kinds.
REFUND = 'refund'  # /revoke: listed in pg_refund_payments
CANCEL = 'cancel'  # /cancel and merchant rejection: listed in pg_revoked_payments


@dataclass
class Operation:
    op_id: int
    payment_id: int
    kind: str
    status: str
    amount: Decimal
    created_at: datetime
    reference: str | None = None
    failure_code: str | None = None
    failure_description: str | None = None
    idempotency_key: str | None = None
    origin: str = 'api'

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data['amount'] = str(self.amount)
        data['created_at'] = iso(self.created_at)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Operation:
        values = dict(data)
        values['amount'] = Decimal(values['amount'])
        values['created_at'] = from_iso(values['created_at'])
        return cls(**values)
