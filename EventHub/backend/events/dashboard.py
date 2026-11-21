"""Server-side numbers of the organizer dashboard (docs/ORGANIZER_DASHBOARD.md).

Everything here works on *sets* of events with a fixed number of queries, so
the dashboard cost does not grow with the number of events. The metric
definitions are those of `events.analytics.event_analytics` (the per-event
analytics page); a test asserts both give the same numbers.
"""

import base64
import binascii
import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import (
    Case,
    Count,
    Exists,
    FloatField,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Cast, Coalesce, NullIf
from django.utils import timezone

from common.choices import EventStatusChoices, PaymentStatusChoices, RegistrationStatusChoices

from .billing import event_currency, quote_breakdown
from .models import Event, EventStaff, Registration

TAB_UPCOMING = 'upcoming'
TAB_PAST = 'past'
TAB_DRAFTS = 'drafts'
TAB_INACTIVE = 'inactive'
TABS = (TAB_UPCOMING, TAB_PAST, TAB_DRAFTS, TAB_INACTIVE)

ORDERINGS = ('date', '-date', '-tickets_sold', '-checkin_rate', '-sold_through')
DEFAULT_ORDERING = {
    TAB_UPCOMING: 'date',
    TAB_PAST: '-date',
    TAB_DRAFTS: '-date',
    TAB_INACTIVE: '-date',
}

SEARCH_MAX_LENGTH = 100
ACTIVITY_WINDOW = timedelta(days=30)
TWO_PLACES = Decimal('0.01')


# ── Who may use the dashboard, and which events it shows ──
def managed_events(user):
    """Events `user` organizes or co-organizes (same people as
    `common.permissions.can_manage_event`, minus the superuser shortcut: a
    superuser's own dashboard lists their own events, not the platform's)."""
    co_organized = EventStaff.objects.filter(event=OuterRef('pk'), user=user, role=EventStaff.ROLE_CO_ORGANIZER)
    return Event.objects.filter(Q(organizer=user) | Exists(co_organized))


def can_use_dashboard(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if getattr(getattr(user, 'profile', None), 'role', '') == 'organizer':
        return True
    return EventStaff.objects.filter(user=user, role=EventStaff.ROLE_CO_ORGANIZER).exists()


# ── Tabs ──
def _end():
    return Coalesce('end_date', 'date')


def with_end(queryset):
    return queryset.annotate(ds_end=_end())


def tab_filters(now):
    """Q objects over `ds_end` (see `with_end`); the four tabs partition every event."""
    S = EventStatusChoices
    return {
        TAB_UPCOMING: Q(status__in=[S.PUBLISHED, S.PENDING], ds_end__gte=now),
        TAB_PAST: Q(status=S.COMPLETED) | Q(status=S.PUBLISHED, ds_end__lt=now),
        TAB_DRAFTS: Q(status=S.DRAFT),
        TAB_INACTIVE: Q(status__in=[S.CANCELLED, S.REJECTED]) | Q(status=S.PENDING, ds_end__lt=now),
    }


# ── Ordering by the computed numbers (in SQL, so paging stays correct) ──
def _count_subquery(queryset, group_key, **extra_filter):
    return Coalesce(
        Subquery(
            queryset.filter(**extra_filter).order_by().values(group_key).annotate(c=Count('pk')).values('c'),
            output_field=IntegerField(),
        ),
        0,
    )


def with_sales_annotations(queryset):
    """Annotate `ds_sold` / `ds_checked_in` / `ds_checkin_rate` / `ds_sold_through`
    with the definitions of `bulk_event_stats`."""
    from bookings.models import Booking, BookingSeat

    confirmed = RegistrationStatusChoices.CONFIRMED
    seats = BookingSeat.objects.filter(booking__event=OuterRef('pk'), booking__status=Booking.Status.CONFIRMED)
    regs = Registration.objects.filter(event=OuterRef('pk'), status=confirmed)
    queryset = queryset.annotate(
        ds_sold=_count_subquery(regs, 'event') + _count_subquery(seats, 'booking__event'),
        ds_checked_in=(
            _count_subquery(regs, 'event', is_checked_in=True)
            + _count_subquery(seats, 'booking__event', is_checked_in=True)
        ),
    )
    as_float = FloatField()
    return queryset.annotate(
        ds_checkin_rate=Coalesce(
            Cast('ds_checked_in', as_float) / NullIf(Cast('ds_sold', as_float), Value(0.0)),
            Value(0.0),
            output_field=as_float,
        ),
        ds_sold_through=Case(
            When(
                max_participants__gt=0,
                then=Cast('ds_sold', as_float) / Cast('max_participants', as_float),
            ),
            default=Value(0.0),
            output_field=as_float,
        ),
    )


_ORDER_BY = {
    'date': ('date', 'id'),
    '-date': ('-date', '-id'),
    '-tickets_sold': ('-ds_sold', '-date', '-id'),
    '-checkin_rate': ('-ds_checkin_rate', '-ds_sold', '-date', '-id'),
    '-sold_through': ('-ds_sold_through', '-ds_sold', '-date', '-id'),
}


def order_events(queryset, ordering):
    return queryset.order_by(*_ORDER_BY[ordering])


# ── Metrics for many events at once ──
def _pct(part, whole):
    return float(round((part / whole) * 100, 1)) if whole else 0.0


def bulk_event_stats(events) -> dict[int, dict]:
    """The `kpis` of `event_analytics` for every event in `events`, as
    {event_id: stats}. Five queries however many events there are.

    `events` need `currency`, `max_participants`, `tax_percent`,
    `service_fee_percent` and `fees_passed_to_buyer` loaded.
    """
    from bookings.models import Booking, BookingSeat
    from payments.models import Payment

    events = list(events)
    ids = [e.pk for e in events]
    confirmed = RegistrationStatusChoices.CONFIRMED

    regs = {
        row['event_id']: row
        for row in Registration.objects.filter(event_id__in=ids)
        .order_by()
        .values('event_id')
        .annotate(
            confirmed=Count('pk', filter=Q(status=confirmed)),
            checked_in=Count('pk', filter=Q(status=confirmed, is_checked_in=True)),
            pending=Count('pk', filter=Q(status=RegistrationStatusChoices.PENDING)),
        )
    }
    seats = {
        row['booking__event_id']: row
        for row in BookingSeat.objects.filter(booking__event_id__in=ids, booking__status=Booking.Status.CONFIRMED)
        .order_by()
        .values('booking__event_id')
        .annotate(sold=Count('pk'), checked_in=Count('pk', filter=Q(is_checked_in=True)))
    }

    # Money: ticket payments (any registration status: a full refund cancels
    # the ticket) net of refunds, plus confirmed group bookings. A refunded
    # booking adds its amount to both gross and refunded, i.e. nothing.
    net = defaultdict(Decimal)
    for row in (
        Payment.objects.filter(
            registration__event_id__in=ids,
            status__in=[PaymentStatusChoices.COMPLETED, PaymentStatusChoices.REFUNDED],
        )
        .order_by()
        .values('registration__event_id')
        .annotate(gross=Sum('amount'), refunded=Sum('refunded_amount'))
    ):
        net[row['registration__event_id']] += row['gross'] - row['refunded']
    for row in (
        Booking.objects.filter(event_id__in=ids, status=Booking.Status.CONFIRMED, amount_paid__isnull=False)
        .order_by()
        .values('event_id')
        .annotate(total=Sum('amount_paid'))
    ):
        net[row['event_id']] += row['total']
    # Bookings that never recorded `amount_paid` are priced from their seats,
    # like `bookings.payments.booking_amount`.
    by_id = {e.pk: e for e in events}
    for event_id, price in BookingSeat.objects.filter(
        booking__event_id__in=ids,
        booking__status=Booking.Status.CONFIRMED,
        booking__amount_paid__isnull=True,
    ).values_list('booking__event_id', 'price'):
        net[event_id] += Decimal(quote_breakdown(by_id[event_id], price)['total'])

    stats = {}
    for event in events:
        reg = regs.get(event.pk, {})
        seat = seats.get(event.pk, {})
        sold = reg.get('confirmed', 0) + seat.get('sold', 0)
        checked_in = reg.get('checked_in', 0) + seat.get('checked_in', 0)
        capacity = event.max_participants or 0
        stats[event.pk] = {
            'tickets_sold': sold,
            'checked_in': checked_in,
            'checkin_rate_pct': _pct(checked_in, sold),
            'capacity': capacity,
            'sold_through_pct': _pct(sold, capacity),
            'pending': reg.get('pending', 0),
            'net_revenue': str(net.get(event.pk, Decimal('0')).quantize(TWO_PLACES)),
            'currency': event_currency(event),
        }
    return stats


# ── Totals over every managed event ──
def dashboard_summary(user, now=None) -> dict:
    from bookings.models import Booking, BookingSeat

    now = now or timezone.now()
    events = with_end(managed_events(user))
    filters = tab_filters(now)
    S = EventStatusChoices

    counted = events.aggregate(
        pending_approval=Count('pk', filter=Q(status=S.PENDING, ds_end__gte=now)),
        upcoming_next_7_days=Count(
            'pk',
            filter=filters[TAB_UPCOMING] & Q(date__gte=now, date__lt=now + timedelta(days=7)),
        ),
        **{tab: Count('pk', filter=q) for tab, q in filters.items()},
    )

    light = events.only(
        'id', 'currency', 'max_participants', 'tax_percent', 'service_fee_percent', 'fees_passed_to_buyer'
    )
    light = list(light)
    stats = bulk_event_stats(light)
    sold = checked_in = 0
    revenue = defaultdict(Decimal)
    for event in light:
        s = stats[event.pk]
        sold += s['tickets_sold']
        checked_in += s['checked_in']
        revenue[event_currency(event)] += Decimal(s['net_revenue'])

    # Sales velocity: tickets confirmed in the last 7 days vs the 7 before.
    week_ago, two_weeks_ago = now - timedelta(days=7), now - timedelta(days=14)
    managed_ids = managed_events(user).values('pk')
    reg_windows = Registration.objects.filter(
        event_id__in=managed_ids, status=RegistrationStatusChoices.CONFIRMED
    ).aggregate(
        last=Count('pk', filter=Q(registered_at__gte=week_ago, registered_at__lt=now)),
        previous=Count('pk', filter=Q(registered_at__gte=two_weeks_ago, registered_at__lt=week_ago)),
    )
    seat_windows = BookingSeat.objects.filter(
        booking__event_id__in=managed_ids, booking__status=Booking.Status.CONFIRMED
    ).aggregate(
        last=Count('pk', filter=Q(booking__created_at__gte=week_ago, booking__created_at__lt=now)),
        previous=Count('pk', filter=Q(booking__created_at__gte=two_weeks_ago, booking__created_at__lt=week_ago)),
    )

    return {
        'tabs': {tab: counted[tab] for tab in TABS},
        'pending_approval': counted['pending_approval'],
        'upcoming_next_7_days': counted['upcoming_next_7_days'],
        'tickets_sold': sold,
        'checked_in': checked_in,
        'checkin_rate_pct': _pct(checked_in, sold),
        'revenue': [
            {'currency': currency, 'net_revenue': str(amount.quantize(TWO_PLACES))}
            for currency, amount in sorted(revenue.items())
            if amount != 0
        ],
        'sales_last_7_days': reg_windows['last'] + seat_windows['last'],
        'sales_previous_7_days': reg_windows['previous'] + seat_windows['previous'],
    }


# ── Activity feed ──
def display_name(first_name, last_name, username) -> str:
    """The attendee list's rule (first + last name, else the username) with one
    addition: a username that looks like an email address is cut at the `@`,
    so the feed never shows an address."""
    name = f'{first_name or ""} {last_name or ""}'.strip() or username or ''
    return name.split('@', 1)[0] if '@' in name else name


def _name(row, prefix):
    return display_name(row[f'{prefix}first_name'], row[f'{prefix}last_name'], row[f'{prefix}username'])


# Fixed rank of each source: items with the same timestamp sort by it, then by pk.
RANK_REGISTRATION = 1
RANK_GROUP_BOOKING = 2
RANK_REGISTRATION_CHECK_IN = 3
RANK_SEAT_CHECK_IN = 4
RANK_REFUND = 5
_UUID_RANKS = (RANK_GROUP_BOOKING, RANK_REFUND)


def encode_cursor(occurred_at, rank, pk) -> str:
    payload = json.dumps({'t': occurred_at.isoformat(), 'r': rank, 'k': str(pk)}, separators=(',', ':'))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip('=')


def decode_cursor(value: str):
    """(occurred_at, rank, pk) of a cursor made by `encode_cursor`; ValueError
    when it is malformed or was tampered with."""
    try:
        raw = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
        data = json.loads(raw)
        occurred_at = datetime.fromisoformat(data['t'])
        rank = data['r']
        if occurred_at.tzinfo is None or type(rank) is not int or not RANK_REGISTRATION <= rank <= RANK_REFUND:
            raise ValueError
        key = data['k']
        pk = uuid.UUID(key) if rank in _UUID_RANKS else int(key)
    except (ValueError, TypeError, KeyError, binascii.Error, UnicodeDecodeError, AttributeError):
        raise ValueError('Invalid cursor.') from None
    return occurred_at, rank, pk


def activity_feed(user, *, limit: int, cursor=None, now=None) -> dict:
    """Recent activity, newest first, in the total order (time, rank, pk)
    descending. `cursor` is a decoded (time, rank, pk) of the last item of the
    previous page; paging never skips or repeats an item, even when many items
    share one timestamp (a group check-in stamps every seat at once)."""
    from bookings.models import Booking, BookingSeat
    from payments.models import Refund

    now = now or timezone.now()
    since = now - ACTIVITY_WINDOW
    managed = managed_events(user).values('pk')
    # One extra row per source tells whether anything older exists.
    take = limit + 1

    def window(field, rank):
        """Rows of one source that come after the cursor in the global order."""
        q = Q(**{f'{field}__gte': since, f'{field}__lt': now})
        if cursor is None:
            return q
        t, r, k = cursor
        if rank < r:
            return q & Q(**{f'{field}__lte': t})
        if rank > r:
            return q & Q(**{f'{field}__lt': t})
        return q & (Q(**{f'{field}__lt': t}) | Q(**{field: t, 'pk__lt': k}))

    user_fields = ('user__first_name', 'user__last_name', 'user__username')
    owner_fields = ('owner__first_name', 'owner__last_name', 'owner__username')
    entries = []  # (occurred_at, rank, pk, item)

    def add(rank, pk, item):
        entries.append((item['occurred_at'], rank, pk, item))

    for row in (
        Registration.objects.filter(window('registered_at', RANK_REGISTRATION), event_id__in=managed)
        .filter(status=RegistrationStatusChoices.CONFIRMED)
        .order_by('-registered_at', '-pk')
        .values('pk', 'registered_at', 'event_id', *user_fields)[:take]
    ):
        add(
            RANK_REGISTRATION,
            row['pk'],
            _item(
                f'registration:{row["pk"]}', 'registration', row['registered_at'], row['event_id'], _name(row, 'user__')
            ),
        )

    for row in (
        Booking.objects.filter(window('created_at', RANK_GROUP_BOOKING), event_id__in=managed)
        .filter(status=Booking.Status.CONFIRMED)
        .annotate(seat_total=Count('seats'))
        .order_by('-created_at', '-pk')
        .values('pk', 'created_at', 'event_id', 'seat_total', *owner_fields)[:take]
    ):
        add(
            RANK_GROUP_BOOKING,
            row['pk'],
            _item(
                f'group_booking:{row["pk"]}',
                'group_booking',
                row['created_at'],
                row['event_id'],
                _name(row, 'owner__'),
                quantity=row['seat_total'],
            ),
        )

    for row in (
        Registration.objects.filter(window('checked_in_at', RANK_REGISTRATION_CHECK_IN), event_id__in=managed)
        .filter(status=RegistrationStatusChoices.CONFIRMED, is_checked_in=True)
        .order_by('-checked_in_at', '-pk')
        .values('pk', 'checked_in_at', 'event_id', *user_fields)[:take]
    ):
        add(
            RANK_REGISTRATION_CHECK_IN,
            row['pk'],
            _item(
                f'check_in:registration:{row["pk"]}',
                'check_in',
                row['checked_in_at'],
                row['event_id'],
                _name(row, 'user__'),
            ),
        )

    claimed_fields = ('claimed_by__first_name', 'claimed_by__last_name', 'claimed_by__username')
    for row in (
        BookingSeat.objects.filter(window('checked_in_at', RANK_SEAT_CHECK_IN), booking__event_id__in=managed)
        .filter(booking__status=Booking.Status.CONFIRMED, is_checked_in=True)
        .order_by('-checked_in_at', '-pk')
        .values(
            'pk',
            'checked_in_at',
            'attendee_name',
            'booking__event_id',
            *claimed_fields,
            *(f'booking__{f}' for f in owner_fields),
        )[:take]
    ):
        name = (
            row['attendee_name'].strip()
            or display_name(row['claimed_by__first_name'], row['claimed_by__last_name'], row['claimed_by__username'])
            or display_name(
                row['booking__owner__first_name'], row['booking__owner__last_name'], row['booking__owner__username']
            )
        )
        add(
            RANK_SEAT_CHECK_IN,
            row['pk'],
            _item(
                f'check_in:booking_seat:{row["pk"]}',
                'check_in',
                row['checked_in_at'],
                row['booking__event_id'],
                display_name(name, '', ''),
            ),
        )

    refund_event = Coalesce('payment__registration__event_id', 'payment__booking__event_id')
    reg_user, booking_owner = 'payment__registration__user__', 'payment__booking__owner__'
    for row in (
        Refund.objects.filter(window('processed_at', RANK_REFUND))
        .filter(status=Refund.Status.SUCCEEDED, payment__isnull=False)
        .annotate(ds_event=refund_event)
        .filter(ds_event__in=managed)
        .order_by('-processed_at', '-pk')
        .values(
            'pk',
            'processed_at',
            'amount',
            'currency',
            'ds_event',
            *(f'{reg_user}{f}' for f in ('first_name', 'last_name', 'username')),
            *(f'{booking_owner}{f}' for f in ('first_name', 'last_name', 'username')),
        )[:take]
    ):
        name = _name(row, reg_user) if row[f'{reg_user}username'] else _name(row, booking_owner)
        add(
            RANK_REFUND,
            row['pk'],
            _item(
                f'refund:{row["pk"]}',
                'refund',
                row['processed_at'],
                row['ds_event'],
                name,
                amount=str(row['amount'].quantize(TWO_PLACES)),
                currency=(row['currency'] or '').upper(),
            ),
        )

    # Ranks differ between sources, so pks of different types never meet in a comparison.
    entries.sort(key=lambda e: (e[0], e[1], e[2]), reverse=True)
    has_more = len(entries) > limit
    entries = entries[:limit]
    items = [e[3] for e in entries]

    titles = dict(Event.objects.filter(pk__in={i['event_id'] for i in items}).values_list('pk', 'title'))
    for item in items:
        item['event_title'] = titles.get(item['event_id'], '')
    next_cursor = encode_cursor(*entries[-1][:3]) if has_more and entries else None
    return {'results': items, 'next_cursor': next_cursor}


def _item(item_id, kind, occurred_at, event_id, attendee_name, *, quantity=1, amount=None, currency=None) -> dict:
    return {
        'id': item_id,
        'type': kind,
        'occurred_at': occurred_at,
        'event_id': event_id,
        'event_title': '',
        'attendee_name': attendee_name,
        'quantity': quantity,
        'amount': amount,
        'currency': currency,
    }
