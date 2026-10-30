"""Generic job handlers. App-specific ones live next to their code
(events.webhooks.deliver_job, events.search.index_event_job)."""

from django.conf import settings
from django.core.mail import send_mail as django_send_mail


def send_email(*, subject: str, body: str, to: list, from_email: str | None = None):
    # fail_silently=False: an SMTP error raises, and the job is retried.
    django_send_mail(subject, body, from_email or settings.DEFAULT_FROM_EMAIL, to, fail_silently=False)


def enqueue_email(subject: str, body: str, to, from_email: str | None = None):
    """Send an email from the worker — never from the HTTP request."""
    from .queue import enqueue

    recipients = [to] if isinstance(to, str) else list(to)
    return enqueue(
        'send_email',
        {
            'subject': subject,
            'body': body,
            'to': recipients,
            'from_email': from_email,
        },
    )
