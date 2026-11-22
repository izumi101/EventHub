"""Realistic Kazakhstan demo data: 60 events in KZT, ~760 attendees, a year of sales.

    python manage.py seed_demo_kz                                    # DJANGO_DEBUG=1: password "password123"
    python manage.py seed_demo_kz --i-know-this-is-a-demo \\
        --credentials-file /tmp/demo-credentials.txt [--organizer USERNAME]   # DJANGO_DEBUG=0
    python manage.py seed_demo_kz --i-know-this-is-a-demo --remove [--dry-run] [--organizer USERNAME]

Contract: docs/DEMO_DATA.md. Creates demo organizers (`kz_*`), check-in staff and
attendees, and 60 events (concerts, conferences, meetups, races, theatre,
children's, exhibitions, online; seat maps, ticket tiers with early-bird
windows, general admission, free and donation events; published, completed,
cancelled, draft, pending and rejected), and their sales: registrations in
every status, payments (completed, pending, failed, expired, refunded,
partially refunded, disputed) with their Refund ledger rows, refund requests
(open, approved, rejected), group bookings, check-ins with gate logs, reviews,
waitlists, promo codes and affiliates.

Accounts. DJANGO_DEBUG=1 keeps the documented password `password123`. With
DJANGO_DEBUG=0 the command needs `--i-know-this-is-a-demo` and a new
`--credentials-file`: every created account gets its own random password,
written only to that file (mode 0600, never overwritten). Nothing secret goes
to stdout or stderr. The accounts' addresses end in `@demo.eventhub.local`.

`--organizer USERNAME` (an existing organizer account): about a third of the
events (20 of 60) are created for that user, who also becomes a co-organizer of
two demo organizers' events. That user never holds a ticket, scans or reviews.

Deterministic: every event draws from its own random generator seeded with a
fixed seed and the event key, and UUIDs come from the same generator.
Idempotent: users, categories and events are looked up by natural key (user
name, category name, event title); an event that already exists is left alone,
so a second run creates nothing. Rows are bulk-inserted: no signal, no
notification and no job is created. Prices, seat zones, tax and fees go
through the real pricing code (events.billing, events.seat_pricing,
bookings.payments) so the stored amounts equal what the app would charge.
"""

import bisect
import heapq
import io
import os
import random
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import UserProfile
from bookings.models import Booking, BookingSeat
from bookings.payments import seat_total
from common import demo_seed
from common.choices import RoleChoices
from events import demo_kz_remove
from events.billing import registration_amount
from events.demo_kz_data import (
    CATEGORIES,
    CITIES,
    EVENTS,
    FEMALE_FIRST,
    HOUR_WEIGHTS,
    KZ_TZ,
    MALE_FIRST,
    ORGANIZERS,
    PHONE_PREFIXES,
    REVIEW_COMMENTS,
    REVIEW_RATING_WEIGHTS,
    SEED,
    STAFF,
    SURNAMES,
    USERNAME_PREFIX,
)
from events.models import (
    Affiliate,
    Category,
    CheckInList,
    CheckInLog,
    Event,
    EventSeat,
    EventStaff,
    PromoCode,
    RefundRequest,
    Registration,
    Review,
    SeatMap,
    TicketType,
    WaitlistEntry,
)
from events.seat_pricing import seat_price
from payments.models import Payment, Refund
from payments.state import PAID_STATUSES, mark_paid

DEMO_PASSWORD = demo_seed.DEV_PASSWORD
EMAIL_DOMAIN = demo_seed.DEMO_EMAIL_DOMAIN
HOLD_MINUTES = 10
CENT = Decimal('0.01')

# Days before the start that the sale opens, by layout (about +-20%).
LEAD_DAYS = {'seated': 55, 'chamber': 40, 'tiers': 60, 'ga': 35, 'free': 18}
ONLINE_LEAD_DAYS = 21
PLATFORM_AGE_DAYS = 420  # nothing was sold before this long ago
ATTENDEE_JOINED_DAYS = 425  # sign-ups over about 14 months
PENDING_HOLD_BUDGET = 12  # live holds on upcoming events, in total
DISPUTE_BUDGET = 8  # disputed payments, in total
SELL_THROUGH_SCALE = 0.8  # of the `fill` of an event that is not sold out
MAX_BUYER_SHARE = 0.35  # of all attendees go to any one event (unless it is a small sold-out one)
LOCAL_AFFINITY = 4.0  # an attendee is this much likelier to go to an event in their own city
INSUFFICIENT_FUNDS_SHARE = 0.35  # of the failed payments (the rest: card_declined)
FAILURES = ('card_declined', 'insufficient_funds')


def _q(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _bulk_create_keeping(model, objs, *fields):
    """bulk_create, then restore `fields` (auto_now / auto_now_add timestamps
    that bulk_create overwrites with now) to the values the objects were built with."""
    wanted = [[getattr(obj, field) for field in fields] for obj in objs]
    model.objects.bulk_create(objs, batch_size=500)
    for obj, values in zip(objs, wanted, strict=True):
        for field, value in zip(fields, values, strict=True):
            setattr(obj, field, value)
    model.objects.bulk_update(objs, list(fields), batch_size=500)


class EventSeeder:
    """Builds one event's sales with its own deterministic random generator."""

    def __init__(self, command, event, spec, attendees, organizer):
        self.cmd = command
        self.event = event
        self.spec = spec
        self.attendees = attendees
        self.organizer = organizer
        self.rng = random.Random(f'{SEED}:{spec["key"]}')  # noqa: S311 - demo data, not security
        self.now = command.now
        self.start = event.date
        self.end = event.end_date or event.date
        self.started = self.start <= self.now
        self.ended = self.end < self.now
        self.cancelled_event = event.status == 'cancelled'
        self.registrations = []  # (Registration, plan dict)
        self.payments = []
        self.refunds = []
        self.refund_requests = []
        self.taken_users = set()
        self.seats = []
        self.tiers = []
        self.remaining = {}

    def uuid(self):
        return uuid.UUID(int=self.rng.getrandbits(128), version=4)

    # ----------------------------------------------------------- times ---- #

    def set_timing(self):
        """When the sale opened (`sale_open`) and when it stops (`sale_close`)."""
        spec, rng = self.spec, self.rng
        lead = spec.get('lead') or LEAD_DAYS[spec['layout']]
        if spec.get('online'):
            lead = ONLINE_LEAD_DAYS
        lead *= rng.uniform(0.8, 1.2)
        opened = self.start - timedelta(days=lead)
        if not self.started:
            # A far-away event only just went on sale.
            opened = min(opened, self.now - timedelta(days=rng.uniform(3, 12)))
        opened = max(opened, self.now - timedelta(days=PLATFORM_AGE_DAYS))
        close = min(self.now - timedelta(minutes=10), self.start - timedelta(minutes=5))
        self.cancelled_at = None
        if self.cancelled_event:
            self.cancelled_at = self.now - timedelta(days=spec.get('cancelled_days_ago', 3), hours=rng.randint(0, 8))
            close = min(close, self.cancelled_at - timedelta(minutes=5))
        if close <= opened + timedelta(hours=1):
            opened = close - timedelta(days=2)
        self.sale_open, self.sale_close = opened, close

    def created_at(self):
        """When the organizer created the event: before it went on sale."""
        if self.spec.get('fill', 0) and self.event.status in ('published', 'completed', 'cancelled'):
            return self.sale_open - timedelta(days=self.rng.uniform(1, 5), hours=self.rng.randint(0, 20))
        return self.now - timedelta(days=self.rng.uniform(2, 25), hours=self.rng.randint(0, 20))

    def sale_time(self):
        """When a ticket was bought: an early-bird burst after the sale opens, a
        quiet middle, a rise in the last week, a few on the day; mostly in the
        evening and at lunch, rarely at night; never in the future."""
        rng, opened, close, start = self.rng, self.sale_open, self.sale_close, self.start
        total = max((start - opened).total_seconds(), 3600.0)
        moment = None
        for _ in range(30):
            roll = rng.random()
            if roll < 0.28:  # early-bird burst
                moment = opened + timedelta(seconds=rng.expovariate(1 / max(min(5 * 86400, total * 0.08), 3600)))
            elif roll < 0.55:  # quiet middle
                moment = opened + timedelta(seconds=rng.uniform(total * 0.05, total * 0.85))
            elif roll < 0.93:  # the last week: more and more towards the start
                moment = start - timedelta(days=7 * rng.random() ** 1.6)
            else:  # on the day
                moment = start - timedelta(hours=min(rng.expovariate(1 / 4.0), 12))
            if opened <= moment <= close:
                break
        else:
            moment = opened + timedelta(seconds=rng.uniform(0, (close - opened).total_seconds()))
        return self._at_a_busy_hour(moment)

    def _at_a_busy_hour(self, moment):
        rng = self.rng
        local = moment.astimezone(KZ_TZ)
        hour = rng.choices(range(24), weights=HOUR_WEIGHTS)[0]
        shifted = datetime(
            local.year, local.month, local.day, hour, rng.randint(0, 59), rng.randint(0, 59), tzinfo=KZ_TZ
        ).astimezone(UTC)
        if shifted > self.sale_close:
            shifted -= timedelta(days=1)
        return shifted if shifted >= self.sale_open else moment

    def after(self, start, min_gap, max_gap, cap):
        """A random moment in [start + min_gap, min(start + max_gap, cap)], or None."""
        low, high = start + min_gap, min(start + max_gap, cap)
        if high < low:
            return None
        return low + timedelta(seconds=self.rng.uniform(0, (high - low).total_seconds()))

    # -------------------------------------------------------- inventory ---- #

    def build_inventory(self):
        """Seats and ticket tiers; sets the event's capacity."""
        layout, event, spec = self.spec['layout'], self.event, self.spec
        if layout == 'seated':
            self.seats = self.cmd.create_seat_map(
                event, spec['rows'], spec['cols'], spec.get('vip_rows', 0), spec.get('premium_rows', 0)
            )
        elif layout == 'chamber':
            # The stock generator (6 x 7, VIP rows 1-2) used by operators.
            call_command('generate_seat_maps', event_ids=[event.id], stdout=io.StringIO())
            self.seats = list(EventSeat.objects.filter(seat_map__event=event).select_related('seat_map'))
            event.max_participants = len(self.seats)
            event.save(update_fields=['max_participants'])
        elif layout == 'tiers':
            for order, t in enumerate(spec['tiers']):
                sale_end = None
                if t['sale_end_days'] is not None:
                    sale_end = event.date - timedelta(days=t['sale_end_days'])
                self.tiers.append(
                    TicketType.objects.create(
                        event=event,
                        name=t['name'],
                        description=t['description'],
                        kind=t['kind'],
                        price=t['price'],
                        quantity=t['quantity'],
                        sale_end=sale_end,
                        order=order,
                        max_per_order=4,
                    )
                )
            event.max_participants = sum(t.quantity for t in self.tiers)
            event.save(update_fields=['max_participants'])
            self.remaining = {t.id: t.quantity for t in self.tiers}
        self.rng.shuffle(self.seats)

    # --------------------------------------------------------------- run ---- #

    def run(self):
        self.set_timing()
        self.build_inventory()
        Event.objects.filter(pk=self.event.pk).update(created_at=self.created_at())
        self.promo = self.create_promo()
        self.affiliate = self.create_affiliate()
        fill = self.spec.get('fill', 0)
        if not fill or self.event.status not in ('published', 'completed', 'cancelled'):
            return
        waitlist = self.spec.get('waitlist', {})
        capacity = self.event.max_participants
        buyers_at_most = int(len(self.attendees) * MAX_BUYER_SHARE)
        if fill < 1:  # a sold-out event stays sold out; the others sell a bit less than their spec
            fill *= SELL_THROUGH_SCALE
        else:
            buyers_at_most = capacity
        target = min(round(capacity * fill), capacity, buyers_at_most)
        target -= waitlist.get('offered', 0)

        booked_seats = self.plan_bookings() if self.spec.get('bookings') else 0
        live = max(target - booked_seats, 0)
        kinds = ['live'] * live
        # History rows: tickets that were cancelled; they hold no capacity.
        if self.is_free_event():
            kinds += ['cancelled_free'] * int(live * 0.04)
        elif not self.cancelled_event:
            kinds += ['expired'] * int(live * 0.05) + ['failed'] * int(live * 0.035)
            if self.event.refundable:
                kinds += ['refunded'] * int(live * 0.04)
        kinds = kinds[: len(self.attendees)]
        self.rng.shuffle(kinds)
        times = sorted(self.sale_time() for _ in kinds)
        for kind, moment, user in zip(kinds, times, self.assign_users(times), strict=True):
            if user is None:
                continue
            slot = self.allocate(kind, moment)
            if slot is not None:
                self.add_ticket(kind, user, moment, slot)
        self.add_pending_holds()
        self.save_all()
        if waitlist:
            self.create_waitlist(waitlist)
        if self.ended:
            self.create_reviews()

    def is_free_event(self):
        return self.spec['layout'] == 'free'

    def assign_users(self, times):
        """A distinct attendee for each moment (ascending): one who had signed up
        by then; the more active ones (heavier weight) are likelier to be drawn."""
        pool, heap, ptr, out = self.cmd.pool, [], 0, []
        for moment in times:
            while ptr < len(pool) and pool[ptr][0] <= moment:
                _, user, weight, city = pool[ptr]
                if user.id not in self.taken_users:
                    if city == self.spec['city']:
                        weight *= LOCAL_AFFINITY  # people mostly go to events in their own city
                    heapq.heappush(heap, (-(self.rng.random() ** (1.0 / weight)), ptr))
                ptr += 1
            out.append(pool[heapq.heappop(heap)[1]][1] if heap else None)
        return out

    def pick_user(self, moment):
        """Any attendee who had signed up by `moment` and holds no ticket here."""
        pool = self.cmd.pool
        eligible = bisect.bisect_right(self.cmd.pool_joined, moment)
        for _ in range(40):
            if not eligible:
                return None
            user = pool[self.rng.randrange(eligible)][1]
            if user.id not in self.taken_users:
                return user
        return None

    def tier_is_open(self, tier_obj, moment):
        return tier_obj.sale_end is None or moment <= tier_obj.sale_end

    def allocate(self, kind, moment):
        """A seat or a tier for one ticket (or {} for general admission / free);
        None when there is nothing left to give."""
        live = kind in ('live', 'pending')
        if self.spec['layout'] in ('seated', 'chamber'):
            if not live:
                return {'seat_zone_from': self.rng.choice(self.all_seats)}
            return {'seat': self.seats.pop()} if self.seats else None
        if self.tiers:
            choices = [t for t in self.tiers if self.tier_is_open(t, moment)]
            if live:
                choices = [t for t in choices if self.remaining[t.id] > 0]
            if not choices:
                return None
            # An open early-bird tier is the popular one.
            weights = [(self.remaining[t.id] if live else t.quantity) * (3 if t.sale_end else 1) for t in choices]
            chosen = self.rng.choices(choices, weights=weights)[0]
            if live:
                self.remaining[chosen.id] -= 1
            return {'tier': chosen}
        return {}

    # ------------------------------------------------------ registrations ---- #

    def new_registration(self, user, slot, status, moment):
        tier_obj = slot.get('tier')
        reg = Registration(
            user=user,
            event=self.event,
            status=status,
            ticket_uuid=self.uuid(),
            ticket_type=tier_obj,
            seat=slot.get('seat'),
        )
        if tier_obj is not None and tier_obj.kind == TicketType.KIND_DONATION:
            reg.donation_amount = Decimal(self.rng.choice(['2000', '3000', '5000', '5000', '10000', '20000']))
        reg.locked_price = self.quoted_price(reg, slot)
        reg.registered_at = moment
        return reg

    def quoted_price(self, reg, slot):
        """Same rules as register_for_event._quoted_base_price (no dynamic pricing)."""
        if self.is_free_event():
            return None
        if reg.ticket_type is not None:
            if reg.ticket_type.kind == TicketType.KIND_FREE:
                return None
            return _q(reg.donation_amount if reg.donation_amount is not None else reg.ticket_type.price)
        seat = slot.get('seat') or slot.get('seat_zone_from')
        if seat is not None:
            return _q(seat_price(self.event, seat))
        return _q(self.event.price)

    def maybe_promo(self, reg, live):
        promo = self.promo
        if promo is None or reg.locked_price is None or self.rng.random() > 0.15:
            return
        if live and promo.max_uses is not None and promo.times_used >= promo.max_uses:
            return
        reg.promo_code = promo
        if live:
            promo.times_used += 1  # reserved by a live ticket (released ones give it back)

    def add_ticket(self, kind, user, moment, slot):
        if kind == 'live':
            self.add_live(user, moment, slot)
        elif kind == 'cancelled_free':
            reg = self.new_registration(user, slot, 'cancelled', moment)
            self.registrations.append((reg, {'kind': 'free'}))
        else:
            self.add_history(user, moment, slot, kind)
        self.taken_users.add(user.id)

    def add_live(self, user, moment, slot):
        reg = self.new_registration(user, slot, 'confirmed', moment)
        self.maybe_promo(reg, live=True)
        if self.affiliate is not None and self.rng.random() < 0.08:
            reg.affiliate = self.affiliate
        paid = reg.locked_price is not None
        paid_at = moment + timedelta(minutes=2, seconds=self.rng.randint(0, 119))
        plan = {'kind': 'confirmed', 'paid_at': paid_at}
        if self.cancelled_event:
            # Event called off: every ticket was voided; the money went back.
            reg.status = 'cancelled'
            if paid:
                at = min(
                    self.cancelled_at + timedelta(minutes=self.rng.randint(2, 90)), self.now - timedelta(minutes=1)
                )
                plan = {
                    'kind': 'refunded',
                    'paid_at': paid_at,
                    'refund': {'at': at, 'kind': Refund.Kind.EVENT_CANCELLED},
                }
            else:
                plan = {'kind': 'free'}
            if reg.promo_code is not None:
                self.promo.times_used -= 1
        elif paid:
            plan = self.paid_plan(paid_at)
        if reg.status != 'cancelled' and reg.seat is not None:
            reg.seat.is_available = False
        if reg.status == 'cancelled':
            reg.seat = None
        self.maybe_check_in(reg, plan, paid)
        self.registrations.append((reg, plan))

    def paid_plan(self, paid_at):
        """What happens to a confirmed, paid ticket after it was bought."""
        rng, now, refundable = self.rng, self.now, self.event.refundable
        roll = rng.random()
        plan = {'kind': 'confirmed', 'paid_at': paid_at}
        if refundable and not self.started and roll < 0.007:  # an open request
            created = self.after(paid_at, timedelta(hours=2), timedelta(days=6), now - timedelta(minutes=20))
            if created:
                plan['request'] = {'status': RefundRequest.STATUS_PENDING, 'created': created}
        elif refundable and 0.015 <= roll < 0.023:  # a request the organizer refused
            created = self.after(
                paid_at,
                timedelta(hours=2),
                timedelta(days=5),
                min(now - timedelta(hours=3), self.start - timedelta(hours=6)),
            )
            resolved = created and self.after(
                created, timedelta(hours=1), timedelta(hours=40), now - timedelta(minutes=30)
            )
            if resolved:
                plan['request'] = {'status': RefundRequest.STATUS_REJECTED, 'created': created, 'resolved': resolved}
        elif 0.027 <= roll < 0.052:  # the organizer refunded part of it
            at = self.after(paid_at, timedelta(days=1), timedelta(days=6), min(now - timedelta(hours=1), self.start))
            if at:
                plan = {
                    'kind': 'partial',
                    'paid_at': paid_at,
                    'refund': {
                        'at': at,
                        'kind': Refund.Kind.ORGANIZER,
                        'share': Decimal(rng.choice(['0.30', '0.40', '0.50'])),
                        'reason': 'Partial refund: seat downgrade',
                    },
                }
        elif 0.052 <= roll < 0.057 and self.cmd.disputes < DISPUTE_BUDGET:  # the card holder disputed it
            at = self.after(paid_at, timedelta(days=1), timedelta(days=20), now - timedelta(hours=1))
            if at:
                self.cmd.disputes += 1
                plan = {'kind': 'disputed', 'paid_at': paid_at, 'dispute_at': at}
        return plan

    def maybe_check_in(self, reg, plan, paid):
        """Who walked in: only valid tickets of an event that has started; nobody
        whose refund is being asked for or whose payment is disputed."""
        if not self.started or reg.status != 'confirmed' or plan['kind'] not in ('confirmed', 'partial'):
            return
        if plan.get('request'):
            return
        share = 0.88 if paid else 0.72
        if not self.ended:
            share *= 0.6  # still arriving
        if self.rng.random() >= share:
            return
        latest = min(self.start + timedelta(minutes=40), self.now - timedelta(minutes=1))
        earliest = self.start - timedelta(minutes=45)
        if latest < earliest:
            return
        reg.is_checked_in = True
        reg.checked_in_at = earliest + timedelta(seconds=self.rng.uniform(0, (latest - earliest).total_seconds()))

    def add_history(self, user, moment, slot, kind):
        reg = self.new_registration(user, slot, 'cancelled', moment)
        self.maybe_promo(reg, live=False)
        reg.seat = None  # released when the ticket was voided
        paid_at = moment + timedelta(minutes=2, seconds=self.rng.randint(0, 119))
        plan = {'kind': kind, 'paid_at': paid_at}
        if kind == 'failed':
            plan['failure'] = 'insufficient_funds' if self.rng.random() < INSUFFICIENT_FUNDS_SHARE else 'card_declined'
        elif kind == 'refunded':
            # Mostly a refund the attendee asked for and the organizer approved;
            # otherwise one the organizer made. No window left: it never paid.
            created = self.after(
                paid_at,
                timedelta(hours=2),
                timedelta(days=5),
                min(self.now - timedelta(hours=3), self.start - timedelta(hours=6)),
            )
            resolved = created and self.after(
                created, timedelta(hours=1), timedelta(hours=30), self.now - timedelta(minutes=30)
            )
            if resolved and self.rng.random() < 0.7:
                plan['refund'] = {
                    'at': resolved,
                    'kind': Refund.Kind.CUSTOMER,
                    'reason': 'Refund request approved',
                    'request': {'status': RefundRequest.STATUS_APPROVED, 'created': created, 'resolved': resolved},
                }
            else:
                at = self.after(
                    paid_at, timedelta(hours=1), timedelta(days=3), min(self.now - timedelta(hours=1), self.start)
                )
                if at:
                    plan['refund'] = {'at': at, 'kind': Refund.Kind.ORGANIZER, 'reason': 'Refunded by the organizer'}
                else:
                    plan['kind'] = 'failed'
                    plan['failure'] = 'card_declined'
        self.registrations.append((reg, plan))

    def add_pending_holds(self):
        """A few live holds (an unpaid ticket with a 10-minute timer) on events about to sell out."""
        if (
            self.started
            or self.cancelled_event
            or self.is_free_event()
            or self.spec.get('fill', 0) >= 0.9
            or self.start - self.now > timedelta(days=21)
            or self.cmd.pending_budget <= 0
        ):
            return
        for _ in range(min(self.rng.randint(0, 2), self.cmd.pending_budget)):
            moment = self.now - timedelta(
                minutes=self.rng.randint(1, HOLD_MINUTES - 3), seconds=self.rng.randint(0, 59)
            )
            user = self.pick_user(moment)
            if user is None:
                continue
            slot = self.allocate('pending', moment)
            if slot is None:
                continue
            reg = self.new_registration(user, slot, 'pending', moment)
            if reg.locked_price is None:
                if reg.seat is not None:
                    self.seats.append(reg.seat)
                if reg.ticket_type is not None:
                    self.remaining[reg.ticket_type_id] += 1
                continue
            reg.seat_held_until = moment + timedelta(minutes=HOLD_MINUTES)
            self.taken_users.add(user.id)
            self.cmd.pending_budget -= 1
            self.registrations.append((reg, {'kind': 'pending'}))

    # ------------------------------------------------------------ money ---- #

    def save_all(self):
        regs = [r for r, _ in self.registrations]
        amounts = {}
        for reg, _ in self.registrations:
            if reg.locked_price is not None:
                amounts[id(reg)] = registration_amount(reg)  # tax, fees and promo as at checkout
        _bulk_create_keeping(Registration, regs, 'registered_at')
        if self.spec['layout'] in ('seated', 'chamber'):
            taken = [r.seat_id for r in regs if r.seat_id and r.status in ('pending', 'confirmed')]
            EventSeat.objects.filter(id__in=taken).update(is_available=False)
        if self.promo is not None:
            self.promo.save(update_fields=['times_used'])

        for reg, plan in self.registrations:
            if id(reg) in amounts:
                self.add_payment(reg, plan, amounts[id(reg)])
        _bulk_create_keeping(Payment, self.payments, 'created_at', 'updated_at')
        _bulk_create_keeping(Refund, self.refunds, 'created_at')
        _bulk_create_keeping(RefundRequest, self.refund_requests, 'created_at')
        self.create_gates(regs)

    def add_payment(self, reg, plan, amount):
        kind = plan['kind']
        started = reg.registered_at
        session = f'mock_sess_{reg.id}_{int(started.timestamp())}'
        created = min(started + timedelta(minutes=1), self.now)
        payment = Payment(
            registration=reg,
            amount=amount,
            currency=self.event.currency.lower(),
            method=Payment.METHOD_CARD,
            stripe_checkout_session_id=session,
            provider='mock',
            provider_session_id=session,
            attempt=1,
            created_at=created,
            updated_at=created,
            status={
                'confirmed': 'completed',
                'partial': 'completed',
                'disputed': 'disputed',
                'pending': 'pending',
                'expired': 'expired',
                'failed': 'failed',
                'refunded': 'refunded',
            }[kind],
        )
        if payment.status in PAID_STATUSES:
            # bulk_create below skips Payment.save(), so stamp the arrival here.
            mark_paid(payment, plan['paid_at'])
            payment.provider_payment_id = f'mock_pay_{reg.id}'
            payment.updated_at = plan['paid_at']
        if kind == 'failed':
            payment.provider_payload = {'failure': plan['failure']}
        if kind == 'disputed':
            payment.provider_payload = {
                'dispute': {
                    'reason': self.rng.choice(['fraudulent', 'product_not_received']),
                    'status': 'needs_response',
                }
            }
            payment.updated_at = plan['dispute_at']
        if plan.get('refund'):
            self.add_refund(reg, payment, plan['refund'], amount)
        if plan.get('request'):
            request = plan['request']
            self.refund_requests.append(
                RefundRequest(
                    registration=reg,
                    status=request['status'],
                    reason=self.rng.choice(['Cannot attend', 'Plans changed', 'Got sick', 'Double booked']),
                    organizer_note='Tickets are transferable instead.'
                    if request['status'] == RefundRequest.STATUS_REJECTED
                    else '',
                    resolved_at=request.get('resolved'),
                    created_at=request['created'],
                )
            )
        self.payments.append(payment)

    def add_refund(self, reg, payment, refund, amount):
        """The ledger row, the payment's refund columns and (for a customer
        refund) the approved request that led to it."""
        at, refund_kind = refund['at'], refund['kind']
        refunded = _q(amount * refund['share']) if 'share' in refund else amount
        reason = refund.get('reason', '')
        if refund_kind == Refund.Kind.EVENT_CANCELLED:
            reason = 'Event cancelled by the organizer'
        payment.refunded_amount = refunded
        payment.refunded_at = at
        payment.refund_reason = reason
        payment.updated_at = at
        refund_id = self.uuid()
        self.refunds.append(
            Refund(
                id=refund_id,
                payment=payment,
                amount=refunded,
                currency=self.event.currency.upper(),
                kind=refund_kind,
                status=Refund.Status.SUCCEEDED,
                reason=reason,
                requested_by=reg.user if refund_kind == Refund.Kind.CUSTOMER else self.organizer,
                provider='mock',
                provider_payment_id=payment.provider_payment_id,
                provider_refund_id=f'mock_re_{refund_id.hex[:16]}',
                idempotency_key=f'refund-{refund_id}',
                attempts=1,
                created_at=at,
                processed_at=at,
            )
        )
        request = refund.get('request')
        if request:
            self.refund_requests.append(
                RefundRequest(
                    registration=reg,
                    status=request['status'],
                    reason=self.rng.choice(['Cannot attend', 'Plans changed', 'Got sick']),
                    resolved_at=request['resolved'],
                    created_at=request['created'],
                )
            )

    # ---------------------------------------------------------- bookings ---- #

    def plan_bookings(self):
        """Group bookings on seated events. Returns the seats they hold."""
        held = 0
        statuses = ['confirmed'] * (self.spec['bookings'] - 3) + ['expired', 'refunded']
        statuses.append('holding' if not self.started else 'confirmed')
        for status in statuses:
            created = self.sale_time()
            if status == 'holding':
                created = self.now - timedelta(minutes=self.rng.randint(1, 8))
            owner = self.pick_user(created)
            if owner is None:
                continue
            refunded_at = None
            if status == 'refunded':
                refunded_at = self.after(
                    created + timedelta(minutes=2),
                    timedelta(hours=1),
                    timedelta(days=2),
                    min(self.now - timedelta(minutes=5), self.start),
                )
                if refunded_at is None:
                    status = 'confirmed'
            held += self.add_booking(status, owner, created, refunded_at)
        return held

    def add_booking(self, status, owner, created, refunded_at):
        size = self.rng.randint(2, 6)
        self.taken_users.add(owner.id)
        booking = Booking(
            id=self.uuid(),
            share_token=self.uuid(),
            owner=owner,
            event=self.event,
            status=status,
            stripe_session_id=f'mock_sess_bk_{self.spec["key"]}_{len(self.cmd.booking_log)}',
        )
        seats = []
        if status in ('confirmed', 'holding'):
            seats = [self.seats.pop() for _ in range(min(size, len(self.seats)))]
        if status == 'holding':
            booking.hold_expires_at = created + timedelta(minutes=HOLD_MINUTES)
        booking.save()
        Booking.objects.filter(pk=booking.pk).update(created_at=created)
        seat_rows = []
        for i, seat in enumerate(seats):
            bs = BookingSeat(booking=booking, seat=seat, price=seat_price(self.event, seat), ticket_uuid=self.uuid())
            if i == 0:
                bs.attendee_name, bs.claimed_by = owner.get_full_name(), owner
            elif self.rng.random() < 0.6:
                friend = self.pick_user(created)
                if friend is not None:
                    bs.attendee_name, bs.claimed_by = friend.get_full_name(), friend
            if self.started and status == 'confirmed' and self.rng.random() < 0.8:
                latest = min(self.start + timedelta(minutes=30), self.now - timedelta(minutes=1))
                earliest = self.start - timedelta(minutes=40)
                if latest >= earliest:
                    bs.is_checked_in = True
                    bs.checked_in_at = earliest + timedelta(
                        seconds=self.rng.uniform(0, (latest - earliest).total_seconds())
                    )
            seat_rows.append(bs)
        BookingSeat.objects.bulk_create(seat_rows)
        BookingSeat.objects.filter(booking=booking).update(created_at=created)
        EventSeat.objects.filter(id__in=[s.id for s in seats]).update(is_available=False)

        # Amount exactly as bookings.payments.booking_amount computes it.
        if seat_rows:
            amount = sum((seat_total(bs) for bs in seat_rows), Decimal('0.00'))
        else:
            ghost = BookingSeat(booking=booking, price=seat_price(self.event, self.rng.choice(self.all_seats)))
            amount = seat_total(ghost) * size
        amount = _q(amount)
        payment = Payment(
            booking=booking,
            amount=amount,
            currency=self.event.currency.lower(),
            provider='mock',
            provider_session_id=booking.stripe_session_id,
            attempt=1,
            status={'confirmed': 'completed', 'holding': 'pending', 'expired': 'expired', 'refunded': 'refunded'}[
                status
            ],
        )
        if status in ('confirmed', 'refunded'):
            booking.amount_paid = amount
            booking.confirmed_at = created + timedelta(minutes=2)
            mark_paid(payment, booking.confirmed_at)
            payment.provider_payment_id = f'mock_pay_bk_{booking.pk.hex[:16]}'
        if status == 'refunded':
            booking.refunded_at = refunded_at
            booking.refund_reason = 'Group could not attend'
            payment.refunded_amount = amount
            payment.refunded_at = refunded_at
            payment.refund_reason = booking.refund_reason
        booking.save(update_fields=['amount_paid', 'confirmed_at', 'refunded_at', 'refund_reason'])
        payment.save()
        Payment.objects.filter(pk=payment.pk).update(
            created_at=min(created + timedelta(minutes=1), self.now),
            updated_at=min(refunded_at or created + timedelta(minutes=2), self.now),
        )
        if status == 'refunded':
            refund_id = self.uuid()
            Refund.objects.create(
                id=refund_id,
                payment=payment,
                amount=amount,
                currency=self.event.currency.upper(),
                kind=Refund.Kind.ORGANIZER,
                status=Refund.Status.SUCCEEDED,
                reason=booking.refund_reason,
                requested_by=self.organizer,
                provider='mock',
                provider_payment_id=payment.provider_payment_id,
                provider_refund_id=f'mock_re_{refund_id.hex[:16]}',
                attempts=1,
                processed_at=refunded_at,
            )
            Refund.objects.filter(pk=refund_id).update(created_at=refunded_at)
        self.cmd.booking_log.append(booking.pk)
        return len(seats)

    # ------------------------------------- gates, staff, waitlist, reviews ---- #

    def create_gates(self, regs):
        """Check-in lists (gates), the staff who scan at them, and the scans."""
        if self.cancelled_event or self.event.status not in ('published', 'completed'):
            return
        staff_count = 3 if self.event.max_participants >= 300 else 2
        staff = self.rng.sample(self.cmd.staff, k=min(staff_count, len(self.cmd.staff)))
        EventStaff.objects.bulk_create(
            [EventStaff(event=self.event, user=user, role=EventStaff.ROLE_CHECK_IN) for user in staff]
        )
        main = CheckInList.objects.create(event=self.event, name='Main entrance', is_default=True)
        gates = [main]
        has_vip = any('VIP' in t.name for t in self.tiers) or self.spec['layout'] in ('seated', 'chamber')
        vip = None
        if has_vip:
            vip = CheckInList.objects.create(event=self.event, name='VIP entrance', color='#d97706')
            gates.append(vip)
        opened = min(self.start - timedelta(days=self.rng.randint(1, 10)), self.now - timedelta(hours=1))
        CheckInList.objects.filter(pk__in=[g.pk for g in gates]).update(created_at=opened)

        logs = []
        for reg in (r for r in regs if r.is_checked_in):
            vip_ticket = (reg.ticket_type is not None and 'VIP' in reg.ticket_type.name) or (
                reg.seat_id is not None and reg.seat.price_zone in ('vip', 'premium')
            )
            gate = vip if (vip_ticket and vip is not None) else main
            scanner = staff[-1] if gate is vip else self.rng.choice(staff)
            # The organizer of a demo event sometimes scans too; the real `--organizer` never does.
            if self.organizer.username.startswith(USERNAME_PREFIX) and self.rng.random() < 0.08:
                scanner = self.organizer
            logs.append(
                CheckInLog(checkin_list=gate, registration=reg, scanned_by=scanner, created_at=reg.checked_in_at)
            )
        _bulk_create_keeping(CheckInLog, logs, 'created_at')

    def create_waitlist(self, spec):
        pool = self.cmd.pool
        free_users = [
            user
            for joined, user, _weight, _city in pool
            if user.id not in self.taken_users and joined < self.now - timedelta(days=7)
        ]
        entries = []
        for status in ('waiting', 'expired', 'offered'):
            for _ in range(spec.get(status, 0)):
                if not free_users:
                    break
                user = free_users.pop(self.rng.randrange(len(free_users)))
                entry = WaitlistEntry(user=user, event=self.event, status=status)
                entry.created_at = self.now - timedelta(days=self.rng.uniform(0.2, 6))
                if status == 'expired':
                    entry.offered_at = self.now - timedelta(days=self.rng.randint(1, 4))
                    entry.offer_expires_at = entry.offered_at + timedelta(minutes=30)
                    entry.created_at = min(entry.created_at, entry.offered_at - timedelta(hours=3))
                if status == 'offered':
                    entry.offered_at = self.now - timedelta(minutes=5)
                    entry.offer_expires_at = self.now + timedelta(minutes=25)
                    entry.created_at = min(entry.created_at, entry.offered_at - timedelta(hours=1))
                entries.append(entry)
        confirmed = [r for r, plan in self.registrations if r.status == 'confirmed' and plan['kind'] == 'confirmed']
        for reg in self.rng.sample(confirmed, k=min(spec.get('converted', 0), len(confirmed))):
            entry = WaitlistEntry(user=reg.user, event=self.event, status='converted')
            waited_since = reg.registered_at - timedelta(hours=self.rng.randint(1, 3))
            entry.created_at = max(waited_since, reg.user.date_joined + timedelta(minutes=1))
            entries.append(entry)
        _bulk_create_keeping(WaitlistEntry, entries, 'created_at')

    def create_reviews(self):
        """Reviews come only from attendees whose ticket was scanned, once the event is over."""
        if self.now - self.end < timedelta(hours=4):
            return
        attended = [r for r, _ in self.registrations if r.is_checked_in and r.status == 'confirmed']
        ratings, weights = zip(*REVIEW_RATING_WEIGHTS.items(), strict=True)
        reviews = []
        for reg in self.rng.sample(attended, k=int(len(attended) * 0.3)):
            rating = self.rng.choices(ratings, weights=weights)[0]
            written = self.after(self.end, timedelta(hours=3), timedelta(days=6), self.now - timedelta(minutes=30))
            if written is None:
                continue
            reviews.append(
                Review(
                    user=reg.user,
                    event=self.event,
                    rating=rating,
                    comment=self.rng.choice(REVIEW_COMMENTS[rating]),
                    created_at=written,
                    updated_at=written,
                )
            )
        _bulk_create_keeping(Review, reviews, 'created_at', 'updated_at')

    # ------------------------------------------------------- promo/affiliate ---- #

    def create_promo(self):
        if 'promo' not in self.spec:
            return None
        code, dtype, value, max_uses = self.spec['promo']
        return PromoCode.objects.create(
            event=self.event, code=code, discount_type=dtype, discount_value=Decimal(value), max_uses=max_uses
        )

    def create_affiliate(self):
        if 'affiliate' not in self.spec:
            return None
        name, code, clicks = self.spec['affiliate']
        return Affiliate.objects.create(event=self.event, name=name, code=code, clicks=clicks)

    @property
    def all_seats(self):
        if not hasattr(self, '_all_seats'):
            self._all_seats = list(EventSeat.objects.filter(seat_map__event=self.event).select_related('seat_map'))
        return self._all_seats


class Command(BaseCommand):
    help = (
        'Seed realistic Kazakhstan demo data (60 events, ~760 attendees, KZT). DJANGO_DEBUG=1, or DJANGO_DEBUG=0 '
        'with --i-know-this-is-a-demo and --credentials-file; idempotent. --remove deletes what it created.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--attendees', type=int, default=760, help='Number of attendee accounts (default 760).')
        parser.add_argument(
            '--organizer',
            default='',
            metavar='USERNAME',
            help='An existing organizer account: it owns about a third of the events and co-organizes two more.',
        )
        parser.add_argument(
            '--credentials-file',
            default='',
            metavar='PATH',
            help=(
                'DJANGO_DEBUG=0: required. A new file (mode 0600, never overwritten) that receives '
                'username<TAB>password<TAB>role for every created account. No password is printed.'
            ),
        )
        parser.add_argument('--remove', action='store_true', help='Delete everything this command created.')
        parser.add_argument('--dry-run', action='store_true', help='With --remove: print what would be deleted.')
        demo_seed.add_demo_flag(parser)

    def handle(self, *args, **options):
        demo_seed.check_allowed('seed_demo_kz', options, needs=f'{demo_seed.CREDENTIALS_OPTION} PATH')
        if options['dry_run'] and not options['remove']:
            raise CommandError('--dry-run only works with --remove.')
        owner = self.resolve_owner(options['organizer'])
        if options['remove']:
            demo_kz_remove.remove(self, owner, dry_run=options['dry_run'])
            return

        self.demo_mode = not settings.DEBUG
        path = options['credentials_file']
        if self.demo_mode and not path:
            raise CommandError(
                f'DJANGO_DEBUG=0 needs {demo_seed.CREDENTIALS_OPTION} PATH: every account gets its own random '
                'password and the file is the only place it is written.'
            )
        if path and not self.demo_mode:
            raise CommandError(
                f'{demo_seed.CREDENTIALS_OPTION} is only used with DJANGO_DEBUG=0 '
                f'(with DJANGO_DEBUG=1 every account has the password {DEMO_PASSWORD}).'
            )
        if options['attendees'] < 1:
            raise CommandError('--attendees must be at least 1.')

        handle = demo_seed.open_credentials_file(path) if path else None
        try:
            self.seed(options, owner, handle)
        except BaseException:
            if handle is not None:
                handle.close()
                if os.path.getsize(path) == 0:
                    os.unlink(path)  # nothing was written: let the operator reuse the name
            raise
        if handle is not None:
            handle.close()

    def resolve_owner(self, username):
        """The `--organizer` user: an existing, real account with the organizer role."""
        if not username:
            return None
        user = User.objects.filter(username=username).select_related('profile').first()
        if user is None:
            raise CommandError(f'--organizer: user "{username}" does not exist.')
        if demo_seed.is_demo_address(user.email) or user.username.startswith(USERNAME_PREFIX):
            raise CommandError(f'--organizer: "{username}" is a demo account; pass a real organizer account.')
        role = getattr(getattr(user, 'profile', None), 'role', '')
        if role != RoleChoices.ORGANIZER:
            raise CommandError(
                f'--organizer: "{username}" is not an organizer (its profile role is "{role or "none"}").'
            )
        return user

    def seed(self, options, owner, handle):
        started = time.monotonic()
        self.now = timezone.now()
        self.owner = owner
        self.booking_log = []
        self.pending_budget = PENDING_HOLD_BUDGET
        self.disputes = 0

        categories = self.seed_categories()
        organizers, self.staff, attendees = self.seed_accounts(options['attendees'], handle)
        self.pool = self.build_pool(attendees)
        self.pool_joined = [item[0] for item in self.pool]

        created, existing, events = 0, 0, {}
        for spec in EVENTS:
            with transaction.atomic():
                event, is_new = self.get_or_create_event(spec, organizers, categories)
                if is_new:
                    EventSeeder(self, event, spec, attendees, event.organizer).run()
                    created += 1
                else:
                    existing += 1
            events[spec['key']] = event
        team = self.seed_team(events, organizers)

        self.stdout.write(
            self.style.SUCCESS(
                f'seed_demo_kz: {created} events created, {existing} already present '
                f'({len(organizers)} organizers, {len(self.staff)} check-in staff, {len(attendees)} attendees, '
                f'{team} team roles added) in {time.monotonic() - started:.1f}s.'
            )
        )
        if owner is not None:
            mine = Event.objects.filter(organizer=owner, title__in=[s['title'] for s in EVENTS]).count()
            self.stdout.write(f'{owner.username} owns {mine} of the demo events.')
        if handle is not None:
            self.stdout.write(
                f'Passwords for {self.credential_count} new accounts are in {options["credentials_file"]}.'
            )
        elif created or self.credential_count:
            self.stdout.write(f'Demo logins: kz_<name> / {DEMO_PASSWORD}, e.g. kz_dana.abenova (organizer).')

    # ------------------------------------------------------------ people ---- #

    def seed_categories(self):
        out = {}
        for name, description, icon in CATEGORIES:
            out[name], _ = Category.objects.get_or_create(
                name=name, defaults={'description': description, 'icon': icon}
            )
        return out

    def seed_accounts(self, attendee_count, handle):
        """Create the organizers, the check-in staff and the attendees in one go
        (one batch of hashing, one credentials file). Returns
        ({organizer key: user}, [staff users], [attendee users])."""
        organizer_specs = self.organizer_specs()
        staff_specs = self.staff_specs()
        attendee_specs = self.attendee_specs(attendee_count)
        users = self._ensure_users(organizer_specs + staff_specs + attendee_specs, handle)
        n_org, n_staff = len(organizer_specs), len(staff_specs)
        organizers = {key: user for (key, *_), user in zip(ORGANIZERS, users[:n_org], strict=True)}
        return organizers, users[n_org : n_org + n_staff], users[n_org + n_staff :]

    def _ensure_users(self, specs, handle):
        """specs: dicts (username, first_name, last_name, kind, role, city, bio, phone, joined)."""
        names = [s['username'] for s in specs]
        existing = {u.username: u for u in User.objects.filter(username__in=names)}
        for user in existing.values():
            if not demo_seed.is_demo_address(user.email):
                raise CommandError(f'User "{user.username}" already exists and is not a demo account; not reusing it.')
        new_specs = [s for s in specs if s['username'] not in existing]
        self.credential_count = 0

        if self.demo_mode:
            passwords = [demo_seed.generate_password() for _ in new_specs]
            hashes = demo_seed.hash_passwords(passwords, progress=self.report_hashing)
        else:
            passwords = [DEMO_PASSWORD] * len(new_specs)
            hashes = [make_password(DEMO_PASSWORD)] * len(new_specs) if new_specs else []

        with transaction.atomic():
            User.objects.bulk_create(  # bulk: no post_save, profiles below
                [
                    User(
                        username=s['username'],
                        email=f'{s["username"]}@{EMAIL_DOMAIN}',
                        first_name=s['first_name'],
                        last_name=s['last_name'],
                        password=password_hash,
                        date_joined=s['joined'],
                    )
                    for s, password_hash in zip(new_specs, hashes, strict=True)
                ],
                batch_size=500,
            )
            users = {u.username: u for u in User.objects.filter(username__in=names)}
            have_profile = set(UserProfile.objects.filter(user__in=users.values()).values_list('user_id', flat=True))
            _bulk_create_keeping(
                UserProfile,
                [
                    UserProfile(
                        user=users[s['username']],
                        role=s['role'],
                        location=s['city'],
                        bio=s['bio'],
                        phone=s['phone'],
                        created_at=s['joined'],
                    )
                    for s in specs
                    if users[s['username']].id not in have_profile
                ],
                'created_at',
            )
            if handle is not None:
                self.credential_count = demo_seed.write_credentials(
                    handle, ((s['username'], pw, s['kind']) for s, pw in zip(new_specs, passwords, strict=True))
                )
            else:
                self.credential_count = len(new_specs)
        return [users[name] for name in names]

    def report_hashing(self, done, total):
        self.stdout.write(f'Hashed {done}/{total} passwords.')

    def joined(self, rng, days_ago):
        return self.now - timedelta(days=days_ago, minutes=rng.randint(0, 1439))

    def organizer_specs(self):
        rng = random.Random(f'{SEED}:organizers')  # noqa: S311 - demo data, not security
        return [
            {
                'username': f'{USERNAME_PREFIX}{key}',
                'first_name': first,
                'last_name': last,
                'kind': 'organizer',
                'role': RoleChoices.ORGANIZER,
                'city': city,
                'bio': bio,
                'phone': self.phone(rng),
                'joined': self.joined(rng, rng.randint(200, 700)),
            }
            for key, first, last, city, bio in ORGANIZERS
        ]

    def staff_specs(self):
        rng = random.Random(f'{SEED}:staff')  # noqa: S311 - demo data, not security
        return [
            {
                'username': f'{USERNAME_PREFIX}staff.{first}.{last}'.lower(),
                'first_name': first,
                'last_name': last,
                'kind': 'check_in',
                'role': RoleChoices.ATTENDEE,
                'city': city,
                'bio': 'Check-in staff at event entrances.',
                'phone': self.phone(rng),
                'joined': self.joined(rng, rng.randint(100, 380)),
            }
            for first, last, city in STAFF
        ]

    def attendee_specs(self, count):
        rng = random.Random(f'{SEED}:attendees')  # noqa: S311 - demo data, not security
        # Never reuse an organizer's or a staff member's user name.
        specs = []
        seen = {f'{USERNAME_PREFIX}{key}' for key, *_ in ORGANIZERS}
        seen |= {f'{USERNAME_PREFIX}staff.{first}.{last}'.lower() for first, last, _ in STAFF}
        cities, weights = zip(*CITIES, strict=True)
        while len(specs) < count:
            female = rng.random() < 0.5
            first = rng.choice(FEMALE_FIRST if female else MALE_FIRST)
            male_last, female_last = rng.choice(SURNAMES)
            last = female_last if female else male_last
            base = f'{USERNAME_PREFIX}{first}.{last}'.lower()
            username, n = base, 1
            while username in seen:
                n += 1
                username = f'{base}{n}'
            seen.add(username)
            # A growing platform: most sign-ups are recent.
            days_ago = max(1, int(ATTENDEE_JOINED_DAYS * rng.random() ** 1.7))
            specs.append(
                {
                    'username': username,
                    'first_name': first,
                    'last_name': last,
                    'kind': 'attendee',
                    'role': RoleChoices.ATTENDEE,
                    'city': rng.choices(cities, weights=weights)[0],
                    'bio': '',
                    'phone': self.phone(rng),
                    'joined': self.joined(rng, days_ago),
                }
            )
        return specs

    @staticmethod
    def phone(rng):
        return f'+7 {rng.choice(PHONE_PREFIXES)} {rng.randint(100, 999)} {rng.randint(10, 99)} {rng.randint(10, 99)}'

    def build_pool(self, attendees):
        """(signed up, user, activity) sorted by sign-up date: a few attendees go to many events."""
        rng = random.Random(f'{SEED}:activity')  # noqa: S311 - demo data, not security
        city_of = dict(UserProfile.objects.filter(user__in=attendees).values_list('user_id', 'location'))
        pool = [
            (user.date_joined, user, min(rng.paretovariate(1.5), 8.0), city_of.get(user.id, '')) for user in attendees
        ]
        pool.sort(key=lambda item: (item[0], item[1].id))
        return pool

    # ------------------------------------------------------------ events ---- #

    def event_start(self, spec):
        if 'offset_minutes' in spec:
            moment = self.now + timedelta(minutes=spec['offset_minutes'])
            return moment.replace(minute=moment.minute - moment.minute % 5, second=0, microsecond=0)
        day = self.now.astimezone(KZ_TZ).date() + timedelta(days=spec['days'])
        return datetime(day.year, day.month, day.day, spec['hour'], 0, tzinfo=KZ_TZ).astimezone(UTC)

    def get_or_create_event(self, spec, organizers, categories):
        # A title is unique among the demo events (and distinct from every other seed
        # command's), so an event found by title is the one a previous run created.
        event = Event.objects.filter(title=spec['title']).select_related('organizer').first()
        if event is not None:
            return event, False
        owner = self.owner if (self.owner is not None and spec.get('mine')) else organizers[spec['organizer']]
        start = self.event_start(spec)
        end = start + timedelta(hours=spec['hours'])
        status = spec.get('status') or ('completed' if end < self.now else 'published')
        online = spec.get('online', False)
        place = f'{spec["venue"]}, {spec["city"]}'
        about = spec.get('about') or f'{spec["title"]} at {place}.'
        how = (
            'Online event: the link arrives with your ticket.'
            if online
            else 'Tickets in tenge (KZT); e-tickets with QR code, entry from one hour before the start.'
        )
        event = Event.objects.create(
            title=spec['title'],
            description=f'{about} {how}',
            organizer=owner,
            category=categories[spec['category']],
            date=start,
            end_date=end,
            location='Online' if online else place,
            address=spec['address'],
            price=Decimal(spec.get('price', '0')),
            max_participants=spec.get('capacity', 100),
            status=status,
            is_online=online,
            online_link=spec.get('link', ''),
            currency='KZT',
            tax_percent=Decimal('0'),  # prices include 12% VAT
            service_fee_percent=Decimal(spec.get('service_fee', '0')),
            refundable=spec.get('refundable', True),
        )
        return event, True

    def seed_team(self, events, organizers):
        """Co-organizers: a demo organizer on some events, and `--organizer` on two
        events of demo organizers (so its dashboard shows co-organized events too)."""
        created = 0
        for spec in EVENTS:
            event = events[spec['key']]
            wanted = []
            if spec.get('coorg') and event.organizer != self.owner:
                wanted.append(organizers[spec['coorg']])
            if spec.get('owner_coorg') and self.owner is not None and event.organizer != self.owner:
                wanted.append(self.owner)
            for user in wanted:
                if user.id == event.organizer_id:
                    continue
                _, is_new = EventStaff.objects.get_or_create(
                    event=event, user=user, defaults={'role': EventStaff.ROLE_CO_ORGANIZER}
                )
                created += is_new
        return created

    def create_seat_map(self, event, rows, cols, vip_rows, premium_rows):
        """Same layout rules as EventViewSet.create_seat_map (premium, then VIP, then standard rows)."""
        zones = {
            'premium': list(range(1, premium_rows + 1)),
            'vip': list(range(premium_rows + 1, premium_rows + vip_rows + 1)),
            'standard': list(range(premium_rows + vip_rows + 1, rows + 1)),
        }
        seat_map = SeatMap.objects.create(
            event=event, rows=rows, cols=cols, layout={'price_zones': {k: v for k, v in zones.items() if v}}
        )
        seats = EventSeat.objects.bulk_create(
            [
                EventSeat(
                    seat_map=seat_map,
                    row=r,
                    col=c,
                    price_zone='premium' if r in zones['premium'] else 'vip' if r in zones['vip'] else 'standard',
                )
                for r in range(1, rows + 1)
                for c in range(1, cols + 1)
            ]
        )
        for seat in seats:
            seat.seat_map = seat_map
        event.max_participants = rows * cols
        event.save(update_fields=['max_participants'])
        return seats
