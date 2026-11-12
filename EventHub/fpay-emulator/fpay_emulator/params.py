"""Merchant request parsing (spec section 1.2).

Accepted encodings, all producing the same parameter tree:

* ``application/x-www-form-urlencoded`` and ``multipart/form-data`` with PHP
  bracket nesting (``pg_receipt_positions[0][name]=...``);
* ``application/json`` (values should be strings; numbers are normalised the
  way the gateway does it *before* the signature check, so ``100.50`` becomes
  ``100.5`` and the signature fails, exactly like the real API);
* a GET query string;
* XML in the single form field ``pg_xml`` with root ``<request>``.

A POST body is the only source for a POST; query parameters on a POST URL are
ignored (conservative, see README).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl

from starlette.datastructures import UploadFile
from starlette.requests import Request

from . import xmlio
from .errors import INVALID_PARAMETER, ApiError
from .signature import Pairs

_KEY_RE = re.compile(r'^([^\[\]]+)((?:\[[^\[\]]*\])+)$')
_SUBKEY_RE = re.compile(r'\[([^\[\]]*)\]')


@dataclass
class ParsedRequest:
    tree: dict[str, Any] | Pairs
    fmt: str
    json_types: dict[str, str] = field(default_factory=dict)

    def get(self, name: str, default: Any = None) -> Any:
        if isinstance(self.tree, Pairs):
            return xmlio.first(self.tree, name, default)
        return self.tree.get(name, default)

    def text(self, name: str) -> str | None:
        """A top-level scalar parameter, or ``None`` when absent or nested."""
        value = self.get(name)
        if value is None or isinstance(value, dict | Pairs):
            return None
        return str(value)


def _next_index(container: dict[str, Any]) -> str:
    ints = [int(k) for k in container if k.isdigit()]
    return str(max(ints) + 1 if ints else 0)


def php_nest(pairs: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """Build a nested tree from ``a[b][]=v`` style names, like PHP's ``$_POST``.

    Insertion order is kept (it enters the signature positions); a repeated
    scalar name keeps its first position and takes the last value.
    """
    root: dict[str, Any] = {}
    for raw_key, value in pairs:
        match = _KEY_RE.match(raw_key)
        if not match:
            root[raw_key] = value
            continue
        base = match.group(1)
        subs = _SUBKEY_RE.findall(match.group(2))
        container = root.get(base)
        if not isinstance(container, dict):
            container = {}
            root[base] = container
        for sub in subs[:-1]:
            key = sub if sub != '' else _next_index(container)
            nested = container.get(key)
            if not isinstance(nested, dict):
                nested = {}
                container[key] = nested
            container = nested
        last = subs[-1] if subs[-1] != '' else _next_index(container)
        container[last] = value
    return root


def php_scalar(value: Any) -> str:
    """How the gateway turns a JSON scalar into the string it signs."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return '1' if value else ''
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float | Decimal):
        number = Decimal(str(value))
        if number == number.to_integral_value():
            return str(int(number))
        return format(number.normalize(), 'f')
    return str(value)


def _json_tree(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        return {str(i): _json_tree(v) for i, v in enumerate(value)}
    return php_scalar(value)


def _json_type(value: Any) -> str:
    if isinstance(value, str):
        return 'string'
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, int | float | Decimal):
        return 'number'
    if value is None:
        return 'null'
    return 'container'


def from_pairs(pairs: Iterable[tuple[str, str]], fmt: str) -> ParsedRequest:
    tree = php_nest(pairs)
    raw_xml = tree.get('pg_xml')
    if isinstance(raw_xml, str) and raw_xml.strip():
        try:
            return ParsedRequest(tree=xmlio.parse(raw_xml, root='request'), fmt='xml')
        except xmlio.XmlError as exc:
            raise ApiError(INVALID_PARAMETER, f'pg_xml: {exc}') from exc
    return ParsedRequest(tree=tree, fmt=fmt)


def from_json(body: bytes) -> ParsedRequest:
    try:
        data = json.loads(body or b'{}', parse_float=Decimal)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError(INVALID_PARAMETER, 'malformed JSON body') from exc
    if not isinstance(data, dict):
        raise ApiError(INVALID_PARAMETER, 'the JSON body must be an object')
    return ParsedRequest(
        tree={str(k): _json_tree(v) for k, v in data.items()},
        fmt='json',
        json_types={str(k): _json_type(v) for k, v in data.items()},
    )


def parse_urlencoded(body: bytes | str) -> list[tuple[str, str]]:
    text = body.decode('utf-8', errors='replace') if isinstance(body, bytes) else body
    return parse_qsl(text, keep_blank_values=True)


async def parse_request(request: Request) -> ParsedRequest:
    if request.method in ('GET', 'HEAD'):
        return from_pairs(parse_urlencoded(request.url.query), 'query')
    content_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
    if content_type == 'application/json':
        return from_json(await request.body())
    if content_type == 'application/x-www-form-urlencoded':
        return from_pairs(parse_urlencoded(await request.body()), 'form')
    if content_type == 'multipart/form-data':
        async with request.form() as form:
            pairs = [(k, v) for k, v in form.multi_items() if not isinstance(v, UploadFile)]
        return from_pairs(pairs, 'multipart')
    # Unknown or missing content type: PHP would not populate $_POST either.
    return ParsedRequest(tree={}, fmt='none')
