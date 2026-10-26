"""Outbound webhook dispatch.

`fire(event, trigger, payload)` looks up active webhooks subscribed to the
trigger and POSTs the payload to each, signed with HMAC-SHA256. Delivery runs
in a background thread so it never blocks the checkout request, and every
attempt is logged to WebhookDelivery for the organizer to inspect.
"""
import hashlib
import hmac
import http.client
import ipaddress
import json
import logging
import socket
import ssl
import threading
from urllib.parse import urlsplit

from django.utils import timezone

from .models import Webhook, WebhookDelivery

logger = logging.getLogger(__name__)

# Keep the HTTP call short so a slow receiver can't pile up threads.
TIMEOUT_SECONDS = 5


class UnsafeWebhookURL(Exception):
    pass


def _public_ips(host: str, port: int) -> list:
    """Resolve `host` and return its addresses, or raise if any of them is not
    a public internet address (loopback, private, CGNAT, link-local/cloud
    metadata, reserved, multicast, IPv4-mapped variants of those…)."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise UnsafeWebhookURL(f'Cannot resolve {host}: {exc}')
    ips = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split('%', 1)[0])
        if ip.version == 6 and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_multicast:
            raise UnsafeWebhookURL(f'{host} resolves to a non-public address')
        ips.append(str(ip))
    if not ips:
        raise UnsafeWebhookURL(f'{host} has no addresses')
    return ips


def _split(url: str):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise UnsafeWebhookURL('Only http(s) URLs are allowed')
    port = parts.port or (443 if parts.scheme == 'https' else 80)
    return parts, port


def is_public_url(url: str) -> bool:
    """SSRF guard used when a webhook is saved (delivery re-checks)."""
    try:
        parts, port = _split(url)
        _public_ips(parts.hostname, port)
    except (UnsafeWebhookURL, ValueError):
        return False
    return True


class _PinnedMixin:
    """Connect to an address vetted *before* the request instead of letting
    the socket layer resolve the name again (DNS rebinding: the first lookup
    returns a public IP, the second one 127.0.0.1). TLS still verifies the
    certificate against the original host name."""

    def __init__(self, *args, pinned_ip, **kwargs):
        super().__init__(*args, **kwargs)
        self._pinned_ip = pinned_ip

        def create_connection(address, timeout=None, source_address=None):
            return socket.create_connection((self._pinned_ip, address[1]), timeout, source_address)

        self._create_connection = create_connection


class _PinnedHTTPConnection(_PinnedMixin, http.client.HTTPConnection):
    pass


class _PinnedHTTPSConnection(_PinnedMixin, http.client.HTTPSConnection):
    pass


def _post(url: str, body: bytes, headers: dict) -> int:
    """POST without following redirects (http.client never does) to the
    vetted address. Returns the HTTP status."""
    parts, port = _split(url)
    ip = _public_ips(parts.hostname, port)[0]
    if parts.scheme == 'https':
        conn = _PinnedHTTPSConnection(parts.hostname, port, timeout=TIMEOUT_SECONDS,
                                      context=ssl.create_default_context(), pinned_ip=ip)
    else:
        conn = _PinnedHTTPConnection(parts.hostname, port, timeout=TIMEOUT_SECONDS, pinned_ip=ip)
    path = (parts.path or '/') + (f'?{parts.query}' if parts.query else '')
    try:
        conn.request('POST', path, body=body, headers=headers)
        return conn.getresponse().status
    finally:
        conn.close()


def _sign(secret: str, body: bytes) -> str:
    if not secret:
        return ''
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _deliver(webhook_id: int, trigger: str, body: bytes, signature: str):
    """Runs in a worker thread: POST once, log the outcome."""
    webhook = Webhook.objects.filter(id=webhook_id).first()
    if webhook is None:
        return

    status_code, success, error = None, False, ''
    try:
        status_code = _post(webhook.url, body, {
            'Content-Type': 'application/json',
            'X-EventHub-Event': trigger,
            'X-EventHub-Signature': signature,
            'User-Agent': 'EventHub-Webhooks/1.0',
        })
        success = 200 <= status_code < 300
        if not success:
            error = f'HTTP {status_code}'
    except UnsafeWebhookURL as exc:
        logger.warning('Blocked webhook delivery to %s: %s', webhook.url, exc)
        error = f'Blocked (SSRF guard): {exc}'[:300]
    except Exception as exc:  # network, timeout, TLS…
        error = str(exc)[:300]

    try:
        Webhook.objects.filter(id=webhook_id).update(
            last_triggered_at=timezone.now(), last_status=status_code,
        )
        WebhookDelivery.objects.create(
            webhook_id=webhook_id, trigger=trigger,
            status_code=status_code, success=success, error=error,
        )
    except Exception as exc:
        logger.warning('Failed to log webhook delivery: %s', exc)


def fire(event, trigger: str, payload: dict):
    """Dispatch `trigger` for `event` to all subscribed webhooks (async).

    Never raises: a webhook problem must not break the business flow that
    triggered it."""
    try:
        hooks = list(Webhook.objects.filter(event=event, is_active=True))
    except Exception:
        logger.exception('Could not load webhooks for event %s', getattr(event, 'id', None))
        return

    if not hooks:
        return

    envelope = {
        'trigger': trigger,
        'event_id': event.id,
        'event_title': event.title,
        'timestamp': timezone.now().isoformat(),
        'data': payload,
    }
    body = json.dumps(envelope, default=str).encode()

    for hook in hooks:
        if trigger not in (hook.triggers or []):
            continue
        signature = _sign(hook.secret, body)
        threading.Thread(
            target=_deliver, args=(hook.id, trigger, body, signature), daemon=True,
        ).start()
