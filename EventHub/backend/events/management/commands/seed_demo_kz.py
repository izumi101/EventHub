"""Realistic Kazakhstan demo data: Almaty and Astana events priced in KZT.

    python manage.py seed_demo_kz                 # DJANGO_DEBUG=1 only

Creates organizers and ~600 attendees (password "password123", like
seed_data), 24 events (concerts, conferences, sports, theatre; seat maps,
ticket tiers, general admission, free and donation events; published,
completed, cancelled, draft and pending), and their sales: registrations in
every status (pending holds, confirmed, cancelled after an expired hold or a
failed payment, refunded), payments (completed, pending, failed, expired,
refunded, partially refunded) with their Refund ledger rows, refund
requests, group bookings, check-ins with gate logs, reviews, waitlists,
promo codes and an affiliate.

Deterministic: every event draws from its own random generator seeded with
a fixed seed and the event key, and UUIDs come from the same generator.
Idempotent: users, categories and events are looked up by natural key (user
name, category name, event title + organizer); an event that already exists
is left alone, so a second run creates nothing. Prices, seat zones, tax and
fees go through the real pricing code (events.billing, events.seat_pricing,
bookings.payments) so the stored amounts equal what the app would charge;
seat maps come from the same layout rules as the organizer API and, for the
chamber hall, from `generate_seat_maps` itself. Rows are bulk-inserted for
speed (a few seconds for ~5 000 tickets).
"""

import io
import random
import time
import uuid
from datetime import UTC, datetime, timedelta
from datetime import timezone as dt_timezone
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
from events.billing import registration_amount
from events.models import (
    Affiliate,
    Category,
    CheckInList,
    CheckInLog,
    Event,
    EventSeat,
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

SEED = 20261112
# Kazakhstan has one time zone, UTC+5, since 1 March 2024.
KZ_TZ = dt_timezone(timedelta(hours=5), 'Asia/Almaty')
DEMO_PASSWORD = 'password123'  # noqa: S105 - documented demo password, DEBUG only (like seed_data)
EMAIL_DOMAIN = 'demo.eventhub.local'
HOLD_MINUTES = 10
CENT = Decimal('0.01')

CATEGORIES = [
    ('Music', 'Concerts, jam sessions, and live performances.', 'music'),
    ('Technology', 'Conferences, meetups, and hands-on workshops.', 'laptop'),
    ('Business', 'Networking, startup, and finance events.', 'briefcase'),
    ('Education', 'Lectures, bootcamps, and learning sessions.', 'book'),
    ('Sports', 'Tournaments, outdoor activities, and fitness events.', 'trophy'),
    ('Theatre', 'Opera, ballet, drama and stand-up.', 'theater'),
]

# username suffix, first name, last name, city, bio
ORGANIZERS = [
    ('dana.abenova', 'Dana', 'Abenova', 'Almaty', 'Qazaq Live Agency: concerts and festivals in Almaty.'),
    ('nurlan.zhakupov', 'Nurlan', 'Zhakupov', 'Astana', 'Tech community lead: conferences, meetups and bootcamps.'),
    ('yerlan.ospanov', 'Yerlan', 'Ospanov', 'Almaty', 'Steppe Run Club: running races and sports events.'),
    ('saule.tulegenova', 'Saule', 'Tulegenova', 'Astana', 'Producer at an independent theatre company.'),
    ('arman.bekov', 'Arman', 'Bekov', 'Almaty', 'Business forums and startup pitch days.'),
    ('aliya.kassymova', 'Aliya', 'Kassymova', 'Astana', 'Family, science and education events.'),
]

FEMALE_FIRST = [
    'Aigerim', 'Aruzhan', 'Dana', 'Madina', 'Aliya', 'Kamila', 'Zhanna', 'Asel', 'Dinara', 'Gulnaz', 'Saule',
    'Ainur', 'Togzhan', 'Inkar', 'Akbota', 'Aizhan', 'Balnur', 'Zarina', 'Moldir', 'Anel', 'Yelena', 'Olga',
    'Anastasia', 'Viktoria', 'Diana', 'Aisha', 'Tomiris', 'Zhuldyz',
]  # fmt: skip
MALE_FIRST = [
    'Daniyar', 'Nurlan', 'Yerlan', 'Arman', 'Askar', 'Bauyrzhan', 'Yerzhan', 'Timur', 'Alikhan', 'Dias',
    'Rustam', 'Azamat', 'Sanzhar', 'Miras', 'Olzhas', 'Nursultan', 'Aibek', 'Marat', 'Ruslan', 'Dmitry',
    'Sergey', 'Andrey', 'Alexei', 'Maxim', 'Ilyas', 'Temirlan', 'Abylai', 'Zhandos',
]  # fmt: skip
# (male form, female form)
SURNAMES = [
    ('Nurlanov', 'Nurlanova'), ('Abenov', 'Abenova'), ('Seitkali', 'Seitkali'), ('Zhakupov', 'Zhakupova'),
    ('Ospanov', 'Ospanova'), ('Bekov', 'Bekova'), ('Tulegenov', 'Tulegenova'), ('Akhmetov', 'Akhmetova'),
    ('Serikbayev', 'Serikbayeva'), ('Omarov', 'Omarova'), ('Kassymov', 'Kassymova'), ('Ibrayev', 'Ibrayeva'),
    ('Sadykov', 'Sadykova'), ('Iskakov', 'Iskakova'), ('Mukhametov', 'Mukhametova'), ('Zhumabayev', 'Zhumabayeva'),
    ('Kim', 'Kim'), ('Tsoi', 'Tsoi'), ('Ivanov', 'Ivanova'), ('Petrov', 'Petrova'), ('Smagulov', 'Smagulova'),
    ('Baimukhanov', 'Baimukhanova'), ('Yesenov', 'Yesenova'), ('Dzhaksybekov', 'Dzhaksybekova'),
]  # fmt: skip

REVIEW_COMMENTS = {
    5: ['Fantastic evening, will come again!', 'Perfect organisation and great sound.', 'Керемет! Loved every minute.'],
    4: ['Very good, the queue at the entrance was a bit long.', 'Great program, parking was hard to find.'],
    3: ['Okay, but it started 30 minutes late.', 'Good content, the hall was too warm.'],
    2: ['Sound quality was poor in the back rows.', 'Too crowded for the venue size.'],
    1: ['Disappointing, not what was advertised.'],
}


def tier(name, kind, price, quantity, description='', sale_end_days=None):
    return {
        'name': name,
        'kind': kind,
        'price': Decimal(price),
        'quantity': quantity,
        'description': description,
        'sale_end_days': sale_end_days,
    }


# key: stable id for the per-event random generator.
# days: start relative to today (Almaty date); negative = already happened.
EVENTS = [
    {
        'key': 'almaty-symphony', 'title': 'Kazakh Classics Symphony Night', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Almaty', 'venue': 'Zhambyl State Philharmonic',
        'address': 'Tole Bi St 35, Almaty', 'days': 12, 'hour': 19, 'hours': 2.5,
        'layout': 'seated', 'rows': 12, 'cols': 20, 'premium_rows': 2, 'vip_rows': 3, 'price': '8000',
        'fill': 0.7, 'bookings': 6,
    },
    {
        'key': 'almaty-jazz', 'title': 'Almaty Jazz Festival 2026', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Almaty', 'venue': 'Republic Palace',
        'address': 'Dostyk Ave 56, Almaty', 'days': 20, 'hour': 18, 'hours': 5,
        'layout': 'tiers', 'tiers': [
            tier('Early Bird', 'paid', '12000', 200, 'Limited first release', sale_end_days=-5),
            tier('Standard', 'paid', '18000', 600),
            tier('VIP', 'paid', '45000', 80, 'Front rows, lounge access'),
        ],
        'fill': 0.5, 'promo': ('JAZZ15', 'percent', '15', 50),
        'affiliate': ('Instagram @almaty.jazz', 'IGJAZZ', 1240),
    },
    {
        'key': 'almaty-qpop', 'title': 'Q-pop Night Live', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Almaty', 'venue': 'Almaty Arena',
        'address': 'Momyshuly St 37, Almaty', 'days': 9, 'hour': 19, 'hours': 3,
        'layout': 'tiers', 'tiers': [
            tier('Fan zone', 'paid', '15000', 150),
            tier('Seated', 'paid', '25000', 100),
            tier('VIP', 'paid', '60000', 20, 'Meet & greet'),
        ],
        'fill': 1.0, 'waitlist': {'waiting': 18, 'expired': 4, 'converted': 3},
    },
    {
        'key': 'almaty-opera-kyz-zhibek', 'title': 'Opera "Kyz Zhibek"', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Almaty', 'venue': 'Abai Opera and Ballet Theatre',
        'address': 'Kabanbay Batyr St 110, Almaty', 'days': -14, 'hour': 19, 'hours': 3,
        'layout': 'seated', 'rows': 10, 'cols': 18, 'premium_rows': 1, 'vip_rows': 3, 'price': '6000',
        'fill': 0.85, 'bookings': 4,
    },
    {
        'key': 'almaty-run-10k', 'title': 'Almaty Autumn Run 10K / 21K', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Almaty', 'venue': 'Republic Square start area',
        'address': 'Zheltoksan St 115, Almaty', 'days': -30, 'hour': 8, 'hours': 5,
        'layout': 'tiers', 'tiers': [
            tier('10K', 'paid', '10000', 300),
            tier('21K Half marathon', 'paid', '15000', 150),
            tier('Kids 2K', 'paid', '3000', 60),
        ],
        'fill': 0.85,
    },
    {
        'key': 'almaty-tech-summit', 'title': 'Kazakhstan Tech Summit', 'category': 'Technology',
        'organizer': 'nurlan.zhakupov', 'city': 'Almaty', 'venue': 'Hotel Kazakhstan Conference Hall',
        'address': 'Abay Ave 52, Almaty', 'days': 25, 'hour': 10, 'hours': 8,
        'layout': 'tiers', 'tiers': [
            tier('Student', 'paid', '5000', 100, 'Student ID at the entrance'),
            tier('Standard', 'paid', '25000', 300),
            tier('Business', 'paid', '60000', 50, 'Networking dinner included'),
        ],
        'fill': 0.55, 'service_fee': '5',
    },
    {
        'key': 'almaty-python-meetup', 'title': 'Almaty Python Meetup #42', 'category': 'Technology',
        'organizer': 'nurlan.zhakupov', 'city': 'Almaty', 'venue': 'SmArt.Point',
        'address': 'Baizakov St 280, Almaty', 'days': 6, 'hour': 19, 'hours': 2.5,
        'layout': 'free', 'capacity': 120, 'fill': 0.8,
    },
    {
        'key': 'almaty-standup', 'title': 'Stand-up Almaty: Open Mic Special', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Almaty', 'venue': 'Comedy Bar on Panfilov',
        'address': 'Panfilov St 98, Almaty', 'days': 4, 'hour': 20, 'hours': 2,
        'layout': 'ga', 'price': '7000', 'capacity': 150, 'fill': 0.9,
        'promo': ('FRIENDS20', 'percent', '20', 30),
    },
    {
        'key': 'almaty-cup-football', 'title': 'Kazakhstan Cup Quarter-final: Almaty vs Shymkent', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Almaty', 'venue': 'Central Stadium',
        'address': 'Satpayev St 29/3, Almaty', 'days': 15, 'hour': 18, 'hours': 2,
        'layout': 'tiers', 'tiers': [
            tier('East stand', 'paid', '3000', 400),
            tier('West stand', 'paid', '5000', 300),
            tier('VIP box', 'paid', '20000', 30),
        ],
        'fill': 0.5, 'refundable': False,
    },
    {
        'key': 'almaty-medeu-ice-show', 'title': 'Medeu Ice Show', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Almaty', 'venue': 'Medeu Skating Rink',
        'address': 'Gornaya St 548, Almaty', 'days': 40, 'hour': 18, 'hours': 2,
        'layout': 'ga', 'price': '9000', 'capacity': 200, 'fill': 0.3, 'status': 'cancelled',
    },
    {
        'key': 'almaty-pitch-day', 'title': 'Almaty Startup Pitch Day', 'category': 'Business',
        'organizer': 'arman.bekov', 'city': 'Almaty', 'venue': 'Esentai Tower Hall',
        'address': 'Al-Farabi Ave 77/7, Almaty', 'days': -7, 'hour': 14, 'hours': 4,
        'layout': 'ga', 'price': '5000', 'capacity': 200, 'fill': 0.75,
    },
    {
        'key': 'almaty-shymbulak-opening', 'title': 'Shymbulak Winter Opening Party', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Almaty', 'venue': 'Shymbulak Resort',
        'address': 'Shymbulak Mountain Resort, Almaty', 'days': 60, 'hour': 16, 'hours': 6,
        'layout': 'ga', 'price': '15000', 'capacity': 500, 'fill': 0, 'status': 'draft',
    },
    {
        'key': 'astana-swan-lake', 'title': 'Ballet "Swan Lake"', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Astana', 'venue': 'Astana Opera',
        'address': 'Kunayev St 1, Astana', 'days': 18, 'hour': 19, 'hours': 3,
        'layout': 'seated', 'rows': 14, 'cols': 24, 'premium_rows': 2, 'vip_rows': 4, 'price': '10000',
        'fill': 0.65, 'bookings': 10,
    },
    {
        'key': 'astana-mozart', 'title': 'Mozart Evening at the Philharmonic', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Astana', 'venue': 'Kazakhconcert Hall',
        'address': 'Tauelsizdik Ave 50, Astana', 'days': -10, 'hour': 19, 'hours': 2,
        'layout': 'seated', 'rows': 8, 'cols': 16, 'premium_rows': 0, 'vip_rows': 2, 'price': '5000',
        'fill': 0.9, 'bookings': 5,
    },
    {
        'key': 'astana-digital-forum', 'title': 'Digital Steppe Forum', 'category': 'Technology',
        'organizer': 'nurlan.zhakupov', 'city': 'Astana', 'venue': 'Astana Hub',
        'address': 'Mangilik El Ave 55/8, Astana', 'days': 30, 'hour': 9, 'hours': 9,
        'layout': 'tiers', 'tiers': [
            tier('Startup', 'paid', '10000', 120),
            tier('Standard', 'paid', '30000', 400),
            tier('Premium', 'paid', '60000', 60, 'Speakers dinner'),
        ],
        'fill': 0.5,
    },
    {
        'key': 'astana-comedy', 'title': 'Astana Comedy Club Live', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Astana', 'venue': 'Kerwen Hall',
        'address': 'Kabanbay Batyr Ave 62, Astana', 'days': 3, 'hour': 20, 'hours': 2,
        'layout': 'ga', 'price': '6000', 'capacity': 180, 'fill': 0.85,
        'promo': ('ASTANA1000', 'fixed', '1000', None),
    },
    {
        'key': 'astana-half-marathon', 'title': 'Astana Half Marathon 2026', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Astana', 'venue': 'Expo 2017 area',
        'address': 'Mangilik El Ave 53/1, Astana', 'days': -21, 'hour': 8, 'hours': 4,
        'layout': 'tiers', 'tiers': [tier('5K', 'paid', '5000', 200), tier('21K', 'paid', '12000', 250)],
        'fill': 0.85,
    },
    {
        'key': 'astana-hockey', 'title': 'Hockey Night at Barys Arena', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Astana', 'venue': 'Barys Arena',
        'address': 'Turan Ave 57, Astana', 'days': 11, 'hour': 19, 'hours': 3,
        'layout': 'tiers', 'tiers': [
            tier('Upper tier', 'paid', '3000', 500),
            tier('Lower tier', 'paid', '7000', 300),
            tier('VIP lodge', 'paid', '25000', 20),
        ],
        'fill': 0.4,
    },
    {
        'key': 'astana-charity-run', 'title': "Charity Run for the Children's Hospital", 'category': 'Sports',
        'organizer': 'aliya.kassymova', 'city': 'Astana', 'venue': 'Central Park',
        'address': 'Turan Ave 1, Astana', 'days': 14, 'hour': 9, 'hours': 3,
        'layout': 'tiers', 'tiers': [tier('Runner (pay what you want)', 'donation', '2000', 300)],
        'fill': 0.5,
    },
    {
        'key': 'astana-pm-bootcamp', 'title': 'Product Management Bootcamp', 'category': 'Education',
        'organizer': 'nurlan.zhakupov', 'city': 'Astana', 'venue': 'Nazarbayev University, Block C3',
        'address': 'Kabanbay Batyr Ave 53, Astana', 'days': 8, 'hour': 10, 'hours': 7,
        'layout': 'ga', 'price': '35000', 'capacity': 40, 'fill': 1.0,
        'waitlist': {'waiting': 12, 'expired': 2, 'converted': 2, 'offered': 1},
    },
    {
        'key': 'astana-science-show', 'title': 'Family Science Show', 'category': 'Education',
        'organizer': 'aliya.kassymova', 'city': 'Astana', 'venue': 'Palace of Schoolchildren',
        'address': 'Respublika Ave 34, Astana', 'days': 5, 'hour': 11, 'hours': 2,
        'layout': 'tiers', 'tiers': [tier('Child', 'paid', '3000', 100), tier('Adult', 'paid', '4500', 100)],
        'fill': 0.6,
    },
    {
        'key': 'astana-food-festival', 'title': 'Astana Food Festival', 'category': 'Business',
        'organizer': 'arman.bekov', 'city': 'Astana', 'venue': 'Khan Shatyr',
        'address': 'Turan Ave 37, Astana', 'days': 45, 'hour': 12, 'hours': 8,
        'layout': 'ga', 'price': '3000', 'capacity': 800, 'fill': 0, 'status': 'pending',
    },
    {
        'key': 'astana-js-meetup', 'title': 'Astana JS Meetup', 'category': 'Technology',
        'organizer': 'nurlan.zhakupov', 'city': 'Astana', 'venue': 'Astana Hub',
        'address': 'Mangilik El Ave 55/8, Astana', 'days': -3, 'hour': 19, 'hours': 2,
        'layout': 'free', 'capacity': 80, 'fill': 0.9,
    },
    {
        'key': 'astana-chamber-seagull', 'title': 'Chamber Theatre: "The Seagull"', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Astana', 'venue': 'Chamber Stage',
        'address': 'Beibitshilik St 10, Astana', 'days': 7, 'hour': 19, 'hours': 2.5,
        'layout': 'chamber', 'price': '4000', 'fill': 0.8,
    },
]  # fmt: skip


def _q(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _bulk_create_keeping(model, objs, field):
    """bulk_create, then restore `field` (an auto_now_add timestamp that
    bulk_create overwrites with now) to the value the object was built with."""
    wanted = [getattr(obj, field) for obj in objs]
    model.objects.bulk_create(objs, batch_size=500)
    for obj, value in zip(objs, wanted, strict=True):
        setattr(obj, field, value)
    model.objects.bulk_update(objs, [field], batch_size=500)


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
        self.past = event.date < self.now
        self.cancelled_event = spec.get('status') == 'cancelled'
        self.registrations = []  # (Registration, plan dict)
        self.payments = []
        self.refunds = []
        self.refund_requests = []
        self.taken_users = set()

    def uuid(self):
        return uuid.UUID(int=self.rng.getrandbits(128), version=4)

    # ----------------------------------------------------------- times ---- #

    def sale_time(self):
        """When a ticket was bought: weeks before the event, never in the future."""
        latest = min(self.now - timedelta(hours=2), self.event.date - timedelta(hours=3))
        return latest - timedelta(minutes=self.rng.randint(0, 40 * 24 * 60))

    # -------------------------------------------------------- inventory ---- #

    def build_inventory(self):
        """Seats / tiers / capacity. Returns (slots, seats_pool)."""
        layout, event, spec = self.spec['layout'], self.event, self.spec
        self.seats, self.tiers = [], []
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
                    sale_end = self.now + timedelta(days=t['sale_end_days'])
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
        self.rng.shuffle(self.seats)

    # --------------------------------------------------------------- run ---- #

    def run(self):
        self.build_inventory()
        self.promo = self.create_promo()
        self.affiliate = self.create_affiliate()
        capacity = self.event.max_participants
        fill = self.spec.get('fill', 0)
        if not fill:
            return
        waitlist = self.spec.get('waitlist', {})
        target = min(round(capacity * fill), capacity) - waitlist.get('offered', 0)

        booked_seats = self.plan_bookings() if self.spec.get('bookings') else 0
        live = max(target - booked_seats, 0)
        buyers = self.rng.sample(self.attendees, k=min(live, len(self.attendees)))
        slots = self.allocate(len(buyers))
        for user, slot in zip(buyers, slots, strict=False):
            self.add_live(user, slot)
        # History rows: tickets that were cancelled; they hold no capacity.
        if not self.is_free_event():
            n = len(buyers)
            for kind, share in (('expired_hold', 0.05), ('failed', 0.03), ('refunded', 0.04)):
                if kind == 'refunded' and not self.event.refundable:
                    continue
                for _ in range(int(n * share)):
                    self.add_history(self.rng.choice(self.attendees), self.allocate(1, history=True)[0], kind)
        self.save_all()
        if waitlist:
            self.create_waitlist(waitlist, buyers)
        if self.past:
            self.create_reviews()

    def is_free_event(self):
        return self.spec['layout'] == 'free'

    def allocate(self, n, history=False):
        """Assign each ticket a seat or a tier (or nothing for GA / free)."""
        if self.seats is not None and self.spec['layout'] in ('seated', 'chamber'):
            if history:
                return [{'seat_zone_from': self.rng.choice(self.all_seats)}]
            return [{'seat': self.seats.pop()} for _ in range(min(n, len(self.seats)))]
        if self.tiers:
            if history:
                return [{'tier': self.rng.choice(self.tiers)}]
            remaining = {t.id: t.quantity for t in self.tiers}
            out = []
            weights = [t.quantity for t in self.tiers]
            for _ in range(n):
                choices = [t for t in self.tiers if remaining[t.id] > 0]
                if not choices:
                    break
                t = self.rng.choices(choices, weights=[weights[self.tiers.index(c)] for c in choices])[0]
                remaining[t.id] -= 1
                out.append({'tier': t})
            return out
        return [{} for _ in range(n)]

    # ------------------------------------------------------ registrations ---- #

    def new_registration(self, user, slot, status):
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
        reg.registered_at = self.sale_time()
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

    def add_live(self, user, slot):
        reg = self.new_registration(user, slot, 'confirmed')
        self.maybe_promo(reg, live=True)
        if self.affiliate is not None and self.rng.random() < 0.08:
            reg.affiliate = self.affiliate
        plan = {'kind': 'confirmed'}
        paid = reg.locked_price is not None
        if self.cancelled_event and paid:
            # Event called off: every ticket was refunded and voided.
            reg.status = 'cancelled'
            plan = {'kind': 'refunded', 'refund_kind': Refund.Kind.EVENT_CANCELLED}
            if reg.promo_code is not None:
                self.promo.times_used -= 1
        elif paid and not self.past and self.rng.random() < 0.04:
            reg.status = 'pending'
            reg.registered_at = self.now - timedelta(minutes=self.rng.randint(1, HOLD_MINUTES - 1))
            reg.seat_held_until = reg.registered_at + timedelta(minutes=HOLD_MINUTES)
            plan = {'kind': 'pending'}
        elif paid:
            roll = self.rng.random()
            if roll < 0.03:
                plan = {'kind': 'partial'}
            elif roll < 0.045 and self.event.refundable and not self.past:
                plan = {'kind': 'confirmed', 'request': 'pending'}
            elif roll < 0.06 and self.event.refundable:
                plan = {'kind': 'confirmed', 'request': 'rejected'}
        if reg.status != 'cancelled' and reg.seat is not None:
            reg.seat.is_available = False
        if reg.status == 'cancelled':
            reg.seat = None
        if self.past and reg.status == 'confirmed' and self.rng.random() < 0.85:
            reg.is_checked_in = True
            reg.checked_in_at = self.event.date + timedelta(minutes=self.rng.randint(-45, 40))
        self.taken_users.add(user.id)
        self.registrations.append((reg, plan))

    def add_history(self, user, slot, kind):
        reg = self.new_registration(user, slot, 'cancelled')
        self.maybe_promo(reg, live=False)
        reg.seat = None  # released when the ticket was voided
        self.registrations.append((reg, {'kind': kind, 'refund_kind': Refund.Kind.CUSTOMER}))

    # ------------------------------------------------------------ money ---- #

    def save_all(self):
        regs = [r for r, _ in self.registrations]
        amounts = {}
        for reg, _ in self.registrations:
            if reg.locked_price is not None:
                amounts[id(reg)] = registration_amount(reg)  # tax, fees and promo as at checkout
        _bulk_create_keeping(Registration, regs, 'registered_at')
        if self.seats is not None and self.spec['layout'] in ('seated', 'chamber'):
            taken = [r.seat_id for r in regs if r.seat_id and r.status in ('pending', 'confirmed')]
            EventSeat.objects.filter(id__in=taken).update(is_available=False)
        if self.promo is not None:
            self.promo.save(update_fields=['times_used'])

        for reg, plan in self.registrations:
            if id(reg) not in amounts:
                continue
            self.add_payment(reg, plan, amounts[id(reg)])
        _bulk_create_keeping(Payment, self.payments, 'created_at')
        _bulk_create_keeping(Refund, self.refunds, 'created_at')
        _bulk_create_keeping(RefundRequest, self.refund_requests, 'created_at')
        self.create_checkins(regs)

    def add_payment(self, reg, plan, amount):
        kind = plan['kind']
        started = reg.registered_at
        session = f'mock_sess_{reg.id}_{int(started.timestamp())}'
        payment = Payment(
            registration=reg,
            amount=amount,
            currency=self.event.currency.lower(),
            method=Payment.METHOD_CARD,
            stripe_checkout_session_id=session,
            provider='mock',
            provider_session_id=session,
            attempt=1,
            created_at=started + timedelta(minutes=1),
        )
        status = {
            'confirmed': 'completed',
            'partial': 'completed',
            'pending': 'pending',
            'expired_hold': 'expired',
            'failed': 'failed',
            'refunded': 'refunded',
        }[kind]
        payment.status = status
        if kind == 'failed':
            payment.provider_payload = {'failure': 'card_declined'}
        if kind in ('partial', 'refunded'):
            latest = min(self.now, self.event.date) - timedelta(hours=1)
            refunded_at = min(started + timedelta(days=self.rng.randint(1, 6)), latest)
            refunded_at = max(refunded_at, started + timedelta(minutes=5))
            if kind == 'partial':
                share = Decimal(self.rng.choice(['0.30', '0.40', '0.50']))
                refund_amount = _q(amount * share)
                reason = 'Partial refund: seat downgrade'
                refund_kind = Refund.Kind.ORGANIZER
            else:
                refund_amount = amount
                refund_kind = plan.get('refund_kind', Refund.Kind.CUSTOMER)
                reason = 'Event cancelled by the organizer' if refund_kind == Refund.Kind.EVENT_CANCELLED else ''
            payment.refunded_amount = refund_amount
            payment.refunded_at = refunded_at
            if kind == 'refunded' and refund_kind == Refund.Kind.CUSTOMER and self.rng.random() < 0.7:
                reason = 'Refund request approved'
                self.refund_requests.append(
                    RefundRequest(
                        registration=reg,
                        status=RefundRequest.STATUS_APPROVED,
                        reason=self.rng.choice(['Cannot attend', 'Plans changed', 'Got sick']),
                        resolved_at=refunded_at,
                        created_at=refunded_at - timedelta(hours=self.rng.randint(2, 30)),
                    )
                )
            elif kind == 'refunded' and refund_kind == Refund.Kind.CUSTOMER:
                refund_kind = Refund.Kind.ORGANIZER
                reason = 'Refunded by the organizer'
            payment.refund_reason = reason
            refund_id = self.uuid()
            self.refunds.append(
                Refund(
                    id=refund_id,
                    payment=payment,
                    amount=refund_amount,
                    currency=self.event.currency.upper(),
                    kind=refund_kind,
                    status=Refund.Status.SUCCEEDED,
                    reason=reason,
                    requested_by=self.organizer if refund_kind != Refund.Kind.CUSTOMER else reg.user,
                    provider='mock',
                    provider_refund_id=f'mock_re_{refund_id.hex[:16]}',
                    idempotency_key=f'refund-{refund_id}',
                    attempts=1,
                    created_at=refunded_at - timedelta(minutes=1),
                    processed_at=refunded_at,
                )
            )
        if plan.get('request'):
            requested = reg.registered_at + timedelta(days=1)
            self.refund_requests.append(
                RefundRequest(
                    registration=reg,
                    status=plan['request'],
                    reason='Cannot attend',
                    organizer_note='Tickets are transferable instead.' if plan['request'] == 'rejected' else '',
                    resolved_at=requested + timedelta(hours=5) if plan['request'] == 'rejected' else None,
                    created_at=requested,
                )
            )
        self.payments.append(payment)

    # ---------------------------------------------------------- bookings ---- #

    def plan_bookings(self):
        """Group bookings on seated events. Returns the seats they hold."""
        held = 0
        statuses = ['confirmed'] * (self.spec['bookings'] - 3) + ['expired', 'refunded']
        statuses.append('confirmed' if self.past else 'holding')
        for status in statuses:
            size = self.rng.randint(2, 6)
            owner = self.rng.choice(self.attendees)
            created = self.sale_time()
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
                held += len(seats)
            if status == 'holding':
                created = self.now - timedelta(minutes=self.rng.randint(1, 8))
                booking.hold_expires_at = created + timedelta(minutes=HOLD_MINUTES)
            booking.save()
            Booking.objects.filter(pk=booking.pk).update(created_at=created)
            seat_rows = []
            for i, seat in enumerate(seats):
                bs = BookingSeat(
                    booking=booking, seat=seat, price=seat_price(self.event, seat), ticket_uuid=self.uuid()
                )
                friend = self.rng.choice(self.attendees)
                if i == 0:
                    bs.attendee_name, bs.claimed_by = owner.get_full_name(), owner
                elif self.rng.random() < 0.6:
                    bs.attendee_name, bs.claimed_by = friend.get_full_name(), friend
                if self.past and status == 'confirmed' and self.rng.random() < 0.8:
                    bs.is_checked_in = True
                    bs.checked_in_at = self.event.date + timedelta(minutes=self.rng.randint(-40, 30))
                seat_rows.append(bs)
            BookingSeat.objects.bulk_create(seat_rows)
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
            if status == 'refunded':
                booking.refunded_at = min(created + timedelta(days=2), self.now - timedelta(hours=1))
                booking.refund_reason = 'Group could not attend'
                payment.refunded_amount = amount
                payment.refunded_at = booking.refunded_at
                payment.refund_reason = booking.refund_reason
            booking.save(update_fields=['amount_paid', 'refunded_at', 'refund_reason'])
            payment.save()
            Payment.objects.filter(pk=payment.pk).update(created_at=created + timedelta(minutes=1))
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
                    provider_refund_id=f'mock_re_{refund_id.hex[:16]}',
                    attempts=1,
                    processed_at=booking.refunded_at,
                )
            self.cmd.booking_log.append(booking.pk)
        return held

    # --------------------------------------------- check-in, waitlist, reviews ---- #

    def create_checkins(self, regs):
        checked = [r for r in regs if r.is_checked_in]
        if not checked and not self.past:
            return
        main = CheckInList.objects.create(event=self.event, name='Main entrance', is_default=True)
        vip = CheckInList.objects.create(event=self.event, name='VIP entrance', color='#d97706')
        logs = []
        for reg in checked:
            vip_ticket = (reg.ticket_type is not None and 'VIP' in reg.ticket_type.name) or (
                reg.seat_id is not None and reg.seat.price_zone in ('vip', 'premium')
            )
            logs.append(
                CheckInLog(
                    checkin_list=vip if vip_ticket else main,
                    registration=reg,
                    scanned_by=self.organizer,
                    created_at=reg.checked_in_at,
                )
            )
        _bulk_create_keeping(CheckInLog, logs, 'created_at')

    def create_waitlist(self, spec, buyers):
        free_users = [u for u in self.attendees if u.id not in self.taken_users]
        entries = []
        for status in ('waiting', 'expired', 'offered'):
            for _ in range(spec.get(status, 0)):
                user = free_users.pop(self.rng.randrange(len(free_users)))
                entry = WaitlistEntry(user=user, event=self.event, status=status)
                if status == 'expired':
                    entry.offered_at = self.now - timedelta(days=self.rng.randint(1, 4))
                    entry.offer_expires_at = entry.offered_at + timedelta(minutes=30)
                if status == 'offered':
                    entry.offered_at = self.now - timedelta(minutes=5)
                    entry.offer_expires_at = self.now + timedelta(minutes=25)
                entries.append(entry)
        for user in self.rng.sample(buyers, k=min(spec.get('converted', 0), len(buyers))):
            entries.append(WaitlistEntry(user=user, event=self.event, status='converted'))
        WaitlistEntry.objects.bulk_create(entries)

    def create_reviews(self):
        attended = [r for r, _ in self.registrations if r.is_checked_in]
        reviews = []
        for reg in self.rng.sample(attended, k=int(len(attended) * 0.3)):
            rating = self.rng.choices([5, 4, 3, 2, 1], weights=[45, 35, 12, 5, 3])[0]
            reviews.append(
                Review(user=reg.user, event=self.event, rating=rating, comment=self.rng.choice(REVIEW_COMMENTS[rating]))
            )
        Review.objects.bulk_create(reviews)

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
    help = 'Seed realistic Kazakhstan demo data (Almaty / Astana, KZT). DJANGO_DEBUG=1 only; idempotent.'

    def add_arguments(self, parser):
        parser.add_argument('--attendees', type=int, default=600, help='Number of attendee accounts (default 600).')

    def handle(self, *args, **options):
        # Demo accounts have a publicly known password — never on a real deployment.
        if not settings.DEBUG:
            raise CommandError('seed_demo_kz creates demo accounts; run it only with DJANGO_DEBUG=1.')
        started = time.monotonic()
        self.now = timezone.now()
        self.booking_log = []
        self.password_hash = make_password(DEMO_PASSWORD)

        categories = self.seed_categories()
        organizers = self.seed_organizers()
        attendees = self.seed_attendees(options['attendees'])

        created, existing = 0, 0
        for spec in EVENTS:
            with transaction.atomic():
                event, is_new = self.get_or_create_event(spec, organizers, categories)
                if is_new:
                    EventSeeder(self, event, spec, attendees, organizers[spec['organizer']]).run()
                    created += 1
                else:
                    existing += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'seed_demo_kz: {created} events created, {existing} already present '
                f'({len(organizers)} organizers, {len(attendees)} attendees) in {time.monotonic() - started:.1f}s.'
            )
        )
        if created:
            self.stdout.write(f'Demo logins: kz_<name> / {DEMO_PASSWORD}, e.g. kz_dana.abenova (organizer).')

    # ------------------------------------------------------------ people ---- #

    def seed_categories(self):
        out = {}
        for name, description, icon in CATEGORIES:
            out[name], _ = Category.objects.get_or_create(
                name=name, defaults={'description': description, 'icon': icon}
            )
        return out

    def _ensure_users(self, specs):
        """specs: list of dicts (username, first_name, last_name, role, city, bio, phone)."""
        existing = {u.username: u for u in User.objects.filter(username__in=[s['username'] for s in specs])}
        new = [
            User(
                username=s['username'],
                email=f'{s["username"]}@{EMAIL_DOMAIN}',
                first_name=s['first_name'],
                last_name=s['last_name'],
                password=self.password_hash,
                date_joined=self.now - timedelta(days=s['joined_days_ago']),
            )
            for s in specs
            if s['username'] not in existing
        ]
        User.objects.bulk_create(new, batch_size=500)  # bulk: no post_save, profiles below
        users = {u.username: u for u in User.objects.filter(username__in=[s['username'] for s in specs])}
        have_profile = set(UserProfile.objects.filter(user__in=users.values()).values_list('user_id', flat=True))
        UserProfile.objects.bulk_create(
            [
                UserProfile(
                    user=users[s['username']], role=s['role'], location=s['city'], bio=s['bio'], phone=s['phone']
                )
                for s in specs
                if users[s['username']].id not in have_profile
            ],
            batch_size=500,
        )
        return [users[s['username']] for s in specs]

    def seed_organizers(self):
        rng = random.Random(f'{SEED}:organizers')  # noqa: S311 - demo data, not security
        specs = [
            {
                'username': f'kz_{key}',
                'first_name': first,
                'last_name': last,
                'role': 'organizer',
                'city': city,
                'bio': bio,
                'phone': f'+7 701 {rng.randint(100, 999)} {rng.randint(10, 99)} {rng.randint(10, 99)}',
                'joined_days_ago': rng.randint(200, 700),
            }
            for key, first, last, city, bio in ORGANIZERS
        ]
        users = self._ensure_users(specs)
        return {key: user for (key, *_), user in zip(ORGANIZERS, users, strict=True)}

    def seed_attendees(self, count):
        rng = random.Random(f'{SEED}:attendees')  # noqa: S311 - demo data, not security
        # Never reuse an organizer's user name: organizers must not hold tickets.
        specs, seen = [], {f'kz_{key}' for key, *_ in ORGANIZERS}
        while len(specs) < count:
            female = rng.random() < 0.5
            first = rng.choice(FEMALE_FIRST if female else MALE_FIRST)
            male_last, female_last = rng.choice(SURNAMES)
            last = female_last if female else male_last
            base = f'kz_{first}.{last}'.lower()
            username, n = base, 1
            while username in seen:
                n += 1
                username = f'{base}{n}'
            seen.add(username)
            specs.append(
                {
                    'username': username,
                    'first_name': first,
                    'last_name': last,
                    'role': 'attendee',
                    'city': rng.choice(['Almaty', 'Almaty', 'Astana', 'Astana', 'Shymkent', 'Karaganda']),
                    'bio': '',
                    'phone': f'+7 7{rng.choice(["01", "02", "05", "07", "47", "77"])} '
                    f'{rng.randint(100, 999)} {rng.randint(10, 99)} {rng.randint(10, 99)}',
                    'joined_days_ago': rng.randint(1, 400),
                }
            )
        return self._ensure_users(specs)

    # ------------------------------------------------------------ events ---- #

    def get_or_create_event(self, spec, organizers, categories):
        organizer = organizers[spec['organizer']]
        event = Event.objects.filter(title=spec['title'], organizer=organizer).first()
        if event is not None:
            return event, False
        today = self.now.astimezone(KZ_TZ).date()
        day = today + timedelta(days=spec['days'])
        start = datetime(day.year, day.month, day.day, spec['hour'], 0, tzinfo=KZ_TZ).astimezone(UTC)
        end = start + timedelta(hours=spec['hours'])
        status = spec.get('status') or ('completed' if end < self.now else 'published')
        event = Event.objects.create(
            title=spec['title'],
            description=(
                f'{spec["title"]} at {spec["venue"]}, {spec["city"]}. Tickets in tenge (KZT); '
                'e-tickets with QR code, entry from one hour before the start.'
            ),
            organizer=organizer,
            category=categories[spec['category']],
            date=start,
            end_date=end,
            location=f'{spec["venue"]}, {spec["city"]}',
            address=spec['address'],
            price=Decimal(spec.get('price', '0')),
            max_participants=spec.get('capacity', 100),
            status=status,
            currency='KZT',
            tax_percent=Decimal('0'),  # prices include 12% VAT
            service_fee_percent=Decimal(spec.get('service_fee', '0')),
            refundable=spec.get('refundable', True),
        )
        return event, True

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
