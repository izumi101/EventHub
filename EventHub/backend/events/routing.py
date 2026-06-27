from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/seats/(?P<event_id>\d+)/$', consumers.SeatMapConsumer.as_asgi()),
]
