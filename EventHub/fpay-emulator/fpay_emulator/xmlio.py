"""XML documents in the Freedom Pay dialect.

Responses are ``<response>`` documents (S1); ``pg_xml`` requests and XML
callbacks are ``<request>`` documents. Parsing goes through ``defusedxml`` and
keeps document order and repeated sibling tags (:class:`Pairs`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from xml.etree.ElementTree import Element  # only the type; parsing uses defusedxml
from xml.sax.saxutils import escape

from defusedxml import ElementTree as SafeET

from .signature import Pairs

XML_DECLARATION = '<?xml version="1.0" encoding="utf-8"?>'

Node = str | Pairs | Mapping[str, Any] | Sequence[tuple[str, Any]]


class XmlError(ValueError):
    """The document is not well-formed or has an unexpected root."""


def _children(node: Any) -> Sequence[tuple[str, Any]]:
    if isinstance(node, Mapping):
        return list(node.items())
    return node


def _render(name: str, value: Any, indent: str | None, depth: int) -> str:
    pad = '' if indent is None else '\n' + indent * depth
    if isinstance(value, Mapping | Pairs):
        inner = ''.join(_render(k, v, indent, depth + 1) for k, v in _children(value))
        close_pad = pad if inner else ''
        return f'{pad}<{name}>{inner}{close_pad}</{name}>'
    text = '' if value is None else str(value)
    return f'{pad}<{name}>{escape(text)}</{name}>'


def render(root: str, fields: Sequence[tuple[str, Any]] | Mapping[str, Any], *, pretty: bool = True) -> bytes:
    """Serialise ``fields`` in the given order under ``root``.

    ``pretty`` mirrors the real gateway: success answers are indented, error
    answers are a single line (spec section 1.2).
    """
    indent = '    ' if pretty else None
    inner = ''.join(_render(k, v, indent, 1) for k, v in _children(fields))
    tail = '\n' if pretty else ''
    body = f'{XML_DECLARATION}\n<{root}>{inner}{tail}</{root}>'
    if pretty:
        body += '\n'
    return body.encode('utf-8')


def _to_pairs(element: Element) -> Pairs:
    pairs = Pairs()
    for child in element:
        if len(child):
            pairs.append((child.tag, _to_pairs(child)))
        else:
            pairs.append((child.tag, child.text or ''))
    return pairs


def parse(data: bytes | str, *, root: str | None = None) -> Pairs:
    """Parse a document into ordered pairs. ``root`` is checked when given."""
    try:
        element = SafeET.fromstring(data.encode('utf-8') if isinstance(data, str) else data)
    except Exception as exc:  # defusedxml raises several unrelated types
        raise XmlError(f'malformed XML: {exc.__class__.__name__}') from exc
    if root is not None and element.tag != root:
        raise XmlError(f'unexpected root element <{element.tag}>')
    return _to_pairs(element)


def first(pairs: Pairs | Sequence[tuple[str, Any]], name: str, default: Any = None) -> Any:
    """Value of the first top-level tag called ``name`` (SimpleXML ``$xml->name``)."""
    for key, value in pairs:
        if key == name:
            return value
    return default
