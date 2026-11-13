"""Start-up checks of the 2FA settings, imported by settings.py (so: no
Django models or app registry here)."""

DEV_ENCRYPTION_KEY = 'dev-only-mfa-encryption-key-change-me'
MIN_KEY_LENGTH = 32


def production_problems(*, encryption_keys, rp_id: str, origins) -> list[str]:
    """What must be fixed before running with DJANGO_DEBUG=0."""
    problems = []
    if not encryption_keys or DEV_ENCRYPTION_KEY in encryption_keys:
        problems.append(
            'MFA_ENCRYPTION_KEY must be set (it encrypts TOTP secrets; generate one with '
            '`python -c "import secrets; print(secrets.token_urlsafe(48))"`)'
        )
    elif any(len(key) < MIN_KEY_LENGTH for key in encryption_keys):
        problems.append(f'every MFA_ENCRYPTION_KEY entry must be at least {MIN_KEY_LENGTH} characters long')
    if not rp_id or '://' in rp_id or ':' in rp_id or '/' in rp_id:
        problems.append('WEBAUTHN_RP_ID must be a bare host name such as eventhub.example (no scheme or port)')
    if not origins:
        problems.append('WEBAUTHN_ORIGINS must list the origin(s) the site is served from')
    return problems
