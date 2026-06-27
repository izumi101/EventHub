"""
Dynamic pricing engine.

Adjusts event ticket price based on demand signals:
  - Fill rate (registrations / capacity)
  - Time to event (urgency)
  - Registration velocity (recent signups per hour)

Price ranges:
  - Base price (organizer-set)
  - Min: base × 0.8  (early-bird discount)
  - Max: base × 2.5  (high-demand surge)

Formula:
  multiplier = 1.0
  + fill_factor   (0→0.5 based on fill rate)
  + urgency_factor (0→0.3 based on days to event)
  + velocity_factor (0→0.2 based on signup speed)

  clamped to [0.8, 2.5]
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)

PRICE_MIN_MULTIPLIER = Decimal('0.80')
PRICE_MAX_MULTIPLIER = Decimal('2.50')


def get_dynamic_price(event) -> dict:
    """
    Return current dynamic price info for an event.

    Returns a dict:
      base_price      — organizer's base price
      current_price   — current adjusted price (Decimal, 2dp)
      multiplier      — current multiplier (float)
      fill_rate       — fill percentage 0-100
      demand_level    — 'low' | 'medium' | 'high' | 'surge'
    """
    if event.is_free or event.price == 0:
        return {
            'base_price': '0.00',
            'current_price': '0.00',
            'multiplier': 1.0,
            'fill_rate': 0,
            'demand_level': 'free',
        }

    base = event.price
    total = event.max_participants or 1
    registered = event.registrations.exclude(
        status__in=['cancelled', 'rejected']
    ).count()

    fill_rate = registered / total if total else 0
    fill_factor = fill_rate * 0.5  # 0 → 0.5

    # Urgency: closer to event → higher price; far out → early-bird discount
    # (negative factor makes the 0.8 floor actually reachable).
    now = timezone.now()
    days_left = max(0, (event.date - now).days)
    if days_left >= 60:
        urgency_factor = -0.2
    elif days_left >= 30:
        urgency_factor = -0.1
    elif days_left >= 7:
        urgency_factor = 0.2
    else:
        urgency_factor = 0.3

    # Velocity: registrations in last 24h
    recent = event.registrations.filter(
        registered_at__gte=now - timedelta(hours=24)
    ).count()
    velocity_factor = min(recent / 20, 0.2)  # cap at 0.2

    multiplier = 1.0 + fill_factor + urgency_factor + velocity_factor
    multiplier_dec = Decimal(str(round(multiplier, 3)))
    multiplier_dec = max(PRICE_MIN_MULTIPLIER, min(PRICE_MAX_MULTIPLIER, multiplier_dec))

    current_price = (base * multiplier_dec).quantize(Decimal('0.01'))

    # Demand label
    if multiplier_dec >= Decimal('2.0'):
        demand_level = 'surge'
    elif multiplier_dec >= Decimal('1.5'):
        demand_level = 'high'
    elif multiplier_dec >= Decimal('1.1'):
        demand_level = 'medium'
    else:
        demand_level = 'low'

    return {
        'base_price': str(base),
        'current_price': str(current_price),
        'multiplier': float(multiplier_dec),
        'fill_rate': round(fill_rate * 100, 1),
        'demand_level': demand_level,
        'registered': registered,
        'capacity': total,
    }
