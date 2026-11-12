"""Structured JSON logs with request ids.

Nothing secret is ever logged: no merchant secret, no signature base string,
no full card number and no CVV. Parameters are logged by name only, except a
short allow-list of identifiers.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: ContextVar[str | None] = ContextVar('request_id', default=None)

_RESERVED = set(logging.LogRecord('', 0, '', 0, '', (), None).__dict__) | {'message', 'asctime'}
_REQUEST_ID_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')
_PAN_RE = re.compile(r'\b\d{12,19}\b')


def scrub(value: Any) -> Any:
    """Mask anything that looks like a full card number."""
    if isinstance(value, str):
        return _PAN_RE.sub(lambda m: m.group(0)[:6] + '…' + m.group(0)[-4:], value)
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [scrub(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            'ts': datetime.fromtimestamp(record.created, UTC).isoformat(timespec='milliseconds'),
            'level': record.levelname,
            'logger': record.name,
            'msg': scrub(record.getMessage()),
        }
        request_id = request_id_var.get()
        if request_id:
            entry['request_id'] = request_id
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith('_'):
                entry[key] = scrub(value)
        if record.exc_info:
            entry['exc'] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure(level: str = 'INFO') -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Our access log replaces uvicorn's; its error log goes through JSON too.
    logging.getLogger('uvicorn.access').disabled = True
    for name in ('uvicorn', 'uvicorn.error'):
        logger = logging.getLogger(name)
        logger.handlers[:] = []
        logger.propagate = True
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)


access_log = logging.getLogger('fpay.access')


class RequestContextMiddleware:
    """ASGI middleware: request id (``X-Request-Id``) and the JSON access log."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get('headers') or []).get(b'x-request-id', b'').decode('latin-1')
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_holder = {'status': 0}

        async def send_with_id(message: Message) -> None:
            if message['type'] == 'http.response.start':
                status_holder['status'] = message['status']
                headers = list(message.get('headers', []))
                headers.append((b'x-request-id', request_id.encode()))
                message = {**message, 'headers': headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            state = scope.get('state') or {}
            extra: dict[str, Any] = {
                'method': scope['method'],
                'path': scope['path'],
                'status': status_holder['status'],
                'duration_ms': round((time.perf_counter() - started) * 1000, 1),
            }
            for key in ('merchant_id', 'payment_id', 'error_code', 'endpoint'):
                if key in state:
                    extra[key] = state[key]
            if 'fault' in state:
                extra['fault'] = state['fault'].get('mode')
            access_log.info('request', extra=extra)
            request_id_var.reset(token)
