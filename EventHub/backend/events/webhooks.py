"""Outbound webhook dispatch.

`fire(event, trigger, payload)` looks up active webhooks subscribed to the
trigger and POSTs the payload to each, signed with HMAC-SHA256. Delivery runs
in a background thread so it never blocks the checkout request, and every
attempt is logged to WebhookDelivery for the organizer to inspect.
"""
import hashlib
import hmac
import json
import logging
import threading
import ipaddress
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from django.utils import timezone

from .models import Webhook, WebhookDelivery

logger = logging.getLogger(__name__)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so a vetted public URL can't 302 to an internal one."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _is_public_url(url: str) -> bool:
    """SSRF guard: allow only http(s) to a publicly-routable host.

    Webhook URLs are organizer-controlled, so without this an organizer could
    point one at internal infrastructure (cloud metadata, localhost, private
    ranges) and have the server fetch it. Resolve the host and reject any
    private / loopback / link-local / reserved address.
    """
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            return False
        port = parts.port or (443 if parts.scheme == 'https' else 80)
        infos = socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP)
    except Exception:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True

# Keep the HTTP call short so a slow receiver can't pile up threads.
TIMEOUT_SECONDS = 5


def _sign(secret: str, body: bytes) -> str:
    if not secret:
        return ''
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _deliver(webhook_id: int, trigger: str, body: bytes, signature: str):
    """Runs in a worker thread: POST once, log the outcome."""
    import urllib.request
    import urllib.error

    webhook = Webhook.objects.filter(id=webhook_id).first()
    if webhook is None:
        return

    if not _is_public_url(webhook.url):
        logger.warning('Blocked webhook delivery to non-public URL: %s', webhook.url)
        WebhookDelivery.objects.create(
            webhook_id=webhook_id, trigger=trigger,
            status_code=None, success=False, error='Blocked: non-public URL (SSRF guard)',
        )
        return

    status_code, success, error = None, False, ''
    try:
        req = urllib.request.Request(
            webhook.url, data=body, method='POST',
            headers={
                'Content-Type': 'application/json',
                'X-EventHub-Event': trigger,
                'X-EventHub-Signature': signature,
                'User-Agent': 'EventHub-Webhooks/1.0',
            },
        )
        with _OPENER.open(req, timeout=TIMEOUT_SECONDS) as resp:
            status_code = resp.status
            success = 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        error = f'HTTP {exc.code}'
    except Exception as exc:  # network, timeout, bad URL…
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
    """Dispatch `trigger` for `event` to all subscribed webhooks (async)."""
    try:
        hooks = list(Webhook.objects.filter(event=event, is_active=True))
    except Exception:
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
