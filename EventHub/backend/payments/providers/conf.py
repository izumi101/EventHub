"""Which payment providers exist and what each needs to run.

Plain Python with no Django imports: `eventhub_backend/settings.py` imports
it for the production start-up guard, before any app is loaded.
"""

from collections.abc import Callable, Iterable

MOCK = 'mock'

# Settings each provider needs before it can take money.
REQUIRED_SETTINGS: dict[str, tuple[str, ...]] = {
    'stripe': ('STRIPE_SECRET_KEY', 'STRIPE_WEBHOOK_SECRET'),
    MOCK: (),
}
KNOWN_PROVIDERS = frozenset(REQUIRED_SETTINGS)


def is_placeholder(value) -> bool:
    """Empty, or a value copied from an example file."""
    value = str(value or '').strip()
    return not value or 'your_' in value or value.endswith('_here')


def parse_enabled(value: str | Iterable[str] | None) -> list[str]:
    """`'stripe, mock'` or a list -> `['stripe', 'mock']` (lower case, no
    blanks or repeats, order kept)."""
    items = value.split(',') if isinstance(value, str) else list(value or [])
    codes = []
    for item in items:
        code = str(item).strip().lower()
        if code and code not in codes:
            codes.append(code)
    return codes


def enabled_codes(enabled: Iterable[str], *, mock_mode: bool) -> list[str]:
    """The enabled providers; `PAYMENTS_MOCK_MODE` adds the mock provider."""
    codes = parse_enabled(enabled)
    if mock_mode and MOCK not in codes:
        codes.append(MOCK)
    return codes


def unknown_codes(enabled: Iterable[str]) -> list[str]:
    return [code for code in parse_enabled(enabled) if code not in KNOWN_PROVIDERS]


def missing_settings(code: str, get_setting: Callable[[str], object]) -> list[str]:
    return [name for name in REQUIRED_SETTINGS.get(code, ()) if is_placeholder(get_setting(name))]


def production_problems(enabled: Iterable[str], *, mock_mode: bool, get_setting: Callable[[str], object]) -> list[str]:
    """What stops a DEBUG=0 deployment from taking payments; [] when fine.

    Every enabled provider must be fully configured, at least one must be
    enabled, and the mock provider is never allowed.
    """
    codes = enabled_codes(enabled, mock_mode=mock_mode)
    problems = []
    unknown = unknown_codes(codes)
    if unknown:
        problems.append(f'PAYMENT_PROVIDERS_ENABLED lists unknown payment providers: {", ".join(unknown)}')
    if MOCK in codes:
        problems.append(
            'the mock payment provider (PAYMENTS_MOCK_MODE, or the deprecated STRIPE_MOCK_MODE, or "mock" '
            'in PAYMENT_PROVIDERS_ENABLED) confirms payments without charging anyone'
        )
    real = [code for code in codes if code in KNOWN_PROVIDERS and code != MOCK]
    if not real and not unknown:
        problems.append('PAYMENT_PROVIDERS_ENABLED must list at least one payment provider')
    for code in real:
        missing = missing_settings(code, get_setting)
        if missing:
            problems.append(f'{" and ".join(missing)} must be set')
    return problems
