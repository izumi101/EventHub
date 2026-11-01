"""A fake merchant HTTP server for Check/Result callbacks and redirects.

It runs on 127.0.0.1 in a thread, records every request, verifies the
emulator's signature like a real merchant would, and answers according to a
programmable queue of behaviours per path.
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from fpay_emulator import xmlio
from fpay_emulator.signature import Pairs, make_signature, script_name, verify_signature

OK = 'ok'
REJECTED = 'rejected'
ERROR = 'error'
WRONG_SIG = 'wrong_sig'
NO_ECHO = 'no_echo'
NO_DESCRIPTION = 'no_description'
PLAIN = 'plain'
HTTP500 = 'http500'
SLOW = 'slow'
CLOSE = 'close'


@dataclass
class Received:
    method: str
    path: str
    query: list[tuple[str, str]]
    form: list[tuple[str, str]]
    xml: Pairs | None
    behaviour: str
    signature_ok: bool

    def fields(self) -> dict[str, Any]:
        if self.xml is not None:
            return dict(self.xml)
        return dict(self.form if self.method == 'POST' else self.query)


@dataclass
class FakeMerchant:
    secret: str
    slow_seconds: float = 1.0
    received: list[Received] = field(default_factory=list)
    plans: dict[str, list[str]] = field(default_factory=dict)
    defaults: dict[str, str] = field(default_factory=dict)
    base_url: str = ''
    _server: ThreadingHTTPServer | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def url(self, path: str) -> str:
        return f'{self.base_url}{path}'

    def plan(self, path: str, *behaviours: str, default: str | None = None) -> None:
        with self._lock:
            self.plans[path] = list(behaviours)
            if default is not None:
                self.defaults[path] = default

    def next_behaviour(self, path: str) -> str:
        with self._lock:
            queue = self.plans.get(path) or []
            if queue:
                return queue.pop(0)
            return self.defaults.get(path, OK)

    def calls(self, path: str | None = None) -> list[Received]:
        with self._lock:
            return [r for r in self.received if path is None or r.path == path]

    async def wait_for(self, path: str, count: int, timeout: float = 5.0) -> list[Received]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            calls = self.calls(path)
            if len(calls) >= count:
                return calls
            await asyncio.sleep(0.02)
        raise AssertionError(f'expected {count} calls to {path}, got {len(self.calls(path))}')

    def start(self) -> None:
        merchant = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:
                self._handle('GET')

            def do_POST(self) -> None:
                self._handle('POST')

            def _handle(self, method: str) -> None:
                parts = urlsplit(self.path)
                query = parse_qsl(parts.query, keep_blank_values=True)
                length = int(self.headers.get('content-length') or 0)
                body = self.rfile.read(length).decode() if length else ''
                form = parse_qsl(body, keep_blank_values=True) if method == 'POST' else []
                xml = None
                form_map = dict(form)
                if 'pg_xml' in form_map:
                    xml = xmlio.parse(form_map['pg_xml'], root='request')
                script = script_name(parts.path)
                if xml is not None:
                    params: Any = xml
                elif method == 'GET':
                    params = Pairs(query)  # the whole $_GET, URL params included
                else:
                    params = Pairs(form)
                sig = dict(params).get('pg_sig')
                signature_ok = verify_signature(script, params, merchant.secret, sig)
                behaviour = merchant.next_behaviour(parts.path)
                with merchant._lock:
                    merchant.received.append(Received(method, parts.path, query, form, xml, behaviour, signature_ok))
                salt = dict(params).get('pg_salt', '')
                self._reply(behaviour, script, salt)

            def _reply(self, behaviour: str, script: str, salt: str) -> None:
                if behaviour == CLOSE:
                    self.close_connection = True
                    self.connection.close()
                    return
                if behaviour == SLOW:
                    time.sleep(merchant.slow_seconds)
                    behaviour = OK
                if behaviour == HTTP500:
                    self._send(500, b'boom', 'text/plain')
                    return
                if behaviour == PLAIN:
                    self._send(200, b'Request was processed.', 'text/plain')
                    return
                status = {OK: 'ok', REJECTED: 'rejected', ERROR: 'error'}.get(behaviour, 'ok')
                fields: list[tuple[str, str]] = [('pg_status', status)]
                if behaviour != NO_DESCRIPTION:
                    fields.append(('pg_description', f'reply {status}'))
                fields.append(('pg_salt', 'differentSalt' if behaviour == NO_ECHO else salt))
                sig = make_signature(script, Pairs(fields), merchant.secret)
                if behaviour == WRONG_SIG:
                    sig = '0' * 32
                fields.append(('pg_sig', sig))
                self._send(200, xmlio.render('response', fields), 'text/xml; charset=utf-8')

            def _send(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header('content-type', content_type)
                self.send_header('content-length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self._server.daemon_threads = True
        self.base_url = f'http://127.0.0.1:{self._server.server_address[1]}'
        threading.Thread(target=self._server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True).start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
