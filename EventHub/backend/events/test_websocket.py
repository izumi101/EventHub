from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from common.ws_testing import WebsocketCommunicator
from eventhub_backend.asgi import application
from events.models import Event, EventSeat, SeatMap

IN_MEMORY = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}


@override_settings(CHANNEL_LAYERS=IN_MEMORY, ALLOWED_HOSTS=['localhost'])
class SeatMapSocketTests(TransactionTestCase):
    def setUp(self):
        self.organizer = User.objects.create_user('org', 'org@example.com', 'Str0ng-pass!')
        self.draft = Event.objects.create(
            title='Draft',
            description='d',
            organizer=self.organizer,
            location='x',
            date=timezone.now() + timedelta(days=3),
            status='draft',
        )
        seat_map = SeatMap.objects.create(event=self.draft, rows=1, cols=1)
        EventSeat.objects.create(seat_map=seat_map, row=1, col=1)

    async def connect(self, protocols=None):
        communicator = WebsocketCommunicator(
            application,
            f'/ws/seats/{self.draft.id}/',
            headers=[(b'origin', b'http://localhost'), (b'host', b'localhost')],
            subprotocols=protocols,
        )
        connected, subprotocol = await communicator.connect()
        return communicator, connected, subprotocol

    async def test_anonymous_cannot_watch_a_draft(self):
        communicator, connected, _ = await self.connect()
        self.assertFalse(connected)

    async def test_organizer_authenticates_with_the_jwt_subprotocol(self):
        token = str(AccessToken.for_user(self.organizer))
        communicator, connected, subprotocol = await self.connect(['eventhub.jwt', token])
        self.assertTrue(connected)
        self.assertEqual(subprotocol, 'eventhub.jwt')
        message = await communicator.receive_json_from()
        self.assertEqual(message['type'], 'snapshot')
        self.assertEqual(len(message['seats']), 1)
        await communicator.disconnect()

    async def test_invalid_token_is_anonymous(self):
        communicator, connected, _ = await self.connect(['eventhub.jwt', 'not-a-jwt'])
        self.assertFalse(connected)
