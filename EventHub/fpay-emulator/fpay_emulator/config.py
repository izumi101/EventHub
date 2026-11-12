"""Configuration from environment variables (all prefixed ``FPAY_``).

Every switch that covers an UNVERIFIED point of the spec is documented in the
README together with the reason for its default.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(ValueError):
    pass


_MERCHANT_RE = re.compile(r'^\d{1,18}$')
REQUEST_METHODS = ('GET', 'POST', 'XML')
REDIRECT_METHODS = ('GET', 'POST', 'AUTOGET', 'AUTOPOST')


@dataclass(frozen=True)
class Merchant:
    merchant_id: str
    secret: str = field(repr=False)
    name: str = ''
    check_url: str | None = None
    result_url: str | None = None
    success_url: str | None = None
    failure_url: str | None = None
    request_method: str = 'POST'

    @property
    def display_name(self) -> str:
        return self.name or f'Merchant {self.merchant_id}'


def _bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or raw == '':
        return default
    value = raw.strip().lower()
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    raise ConfigError(f'{name} must be 0 or 1, got {raw!r}')


def _int(env: Mapping[str, str], name: str, default: int, minimum: int = 0) -> int:
    raw = env.get(name)
    if raw is None or raw == '':
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f'{name} must be an integer, got {raw!r}') from exc
    if value < minimum:
        raise ConfigError(f'{name} must be >= {minimum}')
    return value


def _float(env: Mapping[str, str], name: str, default: float, minimum: float = 0.0) -> float:
    raw = env.get(name)
    if raw is None or raw == '':
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f'{name} must be a number, got {raw!r}') from exc
    if value < minimum:
        raise ConfigError(f'{name} must be >= {minimum}')
    return value


def _choice(env: Mapping[str, str], name: str, default: str, choices: tuple[str, ...]) -> str:
    value = (env.get(name) or default).strip().lower()
    if value not in choices:
        raise ConfigError(f'{name} must be one of {", ".join(choices)}, got {value!r}')
    return value


def _url(env: Mapping[str, str], name: str) -> str | None:
    value = (env.get(name) or '').strip()
    if not value:
        return None
    if not value.startswith(('http://', 'https://')):
        raise ConfigError(f'{name} must be an http(s) URL')
    return value


def parse_merchants(env: Mapping[str, str]) -> dict[str, Merchant]:
    raw = (env.get('FPAY_MERCHANTS') or '').strip()
    if not raw:
        raise ConfigError('FPAY_MERCHANTS is required, e.g. FPAY_MERCHANTS=12345:my_test_secret')
    merchants: dict[str, Merchant] = {}
    for item in raw.split(','):
        item = item.strip()
        if not item:
            continue
        merchant_id, sep, secret = item.partition(':')
        merchant_id = merchant_id.strip()
        if not sep or not _MERCHANT_RE.match(merchant_id) or not secret:
            raise ConfigError('FPAY_MERCHANTS entries must look like <numeric id>:<secret>')
        prefix = f'FPAY_MERCHANT_{merchant_id}_'
        method = (env.get(prefix + 'REQUEST_METHOD') or 'POST').strip().upper()
        if method not in REQUEST_METHODS:
            raise ConfigError(f'{prefix}REQUEST_METHOD must be GET, POST or XML')
        merchants[merchant_id] = Merchant(
            merchant_id=merchant_id,
            secret=secret,
            name=(env.get(prefix + 'NAME') or '').strip(),
            check_url=_url(env, prefix + 'CHECK_URL'),
            result_url=_url(env, prefix + 'RESULT_URL'),
            success_url=_url(env, prefix + 'SUCCESS_URL'),
            failure_url=_url(env, prefix + 'FAILURE_URL'),
            request_method=method,
        )
    if not merchants:
        raise ConfigError('FPAY_MERCHANTS lists no merchant')
    return merchants


@dataclass(frozen=True)
class Settings:
    merchants: dict[str, Merchant]
    public_url: str = 'http://localhost:8080'
    db_path: str = 'fpay-emulator.sqlite3'
    timezone: str = 'Asia/Almaty'
    commission_percent: Decimal = Decimal('2.5')
    commission_payer: str = 'merchant'
    default_currency: str = 'KZT'
    currencies: tuple[str, ...] = ('KZT', 'USD', 'EUR', 'RUB', 'UZS', 'KGS')
    control_enabled: bool = True
    control_token: str | None = field(default=None, repr=False)
    # Check URL (S5)
    check_enabled: bool = False
    check_timeout_seconds: float = 30.0
    reject_failure_code: str = '99999'
    # Result URL (S4)
    reply_mode: str = 'strict'
    reply_salt_must_echo: bool = True
    retry_on_error_reply: bool = True
    retry_interval_seconds: int = 1800
    retry_window_seconds: int = 7200
    callback_timeout_seconds: float = 30.0
    callback_sign_url_query: str = 'get_only'
    result_failure_fields: bool = False
    result_on_expiry: bool = True
    expiry_pg_result: str = '0'
    # init_payment
    order_id_uniqueness: str = 'off'
    lifetime_default_seconds: int = 86400
    lifetime_min_seconds: int = 300
    lifetime_max_seconds: int = 604800
    auto_clearing_default: bool = True
    merchant_test_mode: bool = True
    salt_strict: bool = True
    tax_types: tuple[str, ...] = ('0', '3', '7', '11')
    # capture / refunds
    auto_capture_days: int = 5
    auto_capture_action: str = 'capture'
    auto_process_test_payments: bool = False
    refunds_enabled: bool = True
    refund_window_days: int = 180
    # error codes
    bad_signature_code: str = '9998'
    status_bad_signature_code: str = '1100'
    legacy_status_endpoints: bool = True
    json_status_id_must_be_number: bool = True
    three_ds_password: str = field(default='12345678', repr=False)
    scheduler_tick_seconds: float = 1.0
    log_level: str = 'INFO'

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def merchant(self, merchant_id: str | None) -> Merchant | None:
        if merchant_id is None:
            return None
        return self.merchants.get(merchant_id.strip())

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        timezone = (env.get('FPAY_TIMEZONE') or 'Asia/Almaty').strip()
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ConfigError(f'FPAY_TIMEZONE {timezone!r} is not an IANA time zone') from exc
        try:
            commission = Decimal((env.get('FPAY_COMMISSION_PERCENT') or '2.5').strip())
        except InvalidOperation as exc:
            raise ConfigError('FPAY_COMMISSION_PERCENT must be a decimal number') from exc
        if not Decimal(0) <= commission < Decimal(100):
            raise ConfigError('FPAY_COMMISSION_PERCENT must be in [0, 100)')
        currencies = tuple(
            c.strip().upper() for c in (env.get('FPAY_CURRENCIES') or 'KZT,USD,EUR,RUB,UZS,KGS').split(',') if c.strip()
        )
        default_currency = (env.get('FPAY_DEFAULT_CURRENCY') or 'KZT').strip().upper()
        if default_currency not in currencies:
            raise ConfigError('FPAY_DEFAULT_CURRENCY must be listed in FPAY_CURRENCIES')
        expiry_result = (env.get('FPAY_EXPIRY_PG_RESULT') or '0').strip()
        if expiry_result not in ('0', '2'):
            raise ConfigError('FPAY_EXPIRY_PG_RESULT must be 0 or 2')
        lifetime_min = _int(env, 'FPAY_LIFETIME_MIN_SECONDS', 300, minimum=1)
        public_url = (env.get('FPAY_PUBLIC_URL') or 'http://localhost:8080').strip().rstrip('/')
        if not public_url.startswith(('http://', 'https://')):
            raise ConfigError('FPAY_PUBLIC_URL must be an http(s) URL')
        return cls(
            merchants=parse_merchants(env),
            public_url=public_url,
            db_path=(env.get('FPAY_DB_PATH') or 'fpay-emulator.sqlite3').strip(),
            timezone=timezone,
            commission_percent=commission,
            commission_payer=_choice(env, 'FPAY_COMMISSION_PAYER', 'merchant', ('merchant', 'client')),
            default_currency=default_currency,
            currencies=currencies,
            control_enabled=_bool(env, 'FPAY_CONTROL_ENABLED', True),
            control_token=(env.get('FPAY_CONTROL_TOKEN') or '').strip() or None,
            check_enabled=_bool(env, 'FPAY_CHECK_ENABLED', False),
            check_timeout_seconds=_float(env, 'FPAY_CHECK_TIMEOUT_SECONDS', 30.0, minimum=0.1),
            reject_failure_code=(env.get('FPAY_REJECT_FAILURE_CODE') or '99999').strip(),
            reply_mode=_choice(env, 'FPAY_REPLY_MODE', 'strict', ('strict', 'lenient')),
            reply_salt_must_echo=_bool(env, 'FPAY_REPLY_SALT_MUST_ECHO', True),
            retry_on_error_reply=_bool(env, 'FPAY_RETRY_ON_ERROR_REPLY', True),
            retry_interval_seconds=_int(env, 'FPAY_RETRY_INTERVAL_SECONDS', 1800, minimum=1),
            retry_window_seconds=_int(env, 'FPAY_RETRY_WINDOW_SECONDS', 7200),
            callback_timeout_seconds=_float(env, 'FPAY_CALLBACK_TIMEOUT_SECONDS', 30.0, minimum=0.1),
            callback_sign_url_query=_choice(
                env, 'FPAY_CALLBACK_SIGN_URL_QUERY', 'get_only', ('never', 'get_only', 'always')
            ),
            result_failure_fields=_bool(env, 'FPAY_RESULT_FAILURE_FIELDS', False),
            result_on_expiry=_bool(env, 'FPAY_RESULT_ON_EXPIRY', True),
            expiry_pg_result=expiry_result,
            order_id_uniqueness=_choice(env, 'FPAY_ORDER_ID_UNIQUENESS', 'off', ('off', 'return_existing', 'reject')),
            lifetime_min_seconds=lifetime_min,
            auto_clearing_default=_bool(env, 'FPAY_AUTO_CLEARING_DEFAULT', True),
            merchant_test_mode=_bool(env, 'FPAY_MERCHANT_TEST_MODE', True),
            salt_strict=_bool(env, 'FPAY_SALT_STRICT', True),
            tax_types=tuple(t.strip() for t in (env.get('FPAY_TAX_TYPES') or '0,3,7,11').split(',') if t.strip()),
            auto_capture_days=_int(env, 'FPAY_AUTO_CAPTURE_DAYS', 5),
            auto_capture_action=_choice(env, 'FPAY_AUTO_CAPTURE_ACTION', 'capture', ('capture', 'cancel')),
            auto_process_test_payments=_bool(env, 'FPAY_AUTO_PROCESS_TEST_PAYMENTS', False),
            refunds_enabled=_bool(env, 'FPAY_REFUNDS_ENABLED', True),
            refund_window_days=_int(env, 'FPAY_REFUND_WINDOW_DAYS', 180),
            bad_signature_code=(env.get('FPAY_BAD_SIGNATURE_CODE') or '9998').strip(),
            status_bad_signature_code=(env.get('FPAY_STATUS_BAD_SIGNATURE_CODE') or '1100').strip(),
            legacy_status_endpoints=_bool(env, 'FPAY_LEGACY_STATUS_ENDPOINTS', True),
            json_status_id_must_be_number=_bool(env, 'FPAY_JSON_STATUS_ID_MUST_BE_NUMBER', True),
            three_ds_password=(env.get('FPAY_3DS_PASSWORD') or '12345678'),
            scheduler_tick_seconds=_float(env, 'FPAY_SCHEDULER_TICK_SECONDS', 1.0, minimum=0.05),
            log_level=(env.get('FPAY_LOG_LEVEL') or 'INFO').strip().upper(),
        )
