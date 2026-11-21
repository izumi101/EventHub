"""Sales over time across every managed event (`GET organizer/sales/`,
docs/ORGANIZER_DASHBOARD_PHASE2.md, A1).

The metric definitions are those of `events.analytics` and
`events.dashboard.bulk_event_stats`: tickets are confirmed registrations plus
the seats of confirmed group bookings, money is net of refunds and never
summed across currencies. Days are business-time-zone days (`business_time`).
Six queries however many events there are.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.db.models import Count, Sum, Value
from django.db.models.functions import Coalesce, NullIf, Upper
from django.utils import timezone

from common.choices import PaymentStatusChoices, RegistrationStatusChoices

from .billing import quote_breakdown
from .business_time import (
    business_tz,
    days_between,
    local_date,
    local_today,
    trunc_day,
    window_bounds,
)
from .dashboard import TWO_PLACES, managed_events
from .models import Registration

RANGES = {'7d': 7, '30d': 30, '90d': 90}
DEFAULT_RANGE = '30d'


def _currency(path: str):
    """SQL twin of `billing.event_currency` for the event column at `path`."""
    return Upper(Coalesce(NullIf(path, Value('')), Value('USD')))


def published_markers(managed, start, end) -> list[dict]:
    """Events published in [start, end] as {date, event_id, title, kind}.

    `Event.published_at` does not exist yet (batch B adds it), and a
    publication date is never guessed from `updated_at`, so there are no
    markers until it does.
    """
    return []


def sales_series(user, range_key: str = DEFAULT_RANGE, now=None) -> dict:
    from bookings.models import Booking, BookingSeat
    from payments.models import Payment, Refund

    tz = business_tz()
    now = now or timezone.now()
    end = local_today(now, tz)
    start = end - timedelta(days=RANGES[range_key] - 1)
    days = days_between(start, end)
    lower, upper = window_bounds(start, end, tz)
    managed = managed_events(user).values('pk')
    confirmed_booking = Booking.Status.CONFIRMED

    # ── Tickets ──
    tickets = defaultdict(int)
    for row in (
        Registration.objects.filter(
            event_id__in=managed,
            status=RegistrationStatusChoices.CONFIRMED,
            registered_at__gte=lower,
            registered_at__lt=upper,
        )
        .annotate(day=trunc_day('registered_at', tz))
        .order_by()
        .values('day')
        .annotate(n=Count('pk'))
    ):
        tickets[row['day']] += row['n']
    for row in (
        BookingSeat.objects.filter(
            booking__event_id__in=managed,
            booking__status=confirmed_booking,
            booking__created_at__gte=lower,
            booking__created_at__lt=upper,
        )
        .annotate(day=trunc_day('booking__created_at', tz))
        .order_by()
        .values('day')
        .annotate(n=Count('pk'))
    ):
        tickets[row['day']] += row['n']

    # ── Money: {currency: {day: net}} ──
    money: dict[str, dict] = defaultdict(lambda: defaultdict(Decimal))

    def add(rows, sign=1):
        for row in rows:
            money[row['cur']][row['day']] += sign * row['total']

    # Ticket payments, on the day the money arrived: `Payment.paid_at`, or
    # `created_at` for a paid row that lacks it (written by code that predates
    # the column, e.g. after a rollback).
    add(
        Payment.objects.filter(
            registration__event_id__in=managed,
            status__in=[PaymentStatusChoices.COMPLETED, PaymentStatusChoices.REFUNDED],
        )
        .annotate(paid_on=Coalesce('paid_at', 'created_at'))
        .filter(paid_on__gte=lower, paid_on__lt=upper)
        .annotate(cur=_currency('registration__event__currency'), day=trunc_day('paid_on', tz))
        .order_by()
        .values('cur', 'day')
        .annotate(total=Sum('amount'))
    )
    # Refunds of ticket payments, on the day they succeeded.
    add(
        Refund.objects.filter(
            status=Refund.Status.SUCCEEDED,
            payment__registration__event_id__in=managed,
            processed_at__gte=lower,
            processed_at__lt=upper,
        )
        .annotate(cur=_currency('payment__registration__event__currency'), day=trunc_day('processed_at', tz))
        .order_by()
        .values('cur', 'day')
        .annotate(total=Sum('amount')),
        sign=-1,
    )

    # Group bookings: the amount on the day the booking was confirmed (paid),
    # and a refunded booking's amount back out on `refunded_at`.
    booking_states = [Booking.Status.CONFIRMED, Booking.Status.REFUNDED]
    # A booking confirmed by code that predates `confirmed_at` falls back to
    # `created_at` (readers must tolerate it until the contract step).
    confirmed_day = Coalesce('confirmed_at', 'created_at')
    in_force = Booking.objects.filter(
        event_id__in=managed, status__in=booking_states, amount_paid__isnull=False
    ).annotate(cur=_currency('event__currency'))
    add(
        in_force.annotate(confirmed_on=confirmed_day)
        .filter(confirmed_on__gte=lower, confirmed_on__lt=upper)
        .annotate(day=trunc_day('confirmed_on', tz))
        .order_by()
        .values('cur', 'day')
        .annotate(total=Sum('amount_paid'))
    )
    refunded_day = Coalesce('refunded_at', 'updated_at')
    add(
        in_force.filter(status=Booking.Status.REFUNDED)
        .annotate(refunded_on=refunded_day)
        .filter(refunded_on__gte=lower, refunded_on__lt=upper)
        .annotate(day=trunc_day('refunded_on', tz))
        .order_by()
        .values('cur', 'day')
        .annotate(total=Sum('amount_paid')),
        sign=-1,
    )

    # Bookings that never recorded `amount_paid` are priced from their seats,
    # like `bookings.payments.booking_amount` (grouped per booking in Python).
    unpriced = defaultdict(lambda: {'amount': Decimal('0'), 'cur': '', 'confirmed': None, 'refunded': None})
    for row in (
        BookingSeat.objects.filter(
            booking__event_id__in=managed,
            booking__status__in=booking_states,
            booking__amount_paid__isnull=True,
        )
        .annotate(
            cur=_currency('booking__event__currency'),
            refunded_on=Coalesce('booking__refunded_at', 'booking__updated_at'),
            confirmed_on=Coalesce('booking__confirmed_at', 'booking__created_at'),
        )
        .values(
            'booking_id',
            'booking__status',
            'confirmed_on',
            'refunded_on',
            'cur',
            'price',
            'booking__event__tax_percent',
            'booking__event__service_fee_percent',
            'booking__event__fees_passed_to_buyer',
        )
    ):
        event = SimpleNamespace(
            tax_percent=row['booking__event__tax_percent'],
            service_fee_percent=row['booking__event__service_fee_percent'],
            fees_passed_to_buyer=row['booking__event__fees_passed_to_buyer'],
        )
        booking = unpriced[row['booking_id']]
        booking['amount'] += Decimal(quote_breakdown(event, row['price'])['total'])
        booking['cur'] = row['cur']
        booking['confirmed'] = row['confirmed_on']
        booking['refunded'] = row['refunded_on'] if row['booking__status'] == Booking.Status.REFUNDED else None
    for booking in unpriced.values():
        if lower <= booking['confirmed'] < upper:
            money[booking['cur']][local_date(booking['confirmed'], tz)] += booking['amount']
        if booking['refunded'] is not None and lower <= booking['refunded'] < upper:
            money[booking['cur']][local_date(booking['refunded'], tz)] -= booking['amount']

    return {
        'time_zone': str(tz),
        'start': start.isoformat(),
        'end': end.isoformat(),
        'days': [{'date': d.isoformat(), 'tickets': tickets.get(d, 0)} for d in days],
        'revenue': [
            {
                'currency': currency,
                'days': [
                    {'date': d.isoformat(), 'net_revenue': str(per_day.get(d, Decimal('0')).quantize(TWO_PLACES))}
                    for d in days
                ],
            }
            for currency, per_day in sorted(money.items())
        ],
        'markers': published_markers(managed, start, end),
    }
