"""Freedom Pay `pg_sig` signatures and XML documents.

Protocol: docs/payments/freedompay-protocol.md, section 2.

    pg_sig = md5(script ; v(k1) ; v(k2) ; ... ; secret)

`script` is the last path segment of the URL that is called (or of our
callback URL for notifications), the values are those of every parameter
except `pg_sig`, flattened (nested values get the synthetic name
`parent + name + %03d position`) and ordered by the flat names. The
position counts `pg_sig` too, so a document that carries `pg_sig` in the
middle (the real `get_status3.php` answer) verifies like the reference code.

MD5 with an appended secret is a weak MAC: callers never fulfil an order on
a signature alone (the provider confirms with `get_status3.php`).

Parameter trees are either a mapping or a list of `(name, value)` pairs
(XML, where sibling tags may repeat). Leaves are strings.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import string
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree

SIG_FIELD = 'pg_sig'
_SIG_RE = re.compile(r'^[0-9a-f]{32}$')
_SALT_ALPHABET = string.ascii_letters + string.digits
_SALT_RE = re.compile(r'^[A-Za-z0-9]{1,64}$')
# Any DTD is refused before parsing: no entity expansion, no external entities.
_DTD_RE = re.compile(rb'<!(DOCTYPE|ENTITY)', re.IGNORECASE)
MAX_XML_BYTES = 256 * 1024

Pairs = list[tuple[str, Any]]


class XmlError(ValueError):
    """Not a well-formed `<response>` / `<request>` document."""


def _items(node: Mapping[str, Any] | Iterable[tuple[str, Any]]) -> Iterable[tuple[str, Any]]:
    return node.items() if isinstance(node, Mapping) else node


def _is_tree(value: Any) -> bool:
    if isinstance(value, Mapping):
        return True
    return isinstance(value, list) and all(isinstance(item, tuple) and len(item) == 2 for item in value)


def flatten(node: Mapping[str, Any] | Iterable[tuple[str, Any]], parent: str = '') -> dict[str, str]:
    """The reference flattening (spec 2.3): `{synthetic_name: value}`."""
    flat: dict[str, str] = {}
    for position, (key, value) in enumerate(_items(node), 1):
        if key == SIG_FIELD:
            continue
        name = f'{parent}{key}{position:03d}'
        if _is_tree(value) and not isinstance(value, str):
            flat.update(flatten(value, name))
        elif isinstance(value, list | tuple):
            flat.update(flatten({str(index): item for index, item in enumerate(value)}, name))
        else:
            flat[name] = '' if value is None else str(value)
    return flat


def make_signature(script: str, params: Mapping[str, Any] | Iterable[tuple[str, Any]], secret: str) -> str:
    flat = flatten(params)
    base = ';'.join([script, *(flat[name] for name in sorted(flat)), secret])
    return hashlib.md5(base.encode('utf-8'), usedforsecurity=False).hexdigest()


def find_signature(params: Mapping[str, Any] | Iterable[tuple[str, Any]]) -> Any:
    found = None
    for key, value in _items(params):
        if key == SIG_FIELD:
            found = value
    return found


def verify_signature(script: str, params: Mapping[str, Any] | Iterable[tuple[str, Any]], secret: str) -> bool:
    """Constant-time check of the `pg_sig` carried in `params`."""
    sig = find_signature(params)
    if not isinstance(sig, str) or not _SIG_RE.match(sig) or not secret:
        return False
    return hmac.compare_digest(make_signature(script, params, secret), sig)


def sign(script: str, params: Iterable[tuple[str, Any]], secret: str) -> Pairs:
    """`params` plus a fresh `pg_salt` (unless present) and `pg_sig`, in order."""
    pairs: Pairs = [(key, value) for key, value in params if key != SIG_FIELD]
    if not any(key == 'pg_salt' for key, _ in pairs):
        pairs.append(('pg_salt', new_salt()))
    pairs.append((SIG_FIELD, make_signature(script, pairs, secret)))
    return pairs


def script_name(url_or_path: str) -> str:
    """Last segment of the URL path; '' for a path that ends with '/' (S1, P1)."""
    return urlsplit(url_or_path).path.rsplit('/', 1)[-1]


def new_salt(length: int = 16) -> str:
    return ''.join(secrets.choice(_SALT_ALPHABET) for _ in range(length))


def is_salt(value: Any) -> bool:
    return isinstance(value, str) and bool(_SALT_RE.match(value))


# ───────────────────────── XML ─────────────────────────


def _pairs(element: ElementTree.Element) -> Pairs:
    return [(child.tag, _pairs(child) if len(child) else (child.text or '')) for child in element]


def parse_xml(body: bytes, *, root: str = 'response') -> Pairs:
    """`<root>` children as ordered pairs (nested lists for nested tags)."""
    if not body or len(body) > MAX_XML_BYTES:
        raise XmlError('empty or oversized XML document')
    if _DTD_RE.search(body):
        raise XmlError('XML documents with a DTD are refused')
    try:
        # No DTD can reach the parser (checked above), so no entity expansion
        # or external entity; expat does not fetch anything by itself.
        element = ElementTree.fromstring(body)  # noqa: S314
    except ElementTree.ParseError as exc:
        raise XmlError(f'malformed XML: {exc}') from exc
    if element.tag != root:
        raise XmlError(f'unexpected root element <{element.tag}>')
    return _pairs(element)


def first(pairs: Iterable[tuple[str, Any]], name: str, default: Any = None) -> Any:
    for key, value in pairs:
        if key == name:
            return value
    return default


def render_xml(pairs: Iterable[tuple[str, Any]], *, root: str = 'response') -> bytes:
    element = ElementTree.Element(root)
    for key, value in pairs:
        child = ElementTree.SubElement(element, key)
        child.text = '' if value is None else str(value)
    body = ElementTree.tostring(element, encoding='utf-8', xml_declaration=False)
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + body
