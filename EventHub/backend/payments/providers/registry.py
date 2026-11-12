"""Provider registry: which providers exist, which are enabled, which can
take money right now.

- registered: every provider class known to the code (`register`);
- enabled: listed in `PAYMENT_PROVIDERS_ENABLED`, plus the mock provider
  when `PAYMENTS_MOCK_MODE` is on (the deprecated `STRIPE_MOCK_MODE` is
  resolved into it by settings.py);
- configured: enabled and `is_configured()`; only these are selectable.
"""

from __future__ import annotations

from django.conf import settings

from . import conf
from .base import PaymentProvider

_REGISTRY: dict[str, type[PaymentProvider]] = {}
_BUILTINS_LOADED = False


class UnknownProvider(LookupError):
    """No provider with that code is registered."""


class ProviderNotEnabled(LookupError):
    """The provider exists but this deployment does not enable it."""


def register(provider_class: type[PaymentProvider]) -> type[PaymentProvider]:
    """Class decorator: make `provider_class` available under its code."""
    code = getattr(provider_class, 'code', '')
    if not code:
        raise ValueError(f'{provider_class.__name__} has no provider code')
    existing = _REGISTRY.get(code)
    if existing is not None and existing is not provider_class:
        raise ValueError(f'payment provider {code!r} is already registered by {existing.__name__}')
    _REGISTRY[code] = provider_class
    return provider_class


def _load_builtins() -> None:
    # Imported lazily: provider modules import the SDKs and Django settings.
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    from . import freedompay, mock, stripe  # noqa: F401

    _BUILTINS_LOADED = True


def registered_codes() -> list[str]:
    _load_builtins()
    return sorted(_REGISTRY)


def enabled_codes() -> list[str]:
    return conf.enabled_codes(
        getattr(settings, 'PAYMENT_PROVIDERS_ENABLED', ['stripe']),
        mock_mode=getattr(settings, 'PAYMENTS_MOCK_MODE', False),
    )


def get(code: str, *, require_enabled: bool = True) -> PaymentProvider:
    """The provider instance for `code`.

    Instances are cheap and read settings on use, so a fresh one is returned
    each time (settings overrides in tests apply immediately).
    """
    _load_builtins()
    provider_class = _REGISTRY.get(code)
    if provider_class is None:
        raise UnknownProvider(f'unknown payment provider {code!r}')
    if require_enabled and code not in enabled_codes():
        raise ProviderNotEnabled(f'payment provider {code!r} is not enabled')
    return provider_class()


def enabled() -> list[PaymentProvider]:
    """Enabled providers that the code knows, in the configured order."""
    _load_builtins()
    return [_REGISTRY[code]() for code in enabled_codes() if code in _REGISTRY]


def configured() -> list[PaymentProvider]:
    """Enabled providers that can take money now."""
    return [provider for provider in enabled() if provider.is_configured()]


def for_currency(currency: str) -> list[PaymentProvider]:
    """Configured providers that can charge `currency`, in configured order."""
    return [provider for provider in configured() if provider.supports_currency(currency)]
