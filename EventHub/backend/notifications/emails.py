"""Render a notification `Message` as an email (HTML + plain text) with the
ticket QR codes as inline images."""

import base64
import io

import segno
from django.template.loader import render_to_string

from . import types
from .messages import Message, frontend_url, ticket_validation_url

PREFERENCES_PATH = '/profile/notifications'
# A group booking can hold many seats; beyond this the email links to My
# Bookings instead of embedding every QR code (the job row stays small).
MAX_INLINE_TICKETS = 10


def ticket_qr_png(ticket_uuid) -> bytes:
    """PNG of the QR code the frontend shows for this ticket."""
    buffer = io.BytesIO()
    segno.make(ticket_validation_url(ticket_uuid), error='m').save(buffer, kind='png', scale=6, border=2)
    return buffer.getvalue()


def render_email(type_key: str, message: Message) -> dict:
    """{subject, body, html_body, attachments, headers} for `enqueue_email`."""
    spec = types.get(type_key)
    preferences_url = frontend_url(PREFERENCES_PATH)
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
        'email_optional': spec.email_optional,
        'site_url': frontend_url('/'),
    }
    return {
        'subject': message.subject,
        'body': render_to_string('notifications/email/message.txt', context).strip() + '\n',
        'html_body': render_to_string('notifications/email/message.html', context),
        'attachments': attachments,
        'headers': {'List-Unsubscribe': f'<{preferences_url}>'},
    }
