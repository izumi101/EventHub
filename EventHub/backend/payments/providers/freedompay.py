"""Freedom Pay (ex-PayBox) Merchant API provider (ADR 0001).

Protocol: docs/payments/freedompay-protocol.md. Every call is a signed
`application/x-www-form-urlencoded` POST answered with XML; successful
answers are signed with the same script name and secret, error answers
(`pg_error_code`) are not. An answer without a valid `pg_sig` is never
trusted (S1).

- `create_payment`: `init_payment.php` with `pg_generate_qr=1`; the QR (a
  base64 PNG of the payment page URL) comes back in `CheckoutResult.raw`.
- `handle_callback`: the Result notification, signed with the last path
  segment of *our* callback URL. MD5 is weak, so the orchestration confirms
  a `paid` notification with `get_status` before it issues a ticket.
- `callback_response`: the signed XML reply (`ok` / `rejected` / `error`)
  that echoes the request's `pg_salt`; re-deliveries get the same answer.
- `get_status`: `get_status3.php`.
- `refund`: `revoke` (full or partial, with `pg_idempotency_key`).
- `cancel_session`: the protocol cannot close an unpaid payment page
  (`cancel` reverses a *paid* payment), so this is a documented no-op; an
  abandoned page simply expires after `pg_lifetime`.

Network calls use a 5 s connect / 15 s read timeout. The provider never
touches the database.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl

import requests
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from . import conf
from . import freedompay_signature as sig
from .base import (
    CallbackKind,
    CallbackResult,
    CheckoutResult,
    InvalidCallback,
    PaymentOrder,
    PaymentProvider,
    ProviderRejected,
    ProviderUnavailable,
    RefundResult,
    StatusResult,
)
from .registry import register

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 15
# pg_lifetime: the gateway clamps to [300 (legacy minimum), 604800] seconds.
MIN_LIFETIME_SECONDS = 300
MAX_LIFETIME_SECONDS = 604800
MAX_CALLBACK_BYTES = 32 * 1024
MAX_DESCRIPTION = 1024

INIT_SCRIPT = 'init_payment.php'
STATUS_SCRIPT = 'get_status3.php'
REFUND_SCRIPT = 'revoke'

_DIGITS = re.compile(r'^\d{1,30}$')
_CURRENCY = re.compile(r'^[A-Z]{3}$')
_EMAIL = re.compile(r'^[^@\s;]+@[^@\s;]+\.[^@\s;]+$')
# Request errors that mean "try again later" (refund/cancel in progress, system error).
_RETRYABLE_ERRORS = frozenset({'91021', '91031', '9999'})
# Callback fields kept in PaymentEvent.payload: no card data, no signature.
_KEPT_CALLBACK_FIELDS = (
    'pg_order_id',
    'pg_payment_id',
    'pg_amount',
    'pg_currency',
    'pg_result',
    'pg_can_reject',
    'pg_testing_mode',
    'pg_payment_date',
    'pg_payment_method',
    'pg_captured',
    'pg_failure_code',
)
_STATUS_PENDING = frozenset({'new', 'waiting', 'process'})
_LIFETIME_EXPIRED = '10018'

# What our reply says for each processing outcome (PaymentEvent.Outcome).
REPLY_OK = 'ok'
REPLY_REJECTED = 'rejected'
REPLY_ERROR = 'error'
_REPLY_DESCRIPTIONS = {
    'processed': 'Payment accepted',
    'ignored': 'Notification accepted',
    'orphan': 'Unknown order: the payment will be refunded',
    'duplicate_payment': 'Order already paid: the payment will be refunded',
    'late_payment': 'Order no longer payable: the payment will be refunded',
    'amount_mismatch': 'Amount or currency mismatch: the payment will be refunded',
    'rejected': 'Notification accepted',
    REPLY_ERROR: 'Temporary error, please retry',
}


def _setting(name: str, default=''):
    return getattr(settings, name, default)


def format_amount(amount: Decimal) -> str:
    """`pg_amount`: up to two decimals with a dot separator."""
    return f'{amount.quantize(Decimal("0.01")):f}'


def parse_amount(value) -> Decimal | None:
    """The gateway prints amounts in their shortest form (`100`, `482.5`)."""
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite():
        return None
    exact = amount.quantize(Decimal('0.01'))
    return exact if exact == amount else None


def lifetime_seconds(expires_at, now=None) -> int:
    """Seconds the payment page stays payable: the remaining seat hold,
    clamped to what the gateway accepts."""
    remaining = int((expires_at - (now or timezone.now())).total_seconds())
    return max(MIN_LIFETIME_SECONDS, min(remaining, MAX_LIFETIME_SECONDS))


def _clean_text(value: str, limit: int) -> str:
    # Field values are joined with ';' in the signature: keep ours free of it.
    return ' '.join(str(value).replace(';', ',').split())[:limit]


class _PaymentIdRef:
    """A PaymentRef stand-in for asking about one gateway payment id."""

    def __init__(self, provider_payment_id: str, *, pk='', amount=Decimal('0'), currency='KZT'):
        self.pk = pk
        self.provider_session_id = provider_payment_id
        self.provider_payment_id = provider_payment_id
        self.amount = amount
        self.currency = currency


def payment_id_ref(provider_payment_id: str, **kwargs) -> _PaymentIdRef:
    return _PaymentIdRef(provider_payment_id, **kwargs)


@register
class FreedomPayProvider(PaymentProvider):
    code = 'freedompay'
    supported_currencies = frozenset({'KZT'})

    # ── configuration ──

    def is_configured(self) -> bool:
        return not conf.missing_settings(self.code, _setting)

    @property
    def api_url(self) -> str:
        return str(_setting('FREEDOMPAY_API_URL') or '').rstrip('/')

    @property
    def merchant_id(self) -> str:
        return str(_setting('FREEDOMPAY_MERCHANT_ID') or '').strip()

    @property
    def _secret(self) -> str:
        return str(_setting('FREEDOMPAY_SECRET_KEY') or '')

    def _require_configured(self) -> None:
        missing = conf.missing_settings(self.code, _setting)
        if missing:
            raise ProviderRejected(f'{", ".join(missing)} not set', provider=self.code, code='not_configured')

    # ── transport ──

    def _call(self, script: str, params: list[tuple[str, str]]) -> list[tuple[str, object]]:
        """Signed POST to `<api>/<script>`; the signed answer's fields.

        Raises ProviderUnavailable (network, non-200, unparseable or
        unsigned answer: the outcome is unknown) or ProviderRejected (a
        request error the gateway reported with `pg_error_code`).
        """
        self._require_configured()
        signed = sig.sign(script, [('pg_merchant_id', self.merchant_id), *params], self._secret)
        url = f'{self.api_url}/{script}'
        try:
            response = requests.post(
                url,
                data=signed,
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                allow_redirects=False,
                headers={'Accept': 'text/xml'},
            )
        except requests.RequestException as exc:
            raise ProviderUnavailable(
                f'Freedom Pay {script} unreachable: {exc.__class__.__name__}', provider=self.code
            ) from exc
        if response.status_code != 200:
            raise ProviderUnavailable(
                f'Freedom Pay {script} answered HTTP {response.status_code}',
                provider=self.code,
                code=str(response.status_code),
            )
        try:
            pairs = sig.parse_xml(response.content)
        except sig.XmlError as exc:
            raise ProviderUnavailable(f'Freedom Pay {script} answer is not XML: {exc}', provider=self.code) from exc
        error_code = sig.first(pairs, 'pg_error_code')
        if sig.first(pairs, 'pg_status') != 'ok' and error_code:
            description = str(sig.first(pairs, 'pg_error_description') or '')[:200]
            error_class = ProviderUnavailable if str(error_code) in _RETRYABLE_ERRORS else ProviderRejected
            raise error_class(
                f'Freedom Pay {script} error {error_code}: {description}', provider=self.code, code=str(error_code)
            )
        if not sig.verify_signature(script, pairs, self._secret):
            # S1: an answer without a valid signature is an error, never a confirmation.
            raise ProviderUnavailable(f'Freedom Pay {script} answer is not signed correctly', provider=self.code)
        return pairs

    # ── checkout ──

    def create_payment(self, order: PaymentOrder) -> CheckoutResult:
        if not self.supports_currency(order.currency):
            raise ProviderRejected(f'Freedom Pay does not charge {order.currency}', provider=self.code)
        lifetime = lifetime_seconds(order.expires_at)
        params = [
            ('pg_order_id', order.reference),
            ('pg_amount', format_amount(order.amount)),
            ('pg_currency', order.currency),
            ('pg_description', _clean_text(order.description, MAX_DESCRIPTION) or f'Order {order.reference}'),
            ('pg_lifetime', str(lifetime)),
            ('pg_result_url', str(_setting('FREEDOMPAY_RESULT_URL'))),
            ('pg_request_method', 'POST'),
            ('pg_success_url', order.success_url),
            ('pg_success_url_method', 'AUTOGET'),
            ('pg_failure_url', order.cancel_url),
            ('pg_failure_url_method', 'AUTOGET'),
            ('pg_timeout_after_payment', '5'),
            ('pg_generate_qr', '1'),
            ('pg_idempotency_key', order.idempotency_key[:255]),
        ]
        if _setting('FREEDOMPAY_TESTING_MODE', False):
            params.append(('pg_testing_mode', '1'))
        if order.customer_email and _EMAIL.match(order.customer_email):
            params.append(('pg_user_contact_email', order.customer_email))
        if order.locale in ('ru', 'en', 'kz'):
            params.append(('pg_language', order.locale))
        pairs = self._call(INIT_SCRIPT, params)

        payment_id = str(sig.first(pairs, 'pg_payment_id') or '')
        redirect_url = str(sig.first(pairs, 'pg_redirect_url') or '')
        if not _DIGITS.match(payment_id) or not redirect_url.startswith(('http://', 'https://')):
            raise ProviderUnavailable(
                'Freedom Pay init_payment answer lacks a payment id or page URL', provider=self.code
            )
        qr = sig.first(pairs, 'pg_redirect_qr')
        raw = {'pg_payment_id': payment_id, 'lifetime': lifetime}
        if isinstance(qr, str) and qr.strip():
            raw['redirect_qr'] = ''.join(qr.split())
        return CheckoutResult(
            provider=self.code,
            session_id=payment_id,
            redirect_url=redirect_url,
            expires_at=timezone.now() + timedelta(seconds=lifetime),
            payment_id=payment_id,
            raw=raw,
        )

    # ── callbacks ──

    def callback_fields(self, request) -> list[tuple[str, str]]:
        """The notification's fields in wire order (form body, or the XML
        of a `pg_request_method=XML` call). Raises InvalidCallback."""
        body = request.body
        if len(body) > MAX_CALLBACK_BYTES:
            raise InvalidCallback('callback too large', provider=self.code, code='too_large')
        try:
            text = body.decode('utf-8')
            pairs = parse_qsl(text, keep_blank_values=True, strict_parsing=bool(text), max_num_fields=200)
        except (UnicodeDecodeError, ValueError) as exc:
            raise InvalidCallback('callback is not a form body', provider=self.code, code='malformed') from exc
        if len(pairs) == 1 and pairs[0][0] == 'pg_xml':
            try:
                tree = sig.parse_xml(pairs[0][1].encode('utf-8'), root='request')
            except sig.XmlError as exc:
                raise InvalidCallback(f'bad pg_xml: {exc}', provider=self.code, code='malformed') from exc
            pairs = [(key, value) for key, value in tree if isinstance(value, str)]
        names = [key for key, _ in pairs]
        if len(names) != len(set(names)):
            raise InvalidCallback('callback repeats a parameter', provider=self.code, code='malformed')
        return pairs

    @staticmethod
    def script_for(request) -> str:
        return sig.script_name(request.path)

    def handle_callback(self, request) -> CallbackResult:
        if conf.missing_settings(self.code, _setting):
            raise InvalidCallback('Freedom Pay is not configured', provider=self.code, code='not_configured')
        pairs = self.callback_fields(request)
        script = self.script_for(request)
        if not sig.verify_signature(script, pairs, self._secret):
            raise InvalidCallback('bad Freedom Pay signature', provider=self.code, code='signature')
        fields = dict(pairs)
        payment_id = fields.get('pg_payment_id', '')
        result = fields.get('pg_result', '')
        amount = parse_amount(fields.get('pg_amount', ''))
        currency = fields.get('pg_currency', '').strip().upper()
        if not _DIGITS.match(payment_id) or result not in ('0', '1', '2'):
            raise InvalidCallback('callback lacks pg_payment_id / pg_result', provider=self.code, code='malformed')
        if amount is None or not _CURRENCY.match(currency):
            raise InvalidCallback('callback has no valid amount / currency', provider=self.code, code='malformed')
        kind = {'1': CallbackKind.PAID, '0': CallbackKind.FAILED, '2': CallbackKind.EXPIRED}[result]
        raw = {key: fields[key] for key in _KEPT_CALLBACK_FIELDS if key in fields}
        # Needed for the reply: the echoed salt and the script name it is signed with.
        raw['reply_salt'] = fields.get('pg_salt', '')
        raw['script'] = script
        return CallbackResult(
            provider=self.code,
            # No event id in this protocol: the business identity of the
            # notification. Retries change only pg_salt / pg_can_reject.
            event_id=f'result:{payment_id}:{result}',
            kind=kind,
            reference=fields.get('pg_order_id', ''),
            provider_session_id=payment_id,
            provider_payment_id=payment_id,
            amount=amount,
            currency=currency,
            raw=raw,
        )

    def reply(self, script: str, status: str, description: str, salt: str = '', *, http_status=200) -> HttpResponse:
        """A signed `<response>` (S4): echoes the request salt when it has one."""
        fields = [
            ('pg_status', status),
            ('pg_description', description),
            ('pg_salt', salt if sig.is_salt(salt) else sig.new_salt()),
        ]
        signed = sig.sign(script, fields, self._secret) if self._secret else fields
        return HttpResponse(sig.render_xml(signed), content_type='text/xml; charset=utf-8', status=http_status)

    def callback_response(self, result: CallbackResult, outcome: str) -> HttpResponse:
        status = {REPLY_ERROR: REPLY_ERROR, REPLY_REJECTED: REPLY_REJECTED}.get(outcome, REPLY_OK)
        description = _REPLY_DESCRIPTIONS.get(outcome, 'Notification accepted')
        return self.reply(str(result.raw.get('script', '')), status, description, str(result.raw.get('reply_salt', '')))

    def invalid_callback_response(self, request, reason: str) -> HttpResponse:
        """Answer to a notification we could not authenticate or parse:
        `error` (could not interpret), HTTP 400, nothing applied."""
        try:
            salt = dict(parse_qsl(request.body[:MAX_CALLBACK_BYTES].decode('utf-8'))).get('pg_salt', '')
        except (UnicodeDecodeError, ValueError):
            salt = ''
        return self.reply(self.script_for(request), REPLY_ERROR, reason[:200], salt, http_status=400)

    # ── status ──

    def get_status(self, payment) -> StatusResult:
        payment_id = str(payment.provider_payment_id or payment.provider_session_id or '')
        if _DIGITS.match(payment_id):
            params = [('pg_payment_id', payment_id)]
        elif payment.pk:
            params = [('pg_order_id', str(payment.pk))]
        else:
            raise ProviderRejected('nothing identifies the payment', provider=self.code)
        pairs = self._call(STATUS_SCRIPT, params)

        status = str(sig.first(pairs, 'pg_payment_status') or '')
        payment_id = str(sig.first(pairs, 'pg_payment_id') or payment_id)
        amount = parse_amount(sig.first(pairs, 'pg_amount', ''))
        currency = str(sig.first(pairs, 'pg_currency') or '').strip().upper()
        refunded = abs(parse_amount(sig.first(pairs, 'pg_refund_amount', '0')) or Decimal('0'))
        revoked = abs(parse_amount(sig.first(pairs, 'pg_revoked_amount', '0')) or Decimal('0'))
        failure_code = str(sig.first(pairs, 'pg_failure_code') or '')

        if status == 'success':
            # Refunded and cancelled payments keep `success` (S7).
            fully_returned = amount is not None and amount > 0 and refunded + revoked >= amount
            state = CallbackKind.REFUNDED if fully_returned else CallbackKind.PAID
        elif status == 'error':
            state = CallbackKind.EXPIRED if failure_code == _LIFETIME_EXPIRED else CallbackKind.FAILED
        elif status in _STATUS_PENDING:
            state = StatusResult.PENDING
        else:
            raise ProviderUnavailable(f'unknown Freedom Pay payment status {status!r}', provider=self.code)
        return StatusResult(
            provider=self.code,
            state=state,
            provider_session_id=payment_id,
            provider_payment_id=payment_id,
            amount=amount,
            currency=currency if _CURRENCY.match(currency) else '',
            raw={
                'pg_payment_status': status,
                'pg_refund_amount': str(refunded),
                'pg_revoked_amount': str(revoked),
                'pg_failure_code': failure_code,
                'pg_testing_mode': str(sig.first(pairs, 'pg_testing_mode') or ''),
            },
        )

    # ── refunds ──

    def refund(self, payment, amount: Decimal | None, *, idempotency_key: str, reason: str) -> RefundResult:
        """`revoke`: `amount` None refunds everything that is left (S8).
        Repeating a call with the same `idempotency_key` does not refund
        twice."""
        payment_id = str(payment.provider_payment_id or '')
        if not _DIGITS.match(payment_id):
            raise ProviderRejected('the payment has no Freedom Pay payment id', provider=self.code, code='no_payment')
        params = [('pg_payment_id', payment_id)]
        if amount is not None:
            if amount <= 0:
                raise ProviderRejected(f'cannot refund {amount}', provider=self.code)
            params.append(('pg_refund_amount', format_amount(amount)))
        params.append(('pg_idempotency_key', idempotency_key[:255]))
        pairs = self._call(REFUND_SCRIPT, params)

        refund_id = str(sig.first(pairs, 'pg_revoke_payment_id') or '')
        ok = sig.first(pairs, 'pg_status') == 'ok'
        failure = str(sig.first(pairs, 'pg_failure_code') or '')
        if not ok:
            logger.warning(
                'Freedom Pay declined refund of payment %s: %s %s',
                payment_id,
                failure,
                str(sig.first(pairs, 'pg_failure_description') or '')[:200],
            )
        return RefundResult(
            provider_refund_id=refund_id,
            status='succeeded' if ok else 'failed',
            amount=amount if amount is not None else payment.amount,
            currency=str(payment.currency).upper(),
            raw={'pg_status': str(sig.first(pairs, 'pg_status') or ''), 'pg_failure_code': failure, 'reason': reason},
        )

    def cancel_session(self, payment) -> None:
        # No protocol operation closes an unpaid payment page: `cancel`
        # reverses a paid payment. The page expires after pg_lifetime.
        return None
