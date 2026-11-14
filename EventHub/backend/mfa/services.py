"""2FA use cases: verify a factor (with lockout), enable / disable factors,
login hand-off, notifications and the audit log.

The `mfa` logger is the audit trail: user id, method, client IP, outcome —
never a code, secret or assertion.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.throttling import BaseThrottle

from common.auth import revoke_all_refresh_tokens

from . import email_codes, passkeys, recovery, totp
from .exceptions import INVALID_CODE, REQUIRED_BY_POLICY, MFAError, MFALocked
from .models import EmailCode, EmailFactor, MFAState, RecoveryCode, TOTPDevice, WebAuthnCredential
from .policy import (
    METHOD_EMAIL,
    METHOD_RECOVERY,
    METHOD_TOTP,
    METHOD_WEBAUTHN,
    available_methods,
    email_allowed_for,
    forget_mfa_enabled,
    has_any_factor,
    has_email,
    has_totp,
    has_usable_email,
    has_webauthn,
    mfa_required_for,
)
from .tokens import issue_challenge_token, issue_enrollment_token, issue_jwt_pair

logger = logging.getLogger('mfa')

METHODS = (METHOD_TOTP, METHOD_WEBAUTHN, METHOD_RECOVERY, METHOD_EMAIL)

FACTOR_LABELS = {
    METHOD_TOTP: 'An authenticator app',
    METHOD_WEBAUTHN: 'A passkey',
    METHOD_EMAIL: 'Email codes',
}


def client_ip(request) -> str:
    if request is None:
        return '-'
    try:
        return BaseThrottle().get_ident(request) or '-'
    except Exception:
        return '-'


# ---- Notifications ---- #


def notify_security(user, title: str, body: str) -> None:
    """In-app notification + email (always sent) for a security-relevant
    change."""
    from notifications.service import notify

    notify(user, 'security_alert', title=title, body=body)


# ---- Lockout ---- #


def _lock_seconds(failures: int) -> int:
    over = failures - settings.MFA_MAX_FAILED_ATTEMPTS
    if over < 0:
        return 0
    return min(settings.MFA_LOCKOUT_SECONDS * (2**over), settings.MFA_LOCKOUT_MAX_SECONDS)


def ensure_not_locked(user) -> None:
    state = MFAState.objects.filter(user=user).only('locked_until').first()
    now = timezone.now()
    if state and state.locked_until and state.locked_until > now:
        retry_after = max(int((state.locked_until - now).total_seconds()) + 1, 1)
        raise MFALocked(
            f'Too many wrong codes. Try again in {retry_after} seconds.',
            extra={'retry_after': retry_after},
        )


def _record_failure(user, method: str, context: str, request) -> int:
    with transaction.atomic():
        state, _ = MFAState.objects.select_for_update().get_or_create(user=user)
        state.failed_attempts += 1
        state.last_failure_at = timezone.now()
        lock = _lock_seconds(state.failed_attempts)
        if lock:
            state.locked_until = state.last_failure_at + timedelta(seconds=lock)
        state.save(update_fields=['failed_attempts', 'last_failure_at', 'locked_until'])
    logger.warning(
        'mfa.verify_failed user=%s method=%s context=%s ip=%s consecutive_failures=%s',
        user.pk,
        method,
        context,
        client_ip(request),
        state.failed_attempts,
    )
    if lock:
        logger.warning('mfa.locked user=%s seconds=%s ip=%s', user.pk, lock, client_ip(request))
    return lock


def _record_success(user) -> None:
    MFAState.objects.filter(user=user).exclude(failed_attempts=0, locked_until=None).update(
        failed_attempts=0, locked_until=None
    )


# ---- Verification ---- #


def verify_second_factor(
    user, *, method: str, code=None, credential=None, webauthn_key: str | None = None, request=None, context='login'
) -> str:
    """Verify one factor of `user` or raise MFAError / MFALocked."""
    if method not in METHODS:
        raise MFAError('Unknown verification method.', status_code=status.HTTP_400_BAD_REQUEST)
    ensure_not_locked(user)

    ok = False
    if method == METHOD_TOTP:
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        ok = device is not None and totp.verify(device, code)
    elif method == METHOD_RECOVERY:
        ok = recovery.use(user, code)
    elif method == METHOD_WEBAUTHN:
        ok = webauthn_key is not None and passkeys.verify_assertion(user, credential, webauthn_key) is not None
    elif method == METHOD_EMAIL:
        purpose = EmailCode.PURPOSE_LOGIN if context == 'login' else EmailCode.PURPOSE_STEP_UP
        ok = has_usable_email(user) and email_codes.verify(user, purpose, code)
        if ok:
            EmailFactor.objects.filter(user=user).update(last_used_at=timezone.now())

    if not ok:
        lock = _record_failure(user, method, context, request)
        if lock:
            raise MFALocked(
                f'Too many wrong codes. Try again in {lock} seconds.',
                extra={'retry_after': lock},
            )
        message = (
            'The passkey could not be verified. Try again.'
            if method == METHOD_WEBAUTHN
            else 'That code is not valid. Check it and try again.'
        )
        raise MFAError(message, INVALID_CODE)

    _record_success(user)
    logger.info('mfa.verified user=%s method=%s context=%s ip=%s', user.pk, method, context, client_ip(request))
    if method == METHOD_RECOVERY:
        left = recovery.remaining(user)
        logger.warning('mfa.recovery_code_used user=%s remaining=%s ip=%s', user.pk, left, client_ip(request))
        notify_security(
            user,
            'A recovery code was used',
            f'A recovery code was used to confirm a sign-in or a sensitive action on your account. '
            f'{left} unused codes are left; generate new ones in Profile → Security if you are running low.',
        )
    return method


# ---- Login hand-off ---- #


def login_response(user) -> dict:
    """What POST /auth/login/ answers once the password is right."""
    from accounts.services import build_auth_payload

    if has_any_factor(user):
        return {
            'mfa_required': True,
            'challenge_token': issue_challenge_token(user),
            'methods': available_methods(user),
            'expires_in': settings.MFA_CHALLENGE_TTL_SECONDS,
        }
    if mfa_required_for(user):
        logger.info('mfa.enrollment_required user=%s', user.pk)
        return {
            'mfa_enrollment_required': True,
            'enrollment_token': issue_enrollment_token(user),
            'expires_in': settings.MFA_ENROLLMENT_TTL_SECONDS,
        }
    return build_auth_payload(user)


# ---- Enabling factors ---- #


def _factor_added(user, *, method: str, first: bool, request) -> dict:
    """Shared tail of TOTP confirmation and passkey registration."""
    from accounts.serializers import UserSerializer

    forget_mfa_enabled(user.pk)
    result = {'enabled': True, 'recovery_codes': None, 'tokens': None, 'user': None}
    if first:
        result['recovery_codes'] = recovery.regenerate(user)
        # Sessions opened with the password alone end here.
        revoke_all_refresh_tokens(user)
        result['tokens'] = issue_jwt_pair(user, method=method)
        result['user'] = UserSerializer(user).data
        logger.info('mfa.enabled user=%s method=%s ip=%s', user.pk, method, client_ip(request))
        notify_security(
            user,
            'Two-factor authentication is on',
            'Two-factor authentication was turned on for your EventHub account. '
            'Keep your recovery codes somewhere safe.',
        )
    else:
        logger.info('mfa.factor_added user=%s method=%s ip=%s', user.pk, method, client_ip(request))
        notify_security(
            user, 'New sign-in method added', f'{FACTOR_LABELS[method]} was added to your EventHub account.'
        )
    return result


def start_totp_setup(user) -> dict:
    if TOTPDevice.objects.filter(user=user, confirmed=True).exists():
        raise MFAError(
            'An authenticator app is already set up. Remove it first to set up a new one.',
            'mfa_totp_exists',
            status_code=status.HTTP_409_CONFLICT,
        )
    _, secret = totp.start_setup(user)
    logger.info('mfa.totp_setup_started user=%s', user.pk)
    return {'secret': secret, 'otpauth_uri': totp.provisioning_uri(secret, user)}


def confirm_totp(user, code, request=None) -> dict:
    with transaction.atomic():
        device = TOTPDevice.objects.select_for_update().filter(user=user).first()
        if device is None:
            raise MFAError('Start the authenticator setup first.', 'mfa_no_pending_setup')
        if device.confirmed:
            raise MFAError(
                'The authenticator app is already active.', 'mfa_totp_exists', status_code=status.HTTP_409_CONFLICT
            )
        first = not (has_webauthn(user) or has_usable_email(user))
        if not totp.verify(device, code):
            logger.info('mfa.totp_confirm_failed user=%s ip=%s', user.pk, client_ip(request))
            raise MFAError('That code is not valid. Check the time on your phone and try again.', INVALID_CODE)
        device.confirmed = True
        device.confirmed_at = timezone.now()
        device.save(update_fields=['confirmed', 'confirmed_at'])
        return _factor_added(user, method=METHOD_TOTP, first=first, request=request)


def finish_passkey_registration(user, credential, name, request=None) -> dict:
    with transaction.atomic():
        first = not has_any_factor(user)
        try:
            passkeys.finish_registration(user, credential, name)
        except passkeys.PasskeyError as exc:
            raise MFAError(str(exc), 'mfa_passkey_invalid') from exc
        return _factor_added(user, method=METHOD_WEBAUTHN, first=first, request=request)


def send_email_code(user, purpose: str, request=None) -> dict:
    """Email a code for enrollment or step-up (sign-in codes: views)."""
    if not user.email:
        raise MFAError('Your account has no email address. Use another method.', 'mfa_no_email')
    if purpose == EmailCode.PURPOSE_ENROLL:
        if has_email(user):
            raise MFAError('Email codes are already on.', 'mfa_email_exists', status_code=status.HTTP_409_CONFLICT)
        if not email_allowed_for(user):
            raise MFAError(
                'Your account must use an authenticator app or a passkey.',
                'mfa_email_not_allowed',
                status_code=status.HTTP_403_FORBIDDEN,
            )
    elif not has_usable_email(user):
        raise MFAError('Email codes are not turned on for your account.', 'mfa_email_not_enabled')
    return email_codes.send(user, purpose, request=request)


def send_login_email_code(user, request=None) -> dict:
    """Email a sign-in code. Answers the same whether or not the user has
    email codes turned on (nothing is sent then), so the response says
    nothing about the account beyond what the login response already did."""
    return email_codes.send(user, EmailCode.PURPOSE_LOGIN, request=request, deliver=has_usable_email(user))


def enable_email(user, code, request=None) -> dict:
    with transaction.atomic():
        # Serialise with concurrent enable attempts of the same user.
        MFAState.objects.select_for_update().get_or_create(user=user)
        if has_email(user):
            raise MFAError('Email codes are already on.', 'mfa_email_exists', status_code=status.HTTP_409_CONFLICT)
        if not email_allowed_for(user):
            raise MFAError(
                'Your account must use an authenticator app or a passkey.',
                'mfa_email_not_allowed',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if not email_codes.verify(user, EmailCode.PURPOSE_ENROLL, code):
            logger.info('mfa.email_confirm_failed user=%s ip=%s', user.pk, client_ip(request))
            raise MFAError('That code is not valid or has expired. Ask for a new one.', INVALID_CODE)
        first = not has_any_factor(user)
        EmailFactor.objects.create(user=user, confirmed_at=timezone.now())
        return _factor_added(user, method=METHOD_EMAIL, first=first, request=request)


def regenerate_recovery_codes(user, request=None) -> list[str]:
    if not has_any_factor(user):
        raise MFAError('Turn on two-factor authentication first.', 'mfa_not_enabled')
    codes = recovery.regenerate(user)
    logger.info('mfa.recovery_codes_regenerated user=%s ip=%s', user.pk, client_ip(request))
    notify_security(
        user,
        'New recovery codes',
        'New recovery codes were generated for your EventHub account; the old ones no longer work.',
    )
    return codes


# ---- Removing factors ---- #


def _refuse_if_last_factor(user, remaining_factors: int) -> None:
    if remaining_factors == 0 and mfa_required_for(user):
        raise MFAError(
            'Two-factor authentication is required for your account. Add another method before removing this one.',
            REQUIRED_BY_POLICY,
            status_code=status.HTTP_409_CONFLICT,
        )


def _other_factors(user, *, exclude: str) -> int:
    """Factors that count for `user`, leaving out the one being removed."""
    count = 0
    if exclude != METHOD_TOTP and has_totp(user):
        count += 1
    if exclude != METHOD_EMAIL and has_usable_email(user):
        count += 1
    passkeys_qs = WebAuthnCredential.objects.filter(user=user)
    if exclude.startswith('passkey:'):
        passkeys_qs = passkeys_qs.exclude(pk=int(exclude.split(':', 1)[1]))
    return count + passkeys_qs.count()


def _after_removal(user, *, what: str, request) -> None:
    forget_mfa_enabled(user.pk)
    still_enabled = has_any_factor(user)
    if not still_enabled:
        RecoveryCode.objects.filter(user=user).delete()
        logger.warning('mfa.disabled user=%s via=%s ip=%s', user.pk, what, client_ip(request))
        notify_security(
            user,
            'Two-factor authentication is off',
            'Two-factor authentication was turned off for your EventHub account.',
        )
    else:
        logger.info('mfa.factor_removed user=%s what=%s ip=%s', user.pk, what, client_ip(request))
        notify_security(user, 'Sign-in method removed', f'{what} was removed from your EventHub account.')


@transaction.atomic
def remove_totp(user, request=None) -> None:
    device = TOTPDevice.objects.select_for_update().filter(user=user).first()
    if device is None:
        raise MFAError('No authenticator app is set up.', 'mfa_not_found', status_code=status.HTTP_404_NOT_FOUND)
    if device.confirmed:
        _refuse_if_last_factor(user, _other_factors(user, exclude=METHOD_TOTP))
    device.delete()
    if device.confirmed:
        _after_removal(user, what='The authenticator app', request=request)


@transaction.atomic
def remove_passkey(user, credential_pk, request=None) -> None:
    credential = WebAuthnCredential.objects.select_for_update().filter(user=user, pk=credential_pk).first()
    if credential is None:
        raise MFAError('No such passkey.', 'mfa_not_found', status_code=status.HTTP_404_NOT_FOUND)
    _refuse_if_last_factor(user, _other_factors(user, exclude=f'passkey:{credential.pk}'))
    credential.delete()
    _after_removal(user, what=f'The passkey "{credential.name}"', request=request)


def rename_passkey(user, credential_pk, name: str) -> WebAuthnCredential:
    credential = WebAuthnCredential.objects.filter(user=user, pk=credential_pk).first()
    if credential is None:
        raise MFAError('No such passkey.', 'mfa_not_found', status_code=status.HTTP_404_NOT_FOUND)
    credential.name = name.strip()[:64] or credential.name
    credential.save(update_fields=['name'])
    logger.info('mfa.passkey_renamed user=%s credential=%s', user.pk, credential.pk)
    return credential


@transaction.atomic
def remove_email(user, request=None) -> None:
    factor = EmailFactor.objects.select_for_update().filter(user=user).first()
    if factor is None:
        raise MFAError('Email codes are not turned on.', 'mfa_not_found', status_code=status.HTTP_404_NOT_FOUND)
    _refuse_if_last_factor(user, _other_factors(user, exclude=METHOD_EMAIL))
    factor.delete()
    EmailCode.objects.filter(user=user, is_used=False).update(is_used=True)
    _after_removal(user, what='Email codes', request=request)


@transaction.atomic
def disable_all(user, request=None) -> None:
    if mfa_required_for(user):
        raise MFAError(
            'Two-factor authentication is required for your account and cannot be turned off.',
            REQUIRED_BY_POLICY,
            status_code=status.HTTP_409_CONFLICT,
        )
    if not (has_totp(user) or has_webauthn(user) or has_email(user)):
        return
    TOTPDevice.objects.filter(user=user).delete()
    WebAuthnCredential.objects.filter(user=user).delete()
    EmailFactor.objects.filter(user=user).delete()
    _after_removal(user, what='Every sign-in method', request=request)


@transaction.atomic
def admin_reset(user, *, operator: str) -> dict:
    """manage.py mfa_reset: remove every factor and code, clear the lockout,
    sign the user out everywhere. Policy still applies: a user who must have
    2FA enrolls again at the next sign-in."""
    removed = {
        'totp': TOTPDevice.objects.filter(user=user).delete()[0],
        'passkeys': WebAuthnCredential.objects.filter(user=user).delete()[0],
        'email': EmailFactor.objects.filter(user=user).delete()[0],
        'recovery_codes': RecoveryCode.objects.filter(user=user).delete()[0],
    }
    EmailCode.objects.filter(user=user).delete()
    MFAState.objects.filter(user=user).update(failed_attempts=0, locked_until=None)
    revoke_all_refresh_tokens(user)
    forget_mfa_enabled(user.pk)
    logger.warning(
        'mfa.admin_reset user=%s username=%s operator=%s removed=%s', user.pk, user.username, operator, removed
    )
    notify_security(
        user,
        'Two-factor authentication was reset',
        'An administrator reset two-factor authentication on your EventHub account after verifying your '
        'identity. Set it up again at your next sign-in.',
    )
    return removed
