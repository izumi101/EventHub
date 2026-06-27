from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import UserProfile
from events.models import Category, Event, Registration
from payments.models import Payment


class Command(BaseCommand):
    help = 'Seed EventHub with reproducible development data.'

    def add_arguments(self, parser):
        parser.add_argument('--noinput', action='store_true', help='Run without prompts.')

    def handle(self, *args, **options):
        users = self.seed_users()
        categories = self.seed_categories()
        events = self.seed_events(users, categories)
        self.seed_registrations(users, events)

        self.stdout.write(self.style.SUCCESS(
            f'Seed data ready: {len(users)} users, {len(categories)} categories, {len(events)} events.'
        ))
        self.stdout.write('Demo logins: admin/admin123, organizer/password123, attendee/password123')

    def seed_users(self):
        specs = [
            {
                'username': 'admin',
                'email': 'admin@eventhub.local',
                'password': 'admin123',
                'first_name': 'EventHub',
                'last_name': 'Admin',
                'is_staff': True,
                'is_superuser': True,
                'profile': {'bio': 'Platform administrator', 'location': 'Almaty'},
            },
            {
                'username': 'organizer',
                'email': 'organizer@eventhub.local',
                'password': 'password123',
                'first_name': 'Aruzhan',
                'last_name': 'Organizer',
                'profile': {'bio': 'Creates community and tech events.', 'phone': '+7 777 100 2000', 'location': 'Almaty'},
            },
            {
                'username': 'attendee',
                'email': 'attendee@eventhub.local',
                'password': 'password123',
                'first_name': 'Dias',
                'last_name': 'Attendee',
                'profile': {'bio': 'Likes discovering local events.', 'phone': '+7 777 300 4000', 'location': 'Astana'},
            },
        ]

        users = {}
        for spec in specs:
            profile_data = spec.pop('profile')
            password = spec.pop('password')
            username = spec.pop('username')
            user, created = User.objects.get_or_create(username=username, defaults=spec)
            for field, value in spec.items():
                setattr(user, field, value)
            if created:
                user.set_password(password)
            user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            for field, value in profile_data.items():
                setattr(profile, field, value)
            profile.save()
            users[username] = user
        return users

    def seed_categories(self):
        specs = [
            ('Technology', 'Conferences, meetups, and hands-on workshops.', 'laptop'),
            ('Business', 'Networking, startup, and finance events.', 'briefcase'),
            ('Education', 'Lectures, bootcamps, and learning sessions.', 'book'),
            ('Music', 'Concerts, jam sessions, and live performances.', 'music'),
            ('Sports', 'Tournaments, outdoor activities, and fitness events.', 'trophy'),
        ]

        categories = {}
        for name, description, icon in specs:
            category, _ = Category.objects.update_or_create(
                name=name,
                defaults={'description': description, 'icon': icon},
            )
            categories[name] = category
        return categories

    def seed_events(self, users, categories):
        now = timezone.now()
        specs = [
            {
                'title': 'Angular Meetup Almaty',
                'description': 'A practical meetup about Angular components, routing, and API integration.',
                'category': categories['Technology'],
                'date': now + timedelta(days=10),
                'end_date': now + timedelta(days=10, hours=3),
                'location': 'KBTU, Almaty',
                'address': 'Tole Bi Street 59, Almaty',
                'price': Decimal('0.00'),
                'max_participants': 120,
                'is_online': False,
                'online_link': '',
            },
            {
                'title': 'Startup Pitch Night',
                'description': 'Founders pitch products, meet mentors, and collect feedback from the community.',
                'category': categories['Business'],
                'date': now + timedelta(days=18),
                'end_date': now + timedelta(days=18, hours=2),
                'location': 'Astana Hub',
                'address': 'Mangilik El Avenue 55/8, Astana',
                'price': Decimal('15.00'),
                'max_participants': 80,
                'is_online': False,
                'online_link': '',
            },
            {
                'title': 'Online Django REST Workshop',
                'description': 'Build and test a Django REST Framework API with JWT authentication.',
                'category': categories['Education'],
                'date': now + timedelta(days=25),
                'end_date': now + timedelta(days=25, hours=4),
                'location': 'Online',
                'address': '',
                'price': Decimal('10.00'),
                'max_participants': 200,
                'is_online': True,
                'online_link': 'https://meet.example.com/eventhub-drf',
            },
        ]

        events = {}
        for spec in specs:
            title = spec.pop('title')
            defaults = {
                **spec,
                'organizer': users['organizer'],
                'status': 'published',
            }
            event = Event.objects.filter(title=title, organizer=users['organizer']).first()
            if event is None:
                event = Event.objects.create(title=title, **defaults)
            else:
                for field, value in defaults.items():
                    setattr(event, field, value)
                event.save()
            events[title] = event
        return events

    def seed_registrations(self, users, events):
        free_registration, _ = Registration.objects.update_or_create(
            user=users['attendee'],
            event=events['Angular Meetup Almaty'],
            defaults={'status': 'confirmed', 'notes': 'Excited to join the Angular meetup.'},
        )
        paid_registration, _ = Registration.objects.update_or_create(
            user=users['attendee'],
            event=events['Startup Pitch Night'],
            defaults={'status': 'pending', 'notes': 'Interested in the pitch session.'},
        )
        Payment.objects.update_or_create(
            registration=paid_registration,
            defaults={
                'amount': paid_registration.event.price,
                'currency': 'usd',
                'status': 'pending',
            },
        )
        return [free_registration, paid_registration]
