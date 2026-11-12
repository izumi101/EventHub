"""A minimal, independent Freedom Pay client for the contract suite.

Deliberately does not import ``fpay_emulator``: the suite must judge a gateway
(the emulator or the real Freedom Pay test API) only by what it says over HTTP,
following the spec (EventHub/docs/payments/freedompay-protocol.md).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from dataclasses import dataclass
from typing import Any
from xml.etree.ElementTree import Element  # only the type; parsing uses defusedxml

import httpx
from defusedxml import ElementTree as SafeET


def flatten(params: Any, parent: str = '') -> dict[str, str]:
    """Reference flattening (spec section 2.3). ``params`` is a dict or a list of pairs."""
    items = params.items() if isinstance(params, dict) else params
    flat: dict[str, str] = {}
    for i, (key, value) in enumerate(items, 1):
        if key == 'pg_sig':
            continue
        name = f'{parent}{key}{i:03d}'
        if isinstance(value, dict | list) and not isinstance(value, str):
            flat.update(flatten(value, name))
        else:
            flat[name] = '' if value is None else str(value)
    return flat


def make_sig(script: str, params: Any, secret: str) -> str:
    flat = flatten(params)
    base = ';'.join([script, *(flat[n] for n in sorted(flat)), secret])
    return hashlib.md5(base.encode(), usedforsecurity=False).hexdigest()


def salt() -> str:
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))


def _pairs(element: Element) -> list[tuple[str, Any]]:
    return [(child.tag, _pairs(child) if len(child) else (child.text or '')) for child in element]


@dataclass
class Reply:
    http_status: int
    content_type: str
    pairs: list[tuple[str, Any]]
    raw: bytes

    def get(self, name: str, default: Any = None) -> Any:
        for key, value in self.pairs:
            if key == name:
                return value
        return default

    @property
    def ok(self) -> bool:
        return self.get('pg_status') == 'ok'

    def signature_valid(self, script: str, secret: str) -> bool:
        sig = self.get('pg_sig')
        return isinstance(sig, str) and hmac.compare_digest(make_sig(script, self.pairs, secret), sig)


@dataclass
class Gateway:
    base_url: str
    merchant_id: str
    secret: str
    timeout: float = 30.0

    def call(self, path: str, params: dict[str, Any], *, script: str | None = None, secret: str | None = None) -> Reply:
        data = {'pg_merchant_id': self.merchant_id, **params, 'pg_salt': salt()}
        data['pg_sig'] = make_sig(script or path.rsplit('/', 1)[-1], data, secret or self.secret)
        response = httpx.post(f'{self.base_url}{path}', data=data, timeout=self.timeout)
        pairs: list[tuple[str, Any]] = []
        if response.headers.get('content-type', '').startswith('text/xml'):
            root = SafeET.fromstring(response.content)
            if root.tag != 'response':
                raise ValueError(f'unexpected root <{root.tag}>')
            pairs = _pairs(root)
        return Reply(response.status_code, response.headers.get('content-type', ''), pairs, response.content)
