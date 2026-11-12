"""The ``pg_sig`` signature (spec section 2).

``pg_sig = md5(script ; v(k1) ; v(k2) ; ... ; secret)`` where the values are
taken from the *flattened* parameter tree sorted by the synthetic flat names.

A parameter tree is either a mapping (form, multipart and JSON bodies, where a
name is unique inside its parent) or a :class:`Pairs` list (XML documents,
where sibling tags may repeat and keep document order). Leaves are strings.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit

SIG_FIELD = 'pg_sig'
_SIG_RE = re.compile(r'^[0-9a-f]{32}$')


class Pairs(list):
    """An ordered list of ``(name, value)`` pairs whose names may repeat (XML)."""


def _items(node: Mapping[str, Any] | Pairs) -> Iterable[tuple[str, Any]]:
    if isinstance(node, Mapping):
        return node.items()
    return node


def _leaf(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        # PHP casts true to "1" and false to "".
        return '1' if value else ''
    return str(value)


def flatten(node: Mapping[str, Any] | Pairs, parent: str = '') -> dict[str, str]:
    """Flatten a parameter tree exactly like the reference implementation (S1).

    Each name becomes ``parent + name + '%03d' % position`` where ``position``
    is the 1-based index inside the parent *counting* ``pg_sig`` (which is then
    skipped), so a signature computed over a document that contains ``pg_sig``
    in the middle matches one computed by the PHP and Python references.
    """
    flat: dict[str, str] = {}
    for i, (key, value) in enumerate(_items(node), 1):
        if key == SIG_FIELD:
            continue
        name = f'{parent}{key}{i:03d}'
        if isinstance(value, Mapping | Pairs):
            flat.update(flatten(value, name))
        elif isinstance(value, list | tuple):
            flat.update(flatten({str(j): v for j, v in enumerate(value)}, name))
        else:
            flat[name] = _leaf(value)
    return flat


def signature_base(script: str, params: Mapping[str, Any] | Pairs, secret: str) -> str:
    """The string that is hashed. It contains the secret: never log it."""
    flat = flatten(params)
    return ';'.join([script, *(flat[name] for name in sorted(flat)), secret])


def make_signature(script: str, params: Mapping[str, Any] | Pairs, secret: str) -> str:
    base = signature_base(script, params, secret)
    return hashlib.md5(base.encode('utf-8'), usedforsecurity=False).hexdigest()


def is_well_formed(sig: Any) -> bool:
    """``pg_sig`` must be 32 lowercase hex characters (S2 schema)."""
    return isinstance(sig, str) and bool(_SIG_RE.match(sig))


def verify_signature(script: str, params: Mapping[str, Any] | Pairs, secret: str, sig: Any) -> bool:
    if not is_well_formed(sig):
        return False
    return hmac.compare_digest(make_signature(script, params, secret), sig)


def find_sig(params: Mapping[str, Any] | Pairs) -> Any:
    """The top-level ``pg_sig`` value (the last one wins, like PHP)."""
    found = None
    for key, value in _items(params):
        if key == SIG_FIELD:
            found = value
    return found


def script_name(url_or_path: str) -> str:
    """Last path segment of a URL: from the last ``/`` to the end or ``?`` (S1).

    A path that ends in ``/`` yields the empty string, like the vendor plugins.
    """
    path = urlsplit(url_or_path).path
    return path.rsplit('/', 1)[-1]
