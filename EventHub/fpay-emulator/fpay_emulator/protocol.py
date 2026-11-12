"""Building signed messages: responses, callbacks and redirects."""

from __future__ import annotations

import secrets
import string
from collections.abc import Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import xmlio
from .errors import ApiError
from .signature import SIG_FIELD, Pairs, make_signature, script_name

_SALT_ALPHABET = string.ascii_letters + string.digits
XML_UTF8 = 'text/xml; charset=utf-8'
XML_PLAIN = 'text/xml'


def new_salt(length: int = 16) -> str:
    return ''.join(secrets.choice(_SALT_ALPHABET) for _ in range(length))


def sign_fields(script: str, secret: str, fields: Sequence[tuple[str, Any]]) -> Pairs:
    """Fill ``pg_salt`` (when ``None``) and ``pg_sig`` in place, keeping positions.

    Missing ``pg_salt``/``pg_sig`` entries are appended at the end. The
    signature covers every field except ``pg_sig`` (S1).
    """
    pairs = Pairs((k, v) for k, v in fields)
    names = [k for k, _ in pairs]
    if 'pg_salt' not in names:
        pairs.append(('pg_salt', None))
    if SIG_FIELD not in names:
        pairs.append((SIG_FIELD, None))
    pairs = Pairs((k, new_salt() if k == 'pg_salt' and v is None else v) for k, v in pairs)
    sig = make_signature(script, pairs, secret)
    return Pairs((k, sig if k == SIG_FIELD else v) for k, v in pairs)


def error_document(error: ApiError) -> bytes:
    """Unsigned single-line error answer (S1, X)."""
    fields = [
        ('pg_status', 'error'),
        ('pg_error_code', error.code),
        ('pg_error_description', error.description),
    ]
    return xmlio.render('response', fields, pretty=False)


def success_document(script: str, secret: str, fields: Sequence[tuple[str, Any]]) -> bytes:
    return xmlio.render('response', sign_fields(script, secret, fields))


def split_query(url: str) -> tuple[str, list[tuple[str, str]]]:
    """URL without its query, and the query's pairs."""
    parts = urlsplit(url)
    base = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
    return base, parse_qsl(parts.query, keep_blank_values=True)


def with_query(url: str, extra: Sequence[tuple[str, Any]]) -> str:
    base, existing = split_query(url)
    query = urlencode([*existing, *((k, '' if v is None else str(v)) for k, v in extra)])
    return f'{base}?{query}' if query else base


def signed_for_url(
    url: str, secret: str, fields: Sequence[tuple[str, Any]], *, include_url_query: bool
) -> tuple[Pairs, Pairs]:
    """Sign ``fields`` for delivery to ``url`` (script = last path segment of ``url``).

    Returns ``(signed_fields, signature_input)``. When ``include_url_query``
    the parameters already present in the URL's query take part in the
    signature in front of ours, as the merchant's ``$_GET`` would see them.
    """
    script = script_name(url)
    _, existing = split_query(url)
    if include_url_query and existing:
        merged = Pairs([*existing, *fields])
        signed = sign_fields(script, secret, merged)
        own = Pairs(signed[len(existing) :])
        return own, signed
    signed = sign_fields(script, secret, fields)
    return signed, signed
