"""Recovery codes: 10 one-time codes of 80 bits, stored as salted SHA-256.

80 random bits per code make an offline search hopeless even with a fast
hash, and checking a user's ten codes stays cheap (no PBKDF2 per code).
"""

import hashlib
import hmac
import secrets

from django.db import transaction
from django.utils import timezone

from .models import RecoveryCode

CODE_COUNT = 10
_ALPHABET = 'abcdefghijkmnpqrstuvwxyz23456789'  # 32 symbols, no 0/o/1/l
_GROUPS = 4
_GROUP_LEN = 4  # 16 symbols x 5 bits = 80 bits


def _generate_code() -> str:
    raw = ''.join(secrets.choice(_ALPHABET) for _ in range(_GROUPS * _GROUP_LEN))
    return '-'.join(raw[i : i + _GROUP_LEN] for i in range(0, len(raw), _GROUP_LEN))


def normalize(code) -> str:
    return ''.join(ch for ch in str(code or '').lower() if ch.isalnum())


def _hash(salt: str, code: str) -> str:
    return hashlib.sha256(f'{salt}:{normalize(code)}'.encode()).hexdigest()


@transaction.atomic
def regenerate(user) -> list[str]:
    """Replace every code of the user; returns the plain codes (shown once)."""
    RecoveryCode.objects.filter(user=user).delete()
    codes = [_generate_code() for _ in range(CODE_COUNT)]
    rows = []
    for code in codes:
        salt = secrets.token_hex(16)
        rows.append(RecoveryCode(user=user, salt=salt, code_hash=_hash(salt, code)))
    RecoveryCode.objects.bulk_create(rows)
    return codes


def remaining(user) -> int:
    return RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()


def use(user, code) -> bool:
    """Consume a matching unused code. The UPDATE ... WHERE used_at IS NULL
    makes a code single-use under concurrency."""
    normalized = normalize(code)
    if len(normalized) != _GROUPS * _GROUP_LEN:
        return False
    match = None
    for row in RecoveryCode.objects.filter(user=user, used_at__isnull=True):
        if hmac.compare_digest(row.code_hash, _hash(row.salt, normalized)) and match is None:
            match = row
    if match is None:
        return False
    return bool(RecoveryCode.objects.filter(pk=match.pk, used_at__isnull=True).update(used_at=timezone.now()))
