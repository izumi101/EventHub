"""WebSocket test client for the ASGI app.

channels.testing provides one, but importing that package pulls in daphne
(for its live-server test case) and with it Twisted, which the project no
longer ships. This is the same small client on top of asgiref's
ApplicationCommunicator.
"""

import json
from unittest import mock
from urllib.parse import unquote, urlparse

from asgiref.testing import ApplicationCommunicator


def _no_op():
    pass


class WebsocketCommunicator(ApplicationCommunicator):
    def __init__(self, application, path, headers=None, subprotocols=None):
        parsed = urlparse(path)
        super().__init__(
            application,
            {
                'type': 'websocket',
                'path': unquote(parsed.path),
                'query_string': parsed.query.encode('utf-8'),
                'headers': headers or [],
                'subprotocols': subprotocols or [],
            },
        )

    # As in channels.testing: the test's database connection must survive the
    # consumer's close_old_connections() calls.
    async def send_input(self, message):
        with mock.patch('channels.db.close_old_connections', _no_op):
            return await super().send_input(message)

    async def receive_output(self, timeout=1):
        with mock.patch('channels.db.close_old_connections', _no_op):
            return await super().receive_output(timeout)

    async def connect(self, timeout=1):
        """(True, subprotocol) when accepted, (False, close code) when refused."""
        await self.send_input({'type': 'websocket.connect'})
        response = await self.receive_output(timeout)
        if response['type'] == 'websocket.close':
            return False, response.get('code', 1000)
        assert response['type'] == 'websocket.accept', response
        return True, response.get('subprotocol')

    async def receive_json_from(self, timeout=1):
        response = await self.receive_output(timeout)
        assert response['type'] == 'websocket.send' and 'text' in response, response
        return json.loads(response['text'])

    async def disconnect(self, code=1000, timeout=1):
        await self.send_input({'type': 'websocket.disconnect', 'code': code})
        await self.wait(timeout)
