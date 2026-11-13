"""WebAuthn / passkeys with py_webauthn.

RP ID and the allowed origins come from settings (WEBAUTHN_RP_ID,
WEBAUTHN_ORIGINS) and must match how the SPA is served: WebAuthn only works
in a secure context (https, or http://localhost) and an IP address can't be
an RP ID — see docs/SECURITY_2FA.md.

Challenges are random, kept in the shared cache for a few minutes and
consumed on first use.
"""

import json
import logging
import secrets

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .models import MFAState, WebAuthnCredential

logger = logging.getLogger('mfa')

_TRANSPORTS = {t.value for t in AuthenticatorTransport}
MAX_PASSKEYS = 10


class PasskeyError(ValueError):
    """Registration or assertion refused; the message is safe to show."""


def registration_key(user) -> str:
    return f'mfa:webauthn:register:{user.pk}'


def login_key(challenge_jti: str) -> str:
    return f'mfa:webauthn:login:{challenge_jti}'


def step_up_key(user) -> str:
    return f'mfa:webauthn:step-up:{user.pk}'


def _store(key: str, value) -> None:
    cache.set(key, value, timeout=settings.MFA_WEBAUTHN_CHALLENGE_TTL_SECONDS)


def _consume(key: str):
    """Return the stored value once; a second caller (or a replay) gets None."""
    value = cache.get(key)
    if value is None or not cache.delete(key):
        return None
    return value


def _user_handle(user) -> bytes:
    state, _ = MFAState.objects.get_or_create(user=user)
    if not state.webauthn_user_handle:
        state.webauthn_user_handle = bytes_to_base64url(secrets.token_bytes(32))
        state.save(update_fields=['webauthn_user_handle'])
    return base64url_to_bytes(state.webauthn_user_handle)


def _descriptor(credential: WebAuthnCredential) -> PublicKeyCredentialDescriptor:
    transports = [AuthenticatorTransport(t) for t in credential.transports or [] if t in _TRANSPORTS]
    return PublicKeyCredentialDescriptor(id=base64url_to_bytes(credential.credential_id), transports=transports or None)


def _options_dict(options) -> dict:
    return json.loads(options_to_json(options))


def registration_options(user, name: str) -> dict:
    existing = list(WebAuthnCredential.objects.filter(user=user))
    if len(existing) >= MAX_PASSKEYS:
        raise PasskeyError(f'You can register up to {MAX_PASSKEYS} passkeys. Remove one first.')
    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_name=user.username,
        user_id=_user_handle(user),
        user_display_name=user.get_full_name() or user.username,
        timeout=settings.MFA_WEBAUTHN_CHALLENGE_TTL_SECONDS * 1000,
        exclude_credentials=[_descriptor(c) for c in existing],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    _store(registration_key(user), {'challenge': bytes_to_base64url(options.challenge), 'name': name})
    return _options_dict(options)


def finish_registration(user, credential, name: str | None = None) -> WebAuthnCredential:
    state = _consume(registration_key(user))
    if state is None:
        raise PasskeyError('The passkey request expired. Start again.')
    if not isinstance(credential, dict):
        raise PasskeyError('Invalid passkey response.')
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(state['challenge']),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=list(settings.WEBAUTHN_ORIGINS),
            require_user_verification=False,
        )
    except (InvalidRegistrationResponse, KeyError, TypeError, ValueError) as exc:
        logger.warning('mfa.passkey_registration_failed user=%s reason=%s', user.pk, exc)
        raise PasskeyError('The passkey could not be verified.') from exc

    response = credential.get('response') if isinstance(credential.get('response'), dict) else {}
    transports = [t for t in response.get('transports') or [] if isinstance(t, str) and t in _TRANSPORTS]
    label = (name or state.get('name') or '').strip()[:64] or 'Passkey'
    try:
        with transaction.atomic():
            return WebAuthnCredential.objects.create(
                user=user,
                name=label,
                credential_id=bytes_to_base64url(verified.credential_id),
                public_key=verified.credential_public_key,
                sign_count=verified.sign_count,
                transports=transports,
                aaguid=str(verified.aaguid or ''),
                backed_up=bool(verified.credential_backed_up),
            )
    except IntegrityError as exc:
        raise PasskeyError('This passkey is already registered.') from exc


def authentication_options(user, key: str) -> dict:
    credentials = list(WebAuthnCredential.objects.filter(user=user))
    if not credentials:
        raise PasskeyError('No passkey is registered for this account.')
    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        timeout=settings.MFA_WEBAUTHN_CHALLENGE_TTL_SECONDS * 1000,
        allow_credentials=[_descriptor(c) for c in credentials],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    _store(key, bytes_to_base64url(options.challenge))
    return _options_dict(options)


def verify_assertion(user, credential, key: str) -> WebAuthnCredential | None:
    """The credential that signed the stored challenge, or None."""
    challenge = _consume(key)
    if challenge is None or not isinstance(credential, dict):
        return None
    credential_id = credential.get('id')
    row = WebAuthnCredential.objects.filter(user=user, credential_id=credential_id).first()
    if row is None:
        return None
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=list(settings.WEBAUTHN_ORIGINS),
            credential_public_key=bytes(row.public_key),
            credential_current_sign_count=row.sign_count,
            require_user_verification=False,
        )
    except InvalidAuthenticationResponse as exc:
        if 'sign count' in str(exc).lower():
            # The counter went backwards or stood still: the private key may
            # have been copied to another authenticator.
            logger.warning(
                'mfa.passkey_clone_suspected user=%s credential=%s stored_count=%s', user.pk, row.pk, row.sign_count
            )
        else:
            logger.info('mfa.passkey_assertion_invalid user=%s credential=%s reason=%s', user.pk, row.pk, exc)
        return None
    except (KeyError, TypeError, ValueError) as exc:
        logger.info('mfa.passkey_assertion_malformed user=%s reason=%s', user.pk, exc)
        return None
    # Conditional on the counter we verified against: two racing assertions
    # can't both move it.
    updated = WebAuthnCredential.objects.filter(pk=row.pk, sign_count=row.sign_count).update(
        sign_count=verified.new_sign_count, last_used_at=timezone.now()
    )
    if not updated:
        return None
    return row
