"""Every feature flag the code knows about — the single source of truth.

A flag is declared here first, with the value it falls back to whenever
Unleash can't answer (not configured, unreachable, not yet polled, or the flag
doesn't exist there). Unleash decides only for flags it knows; the code never
asks for a name that isn't declared here.

Flags are temporary: each one names an owner and a date by which it is either
removed together with the code path it guards, or the old path is. See
docs/FEATURE_FLAGS.md for naming, lifecycle and the safe-default rule.
"""

import re
from dataclasses import dataclass
from datetime import date

# `<area>.<capability>`, lower snake case: `payments.freedompay`.
FLAG_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$')


@dataclass(frozen=True, slots=True)
class Flag:
    key: str
    # The value used whenever Unleash can't answer. New capabilities default
    # to False (off until rolled out); kill switches for existing behaviour
    # default to True (on unless an operator turns them off).
    default: bool
    description: str
    # Team or person who removes the flag once the rollout is finished.
    owner: str
    # The flag and the losing code path are deleted by this date
    # (`manage.py check` warns once it has passed).
    remove_by: date
    # Evaluated for the signed-in user by GET /api/v1/feature-flags/, so the
    # SPA can show or hide UI. Server-only flags stay False.
    client_visible: bool = False

    def __str__(self) -> str:
        return self.key


class Flags:
    """Namespace of the declared flags: `is_enabled(Flags.PAYMENTS_FREEDOMPAY)`."""

    PAYMENTS_FREEDOMPAY = Flag(
        key='payments.freedompay',
        default=False,
        description='Offer Freedom Pay as the payment method for KZT events (payment provider layer, roadmap phase 1).',
        owner='payments',
        remove_by=date(2027, 6, 30),
        client_visible=True,
    )
    CHECKIN_OFFLINE_SCANNER = Flag(
        key='checkin.offline_scanner',
        default=False,
        description='Offline-capable ticket scanner for check-in staff (offline PWA scanner, roadmap phase 8).',
        owner='check-in',
        remove_by=date(2027, 9, 30),
        client_visible=True,
    )


ALL_FLAGS: tuple[Flag, ...] = tuple(value for value in vars(Flags).values() if isinstance(value, Flag))
FLAGS_BY_KEY: dict[str, Flag] = {flag.key: flag for flag in ALL_FLAGS}
CLIENT_FLAGS: tuple[Flag, ...] = tuple(flag for flag in ALL_FLAGS if flag.client_visible)


def registry_problems(flags=None) -> list[str]:
    """Declaration mistakes that must stop the app from starting."""
    flags = ALL_FLAGS if flags is None else flags
    problems = []
    seen = set()
    for flag in flags:
        if not FLAG_KEY_PATTERN.match(flag.key):
            problems.append(f'{flag.key!r} is not a valid flag key (expected "<area>.<capability>", lower snake case)')
        if flag.key in seen:
            problems.append(f'{flag.key!r} is declared more than once')
        seen.add(flag.key)
        if not isinstance(flag.default, bool):
            problems.append(f'{flag.key!r} must have a bool default')
        if not flag.description.strip() or not flag.owner.strip():
            problems.append(f'{flag.key!r} needs a description and an owner')
    return problems
