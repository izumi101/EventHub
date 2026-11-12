"""Hand-picked showcase events for a live demo (`manage.py seed_showcase`).

Eighteen events in Almaty and Astana owned by the demo `organizer` account:
mostly KZT (paid through Freedom Pay in demo mode), two in USD (Stripe /
mock), two free, a few with seat maps or ticket tiers, one waiting for
moderation so the admin review flow can be shown. No registrations are
created: the audience sees an empty, clean catalogue and buys live.

Idempotent: an event that already exists (same title and organizer) is left
as it is. Refuses to run unless DJANGO_DEBUG=1, like the other seed commands.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import UserProfile
from common.choices import EventStatusChoices, RoleChoices
from events.models import Category, Event, EventSeat, SeatMap, TicketType

# Kazakhstan has one time zone, UTC+5, since 1 March 2024.
KZ_TZ = dt_timezone(timedelta(hours=5), 'Asia/Almaty')

CATEGORIES = [
    ('Music', 'Concerts, jam sessions, and live performances.', 'music'),
    ('Technology', 'Conferences, meetups, and hands-on workshops.', 'laptop'),
    ('Business', 'Networking, startup, and finance events.', 'briefcase'),
    ('Education', 'Lectures, bootcamps, and learning sessions.', 'book'),
    ('Sports', 'Tournaments, outdoor activities, and fitness events.', 'trophy'),
    ('Theatre', 'Opera, ballet, drama and stand-up.', 'theater'),
]


@dataclass(frozen=True)
class Tier:
    name: str
    price: str
    quantity: int
    kind: str = TicketType.KIND_PAID
    description: str = ''


@dataclass(frozen=True)
class Spec:
    title: str
    category: str
    city: str
    venue: str
    address: str
    days: int  # from today, Kazakhstan time
    hour: int
    hours: int
    description: str
    price: str = '0'
    currency: str = 'KZT'
    capacity: int = 200
    # (rows, cols, premium rows, vip rows); the rest of the rows are standard.
    seat_map: tuple[int, int, int, int] | None = None
    tiers: tuple[Tier, ...] = field(default_factory=tuple)
    status: str = EventStatusChoices.PUBLISHED
    is_online: bool = False
    online_link: str = ''
    service_fee: str = '0'


EVENTS = [
    Spec(
        'Almaty Product Conference',
        'Technology',
        'Almaty',
        'SmArt.Point',
        'Zheltoksan St 115, Almaty',
        days=14,
        hour=10,
        hours=8,
        price='5000',
        capacity=150,
        description='Product managers and engineers from Almaty startups share how they ship. '
        'Tickets are paid in tenge through Freedom Pay, by card or by scanning a QR code.',
    ),
    Spec(
        'Dimash Qudaibergen: Stranger Tour',
        'Music',
        'Almaty',
        'Almaty Arena',
        'Momyshuly St 6, Almaty',
        days=21,
        hour=19,
        hours=3,
        price='25000',
        seat_map=(10, 14, 2, 3),
        description='An evening of classical crossover and pop with a full orchestra. Seated hall: choose your seat '
        'on the map, premium rows are closest to the stage.',
    ),
    Spec(
        'Kazakhstan Philharmonic: Kurmangazy Night',
        'Music',
        'Almaty',
        'Kazakh State Philharmonic',
        'Kaldayakov St 35, Almaty',
        days=9,
        hour=19,
        hours=2,
        price='8000',
        seat_map=(8, 12, 1, 2),
        description='The Kurmangazy Orchestra of Folk Instruments plays kuis and new works for dombra and kobyz.',
    ),
    Spec(
        'Swan Lake at Astana Opera',
        'Theatre',
        'Astana',
        'Astana Opera',
        'Kunayev St 1, Astana',
        days=17,
        hour=19,
        hours=3,
        price='15000',
        seat_map=(10, 16, 2, 3),
        description="Tchaikovsky's ballet in three acts with the Astana Opera ballet company and orchestra.",
    ),
    Spec(
        'Abai: Opera in Two Acts',
        'Theatre',
        'Almaty',
        'Abai Kazakh National Opera and Ballet Theatre',
        'Kabanbay Batyr St 110, Almaty',
        days=28,
        hour=19,
        hours=3,
        price='9000',
        capacity=300,
        description='The national opera by Akhmet Zhubanov and Latif Hamidi about the poet Abai Kunanbayev.',
    ),
    Spec(
        'Astana Hub Demo Day',
        'Business',
        'Astana',
        'Astana Hub',
        'Mangilik El Ave 55/8, Astana',
        days=11,
        hour=14,
        hours=4,
        capacity=250,
        description='Twenty startups from the Astana Hub accelerator pitch to investors. Free entry with registration.',
    ),
    Spec(
        'Fintech Forum Kazakhstan',
        'Business',
        'Almaty',
        'Rixos Almaty',
        'Seifullin Ave 506/99, Almaty',
        days=35,
        hour=9,
        hours=9,
        capacity=400,
        service_fee='3',
        description='Payments, open banking and digital tenge: two stages, a networking lunch and a partner expo.',
        tiers=(
            Tier('Standard', '30000', 300, description='Both stages and the expo'),
            Tier('Business', '75000', 80, description='Front rows, networking lunch, speaker Q&A'),
            Tier('Student', '0', 20, kind=TicketType.KIND_FREE, description='With a valid student ID'),
        ),
    ),
    Spec(
        'Angular & Django Meetup',
        'Technology',
        'Almaty',
        'Kolesa Group Office',
        'Nazarbayev Ave 50, Almaty',
        days=6,
        hour=19,
        hours=3,
        capacity=80,
        description='Two talks: typed API clients generated from OpenAPI, and WebSockets with Django Channels.',
    ),
    Spec(
        'Python Bootcamp: Data Analysis',
        'Education',
        'Astana',
        'Nazarbayev University',
        'Kabanbay Batyr Ave 53, Astana',
        days=24,
        hour=10,
        hours=6,
        price='12000',
        capacity=40,
        description='A one-day hands-on course: pandas, SQL on real data and a small dashboard by the evening.',
    ),
    Spec(
        'Almaty Marathon 2026: 10 km',
        'Sports',
        'Almaty',
        'Republic Square',
        'Satpayev St 1, Almaty',
        days=30,
        hour=8,
        hours=4,
        price='7000',
        capacity=500,
        description='The 10 km distance of the Almaty Marathon through the city centre. '
        'Bib, chip timing and medal included.',
    ),
    Spec(
        'Barys Astana vs Avangard Omsk',
        'Sports',
        'Astana',
        'Barys Arena',
        'Turan Ave 57, Astana',
        days=8,
        hour=19,
        hours=3,
        price='4000',
        seat_map=(12, 16, 2, 2),
        description='KHL regular season match. Choose your seat on the map; premium rows are by the ice.',
    ),
    Spec(
        'Shymbulak Freeride Weekend',
        'Sports',
        'Almaty',
        'Shymbulak Mountain Resort',
        'Medeu District, Almaty',
        days=45,
        hour=9,
        hours=8,
        price='18000',
        capacity=60,
        description='Guided off-piste day with avalanche safety briefing, lift pass and lunch at the resort.',
    ),
    Spec(
        'Stand-up Almaty: Open Mic Special',
        'Theatre',
        'Almaty',
        'Almaty Stand Up Club',
        'Abylai Khan Ave 79, Almaty',
        days=5,
        hour=20,
        hours=2,
        price='5000',
        capacity=120,
        description='Eight comedians, new material in Kazakh and Russian. 18+.',
    ),
    Spec(
        'Women in Tech Astana',
        'Technology',
        'Astana',
        'Palace of Independence',
        'Tauelsizdik Ave 52, Astana',
        days=19,
        hour=11,
        hours=6,
        capacity=300,
        description='Talks and mentoring sessions for women building careers in engineering and product.',
        tiers=(
            Tier('Free entry', '0', 250, kind=TicketType.KIND_FREE),
            Tier('Supporter', '0', 50, kind=TicketType.KIND_DONATION, description='Pay what you want'),
        ),
    ),
    Spec(
        'Global AI Summit (online)',
        'Technology',
        'Online',
        'Online',
        '',
        days=26,
        hour=17,
        hours=5,
        price='49',
        currency='USD',
        capacity=1000,
        is_online=True,
        online_link='https://meet.example.com/ai-summit',
        description='Speakers from Europe and Asia on applied AI. Paid in USD through Stripe; '
        'the link is sent with the ticket.',
    ),
    Spec(
        'International Startup Pitch Night',
        'Business',
        'Astana',
        'Astana International Financial Centre',
        'Mangilik El Ave 55/20, Astana',
        days=13,
        hour=18,
        hours=3,
        price='25',
        currency='USD',
        capacity=150,
        description='Founders from Central Asia pitch in English to international funds. Paid in USD through Stripe.',
    ),
    Spec(
        'Jazz on the Roof',
        'Music',
        'Almaty',
        'Esentai Gallery Rooftop',
        'Al-Farabi Ave 77/8, Almaty',
        days=16,
        hour=20,
        hours=3,
        price='12000',
        capacity=90,
        description='An evening of jazz standards with the Almaty Jazz Quartet above the city lights.',
    ),
    Spec(
        'Astana Craft Fair',
        'Education',
        'Astana',
        'EXPO Congress Centre',
        'Mangilik El Ave 53/1, Astana',
        days=40,
        hour=11,
        hours=7,
        price='2000',
        capacity=600,
        status=EventStatusChoices.PENDING,
        description='Makers, workshops and local food. Waiting for the platform moderator to approve it.',
    ),
]


def create_seat_map(event, rows, cols, premium_rows, vip_rows):
    """Premium rows first, then VIP, then standard (the layout EventViewSet.create_seat_map uses)."""
    zones = {
        'premium': list(range(1, premium_rows + 1)),
        'vip': list(range(premium_rows + 1, premium_rows + vip_rows + 1)),
        'standard': list(range(premium_rows + vip_rows + 1, rows + 1)),
    }
    seat_map = SeatMap.objects.create(
        event=event, rows=rows, cols=cols, layout={'price_zones': {name: rws for name, rws in zones.items() if rws}}
    )
    EventSeat.objects.bulk_create(
        EventSeat(
            seat_map=seat_map,
            row=row,
            col=col,
            price_zone=next(name for name, rws in zones.items() if row in rws),
        )
        for row in range(1, rows + 1)
        for col in range(1, cols + 1)
    )
    event.max_participants = rows * cols
    event.save(update_fields=['max_participants'])


class Command(BaseCommand):
    help = 'Create 18 hand-picked demo events in Almaty and Astana for the demo organizer (DJANGO_DEBUG=1 only).'

    def add_arguments(self, parser):
        parser.add_argument('--organizer', default='organizer', help='Username that owns the events.')

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('seed_showcase creates demo content; run it only with DJANGO_DEBUG=1.')
        try:
            organizer = User.objects.get(username=options['organizer'])
        except User.DoesNotExist:
            raise CommandError(f'User "{options["organizer"]}" does not exist; run seed_data first.') from None

        with transaction.atomic():
            profile, _ = UserProfile.objects.get_or_create(user=organizer)
            if profile.role != RoleChoices.ORGANIZER:
                profile.role = RoleChoices.ORGANIZER
                profile.save(update_fields=['role'])
            categories = {
                name: Category.objects.update_or_create(name=name, defaults={'description': desc, 'icon': icon})[0]
                for name, desc, icon in CATEGORIES
            }
            created = sum(self.create_event(spec, organizer, categories) for spec in EVENTS)

        self.stdout.write(
            self.style.SUCCESS(f'seed_showcase: {created} events created, {len(EVENTS) - created} already present.')
        )

    def create_event(self, spec: Spec, organizer, categories) -> bool:
        if Event.objects.filter(title=spec.title, organizer=organizer).exists():
            return False
        today = timezone.now().astimezone(KZ_TZ).date()
        day = today + timedelta(days=spec.days)
        start = datetime(day.year, day.month, day.day, spec.hour, 0, tzinfo=KZ_TZ).astimezone(UTC)
        event = Event.objects.create(
            title=spec.title,
            description=spec.description,
            organizer=organizer,
            category=categories[spec.category],
            date=start,
            end_date=start + timedelta(hours=spec.hours),
            location=spec.venue if spec.is_online else f'{spec.venue}, {spec.city}',
            address=spec.address,
            price=Decimal(spec.price),
            max_participants=spec.capacity,
            status=spec.status,
            currency=spec.currency,
            is_online=spec.is_online,
            online_link=spec.online_link,
            service_fee_percent=Decimal(spec.service_fee),
            tax_percent=Decimal('0'),  # KZT prices include 12% VAT
        )
        if spec.seat_map:
            create_seat_map(event, *spec.seat_map)
        TicketType.objects.bulk_create(
            TicketType(
                event=event,
                name=tier.name,
                description=tier.description,
                kind=tier.kind,
                price=Decimal(tier.price),
                quantity=tier.quantity,
                order=position,
            )
            for position, tier in enumerate(spec.tiers)
        )
        return True
