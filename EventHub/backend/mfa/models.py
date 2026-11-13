"""Second factors of a user (docs/adr/0002-two-factor-authentication.md).

A user "has 2FA" when they own a confirmed TOTP device or at least one
WebAuthn credential. Recovery codes are a fallback, not a factor of their own.
"""

from django.contrib.auth.models import User
from django.db import models


class TOTPDevice(models.Model):
    """An authenticator app. The secret is Fernet-encrypted (mfa/crypto.py)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='totp_device')
    encrypted_secret = models.TextField(help_text='Fernet token; never the plain secret.')
    # Inactive until the first code is confirmed (enrollment step 2).
    confirmed = models.BooleanField(default=False)
    # Highest RFC 6238 time step accepted so far: that code and every older
    # one are refused afterwards (replay protection).
    last_used_step = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'TOTP device'

    def __str__(self):
        state = 'active' if self.confirmed else 'pending'
        return f'TOTP for {self.user.username} ({state})'


class WebAuthnCredential(models.Model):
    """A passkey or security key registered with WebAuthn."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='webauthn_credentials')
    name = models.CharField(max_length=64)
    # base64url of the raw credential id (what the browser sends back).
    credential_id = models.CharField(max_length=1366, unique=True)
    public_key = models.BinaryField()
    sign_count = models.BigIntegerField(default=0)
    transports = models.JSONField(default=list, blank=True)
    aaguid = models.CharField(max_length=36, blank=True)
    backed_up = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'WebAuthn credential'

    def __str__(self):
        return f'{self.name} ({self.user.username})'


class RecoveryCode(models.Model):
    """One-time fallback code; only a salted SHA-256 hash is stored."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mfa_recovery_codes')
    salt = models.CharField(max_length=32)
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'used_at'])]

    def __str__(self):
        return f'Recovery code of {self.user.username} ({"used" if self.used_at else "unused"})'


class MFAState(models.Model):
    """Per-user counters: consecutive failures / lockout, WebAuthn user handle."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='mfa_state')
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    # Random, stable WebAuthn user.id (never the database id).
    webauthn_user_handle = models.CharField(max_length=128, blank=True)

    class Meta:
        verbose_name = 'MFA state'

    def __str__(self):
        return f'MFA state of {self.user.username}'
