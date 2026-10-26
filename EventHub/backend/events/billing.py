"""Compute the real amount owed for a registration, with tax & fees.

This is the single source of truth for money. Both the mock and the real
Stripe flow call `registration_amount`, and the checkout UI / invoice render
`price_breakdown` so the line items the attendee sees equal what they pay.

Pricing dimensions, in order:
  1. Base price — ticket tier, seat zone, or the flat event price.
  2. Promo discount (locked in at registration time).
  3. Tax (% of discounted subtotal).
  4. Service fee (% of discounted subtotal).
Tax/fee are added on top when `fees_passed_to_buyer`, otherwise absorbed
(shown for transparency but not added to the total).
"""
from decimal import Decimal, ROUND_HALF_UP

# Stripe amounts are integers in the currency's minor unit; these currencies
# have no minor unit (or a 3-digit one) and must not be multiplied by 100.
# https://docs.stripe.com/currencies#zero-decimal
ZERO_DECIMAL_CURRENCIES = {
    'BIF', 'CLP', 'DJF', 'GNF', 'JPY', 'KMF', 'KRW', 'MGA', 'PYG', 'RWF',
    'UGX', 'VND', 'VUV', 'XAF', 'XOF', 'XPF',
}
THREE_DECIMAL_CURRENCIES = {'BHD', 'JOD', 'KWD', 'OMR', 'TND'}


def _q(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def event_currency(event) -> str:
    """ISO code of the money the event is priced in (upper case)."""
    return (getattr(event, 'currency', '') or 'USD').upper()


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


def _base_price(registration) -> Decimal:
    """Price after tier/seat selection and promo, before tax & fees."""
    from .models import TicketType
    event = registration.event
    tt = registration.ticket_type if registration.ticket_type_id else None

    if tt is not None and tt.kind == TicketType.KIND_FREE:
        return Decimal('0.00')

    if registration.locked_price is not None:
        # Quoted price frozen at registration time (tier, seat zone, donation
        # or the dynamic GA price), so later price edits can't change what an
        # attendee with a pending hold is charged.
        base = _q(registration.locked_price)
    elif tt is not None:
        if tt.kind == TicketType.KIND_DONATION:
            chosen = registration.donation_amount if registration.donation_amount is not None else tt.price
            base = max(_q(chosen), _q(tt.price))
        else:
            base = _q(tt.price)
    elif event.is_free:
        return Decimal('0.00')
    elif registration.seat_id and registration.seat:
        from .seat_pricing import seat_price
        base = Decimal(str(seat_price(event, registration.seat)))
    else:
        base = _q(event.price)

    if registration.promo_code_id and registration.promo_code:
        from .promo import apply_discount
        base = apply_discount(base, registration.promo_code)

    return _q(base)


def price_breakdown(registration) -> dict:
    """Itemised price: subtotal, tax, fee, total (all stringified Decimals)."""
    event = registration.event
    subtotal = _base_price(registration)

    tax_pct = Decimal(str(event.tax_percent or 0))
    fee_pct = Decimal(str(event.service_fee_percent or 0))

    tax = _q(subtotal * tax_pct / Decimal('100')) if subtotal > 0 else Decimal('0.00')
    fee = _q(subtotal * fee_pct / Decimal('100')) if subtotal > 0 else Decimal('0.00')

    passed = event.fees_passed_to_buyer
    total = _q(subtotal + tax + fee) if passed else subtotal

    return {
        'subtotal': str(subtotal),
        'tax_percent': str(tax_pct),
        'tax': str(tax),
        'fee_percent': str(fee_pct),
        'fee': str(fee),
        'fees_passed_to_buyer': passed,
        'total': str(total),
        'currency': event_currency(event),
    }


def registration_amount(registration) -> Decimal:
    """The single number charged to the attendee at checkout."""
    return _q(price_breakdown(registration)['total'])


def quote_breakdown(event, base_price, promo=None) -> dict:
    """Tax/fee breakdown for an arbitrary base price (used by the buy box).

    Lets the frontend show the full line-item total before a registration row
    exists. `promo` is an optional PromoCode already validated by the caller.
    """
    base = _q(base_price)
    if promo is not None:
        from .promo import apply_discount
        base = apply_discount(base, promo)

    tax_pct = Decimal(str(event.tax_percent or 0))
    fee_pct = Decimal(str(event.service_fee_percent or 0))
    tax = _q(base * tax_pct / Decimal('100')) if base > 0 else Decimal('0.00')
    fee = _q(base * fee_pct / Decimal('100')) if base > 0 else Decimal('0.00')
    passed = event.fees_passed_to_buyer
    total = _q(base + tax + fee) if passed else base

    return {
        'subtotal': str(base),
        'tax_percent': str(tax_pct), 'tax': str(tax),
        'fee_percent': str(fee_pct), 'fee': str(fee),
        'fees_passed_to_buyer': passed,
        'total': str(total), 'currency': event_currency(event),
    }
