"""Sales analytics for an organizer's event.

Aggregates confirmed registrations and completed payments into the numbers a
dashboard needs: headline KPIs, a daily sales timeline, and breakdowns by
ticket tier and promoter. All money comes from the Payment rows so refunds are
reflected (net of refunds) automatically.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from common.choices import RegistrationStatusChoices, PaymentStatusChoices


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
        event=event, status__in=[Booking.Status.CONFIRMED, Booking.Status.REFUNDED],
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
    group_checked_in = sum(
        1 for booking, _, _ in group_confirmed for bs in booking.seats.all() if bs.is_checked_in
    )

    net = gross - refunded

    tickets_sold = len(confirmed) + group_seats
    avg_order = (net / paid_count) if paid_count else Decimal('0')

    # ── Daily timeline (last 30 days up to event or today) ──
    today = timezone.now().date()
    start = today - timedelta(days=29)
    by_day_count = defaultdict(int)
    by_day_revenue = defaultdict(Decimal)
    for r in confirmed:
        d = r.registered_at.date()
        if d < start:
            d = start
        by_day_count[d] += 1
        pay = getattr(r, 'payment', None)
        if pay:
            by_day_revenue[d] += pay.net_amount

    for booking, amount, seats in group_confirmed:
        d = max(booking.created_at.date(), start)
        by_day_count[d] += seats
        by_day_revenue[d] += amount

    timeline = []
    for i in range(30):
        d = start + timedelta(days=i)
        timeline.append({
            'date': d.isoformat(),
            'tickets': by_day_count.get(d, 0),
            'revenue': float(by_day_revenue.get(d, Decimal('0'))),
        })

    # ── Breakdown by ticket type ──
    tier_count = defaultdict(int)
    tier_revenue = defaultdict(Decimal)
    for r in confirmed:
        name = r.ticket_type.name if r.ticket_type_id else 'General'
        tier_count[name] += 1
        pay = getattr(r, 'payment', None)
        if pay:
            tier_revenue[name] += pay.net_amount
    if group_confirmed:
        tier_count['Group booking'] += group_seats
        tier_revenue['Group booking'] += sum((amount for _, amount, _ in group_confirmed), Decimal('0'))
    by_ticket_type = [
        {'name': k, 'count': tier_count[k], 'revenue': float(tier_revenue[k])}
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
