"""Who must have 2FA, who has it, and whether a token proves it."""

from django.conf import settings
from django.core.cache import cache

ENABLED_CACHE_SECONDS = 300

# Values accepted in MFA_REQUIRED_ROLES.
KNOWN_ROLES = frozenset({'attendee', 'organizer', 'staff', 'superuser'})

METHOD_TOTP = 'totp'
METHOD_WEBAUTHN = 'webauthn'
METHOD_RECOVERY = 'recovery_code'

# RFC 8176 authentication method references carried in the `amr` claim.
AMR_BY_METHOD = {METHOD_TOTP: 'otp', METHOD_WEBAUTHN: 'hwk', METHOD_RECOVERY: 'rec'}


def required_roles() -> frozenset[str]:
    return frozenset(settings.MFA_REQUIRED_ROLES)


def mfa_required_for(user) -> bool:
    """True when the deployment's policy obliges this user to use 2FA."""
    if user is None or not user.is_authenticated:
        return False
    roles = required_roles()
    if not roles:
        return False
    if 'staff' in roles and user.is_staff:
        return True
    if 'superuser' in roles and user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'role', None) in roles


def has_totp(user) -> bool:
    from .models import TOTPDevice

    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def has_webauthn(user) -> bool:
    from .models import WebAuthnCredential

    return WebAuthnCredential.objects.filter(user=user).exists()


def _enabled_cache_key(user_id) -> str:
    return f'mfa:enabled:{user_id}'


def forget_mfa_enabled(user_id) -> None:
    """Drop the cached answer of mfa_enabled() after factors changed."""
    cache.delete(_enabled_cache_key(user_id))


def mfa_enabled(user) -> bool:
    """A confirmed TOTP device or at least one passkey.

    Asked on every authenticated API request, so the answer is cached in the
    shared cache; every change of factors calls forget_mfa_enabled() (model
    signals in mfa/signals.py)."""
    if user is None or not user.is_authenticated:
        return False
    key = _enabled_cache_key(user.pk)
    cached = cache.get(key)
    if cached is not None:
        return bool(cached)
    enabled = has_totp(user) or has_webauthn(user)
    cache.set(key, int(enabled), ENABLED_CACHE_SECONDS)
    return enabled


def available_methods(user) -> list[str]:
    from .models import RecoveryCode

    methods = []
    if has_totp(user):
        methods.append(METHOD_TOTP)
    if has_webauthn(user):
        methods.append(METHOD_WEBAUTHN)
    if RecoveryCode.objects.filter(user=user, used_at__isnull=True).exists():
        methods.append(METHOD_RECOVERY)
    return methods


def token_mfa_at(token) -> int | None:
    """`mfa_at` of a validated SimpleJWT token (None when absent / no token)."""
    if token is None:
        return None
    try:
        value = token.get('mfa_at')
    except AttributeError:
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def token_satisfies_policy(user, token) -> bool:
    """An access token is acceptable for this user: either it records a
    second factor, or the user neither needs nor has 2FA."""
    if token_mfa_at(token) is not None:
        return True
    return not (mfa_required_for(user) or mfa_enabled(user))
