"""Promo-code validation and discount math.

Single source of truth for: looking up a code, checking it's usable, and
computing the final price. Used by both the public "validate" endpoint and the
checkout flow so the number the attendee sees equals the number they pay.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import F, Q

from .models import PromoCode


class PromoError(Exception):
    """Raised when a promo code cannot be applied. Message is user-facing."""


def _q(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def get_valid_promo(event, code: str) -> PromoCode:
    """Return the active PromoCode for `code` on `event` or raise PromoError."""
    if not code or not code.strip():
        raise PromoError('Enter a promo code.')

    promo = PromoCode.objects.filter(event=event, code__iexact=code.strip()).first()
    # One message for "unknown", "inactive", "expired" and "used up" so the
    # public validate endpoint can't be used to enumerate existing codes.
    if promo is None or not promo.is_valid:
        raise PromoError(INVALID_PROMO_MESSAGE)
    return promo


INVALID_PROMO_MESSAGE = 'This promo code is invalid or no longer available.'


def reserve_promo(promo: PromoCode) -> None:
    """Atomically take one use of `promo` (call inside the registration's
    transaction). Two buyers racing for the last use of a `max_uses=1` code
    can't both succeed: the conditional UPDATE matches for only one of them.
    """
    taken = (
        PromoCode.objects.filter(pk=promo.pk, is_active=True)
        .filter(Q(max_uses__isnull=True) | Q(times_used__lt=F('max_uses')))
        .update(times_used=F('times_used') + 1)
    )
    if not taken:
        raise PromoError(INVALID_PROMO_MESSAGE)


def release_promo(registration) -> None:
    """Give back the use reserved by a registration that will never be paid
    (hold expired, cancelled, refunded)."""
    if not registration.promo_code_id:
        return
    PromoCode.objects.filter(pk=registration.promo_code_id, times_used__gt=0).update(
        times_used=F('times_used') - 1,
    )


def apply_discount(base_price, promo: PromoCode) -> Decimal:
    """Return the final price after applying `promo` to `base_price` (>= 0)."""
    base = _q(base_price)
    if promo.discount_type == PromoCode.DISCOUNT_PERCENT:
        pct = min(Decimal(str(promo.discount_value)), Decimal('100'))
        discounted = base * (Decimal('1') - pct / Decimal('100'))
    else:  # fixed
        discounted = base - Decimal(str(promo.discount_value))
    return max(_q(discounted), Decimal('0.00'))


def quote(event, code: str, base_price=None):
    """Validate `code` and return a dict the frontend renders at checkout.

    `base_price` lets the caller pass the tier/seat price the attendee actually
    selected; without it we fall back to the flat event price.
    """
    promo = get_valid_promo(event, code)
    base = _q(event.price if base_price is None else base_price)
    final = apply_discount(base, promo)
    return {
        'code': promo.code,
        'discount_type': promo.discount_type,
        'discount_value': str(promo.discount_value),
        'base_price': str(base),
        'final_price': str(final),
        'savings': str(_q(base - final)),
    }
