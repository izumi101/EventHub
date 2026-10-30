"""Flag evaluation: the only way code asks whether a flag is on.

    from featureflags import Flags, is_enabled

    if is_enabled(Flags.PAYMENTS_FREEDOMPAY, request.user):
        ...

A lookup never raises and never waits on the network: Unleash's answer comes
from the state the background poll last fetched, and whenever there is no
answer — Unleash off, unreachable, not polled yet, the flag missing there, or
any error — the flag's registry default is returned.
"""

import contextlib
import logging
import threading

from django.core.exceptions import ObjectDoesNotExist

from .client import get_client
from .registry import CLIENT_FLAGS, FLAGS_BY_KEY, Flag

logger = logging.getLogger(__name__)

# Test/maintenance overrides: flag key -> value, consulted before Unleash.
_overrides: dict[str, bool] = {}
_overrides_lock = threading.Lock()


def _resolve(flag: Flag | str) -> Flag | None:
    if isinstance(flag, Flag):
        return flag
    return FLAGS_BY_KEY.get(flag)


def _role(user) -> str:
    try:
        return user.profile.role
    except (ObjectDoesNotExist, AttributeError):
        return ''


def build_context(user=None) -> dict:
    """The Unleash context for a user: `userId` for gradual rollouts and user
    lists, `role` and `isStaff` for constraints. No personal data (names,
    emails, IPs) leaves the backend. Unleash adds `appName` and `environment`."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return {}
    return {
        'userId': str(user.pk),
        'properties': {
            'role': _role(user),
            'isStaff': 'true' if user.is_staff else 'false',
        },
    }


def is_enabled(flag: Flag | str, user=None) -> bool:
    """Whether `flag` is on for `user` (None or anonymous: no user context)."""
    resolved = _resolve(flag)
    if resolved is None:
        # Programming error, but a flag lookup must not take a request down.
        logger.error('Unknown feature flag %r: declare it in featureflags/registry.py; answering False', flag)
        return False
    try:
        override = _overrides.get(resolved.key)
        if override is not None:
            return override
        client = get_client()
        if client is None:
            return resolved.default
        default = resolved.default
        return bool(
            client.is_enabled(
                resolved.key,
                build_context(user),
                # Consulted when Unleash doesn't know the flag (not polled yet,
                # not created there, or archived).
                fallback_function=lambda _name, _context: default,
            )
        )
    except Exception:
        logger.exception('Feature flag %s could not be evaluated; using its default', resolved.key)
        return resolved.default


def client_flags(user=None) -> dict[str, bool]:
    """The flags the SPA may see, evaluated for `user`."""
    return {flag.key: is_enabled(flag, user) for flag in CLIENT_FLAGS}


class override_flags(contextlib.ContextDecorator):
    """Force flag values, ignoring Unleash and the defaults (tests, one-off
    scripts); named like Django's `override_settings`:

        with override_flags({Flags.PAYMENTS_FREEDOMPAY: True}):
            ...

        @override_flags({Flags.PAYMENTS_FREEDOMPAY: True})
        def test_...(self): ...

    Process-wide, so not for production request code.
    """

    def __init__(self, values: dict[Flag | str, bool]):
        self._values = {}
        for flag, value in values.items():
            resolved = _resolve(flag)
            if resolved is None:
                raise KeyError(f'Unknown feature flag {flag!r}')
            self._values[resolved.key] = bool(value)
        self._saved: list[dict[str, bool]] = []

    def __enter__(self):
        with _overrides_lock:
            self._saved.append(dict(_overrides))
            _overrides.update(self._values)
        return self

    def __exit__(self, *exc_info):
        with _overrides_lock:
            _overrides.clear()
            _overrides.update(self._saved.pop())
        return False
