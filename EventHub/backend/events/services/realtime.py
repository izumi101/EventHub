"""WebSocket broadcasts for live seat-map updates."""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from ..models import EventSeat

logger = logging.getLogger(__name__)


def broadcast_seat_update(seat: EventSeat):
    """Push seat availability change to all WebSocket clients watching this event."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        group_name = f'seat_map_{seat.seat_map.event_id}'
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'seat.update',
                'seat_id': seat.id,
                'is_available': seat.is_available,
                'price_zone': seat.price_zone,
            },
        )
    except Exception:
        # Never let a broadcast failure break the purchase flow, but make it
        # visible: open seat maps go stale until the next snapshot.
        logger.warning('Seat update broadcast failed for seat %s', seat.id, exc_info=True)
