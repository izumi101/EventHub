"""Single-purpose MFA tokens and JWT pairs that record the second factor.

- MFAChallengeToken: proves "password checked, second factor pending" for a
  few minutes. Exchanged once for a JWT pair at /auth/mfa/login/verify/.
- MFAEnrollmentToken: lets a user who must have 2FA (and has none) reach the
  enrollment endpoints only.

Both are SimpleJWT tokens with their own `token_type`, so JWTAuthentication
(access tokens only) and the refresh endpoint refuse them.
"""

import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken, Token

from .policy import AMR_BY_METHOD

CHALLENGE_MAX_FAILURES = 5


class MFAChallengeToken(Token):
    token_type = 'mfa_challenge'  # noqa: S105 - a token type name, not a secret

    @property
    def lifetime(self):
        return timedelta(seconds=settings.MFA_CHALLENGE_TTL_SECONDS)


class MFAEnrollmentToken(Token):
    token_type = 'mfa_enrollment'  # noqa: S105 - a token type name, not a secret

    @property
    def lifetime(self):
        return timedelta(seconds=settings.MFA_ENROLLMENT_TTL_SECONDS)


class MFATokenError(Exception):
    """The challenge/enrollment token is invalid, expired or already used."""


def _spent_key(jti: str) -> str:
    return f'mfa:spent:{jti}'


def _failures_key(jti: str) -> str:
    return f'mfa:challenge-failures:{jti}'


def _remaining_seconds(token: Token) -> int:
    return max(int(token['exp']) - int(time.time()), 1) + 60


def issue_challenge_token(user) -> str:
    return str(MFAChallengeToken.for_user(user))


def issue_enrollment_token(user) -> str:
    return str(MFAEnrollmentToken.for_user(user))


def _load(token_class, raw: str):
    if not isinstance(raw, str) or not raw:
        raise MFATokenError('Missing token.')
    try:
        token = token_class(raw)
    except TokenError as exc:
        raise MFATokenError('This sign-in step has expired. Sign in again.') from exc
    if cache.get(_spent_key(token['jti'])):
        raise MFATokenError('This sign-in step has already been used. Sign in again.')
    user_id = token.get(jwt_settings.USER_ID_CLAIM)
    user = User.objects.select_related('profile').filter(pk=user_id, is_active=True).first()
    if user is None:
        raise MFATokenError('This sign-in step has expired. Sign in again.')
    return token, user


def load_challenge(raw: str):
    """(token, user) for a valid, unspent challenge token."""
    token, user = _load(MFAChallengeToken, raw)
    if int(cache.get(_failures_key(token['jti'])) or 0) >= CHALLENGE_MAX_FAILURES:
        raise MFATokenError('Too many wrong codes for this sign-in. Sign in again.')
    return token, user


def load_enrollment(raw: str):
    return _load(MFAEnrollmentToken, raw)


def spend(token: Token) -> bool:
    """Mark the token used; False if someone else spent it first (atomic)."""
    return cache.add(_spent_key(token['jti']), 1, timeout=_remaining_seconds(token))


def record_challenge_failure(token: Token) -> None:
    key = _failures_key(token['jti'])
    cache.add(key, 0, timeout=_remaining_seconds(token))
    try:
        cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, timeout=_remaining_seconds(token))


def _amr(base, method: str) -> list[str]:
    amr = [a for a in (base or ['pwd']) if isinstance(a, str)]
    value = AMR_BY_METHOD[method]
    if value not in amr:
        amr.append(value)
    if 'mfa' not in amr:
        amr.append('mfa')
    return amr


def issue_jwt_pair(user, *, method: str | None = None, amr=None, mfa_at: int | None = None) -> dict:
    """A refresh/access pair. With `method` (a second factor just verified)
    the tokens carry amr and mfa_at=now; with `mfa_at` given explicitly the
    claims are carried over (e.g. after a password change)."""
    refresh = RefreshToken.for_user(user)
    if method is not None:
        refresh['amr'] = _amr(['pwd'], method)
        refresh['mfa_at'] = int(time.time())
    elif mfa_at is not None:
        refresh['amr'] = list(amr or ['pwd', 'mfa'])
        refresh['mfa_at'] = int(mfa_at)
    else:
        refresh['amr'] = ['pwd']
    # The access token copies every refresh claim (amr, mfa_at); a later
    # refresh copies them again, so refreshing never moves mfa_at forward.
    return {'refresh': str(refresh), 'access': str(refresh.access_token)}


def step_up_access_token(user, current_token, method: str) -> tuple[str, int]:
    """A new access token with mfa_at=now; the refresh token is untouched,
    so the next refresh falls back to the login's mfa_at."""
    access = AccessToken.for_user(user)
    base = None
    if current_token is not None:
        try:
            base = current_token.get('amr')
        except AttributeError:
            base = None
    mfa_at = int(time.time())
    access['amr'] = _amr(base, method)
    access['mfa_at'] = mfa_at
    return str(access), mfa_at
