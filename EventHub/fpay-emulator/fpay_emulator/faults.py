"""Failure injection for the merchant API (``POST /_emulator/faults``).

Transport modes are applied by :class:`FaultMiddleware` around the endpoint;
``latency`` is applied inside the endpoint while the payment's operation lock
is held, so a concurrent refund or cancel sees "already in progress".

``phase`` decides when a transport fault fires: ``before`` the request is
processed (nothing happened), or ``after`` it (the operation took effect but
the answer is lost: the reconciliation case).
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .store import Store

log = logging.getLogger('fpay.faults')

HTTP_500 = 'http_500'
HTTP_502 = 'http_502'
TIMEOUT = 'timeout'
LATENCY = 'latency'
DROP = 'drop'
MALFORMED_XML = 'malformed_xml'
UNSIGNED_SUCCESS = 'unsigned_success'
WRONG_SIGNATURE = 'wrong_signature'
MODES = (HTTP_500, HTTP_502, TIMEOUT, LATENCY, DROP, MALFORMED_XML, UNSIGNED_SUCCESS, WRONG_SIGNATURE)
TRANSPORT_MODES = tuple(m for m in MODES if m != LATENCY)
BODY_MODES = (MALFORMED_XML, UNSIGNED_SUCCESS, WRONG_SIGNATURE)
PHASES = ('before', 'after')

ENDPOINTS = ('init_payment', 'payment', 'get_status', 'do_capture', 'cancel', 'revoke', 'healthcheck', '*')

_ENDPOINT_BY_SCRIPT = {
    'init_payment': 'init_payment',
    'init_payment.php': 'init_payment',
    'payment.php': 'payment',
    'get_status3.php': 'get_status',
    'get_status2.php': 'get_status',
    'get_status.php': 'get_status',
    'do_capture.php': 'do_capture',
    'cancel': 'cancel',
    'cancel.php': 'cancel',
    'revoke': 'revoke',
    'revoke.php': 'revoke',
}
DEFAULT_TIMEOUT_MS = 30_000
_SIG_RE = re.compile(rb'<pg_sig>[^<]*</pg_sig>\s*')


def endpoint_for_path(path: str) -> str | None:
    if path == '/status/healthcheck':
        return 'healthcheck'
    if path.count('/') != 1:
        return None
    return _ENDPOINT_BY_SCRIPT.get(path[1:])


class ConnectionDropped(ConnectionError):
    """Raised when no real transport is available to abort (in-process tests)."""


class FaultRegistry:
    def __init__(self, store: Store, rng: random.Random | None = None) -> None:
        self._store = store
        self._rng = rng or random.Random()  # noqa: S311 - fault sampling, not security

    @staticmethod
    def validate(spec: dict[str, Any]) -> dict[str, Any]:
        endpoint = spec.get('endpoint', '*')
        mode = spec.get('mode')
        if endpoint not in ENDPOINTS:
            raise ValueError(f'endpoint must be one of {", ".join(ENDPOINTS)}')
        if mode not in MODES:
            raise ValueError(f'mode must be one of {", ".join(MODES)}')
        phase = spec.get('phase', 'before')
        if phase not in PHASES:
            raise ValueError('phase must be before or after')
        count = spec.get('count')
        if count is not None and (not isinstance(count, int) or isinstance(count, bool) or count < 1):
            raise ValueError('count must be a positive integer or null (unlimited)')
        probability = spec.get('probability', 1.0)
        if not isinstance(probability, int | float) or isinstance(probability, bool) or not 0 < probability <= 1:
            raise ValueError('probability must be in (0, 1]')
        latency_ms = spec.get('latency_ms')
        if latency_ms is None:
            latency_ms = DEFAULT_TIMEOUT_MS if mode == TIMEOUT else (1000 if mode == LATENCY else 0)
        if not isinstance(latency_ms, int) or isinstance(latency_ms, bool) or not 0 <= latency_ms <= 600_000:
            raise ValueError('latency_ms must be an integer between 0 and 600000')
        return {
            'endpoint': endpoint,
            'mode': mode,
            'phase': phase,
            'count': count,
            'remaining': count,
            'probability': float(probability),
            'latency_ms': latency_ms,
            'hits': 0,
        }

    def add(self, spec: dict[str, Any]) -> dict[str, Any]:
        data = self.validate(spec)
        fault_id = self._store.add_fault(data['endpoint'], data)
        return {'fault_id': fault_id, **data}

    def list(self) -> list[dict[str, Any]]:
        return self._store.faults()

    def clear(self) -> int:
        return self._store.clear_faults()

    def take(self, endpoint: str, modes: tuple[str, ...]) -> dict[str, Any] | None:
        """The first matching active fault, consuming one use of it."""
        for fault in self._store.faults():
            if fault['endpoint'] not in (endpoint, '*') or fault['mode'] not in modes:
                continue
            if fault['probability'] < 1 and self._rng.random() >= fault['probability']:
                continue
            fault_id = fault.pop('fault_id')
            fault['hits'] += 1
            if fault['remaining'] is not None:
                fault['remaining'] -= 1
            self._store.update_fault(fault_id, None if fault['remaining'] == 0 else fault)
            log.info('fault injected', extra={'fault': fault['mode'], 'endpoint': endpoint, 'fault_id': fault_id})
            return {'fault_id': fault_id, **fault}
        return None


def _html(status: int, title: str) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    body = f'<html><head><title>{status} {title}</title></head><body><h1>{status} {title}</h1></body></html>'
    return status, [(b'content-type', b'text/html; charset=utf-8')], body.encode()


def mutate_body(mode: str, body: bytes) -> bytes:
    if mode == MALFORMED_XML:
        # Cut the document in the middle of an element: not well-formed.
        return body[: max(1, len(body) // 2)].rstrip(b'>') + b'<pg_'
    if mode == UNSIGNED_SUCCESS:
        return _SIG_RE.sub(b'', body)
    if mode == WRONG_SIGNATURE:
        return _SIG_RE.sub(b'<pg_sig>00000000000000000000000000000000</pg_sig>\n', body, count=1)
    return body


class FaultMiddleware:
    """Pure ASGI middleware applying transport faults to merchant API paths."""

    def __init__(self, app: ASGIApp, registry_getter: Any) -> None:
        self.app = app
        self._registry_getter = registry_getter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        endpoint = endpoint_for_path(scope['path'])
        registry: FaultRegistry | None = self._registry_getter()
        fault = registry.take(endpoint, TRANSPORT_MODES) if endpoint and registry else None
        if fault is None:
            await self.app(scope, receive, send)
            return
        scope.setdefault('state', {})['fault'] = fault
        mode = fault['mode']
        if mode in BODY_MODES:
            await self._mutate(scope, receive, send, mode)
            return
        if fault['phase'] == 'after':
            await self.app(scope, receive, _discard)
        await self._fail(scope, send, mode, fault['latency_ms'])

    async def _mutate(self, scope: Scope, receive: Receive, send: Send, mode: str) -> None:
        start: dict[str, Any] = {}
        chunks: list[bytes] = []

        async def capture(message: Message) -> None:
            if message['type'] == 'http.response.start':
                start.update(message)
            elif message['type'] == 'http.response.body':
                chunks.append(message.get('body', b''))

        await self.app(scope, receive, capture)
        body = mutate_body(mode, b''.join(chunks))
        headers = [(k, v) for k, v in start.get('headers', []) if k.lower() != b'content-length']
        headers.append((b'content-length', str(len(body)).encode()))
        await send({'type': 'http.response.start', 'status': start.get('status', 200), 'headers': headers})
        await send({'type': 'http.response.body', 'body': body})

    async def _fail(self, scope: Scope, send: Send, mode: str, latency_ms: int) -> None:
        if mode == TIMEOUT:
            await asyncio.sleep(latency_ms / 1000)
            status, headers, body = _html(504, 'Gateway Time-out')
        elif mode == DROP:
            await self._drop(scope)
            return
        elif mode == HTTP_502:
            status, headers, body = _html(502, 'Bad Gateway')
        else:
            status, headers, body = _html(500, 'Internal Server Error')
        await send({'type': 'http.response.start', 'status': status, 'headers': headers})
        await send({'type': 'http.response.body', 'body': body})

    @staticmethod
    async def _drop(scope: Scope) -> None:
        transport = scope.get('fpay.transport')
        if transport is None:
            raise ConnectionDropped('connection dropped by fault injection')
        transport.abort()
        # Let the server notice the disconnect so it does not answer a 500.
        await asyncio.sleep(0.05)


async def _discard(message: Message) -> None:
    return None
