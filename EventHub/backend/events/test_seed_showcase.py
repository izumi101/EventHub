from io import StringIO

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from events.management.commands.seed_showcase import EVENTS
from events.management.commands.seed_showcase import Command as SeedShowcaseCommand
from events.models import Event, EventSeat, TicketType


@override_settings(DEBUG=True)
class SeedShowcaseTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user('organizer', 'organizer@example.com', 'Str0ng-pass!')

    def run_command(self):
        out = StringIO()
        call_command('seed_showcase', stdout=out)
        return out.getvalue()

    def test_creates_every_event_once(self):
        self.assertIn(f'{len(EVENTS)} events created', self.run_command())
        self.assertIn(f'0 events created, {len(EVENTS)} already present', self.run_command())
        self.assertEqual(Event.objects.filter(organizer=self.organizer).count(), len(EVENTS))

    def test_organizer_role_and_inventory(self):
        self.run_command()
        self.organizer.profile.refresh_from_db()
        self.assertEqual(self.organizer.profile.role, 'organizer')
        seated = Event.objects.get(title='Swan Lake at Astana Opera')
        self.assertEqual(seated.max_participants, 10 * 16)
        self.assertEqual(EventSeat.objects.filter(seat_map__event=seated).count(), 160)
        self.assertEqual(
            EventSeat.objects.filter(seat_map__event=seated, price_zone='premium').values('row').distinct().count(), 2
        )
        self.assertEqual(TicketType.objects.filter(event__title='Fintech Forum Kazakhstan').count(), 3)
        self.assertEqual(Event.objects.get(title='Almaty Product Conference').currency, 'KZT')
        self.assertEqual(Event.objects.filter(status='pending').count(), 1)

    @override_settings(DEBUG=False)
    def test_refuses_without_debug(self):
        with self.assertRaises(CommandError):
            self.run_command()

    @override_settings(DEBUG=False, PAYMENT_PROVIDERS_ENABLED=['freedompay'])
    def test_demo_deployment_without_stripe_gets_only_sellable_events(self):
        out = StringIO()
        call_command('seed_showcase', '--i-know-this-is-a-demo', stdout=out)
        unpayable = [spec for spec in EVENTS if not SeedShowcaseCommand.payable(spec)]
        self.assertTrue(unpayable)
        self.assertIn(f'Skipped {len(unpayable)} paid events', out.getvalue())
        self.assertEqual(Event.objects.count(), len(EVENTS) - len(unpayable))
        self.assertFalse(Event.objects.exclude(currency='KZT').exclude(price=0).exists())
