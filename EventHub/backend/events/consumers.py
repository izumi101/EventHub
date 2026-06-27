"""
WebSocket consumers for real-time seat-map updates.

Each seat-map page joins the group  `seat_map_{event_id}`.
When a seat changes availability (reserved / released) the backend broadcasts
to the whole group so every connected browser sees the update instantly.
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class SeatMapConsumer(AsyncWebsocketConsumer):
    """
    ws://host/ws/seats/{event_id}/

    On connect  → join group seat_map_{event_id}, send current seat snapshot.
    On message  → ignored (read-only channel from client perspective).
    On disconnect → leave group.

    Seat updates are pushed via channel_layer.group_send() from Django views /
    services whenever a seat changes state.
    """

    async def connect(self):
        self.event_id = self.scope['url_route']['kwargs']['event_id']
        self.group_name = f'seat_map_{self.event_id}'

        # Join broadcast group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send full seat snapshot so the client doesn't need a separate HTTP call
        snapshot = await self._get_seat_snapshot()
        await self.send(text_data=json.dumps({
            'type': 'snapshot',
            'seats': snapshot,
        }))
        logger.debug('WS connect: event=%s group=%s', self.event_id, self.group_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.debug('WS disconnect: event=%s code=%s', self.event_id, close_code)

    # ── Receive message from WebSocket client (ignored — read-only for now)
    async def receive(self, text_data=None, bytes_data=None):
        pass

    # ── Receive broadcast from channel layer → forward to WebSocket client
    async def seat_update(self, event):
        """
        Handler for group_send type='seat.update'.
        Broadcasts a single seat state change to this client.
        """
        await self.send(text_data=json.dumps({
            'type': 'seat_update',
            'seat_id': event['seat_id'],
            'is_available': event['is_available'],
            'price_zone': event.get('price_zone', 'standard'),
        }))

    # ── DB helpers (run in threadpool)
    @database_sync_to_async
    def _get_seat_snapshot(self):
        from .models import SeatMap
        try:
            seat_map = SeatMap.objects.get(event_id=self.event_id)
            return [
                {
                    'id': s.id,
                    'row': s.row,
                    'col': s.col,
                    'price_zone': s.price_zone,
                    'is_available': s.is_available,
                }
                for s in seat_map.seats.all()
            ]
        except SeatMap.DoesNotExist:
            return []
