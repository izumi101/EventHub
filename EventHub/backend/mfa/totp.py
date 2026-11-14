"""TOTP (RFC 6238): 6 digits, 30-second steps, SHA-1 — the authenticator-app default."""

import hmac
import time

import pyotp
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .crypto import decrypt_secret, encrypt_secret, needs_rotation
from .models import TOTPDevice

DIGITS = 6
INTERVAL = 30
# Accept the previous and the next step as well (clock drift of up to ~30 s).
VALID_WINDOW = 1


def normalize_code(code) -> str:
    return ''.join(str(code or '').split()).replace('-', '')


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // INTERVAL)


def new_secret() -> str:
    return pyotp.random_base32(length=32)  # 160 bits, as RFC 4226 recommends


def provisioning_uri(secret: str, user) -> str:
    account = user.email or user.username
    return pyotp.TOTP(secret, digits=DIGITS, interval=INTERVAL).provisioning_uri(
        name=account, issuer_name=settings.MFA_TOTP_ISSUER
    )


def start_setup(user) -> tuple[TOTPDevice, str]:
    """Create (or replace) the user's *pending* device; returns the plain
    secret for the QR code. A confirmed device is never replaced here."""
    secret = new_secret()
    device, _ = TOTPDevice.objects.update_or_create(
        user=user,
        defaults={
            'encrypted_secret': encrypt_secret(secret),
            'confirmed': False,
            'confirmed_at': None,
            'last_used_step': None,
            'last_used_at': None,
        },
    )
    return device, secret


def code_for_step(secret: str, step: int) -> str:
    return pyotp.TOTP(secret, digits=DIGITS, interval=INTERVAL).generate_otp(step)


def verify(device: TOTPDevice, code, now: float | None = None) -> bool:
    """Check `code` against steps current±1 and burn the matching step.

    Replay protection: the step is recorded with a conditional UPDATE, so a
    code (or any older code) is accepted at most once — also when two
    requests race with the same code.
    """
    code = normalize_code(code)
    if len(code) != DIGITS or not code.isdigit():
        return False
    secret = decrypt_secret(device.encrypted_secret)
    step_now = current_step(now)
    matched = None
    # Compare against every candidate (no early exit) in constant time.
    for step in range(step_now - VALID_WINDOW, step_now + VALID_WINDOW + 1):
        if hmac.compare_digest(code_for_step(secret, step), code) and matched is None:
            matched = step
    if matched is None:
        return False
    burned = (
        TOTPDevice.objects.filter(pk=device.pk)
        .filter(Q(last_used_step__isnull=True) | Q(last_used_step__lt=matched))
        .update(last_used_step=matched, last_used_at=timezone.now())
    )
    if not burned:
        return False
    device.last_used_step = matched
    if needs_rotation(device.encrypted_secret):
        device.encrypted_secret = encrypt_secret(secret)
        device.save(update_fields=['encrypted_secret'])
    return True
