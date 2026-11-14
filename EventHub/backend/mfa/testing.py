"""Test helpers for code behind the 2FA rules (used by tests only)."""

import time

from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from . import totp
from .crypto import encrypt_secret
from .models import TOTPDevice


def mfa_access_token(user, *, age_seconds: int = 0, amr=('pwd', 'otp', 'mfa')) -> AccessToken:
    """An access token that records a second factor `age_seconds` ago."""
    token = AccessToken.for_user(user)
    token['amr'] = list(amr)
    token['mfa_at'] = int(time.time()) - age_seconds
    return token


def authenticate_with_recent_mfa(client, user, *, age_seconds: int = 0) -> AccessToken:
    """APIClient.force_authenticate with a token that satisfies step-up."""
    token = mfa_access_token(user, age_seconds=age_seconds)
    client.force_authenticate(user, token=token)
    return token


def enroll_totp(user, secret: str | None = None) -> str:
    """Give `user` a confirmed authenticator app; returns its secret."""
    secret = secret or totp.new_secret()
    TOTPDevice.objects.update_or_create(
        user=user,
        defaults={
            'encrypted_secret': encrypt_secret(secret),
            'confirmed': True,
            'confirmed_at': timezone.now(),
            'last_used_step': None,
        },
    )
    return secret


def totp_code(secret: str, *, step_offset: int = 0) -> str:
    return totp.code_for_step(secret, totp.current_step() + step_offset)


def mark_admin_session_verified(client, user) -> None:
    """For tests of /admin/ pages: the session passed the admin's second step."""
    from .middleware import SESSION_AT, SESSION_USER

    session = client.session
    session[SESSION_USER] = user.pk
    session[SESSION_AT] = int(time.time())
    session.save()
