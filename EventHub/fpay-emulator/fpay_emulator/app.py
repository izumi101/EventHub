"""ASGI application factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import __version__
from .api import MerchantApi
from .callbacks import Notifier
from .clock import Clock
from .config import Settings
from .control import ControlApi
from .faults import FaultMiddleware, FaultRegistry
from .gateway import Gateway
from .logs import RequestContextMiddleware
from .pages import PaymentPages
from .store import Store

log = logging.getLogger('fpay.app')
HERE = Path(__file__).parent
MAX_BODY_BYTES = 1024 * 1024

SECURITY_HEADERS = [
    (b'x-content-type-options', b'nosniff'),
    (b'referrer-policy', b'no-referrer'),
    (b'cache-control', b'no-store'),
]
# The hosted page may be framed (payment frame mode, S3) and posts back to any merchant URL.
HTML_CSP = (
    b"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    b"form-action 'self' http: https:; frame-ancestors *; base-uri 'none'"
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                headers += SECURITY_HEADERS
                content_type = dict(headers).get(b'content-type', b'')
                if content_type.startswith(b'text/html'):
                    headers.append((b'content-security-policy', HTML_CSP))
                message = {**message, 'headers': headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class EmulatorApp:
    """The outermost ASGI callable.

    It records uvicorn's transport in the scope *before* Starlette wraps
    ``send`` (``ServerErrorMiddleware``), so the ``drop`` fault can abort the
    TCP connection for real. In-process test transports have none.
    """

    def __init__(self, app: Starlette, emulator: Emulator) -> None:
        self.app = app
        self.emulator = emulator
        self.state = app.state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] == 'http':
            transport = getattr(getattr(send, '__self__', None), 'transport', None)
            if transport is not None:
                scope['fpay.transport'] = transport
        await self.app(scope, receive, send)


class Emulator:
    """Wires the components together; owns the background scheduler."""

    def __init__(self, settings: Settings, *, http_transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.store = Store(settings.db_path)
        self.clock = Clock(self.store)
        self.http = httpx.AsyncClient(
            transport=http_transport,
            follow_redirects=False,
            headers={'user-agent': f'fpay-emulator/{__version__}'},
        )
        self.faults = FaultRegistry(self.store)
        self.notifier = Notifier(settings, self.store, self.clock, self.http)
        self.gateway = Gateway(settings, self.store, self.clock, self.notifier, self.faults)
        self.templates = Jinja2Templates(directory=str(HERE / 'templates'))
        self.api = MerchantApi(self.gateway, self.templates)
        self.pages = PaymentPages(self.gateway, self.templates)
        self.control = ControlApi(self.gateway, self.api)
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self.gateway.run_scheduler(self._stop), name='fpay-scheduler')
        log.info(
            'emulator started',
            extra={
                'version': __version__,
                'merchants': sorted(self.settings.merchants),
                'public_url': self.settings.public_url,
                'reply_mode': self.settings.reply_mode,
                'check_enabled': self.settings.check_enabled,
                'control_enabled': self.settings.control_enabled,
                'control_token': bool(self.settings.control_token),
            },
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.http.aclose()
        self.store.close()

    async def healthcheck(self, request: Request) -> Response:
        ok = self.store.ping()
        body = {'status': 'ok' if ok else 'error', 'time': datetime.now(UTC).isoformat(timespec='seconds')}
        return JSONResponse(body, status_code=200 if ok else 503)

    async def index(self, request: Request) -> Response:
        return JSONResponse(
            {
                'service': 'Freedom Pay gateway emulator',
                'version': __version__,
                'docs': 'see README.md',
                'healthcheck': '/status/healthcheck',
            }
        )

    def routes(self) -> list[Route | Mount]:
        routes: list[Route | Mount] = [
            Route('/', self.index, methods=['GET']),
            Route('/status/healthcheck', self.healthcheck, methods=['GET']),
            *self.api.routes(),
            *self.pages.routes(),
            Mount('/static', app=StaticFiles(directory=str(HERE / 'static')), name='static'),
        ]
        if self.settings.control_enabled:
            routes += self.control.routes()
        return routes


def create_app(
    settings: Settings | None = None,
    *,
    http_transport: httpx.AsyncBaseTransport | None = None,
    run_scheduler: bool = True,
) -> EmulatorApp:
    settings = settings or Settings.from_env()
    emulator = Emulator(settings, http_transport=http_transport)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        if run_scheduler:
            await emulator.start()
        try:
            yield
        finally:
            await emulator.stop()

    app = Starlette(
        routes=emulator.routes(),
        middleware=[
            Middleware(RequestContextMiddleware),
            Middleware(SecurityHeadersMiddleware),
            Middleware(FaultMiddleware, registry_getter=lambda: emulator.faults),
        ],
        lifespan=lifespan,
        max_body_size=MAX_BODY_BYTES,
    )
    app.state.emulator = emulator
    return EmulatorApp(app, emulator)
