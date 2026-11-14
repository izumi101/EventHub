"""Operator overrides of the API rate limits (`DJANGO_THROTTLE_RATES`).

The defaults in settings suit one real user per address. A browser test run
signs dozens of fresh accounts in from one address within minutes, and an
operator may want different limits on a given deployment, so the rates can
be replaced per scope without a code change:

    DJANGO_THROTTLE_RATES=login=60/min,register=60/min,mfa_ip=120/min

Only scopes that already exist can be changed (a typo must not silently do
nothing), and every rate must be one Django REST framework can parse.
"""

import re

# DRF's SimpleRateThrottle.parse_rate reads "<count>/<period>" and looks only
# at the first letter of the period; accept the spellings it documents.
_RATE = re.compile(r'^[1-9][0-9]*/(s|sec|second|m|min|minute|h|hour|d|day)$')


def parse_overrides(raw: str, known_scopes) -> dict[str, str]:
    """`scope=rate` pairs, comma separated, to a dict. Raises ValueError
    naming every problem (unknown scope, bad rate, duplicate, bad pair)."""
    overrides: dict[str, str] = {}
    problems: list[str] = []
    for item in (part.strip() for part in raw.split(',')):
        if not item:
            continue
        scope, sep, rate = (piece.strip() for piece in item.partition('='))
        if not sep or not scope or not rate:
            problems.append(f'"{item}" is not scope=rate')
        elif scope not in known_scopes:
            problems.append(f'unknown scope "{scope}" (known: {", ".join(sorted(known_scopes))})')
        elif not _RATE.match(rate):
            problems.append(f'"{rate}" for {scope} is not a rate such as 60/min')
        elif scope in overrides:
            problems.append(f'{scope} is listed twice')
        else:
            overrides[scope] = rate
    if problems:
        raise ValueError('; '.join(problems))
    return overrides
