"""Generic job handlers. App-specific ones live next to their code
(events.webhooks.deliver_job, events.search.index_event_job)."""

import base64
import binascii
import re
from email.mime.image import MIMEImage

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from .queue import PermanentJobError

# Attachments travel base64-encoded inside the job row, so they stay small:
# a ticket QR code is ~1-2 KB. Anything bigger belongs in object storage.
MAX_ATTACHMENTS = 10
MAX_ATTACHMENT_BYTES = 256 * 1024
ALLOWED_ATTACHMENT_TYPES = {'image/png', 'image/jpeg', 'application/pdf', 'text/calendar'}
# Headers a job may set; everything else (From, To, Bcc, …) is ours.
ALLOWED_HEADERS = {'List-Unsubscribe', 'List-Unsubscribe-Post'}
_SAFE_NAME = re.compile(r'[^A-Za-z0-9._-]+')
_SAFE_CID = re.compile(r'^[A-Za-z0-9._-]{1,64}$')


def _decode_attachment(item: dict) -> tuple[str, bytes, str, str]:
    """Validate one attachment of a job payload: (filename, content,
    mimetype, content id). Raises PermanentJobError: retrying a malformed
    payload can't help."""
    mimetype = str(item.get('mimetype', ''))
    if mimetype not in ALLOWED_ATTACHMENT_TYPES:
        raise PermanentJobError(f'Attachment type not allowed: {mimetype!r}')
    filename = _SAFE_NAME.sub('_', str(item.get('filename') or 'attachment'))[:100].strip('._') or 'attachment'
    try:
        content = base64.b64decode(item.get('content_b64') or '', validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PermanentJobError(f'Attachment {filename} is not valid base64') from exc
    if not content or len(content) > MAX_ATTACHMENT_BYTES:
        raise PermanentJobError(f'Attachment {filename} is empty or larger than {MAX_ATTACHMENT_BYTES} bytes')
    cid = str(item.get('cid') or '')
    if cid and (not _SAFE_CID.match(cid) or not mimetype.startswith('image/')):
        raise PermanentJobError(f'Invalid inline content id for {filename}')
    return filename, content, mimetype, cid


def build_email_message(
    *,
    subject: str,
    body: str,
    to: list,
    from_email: str | None = None,
    html_body: str | None = None,
    attachments: list | None = None,
    headers: dict | None = None,
) -> EmailMultiAlternatives:
    """The message `send_email` sends: plain text, plus an HTML alternative
    and inline (cid:) images or regular attachments when given."""
    attachments = attachments or []
    if len(attachments) > MAX_ATTACHMENTS:
        raise PermanentJobError(f'Too many attachments ({len(attachments)} > {MAX_ATTACHMENTS})')
    extra_headers = {k: str(v) for k, v in (headers or {}).items() if k in ALLOWED_HEADERS}
    # Header injection: a header value never carries a line break.
    if any('\n' in v or '\r' in v for v in extra_headers.values()):
        raise PermanentJobError('Invalid header value')

    message = EmailMultiAlternatives(
        subject=subject.replace('\n', ' ').replace('\r', ' '),
        body=body,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=list(to),
        headers=extra_headers,
    )
    if html_body:
        message.attach_alternative(html_body, 'text/html')
    has_inline = False
    for item in attachments:
        filename, content, mimetype, cid = _decode_attachment(item)
        if cid:
            image = MIMEImage(content, _subtype=mimetype.split('/', 1)[1])
            image.add_header('Content-ID', f'<{cid}>')
            image.add_header('Content-Disposition', 'inline', filename=filename)
            message.attach(image)
            has_inline = True
        else:
            message.attach(filename, content, mimetype)
    if has_inline:
        # multipart/related keeps cid: images next to the HTML that shows them.
        message.mixed_subtype = 'related'
    return message


def send_email(
    *,
    subject: str,
    body: str,
    to: list,
    from_email: str | None = None,
    html_body: str | None = None,
    attachments: list | None = None,
    headers: dict | None = None,
):
    message = build_email_message(
        subject=subject,
        body=body,
        to=to,
        from_email=from_email,
        html_body=html_body,
        attachments=attachments,
        headers=headers,
    )
    # fail_silently=False: an SMTP error raises, and the job is retried.
    message.send(fail_silently=False)


def enqueue_email(
    subject: str,
    body: str,
    to,
    from_email: str | None = None,
    *,
    html_body: str | None = None,
    attachments: list | None = None,
    headers: dict | None = None,
):
    """Send an email from the worker — never from the HTTP request.

    `attachments`: dicts {filename, mimetype, content_b64[, cid]}; with a
    `cid` the image is shown inline by `<img src="cid:...">` in `html_body`.
    The payload is validated now (a bad attachment fails the caller, not the
    worker) and again when the job runs.
    """
    from .queue import enqueue

    recipients = [to] if isinstance(to, str) else list(to)
    payload = {
        'subject': subject,
        'body': body,
        'to': recipients,
        'from_email': from_email,
    }
    if html_body:
        payload['html_body'] = html_body
    if attachments or headers:
        build_email_message(subject=subject, body=body, to=recipients, attachments=attachments, headers=headers)
    if attachments:
        payload['attachments'] = attachments
    if headers:
        payload['headers'] = headers
    return enqueue('send_email', payload)
