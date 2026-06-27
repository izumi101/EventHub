"""
ASGI config for eventhub_backend.

Handles both HTTP (Django REST) and WebSocket (Django Channels) connections.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eventhub_backend.settings')

# Must be initialised before importing Channels routers (which trigger app registry).
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from events.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    # Regular HTTP → Django REST Framework
    'http': django_asgi_app,

    # WebSocket → Django Channels (seat-map real-time updates)
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
