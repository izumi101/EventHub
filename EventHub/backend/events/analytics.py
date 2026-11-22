"""Sales analytics for an organizer's event.

Aggregates confirmed registrations and completed payments into the numbers a
dashboard needs: headline KPIs, a daily sales timeline, and breakdowns by
ticket tier and promoter. All money comes from the Payment rows so refunds are
reflected (net of refunds) automatically.
"""

from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from common.choices import PaymentStatusChoices, RegistrationStatusChoices

from .business_time import business_tz, days_between, local_date, local_today

TIMELINE_DAYS = 30
PAID_STATUSES = (PaymentStatusChoices.COMPLETED, PaymentStatusChoices.REFUNDED)


def _active_regs(event):
    return event.registrations.exclude(
        status__in=[RegistrationStatusChoices.CANCELLED, RegistrationStatusChoices.REJECTED]
    ).select_related('payment', 'ticket_type', 'affiliate')


def _revenue(event):
    """Money taken for the event: (gross, refunded, paid_count, group_confirmed).
    Ticket payments plus group bookings; `group_confirmed` lists
    (booking, amount, seats) of the bookings still in force."""
    # ── Revenue (net of refunds) from every payment of the event ──
    # Includes cancelled registrations: a full refund cancels the ticket, and
    # skipping those rows would make the "refunded" figure leave them out.
    from payments.models import Payment

    gross = Decimal('0')
    refunded = Decimal('0')
    paid_count = 0
    for pay in Payment.objects.filter(
        registration__event=event,
        status__in=[PaymentStatusChoices.COMPLETED, PaymentStatusChoices.REFUNDED],
    ):
        gross += pay.amount
        refunded += pay.refunded_amount
        if pay.status == PaymentStatusChoices.COMPLETED:
            paid_count += 1

    # ── Group bookings (no Registration/Payment rows of their own) ──
    from bookings.models import Booking
    from bookings.payments import booking_amount

    group_confirmed = []
    for booking in Booking.objects.filter(
        event=event,
        status__in=[Booking.Status.CONFIRMED, Booking.Status.REFUNDED],
    ).prefetch_related('seats'):
        amount = booking.amount_paid if booking.amount_paid is not None else booking_amount(booking)
        gross += amount
        if booking.status == Booking.Status.REFUNDED:
            refunded += amount
        else:
            paid_count += 1
            group_confirmed.append((booking, amount, len(booking.seats.all())))
    return gross, refunded, paid_count, group_confirmed


def net_revenue(event) -> Decimal:
    gross, refunded, _, _ = _revenue(event)
    return gross - refunded


def event_analytics(event) -> dict:
    regs = list(_active_regs(event))

    confirmed = [r for r in regs if r.status == RegistrationStatusChoices.CONFIRMED]
    checked_in = [r for r in confirmed if r.is_checked_in]

    gross, refunded, paid_count, group_confirmed = _revenue(event)
    group_seats = sum(seats for _, _, seats in group_confirmed)
    group_checked_in = sum(1 for booking, _, _ in group_confirmed for bs in booking.seats.all() if bs.is_checked_in)

    net = gross - refunded

    tickets_sold = len(confirmed) + group_seats
    avg_order = (net / paid_count) if paid_count else Decimal('0')

    # ── Daily timeline: the last 30 business-time-zone days up to today ──
    # A sale older than the window is outside it (it is not piled onto the
    # first day); `organizer/sales/` shares the bucketing.
    tz = business_tz()
    end = local_today(tz=tz)
    start = end - timedelta(days=TIMELINE_DAYS - 1)
    by_day_count = defaultdict(int)
    by_day_revenue = defaultdict(Decimal)

    # A ticket counts on the day it was made; its money on the day the money
    # arrived (`Payment.paid_at`, `Booking.confirmed_at`), which can differ
    # (an offline payment is marked paid later).
    def in_window(moment):
        return start <= local_date(moment, tz) <= end

    for r in confirmed:
        if in_window(r.registered_at):
            by_day_count[local_date(r.registered_at, tz)] += 1
        pay = getattr(r, 'payment', None)
        if pay and pay.status in PAID_STATUSES:
            # `created_at` only for a paid row written by code that predates `paid_at`.
            paid_on = pay.paid_at or pay.created_at
            if in_window(paid_on):
                by_day_revenue[local_date(paid_on, tz)] += pay.net_amount

    for booking, amount, seats in group_confirmed:
        if in_window(booking.created_at):
            by_day_count[local_date(booking.created_at, tz)] += seats
        confirmed_on = booking.confirmed_at or booking.created_at
        if in_window(confirmed_on):
            by_day_revenue[local_date(confirmed_on, tz)] += amount

    timeline = [
        {
            'date': d.isoformat(),
            'tickets': by_day_count.get(d, 0),
            'revenue': float(by_day_revenue.get(d, Decimal('0'))),
        }
        for d in days_between(start, end)
    ]

    # ── Breakdown by ticket type ──
    # One row per tier (two tiers may share a name), plus "General" for
    # tickets without a tier and the group-booking pseudo row. `remaining`
    # is `TicketType.available`: the tier's quantity less its active
    # (not cancelled / rejected) registrations, never negative.
    active_per_type = Counter(r.ticket_type_id for r in regs if r.ticket_type_id)
    group_key = 'group'
    tier_name = {}
    tier_limits = {}  # key -> (quantity, remaining); null = unlimited
    tier_count = defaultdict(int)
    tier_revenue = defaultdict(Decimal)
    for r in confirmed:
        key = r.ticket_type_id
        if key is None:
            tier_name[key] = 'General'
            tier_limits[key] = (None, None)
        else:
            quantity = r.ticket_type.quantity
            tier_name[key] = r.ticket_type.name
            tier_limits[key] = (
                quantity,
                None if quantity is None else max(quantity - active_per_type[key], 0),
            )
        tier_count[key] += 1
        pay = getattr(r, 'payment', None)
        if pay:
            tier_revenue[key] += pay.net_amount
    if group_confirmed:
        tier_name[group_key] = 'Group booking'
        tier_limits[group_key] = (None, None)
        tier_count[group_key] += group_seats
        tier_revenue[group_key] += sum((amount for _, amount, _ in group_confirmed), Decimal('0'))
    by_ticket_type = [
        {
            'name': tier_name[k],
            'count': tier_count[k],
            'revenue': float(tier_revenue[k]),
            'quantity': tier_limits[k][0],
            'remaining': tier_limits[k][1],
        }
        for k in sorted(tier_count, key=lambda x: -tier_revenue[x])
    ]

    # ── Breakdown by promoter (affiliate) ──
    aff_count = defaultdict(int)
    aff_revenue = defaultdict(Decimal)
    for r in confirmed:
        if r.affiliate_id:
            aff_count[r.affiliate.name] += 1
            pay = getattr(r, 'payment', None)
            if pay:
                aff_revenue[r.affiliate.name] += pay.net_amount
    by_affiliate = [
        {'name': k, 'count': aff_count[k], 'revenue': float(aff_revenue[k])}
        for k in sorted(aff_count, key=lambda x: -aff_revenue[x])
    ]

    # ── Capacity & conversion ──
    capacity = event.max_participants or 0
    sold_through = round((tickets_sold / capacity) * 100, 1) if capacity else 0
    total_checked_in = len(checked_in) + group_checked_in
    checkin_rate = round((total_checked_in / tickets_sold) * 100, 1) if tickets_sold else 0

    return {
        'currency': event.currency or 'USD',
        'kpis': {
            'net_revenue': float(net),
            'gross_revenue': float(gross),
            'refunded': float(refunded),
            'tickets_sold': tickets_sold,
            'paid_orders': paid_count,
            'avg_order_value': float(avg_order),
            'capacity': capacity,
            'sold_through_pct': sold_through,
            'checked_in': total_checked_in,
            'checkin_rate_pct': checkin_rate,
            'pending': len([r for r in regs if r.status == RegistrationStatusChoices.PENDING]),
            'group_bookings': len(group_confirmed),
            'group_seats': group_seats,
        },
        'timeline': timeline,
        'by_ticket_type': by_ticket_type,
        'by_affiliate': by_affiliate,
    }
