"""Email one-time codes (ADR 0002, amendment 1).

A 6-digit code is emailed for one purpose (sign-in, step-up, enrollment),
lives MFA_EMAIL_CODE_TTL_SECONDS, allows MFA_EMAIL_CODE_MAX_ATTEMPTS guesses
and works once. Only an HMAC of the code is stored. Sending a new code for a
purpose retires the previous one; sending is limited per user and purpose
(one a minute, a few an hour) so the endpoint can't be used to flood a
mailbox, while finishing one flow (e.g. enrollment) never blocks the next
(the sign-in right after it). The email
leaves through the outbox (jobs.handlers.enqueue_email), never from the
request.
"""

import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework import status

from common.codes import generate_numeric_code

from .exceptions import MFAError
from .models import EmailCode, MFAState

logger = logging.getLogger('mfa')

CODE_LENGTH = 6
THROTTLED = 'mfa_email_throttled'

_SUBJECTS = {
    EmailCode.PURPOSE_LOGIN: 'EventHub — your sign-in code',
    EmailCode.PURPOSE_STEP_UP: 'EventHub — confirm it is you',
    EmailCode.PURPOSE_ENROLL: 'EventHub — confirm your email for two-factor authentication',
}
_REASONS = {
    EmailCode.PURPOSE_LOGIN: 'to finish signing in to EventHub',
    EmailCode.PURPOSE_STEP_UP: 'to confirm a sensitive action on your EventHub account',
    EmailCode.PURPOSE_ENROLL: 'to turn on email codes for two-factor authentication',
}


def _hash(salt: str, user_id: int, purpose: str, code: str) -> str:
    # Keyed with SECRET_KEY: 10^6 codes are trivial to enumerate against a
    # plain hash, not against an HMAC whose key is not in the database.
    return salted_hmac('mfa.email_code', f'{salt}:{user_id}:{purpose}:{code}', algorithm='sha256').hexdigest()


def normalize(code) -> str:
    return ''.join(ch for ch in str(code or '') if ch.isdigit())


def ttl_seconds() -> int:
    return int(settings.MFA_EMAIL_CODE_TTL_SECONDS)


def _retry_after(user, purpose: str, now) -> int:
    """Seconds until the user may get another code for `purpose` (0 = now)."""
    recent = EmailCode.objects.filter(user=user, purpose=purpose, created_at__gt=now - timedelta(hours=1)).order_by(
        '-created_at'
    )
    times = list(recent.values_list('created_at', flat=True)[: int(settings.MFA_EMAIL_MAX_PER_HOUR)])
    wait = 0
    if times:
        wait = int((times[0] + timedelta(seconds=int(settings.MFA_EMAIL_RESEND_SECONDS)) - now).total_seconds())
    if len(times) >= int(settings.MFA_EMAIL_MAX_PER_HOUR):
        wait = max(wait, int((times[-1] + timedelta(hours=1) - now).total_seconds()))
    return max(wait, 0)


def send(user, purpose: str, *, request=None, deliver: bool = True) -> dict:
    """Create a code for `purpose` and email it to `user.email`.

    Raises MFAError(429, mfa_email_throttled, retry_after) when the user asked
    too often. With deliver=False the same bookkeeping happens without an
    email (callers that must answer identically whether or not the user has
    email codes turned on)."""
    from jobs.handlers import enqueue_email

    from .services import client_ip

    with transaction.atomic():
        # One row lock per user serialises concurrent sends, so the limits hold.
        MFAState.objects.select_for_update().get_or_create(user=user)
        now = timezone.now()
        wait = _retry_after(user, purpose, now)
        if wait:
            raise MFAError(
                f'A code was sent recently. You can ask for a new one in {wait} seconds.',
                THROTTLED,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                extra={'retry_after': wait},
            )
        EmailCode.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
        code = generate_numeric_code(CODE_LENGTH)
        salt = secrets.token_hex(16)
        EmailCode.objects.create(
            user=user,
            purpose=purpose,
            salt=salt,
            code_hash=_hash(salt, user.pk, purpose, code),
            expires_at=now + timedelta(seconds=ttl_seconds()),
        )
        if deliver and user.email:
            minutes = ttl_seconds() // 60
            enqueue_email(
                _SUBJECTS[purpose],
                f'Your EventHub code is: {code}\n\n'
                f'Enter it {_REASONS[purpose]}. It expires in {minutes} minutes and works once.\n\n'
                'If you did not try to sign in, someone may know your password: change it right away.\n\n'
                'EventHub Team',
                user.email,
            )
    logger.info(
        'mfa.email_code_sent user=%s purpose=%s delivered=%s ip=%s',
        user.pk,
        purpose,
        bool(deliver and user.email),
        client_ip(request),
    )
    return {
        'sent': True,
        'expires_in': ttl_seconds(),
        'resend_in': int(settings.MFA_EMAIL_RESEND_SECONDS),
    }


def verify(user, purpose: str, code) -> bool:
    """Consume the latest live code of `user` for `purpose` if `code` matches.

    The attempt is counted before comparing (parallel guesses can't exceed
    the budget) and the code is burned once the budget is spent; a match is
    marked used with a conditional UPDATE, so a code works once even under
    concurrency. Wrong, expired, used and missing codes all answer False."""
    normalized = normalize(code)
    if len(normalized) != CODE_LENGTH:
        return False
    now = timezone.now()
    entry = (
        EmailCode.objects.filter(user=user, purpose=purpose, is_used=False, expires_at__gt=now)
        .order_by('-created_at')
        .first()
    )
    if entry is None:
        return False
    max_attempts = int(settings.MFA_EMAIL_CODE_MAX_ATTEMPTS)
    counted = EmailCode.objects.filter(pk=entry.pk, is_used=False, attempts__lt=max_attempts).update(
        attempts=F('attempts') + 1
    )
    if not counted:
        return False
    if hmac.compare_digest(entry.code_hash, _hash(entry.salt, user.pk, purpose, normalized)):
        return bool(EmailCode.objects.filter(pk=entry.pk, is_used=False).update(is_used=True))
    EmailCode.objects.filter(pk=entry.pk, attempts__gte=max_attempts).update(is_used=True)
    return False


def purge_expired(older_than: timedelta = timedelta(days=1)) -> int:
    """Delete codes that expired more than `older_than` ago."""
    return EmailCode.objects.filter(expires_at__lt=timezone.now() - older_than).delete()[0]
