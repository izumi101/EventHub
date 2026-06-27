"""
Per-zone seat pricing.

Each seat's price = event base price × zone multiplier.
Multipliers can be overridden per seat map via `SeatMap.layout['zone_prices']`,
otherwise the platform defaults apply.
"""

from decimal import Decimal, ROUND_HALF_UP

DEFAULT_ZONE_MULTIPLIERS = {
    'standard': Decimal('1.0'),
    'vip':      Decimal('2.0'),
    'premium':  Decimal('3.0'),
}


def zone_multipliers(seat_map) -> dict:
    """Return {zone: Decimal multiplier} for a seat map."""
    overrides = {}
    try:
        raw = (seat_map.layout or {}).get('zone_prices') or {}
        overrides = {k: Decimal(str(v)) for k, v in raw.items()}
    except Exception:
        overrides = {}
    return {**DEFAULT_ZONE_MULTIPLIERS, **overrides}


def seat_price(event, seat) -> Decimal:
    """Compute the price of a single seat for an event."""
    base = Decimal(str(event.price or 0))
    mults = zone_multipliers(seat.seat_map)
    mult = mults.get(seat.price_zone, Decimal('1.0'))
    return (base * mult).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def zone_price_table(event) -> list[dict]:
    """Return the price for each zone present in the event's seat map."""
    try:
        seat_map = event.seat_map
    except Exception:
        return []

    base = Decimal(str(event.price or 0))
    mults = zone_multipliers(seat_map)
    zones_present = (
        seat_map.seats.values_list('price_zone', flat=True).distinct()
    )
    table = []
    for zone in zones_present:
        mult = mults.get(zone, Decimal('1.0'))
        table.append({
            'zone': zone,
            'multiplier': float(mult),
            'price': str((base * mult).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
        })
    # stable order: standard, vip, premium, then any others
    order = {'standard': 0, 'vip': 1, 'premium': 2}
    table.sort(key=lambda r: order.get(r['zone'], 99))
    return table
