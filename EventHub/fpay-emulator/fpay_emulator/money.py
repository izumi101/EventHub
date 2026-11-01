"""Decimal money helpers. Floats never touch an amount."""

from __future__ import annotations

import re
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

CENT = Decimal('0.01')
MIN_AMOUNT = Decimal('0.01')
MAX_AMOUNT = Decimal('99999999')
_AMOUNT_RE = re.compile(r'^\d{1,8}(\.\d{1,2})?$')
_LOOSE_AMOUNT_RE = re.compile(r'^\d{1,8}(\.\d+)?$')


def parse_amount(text: str) -> Decimal | None:
    """``pg_amount``: dot separator, up to two decimals, 0.01 to 99999999 (S2)."""
    if not isinstance(text, str) or not _AMOUNT_RE.match(text):
        return None
    value = Decimal(text)
    if value < MIN_AMOUNT or value > MAX_AMOUNT:
        return None
    return value


def parse_optional_amount(text: str, *, truncate: bool = False) -> Decimal | None:
    """An optional amount where ``0`` is allowed (refund/clearing amounts).

    With ``truncate`` extra decimal digits are dropped instead of refused
    (``pg_clearing_amount``, S10).
    """
    if not isinstance(text, str):
        return None
    pattern = _LOOSE_AMOUNT_RE if truncate else _AMOUNT_RE
    if not pattern.match(text):
        return None
    value = Decimal(text)
    if truncate:
        value = value.quantize(CENT, rounding=ROUND_DOWN)
    if value > MAX_AMOUNT:
        return None
    return value


def plain(value: Decimal) -> str:
    """Shortest decimal form, like the gateway prints amounts: ``100``, ``482.5``."""
    quantized = value.quantize(CENT)
    text = format(quantized, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'


def two_places(value: Decimal) -> str:
    return format(value.quantize(CENT), 'f')


def negative(value: Decimal) -> str:
    """Refund sums in ``get_status3.php``: negative, two decimals (``-20.00``)."""
    return two_places(-value) if value else '0.00'


def percent_of(amount: Decimal, percent: Decimal) -> Decimal:
    return (amount * percent / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
