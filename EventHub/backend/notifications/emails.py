"""Render a notification `Message` as an email (HTML + plain text) with the
brand mark and the ticket QR codes as inline images."""

import base64
import io
from functools import cache
from pathlib import Path

import segno
from django.template.loader import render_to_string

from . import types, unsubscribe
from .messages import Message, frontend_url, ticket_validation_url

PREFERENCES_PATH = '/profile/notifications'
# A group booking can hold many seats; beyond this the email links to My
# Bookings instead of embedding every QR code (the job row stays small).
MAX_INLINE_TICKETS = 9
# The EventHub symbol on its charcoal tile (PNG: mail clients don't render SVG).
LOGO_PATH = Path(__file__).resolve().parent / 'assets' / 'logo-mark.png'
LOGO_CID = 'eventhub-logo'


@cache
def logo_attachment() -> dict:
    return {
        'filename': 'eventhub.png',
        'mimetype': 'image/png',
        'content_b64': base64.b64encode(LOGO_PATH.read_bytes()).decode('ascii'),
        'cid': LOGO_CID,
    }


def ticket_qr_png(ticket_uuid) -> bytes:
    """PNG of the QR code the frontend shows for this ticket."""
    buffer = io.BytesIO()
    segno.make(ticket_validation_url(ticket_uuid), error='m').save(buffer, kind='png', scale=6, border=2)
    return buffer.getvalue()


def render_email(type_key: str, message: Message, *, user=None) -> dict:
    """{subject, body, html_body, attachments, headers} for `enqueue_email`.

    Rendered in the active language (`notify()` switches to the recipient's).
    An optional email to `user` gets a one-click unsubscribe link (RFC 8058:
    `List-Unsubscribe` + `List-Unsubscribe-Post`) and a footer link to the
    unsubscribe page; a mandatory one gets neither, only the preferences link.
    """
    spec = types.get(type_key)
    preferences_url = frontend_url(PREFERENCES_PATH)
    headers = {}
    unsubscribe_url = ''
    if spec.email_optional and user is not None and user.pk is not None:
        token = unsubscribe.make_token(user, type_key)
        unsubscribe_url = unsubscribe.page_url(token)
        headers = {
            'List-Unsubscribe': f'<{unsubscribe.api_url(token)}>',
            'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
        }
    tickets = []
    attachments = []
    for index, ticket in enumerate(message.tickets[:MAX_INLINE_TICKETS]):
        cid = f'ticket-qr-{index}'
        tickets.append({'ticket': ticket, 'cid': cid})
        attachments.append(
            {
                'filename': f'ticket-{ticket.short_id}.png',
                'mimetype': 'image/png',
                'content_b64': base64.b64encode(ticket_qr_png(ticket.ticket_uuid)).decode('ascii'),
                'cid': cid,
            }
        )
    context = {
        'message': message,
        'tickets': tickets,
        'more_tickets': max(len(message.tickets) - MAX_INLINE_TICKETS, 0),
        'preferences_url': preferences_url,
        'unsubscribe_url': unsubscribe_url,
        'email_optional': spec.email_optional,
        'site_url': frontend_url('/'),
        'logo_cid': LOGO_CID,
    }
    return {
        'subject': message.subject,
        'body': render_to_string('notifications/email/message.txt', context).strip() + '\n',
        'html_body': render_to_string('notifications/email/message.html', context),
        # The logo goes last: the ticket QR codes keep their positions.
        'attachments': [*attachments, logo_attachment()],
        'headers': headers,
    }
