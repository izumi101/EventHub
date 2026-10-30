"""JWT authentication for WebSockets.

Browsers can't set headers on a WebSocket, and a token in the URL ends up in
server logs. The SPA therefore offers two subprotocols, ['eventhub.jwt',
'<access token>']; this middleware turns a valid token into scope['user'] and
the consumer answers with the 'eventhub.jwt' subprotocol.
"""

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware

JWT_SUBPROTOCOL = 'eventhub.jwt'


@database_sync_to_async
def _user_for(token: str):
    from django.contrib.auth.models import User
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    try:
        user_id = AccessToken(token)['user_id']
    except (TokenError, KeyError):
        return None
    return User.objects.filter(pk=user_id, is_active=True).first()


class JwtSubprotocolAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        protocols = scope.get('subprotocols') or []
        if len(protocols) >= 2 and protocols[0] == JWT_SUBPROTOCOL:
            user = await _user_for(protocols[1])
            if user is not None:
                scope = dict(scope, user=user)
        return await super().__call__(scope, receive, send)
