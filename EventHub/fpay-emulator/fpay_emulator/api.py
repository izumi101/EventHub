"""Merchant API endpoints (spec sections 3, 5 and 6).

Every call is authenticated the same way: ``pg_merchant_id`` (1100 when
missing), a known merchant and a valid ``pg_sig`` over all parameters with the
script name taken from the path exactly as called (9998, or 1100 on
``get_status*.php``). Request errors are unsigned XML with HTTP 200; successful
answers are signed with the same script name and the merchant's secret.
"""

from __future__ import annotations

import asyncio
import base64
import io
import ipaddress
import logging
import re
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import segno
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from . import errors
from .config import REDIRECT_METHODS, REQUEST_METHODS, Merchant
from .errors import ApiError, invalid
from .faults import LATENCY
from .gateway import Gateway
from .models import CANCEL, ERROR, REFUND, SUCCESS, Operation, Payment, iso
from .money import negative, parse_amount, parse_optional_amount, plain
from .params import ParsedRequest, parse_request
from .protocol import XML_PLAIN, XML_UTF8, error_document, success_document
from .signature import Pairs, find_sig, script_name, verify_signature

log = logging.getLogger('fpay.api')

_SALT_RE = re.compile(r'^[A-Za-z0-9]+$')
_USER_ID_RE = re.compile(r'^[a-zA-Z0-9_-]+$')
_PHONE_RE = re.compile(r'^\d{10,15}$')
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_CURRENCY_RE = re.compile(r'^[A-Z]{3}$')
_DIGITS_RE = re.compile(r'^\d{1,19}$')
LANGUAGES = ('ru', 'en', 'kz', 'kg', 'uz')
PAYMENT_METHODS = ('bankcard', 'mobile_commerce', 'wallet', 'internetbank', 'other', 'cash')

Handler = Callable[[Merchant, ParsedRequest, str], Awaitable[list[tuple[str, Any]]]]


def _flag(parsed: ParsedRequest, name: str, default: bool) -> bool:
    raw = parsed.text(name)
    if raw is None or raw == '':
        return default
    if raw not in ('0', '1'):
        raise invalid(name, 'must be 0 or 1')
    return raw == '1'


def _url(parsed: ParsedRequest, name: str) -> str | None:
    """``None`` when absent, ``''`` when explicitly empty, else a checked URL."""
    raw = parsed.text(name)
    if raw is None:
        return None
    raw = raw.strip()
    if raw == '':
        return ''
    if len(raw) > 255 or not raw.startswith(('http://', 'https://')):
        raise invalid(name, 'must be an http(s) URL of at most 255 characters')
    return raw


def _choice(parsed: ParsedRequest, name: str, choices: tuple[str, ...], default: str | None) -> str | None:
    raw = parsed.text(name)
    if raw is None or raw == '':
        return default
    value = raw.strip().upper() if choices[0].isupper() else raw.strip()
    if value not in choices:
        raise invalid(name, f'must be one of {", ".join(choices)}')
    return value


def validate_receipt(parsed: ParsedRequest, tax_types: tuple[str, ...]) -> Any:
    positions = parsed.get('pg_receipt_positions')
    if positions is None:
        return None
    if not isinstance(positions, dict | Pairs):
        raise invalid('pg_receipt_positions', 'must be a list of positions')
    items = positions.items() if isinstance(positions, dict) else positions
    result = []
    for index, position in items:
        if not isinstance(position, dict | Pairs):
            raise invalid(f'pg_receipt_positions[{index}]', 'must be an object')
        data = dict(position.items() if isinstance(position, dict) else position)
        for required in ('count', 'name', 'price'):
            if not isinstance(data.get(required), str) or data[required] == '':
                raise invalid(f'pg_receipt_positions[{index}][{required}]', 'required')
        if parse_optional_amount(data['price']) is None:
            raise invalid(f'pg_receipt_positions[{index}][price]', 'must be an amount')
        if not re.match(r'^\d+(\.\d+)?$', data['count']):
            raise invalid(f'pg_receipt_positions[{index}][count]', 'must be a number')
        if 'tax_type' in data and data['tax_type'] not in tax_types:
            raise invalid(f'pg_receipt_positions[{index}][tax_type]', f'must be one of {", ".join(tax_types)}')
        result.append({k: v for k, v in data.items() if isinstance(v, str)})
    return result


def _payment_id(parsed: ParsedRequest, code: str) -> int:
    raw = parsed.text('pg_payment_id')
    if raw is None or raw == '':
        raise invalid('pg_payment_id', 'required')
    if not _DIGITS_RE.match(raw):
        raise ApiError(code, 'pg_payment_id: unknown payment')
    return int(raw)


class MerchantApi:
    def __init__(self, gateway: Gateway, templates: Jinja2Templates) -> None:
        self.gw = gateway
        self.settings = gateway.settings
        self.templates = templates

    def routes(self) -> list[Route]:
        methods = ['GET', 'POST']
        routes = [
            Route('/init_payment', self._endpoint('init_payment', self.init_payment), methods=methods),
            Route('/init_payment.php', self._endpoint('init_payment', self.init_payment), methods=methods),
            Route('/payment.php', self.payment_form, methods=methods),
            Route('/get_status3.php', self._endpoint('get_status', self.get_status, status=True), methods=methods),
            Route('/do_capture.php', self._endpoint('do_capture', self.do_capture), methods=methods),
            Route('/cancel', self._endpoint('cancel', self.cancel), methods=methods),
            Route('/cancel.php', self._endpoint('cancel', self.cancel), methods=methods),
            Route('/revoke', self._endpoint('revoke', self.revoke), methods=methods),
            Route('/revoke.php', self._endpoint('revoke', self.revoke), methods=methods),
        ]
        if self.settings.legacy_status_endpoints:
            for path in ('/get_status2.php', '/get_status.php'):
                routes.append(Route(path, self._endpoint('get_status', self.get_status, status=True), methods=methods))
        return routes

    # -- plumbing -----------------------------------------------------------

    def authenticate(self, parsed: ParsedRequest, script: str, *, status: bool) -> Merchant:
        merchant_id = parsed.text('pg_merchant_id')
        if not merchant_id:
            raise ApiError(errors.MERCHANT_ID_MISSING)
        bad_code = self.settings.status_bad_signature_code if status else self.settings.bad_signature_code
        merchant = self.settings.merchant(merchant_id)
        if merchant is None:
            raise ApiError(bad_code, errors.REQUEST_ERROR_TEXT[errors.BAD_SIGNATURE])
        if not verify_signature(script, parsed.tree, merchant.secret, find_sig(parsed.tree)):
            raise ApiError(bad_code, errors.REQUEST_ERROR_TEXT[errors.BAD_SIGNATURE])
        salt = parsed.text('pg_salt')
        if not salt:
            raise invalid('pg_salt', 'required')
        if self.settings.salt_strict and not _SALT_RE.match(salt):
            raise invalid('pg_salt', 'must contain Latin letters and digits only')
        return merchant

    def _endpoint(
        self, name: str, handler: Handler, *, status: bool = False
    ) -> Callable[[Request], Awaitable[Response]]:
        content_type = XML_PLAIN if status else XML_UTF8

        async def endpoint(request: Request) -> Response:
            script = script_name(request.url.path)
            state = request.scope.setdefault('state', {})
            state['endpoint'] = name
            try:
                parsed = await parse_request(request)
                merchant = self.authenticate(parsed, script, status=status)
                state['merchant_id'] = merchant.merchant_id
                fields = await handler(merchant, parsed, script)
            except ApiError as exc:
                state['error_code'] = exc.code
                log.info('request refused', extra={'endpoint': name, 'error_code': exc.code, 'detail': exc.description})
                return Response(error_document(exc), headers={'content-type': content_type})
            return Response(success_document(script, merchant.secret, fields), headers={'content-type': content_type})

        return endpoint

    async def _latency(self, endpoint: str) -> None:
        fault = self.gw.faults.take(endpoint, (LATENCY,))
        if fault:
            await asyncio.sleep(fault['latency_ms'] / 1000)

    def _own_payment(self, merchant: Merchant, payment_id: int, missing_code: str, foreign_code: str) -> Payment:
        payment = self.gw.store.get_payment(payment_id)
        if payment is None:
            raise ApiError(missing_code)
        if payment.merchant_id != merchant.merchant_id:
            raise ApiError(foreign_code)
        self.gw.expire_if_due(payment)
        return payment

    # -- init_payment -------------------------------------------------------

    def validate_init(self, merchant: Merchant, parsed: ParsedRequest) -> dict[str, Any]:
        settings = self.settings
        amount = parse_amount(parsed.text('pg_amount') or '')
        if amount is None:
            raise invalid('pg_amount', 'required: 0.01 to 99999999 with up to two decimals and a dot separator')
        description = parsed.text('pg_description')
        if not description or not description.strip():
            raise invalid('pg_description', 'required')
        if len(description) > 1024:
            raise invalid('pg_description', 'at most 1024 characters')
        order_id = parsed.text('pg_order_id')
        if order_id is not None and (order_id == '' or len(order_id) > 50):
            raise invalid('pg_order_id', '1 to 50 characters')
        currency = (parsed.text('pg_currency') or settings.default_currency).strip()
        if not _CURRENCY_RE.match(currency) or currency not in settings.currencies:
            raise invalid('pg_currency', f'must be one of {", ".join(settings.currencies)}')
        lifetime_raw = parsed.text('pg_lifetime')
        lifetime = settings.lifetime_default_seconds
        if lifetime_raw not in (None, ''):
            if not re.match(r'^-?\d+$', lifetime_raw):
                raise invalid('pg_lifetime', 'must be an integer number of seconds')
            # Out-of-range values are clamped, not refused (L2).
            lifetime = min(max(int(lifetime_raw), settings.lifetime_min_seconds), settings.lifetime_max_seconds)
        timeout_raw = parsed.text('pg_timeout_after_payment')
        timeout_after = 10
        if timeout_raw not in (None, ''):
            if not timeout_raw.isdigit() or int(timeout_raw) > 3600:
                raise invalid('pg_timeout_after_payment', 'must be 0 to 3600 seconds')
            timeout_after = int(timeout_raw)
        user_id = parsed.text('pg_user_id')
        if user_id is not None and not _USER_ID_RE.match(user_id):
            raise invalid('pg_user_id', 'Latin letters, digits, _ and - only')
        phone = parsed.text('pg_user_phone')
        if phone is not None and phone != '' and not _PHONE_RE.match(phone):
            raise invalid('pg_user_phone', 'digits with the country code, e.g. 77777777777')
        email = parsed.text('pg_user_contact_email')
        if email is not None and email != '' and not _EMAIL_RE.match(email):
            raise invalid('pg_user_contact_email', 'must be an e-mail address')
        user_ip = parsed.text('pg_user_ip')
        if user_ip not in (None, ''):
            try:
                ipaddress.ip_address(user_ip)
            except ValueError as exc:
                raise invalid('pg_user_ip', 'must be an IPv4 or IPv6 address') from exc
        idempotency_key = parsed.text('pg_idempotency_key')
        if idempotency_key is not None and not (0 < len(idempotency_key) <= 255):
            raise invalid('pg_idempotency_key', '1 to 255 characters')

        def default_url(name: str, merchant_value: str | None) -> str | None:
            value = _url(parsed, name)
            if value is None:
                return merchant_value  # omitted: the merchant setting
            return value or None  # explicitly empty: none (L2)

        testing_flag = _flag(parsed, 'pg_testing_mode', False)
        testing = settings.merchant_test_mode or testing_flag
        custom = [
            [name, value]
            for name, value in (parsed.tree.items() if isinstance(parsed.tree, dict) else parsed.tree)
            if not name.startswith('pg_') and isinstance(value, str)
        ]
        pg_params = {k: v for k in ('pg_param1', 'pg_param2', 'pg_param3') if (v := parsed.text(k)) is not None}
        return {
            'amount': amount,
            'currency': currency,
            'description': description,
            'order_id': order_id,
            'lifetime': lifetime,
            'testing_mode': testing,
            'auto_clearing': _flag(parsed, 'pg_auto_clearing', settings.auto_clearing_default),
            'check_url': default_url('pg_check_url', merchant.check_url),
            'result_url': default_url('pg_result_url', merchant.result_url),
            'request_method': _choice(parsed, 'pg_request_method', REQUEST_METHODS, merchant.request_method),
            'success_url': default_url('pg_success_url', merchant.success_url),
            'success_url_method': _choice(parsed, 'pg_success_url_method', REDIRECT_METHODS, 'GET'),
            'failure_url': default_url('pg_failure_url', merchant.failure_url),
            'failure_url_method': _choice(parsed, 'pg_failure_url_method', REDIRECT_METHODS, 'GET'),
            'timeout_after_payment': timeout_after,
            'language': _choice(parsed, 'pg_language', LANGUAGES, None),
            'user_phone': phone or None,
            'user_email': email or None,
            'user_ip': user_ip or None,
            'user_id': user_id,
            'payment_method_filter': _choice(parsed, 'pg_payment_method', PAYMENT_METHODS, None),
            'custom_params': custom,
            'pg_params': pg_params,
            'receipt_positions': validate_receipt(parsed, settings.tax_types),
            'idempotency_key': idempotency_key,
            'redirect_qr': _flag(parsed, 'pg_generate_qr', False),
        }

    def _create(self, merchant: Merchant, parsed: ParsedRequest) -> Payment:
        values = self.validate_init(merchant, parsed)
        key = values['idempotency_key']
        if key:
            known = self.gw.store.get_idempotent(merchant.merchant_id, 'init_payment', key)
            if known and (existing := self.gw.store.get_payment(known['payment_id'])):
                return existing
        if values['order_id'] is not None and self.settings.order_id_uniqueness != 'off':
            existing = self.gw.store.latest_payment_by_order(merchant.merchant_id, values['order_id'])
            if existing is not None:
                if self.settings.order_id_uniqueness == 'reject':
                    raise ApiError(errors.DUPLICATE_ORDER_ID)
                return existing
        payment = self.gw.create_payment(merchant, values)
        if key:
            self.gw.store.put_idempotent(
                merchant.merchant_id, 'init_payment', key, {'payment_id': payment.payment_id}, iso(self.gw.now())
            )
        return payment

    @staticmethod
    def _qr(url: str) -> str:
        qr = segno.make(url, error='m')
        width = qr.symbol_size(border=4)[0]
        buffer = io.BytesIO()
        qr.save(buffer, kind='png', scale=max(1, 300 // width), border=4)
        return base64.b64encode(buffer.getvalue()).decode('ascii')

    async def init_payment(self, merchant: Merchant, parsed: ParsedRequest, script: str) -> list[tuple[str, Any]]:
        await self._latency('init_payment')
        payment = self._create(merchant, parsed)
        url = self.gw.redirect_url(payment)
        fields: list[tuple[str, Any]] = [
            ('pg_status', 'ok'),
            ('pg_payment_id', str(payment.payment_id)),
            ('pg_redirect_url', url),
            ('pg_redirect_url_type', 'need data'),
        ]
        if payment.redirect_qr:
            fields.append(('pg_redirect_qr', self._qr(url)))
        return fields

    async def payment_form(self, request: Request) -> Response:
        """``payment.php``: the browser posts the signed form and is sent to the page."""
        state = request.scope.setdefault('state', {})
        state['endpoint'] = 'payment'
        try:
            parsed = await parse_request(request)
            merchant = self.authenticate(parsed, script_name(request.url.path), status=False)
            await self._latency('payment')
            payment = self._create(merchant, parsed)
        except ApiError as exc:
            state['error_code'] = exc.code
            return self.templates.TemplateResponse(
                request, 'error.html', {'code': exc.code, 'description': exc.description}, status_code=200
            )
        return RedirectResponse(self.gw.redirect_url(payment), status_code=302)

    # -- get_status3.php ----------------------------------------------------

    async def get_status(self, merchant: Merchant, parsed: ParsedRequest, script: str) -> list[tuple[str, Any]]:
        await self._latency('get_status')
        raw_id = parsed.text('pg_payment_id')
        order_id = parsed.text('pg_order_id')
        if (
            self.settings.json_status_id_must_be_number
            and parsed.fmt == 'json'
            and parsed.json_types.get('pg_payment_id') == 'string'
        ):
            raise ApiError(errors.SYSTEM_ERROR)  # S7: a string pg_payment_id in JSON
        if raw_id:
            payment = self.gw.store.get_payment(int(raw_id)) if _DIGITS_RE.match(raw_id) else None
        elif order_id:
            payment = self.gw.store.latest_payment_by_order(merchant.merchant_id, order_id)
        else:
            raise ApiError(errors.STATUS_ID_MISSING)
        if payment is None or payment.merchant_id != merchant.merchant_id:
            raise ApiError(errors.PAYMENT_NOT_FOUND)
        self.gw.expire_if_due(payment)
        return self.status_fields(payment)

    def status_fields(self, payment: Payment) -> list[tuple[str, Any]]:
        """``get_status3.php`` answer, in the real (not alphabetical) element order (S7)."""
        ops = self.gw.store.operations(payment.payment_id)
        money = self.gw.money(payment, ops)
        can_reject = payment.can_reject and payment.status == SUCCESS and not payment.merchant_rejected
        fields: list[tuple[str, Any]] = [
            ('pg_status', 'ok'),
            ('pg_payment_id', str(payment.payment_id)),
            ('pg_can_reject', '1' if can_reject else '0'),
        ]
        if payment.testing_mode:
            fields.append(('pg_testing_mode', '1'))
        fields += [
            ('pg_currency', payment.currency),
            ('pg_amount', plain(payment.amount)),
            ('pg_payment_method', payment.payment_method),
            ('pg_captured', '1' if payment.captured else '0'),
            ('pg_create_date', payment.created_at.strftime('%Y-%m-%dT%H:%M:%SZ')),
            ('pg_salt', None),
            ('pg_sig', None),
            ('pg_payment_status', payment.status),
        ]
        if payment.reference:
            fields.append(('pg_reference', payment.reference))
        fields.append(('pg_clearing_amount', plain(payment.clearing_amount)))
        if payment.card:
            fields += [('pg_card_pan', payment.card['pan']), ('pg_card_name', payment.card['owner'])]
        if payment.status == SUCCESS and payment.auth_code:
            fields.append(('pg_auth_code', payment.auth_code))
        if payment.user_phone:
            fields.append(('pg_user_phone', payment.user_phone))
        if payment.user_email:
            fields.append(('pg_user_email', payment.user_email))
        if payment.status == ERROR and payment.failure_code:
            fields += [
                ('pg_failure_code', payment.failure_code),
                ('pg_failure_description', payment.failure_description or ''),
            ]
        refunds = [o for o in ops if o.kind == REFUND]
        if refunds:
            fields.append(('pg_refund_amount', negative(money.refunded)))
            fields.append(('pg_refund_payments', Pairs(('pg_refund_payment', self._refund_entry(o)) for o in refunds)))
        cancels = [o for o in ops if o.kind == CANCEL]
        if cancels:
            fields.append(('pg_revoked_amount', negative(money.cancelled)))
            fields.append(
                (
                    'pg_revoked_payments',
                    Pairs(
                        (
                            'pg_revoked_payment',
                            Pairs([('pg_payment_id', str(o.op_id)), ('pg_payment_status', o.status)]),
                        )
                        for o in cancels
                    ),
                )
            )
        return fields

    def _refund_entry(self, op: Operation) -> Pairs:
        entry = Pairs(
            [
                ('pg_payment_id', str(op.op_id)),
                ('pg_payment_status', op.status),
                ('pg_amount', negative(op.amount)),
                ('pg_payment_date', self.gw.local_time(op.created_at)),
            ]
        )
        if op.reference:
            entry.append(('pg_reference', op.reference))
        if op.status == ERROR and op.failure_code:
            entry += [('pg_failure_code', op.failure_code), ('pg_failure_description', op.failure_description or '')]
        return entry

    # -- do_capture.php -----------------------------------------------------

    async def do_capture(self, merchant: Merchant, parsed: ParsedRequest, script: str) -> list[tuple[str, Any]]:
        payment_id = _payment_id(parsed, errors.CAPTURE_NOT_POSSIBLE)
        raw_amount = parsed.text('pg_clearing_amount')
        amount = None
        if raw_amount not in (None, ''):
            amount = parse_optional_amount(raw_amount, truncate=True)
            if amount is None:
                raise invalid('pg_clearing_amount', 'must be a non-negative amount')
        payment = self._own_payment(merchant, payment_id, errors.CAPTURE_NOT_POSSIBLE, errors.CAPTURE_NOT_POSSIBLE)
        async with self.gw.lock(payment.payment_id):
            await self._latency('do_capture')
            payment = self.gw.store.get_payment(payment_id) or payment
            captured = self.gw.capture(payment, amount)
        return [
            ('pg_status', 'ok'),
            ('pg_amount', plain(payment.amount)),
            ('pg_clearing_amount', plain(captured)),
        ]

    # -- cancel / revoke ----------------------------------------------------

    def _idempotent(self, merchant: Merchant, scope: str, parsed: ParsedRequest) -> tuple[str | None, Any]:
        key = parsed.text('pg_idempotency_key')
        if key is None or key == '':
            return None, None
        if len(key) > 255:
            raise invalid('pg_idempotency_key', 'at most 255 characters')
        return key, self.gw.store.get_idempotent(merchant.merchant_id, scope, key)

    async def _exclusive(self, payment: Payment, kind: str, endpoint: str, work: Callable[[], Operation]) -> Operation:
        busy = self.gw.busy.get(payment.payment_id)
        if busy:
            raise ApiError(errors.REFUND_IN_PROGRESS if busy == REFUND else errors.CANCEL_IN_PROGRESS)
        self.gw.busy[payment.payment_id] = kind
        try:
            async with self.gw.lock(payment.payment_id):
                await self._latency(endpoint)
                return work()
        finally:
            self.gw.busy.pop(payment.payment_id, None)

    async def cancel(self, merchant: Merchant, parsed: ParsedRequest, script: str) -> list[tuple[str, Any]]:
        payment_id = _payment_id(parsed, errors.CAPTURE_NOT_POSSIBLE)
        key, known = self._idempotent(merchant, 'cancel', parsed)
        if known is not None:
            return [tuple(item) for item in known['fields']]
        validate_receipt(parsed, self.settings.tax_types)
        payment = self._own_payment(merchant, payment_id, errors.CAPTURE_NOT_POSSIBLE, errors.CAPTURE_NOT_POSSIBLE)
        if not self.settings.refunds_enabled and payment.captured:
            raise ApiError(errors.ACTION_DISABLED)

        def work() -> Operation:
            current = self.gw.store.get_payment(payment_id) or payment
            return self.gw.cancel(current, key)

        op = await self._exclusive(payment, CANCEL, 'cancel', work)
        fields: list[tuple[str, Any]] = [
            ('pg_status', 'ok' if op.status == SUCCESS else 'error'),
            ('pg_cancel_payment_id', str(op.op_id)),
        ]
        if op.status != SUCCESS:
            fields += [('pg_failure_code', op.failure_code), ('pg_failure_description', op.failure_description)]
        if key:
            self.gw.store.put_idempotent(merchant.merchant_id, 'cancel', key, {'fields': fields}, iso(self.gw.now()))
        return fields

    async def revoke(self, merchant: Merchant, parsed: ParsedRequest, script: str) -> list[tuple[str, Any]]:
        payment_id = _payment_id(parsed, errors.INVALID_PARAMETER)
        raw_amount = parsed.text('pg_refund_amount')
        amount: Decimal | None = None
        if raw_amount not in (None, ''):
            amount = parse_optional_amount(raw_amount)
            if amount is None:
                raise invalid('pg_refund_amount', 'must be 0 to 99999999 with up to two decimals')
        key, known = self._idempotent(merchant, 'revoke', parsed)
        if known is not None:
            return [tuple(item) for item in known['fields']]
        validate_receipt(parsed, self.settings.tax_types)
        payment = self._own_payment(merchant, payment_id, errors.INVALID_PARAMETER, errors.CAPTURE_NOT_POSSIBLE)

        def work() -> Operation:
            current = self.gw.store.get_payment(payment_id) or payment
            return self.gw.refund(current, amount, key)

        op = await self._exclusive(payment, REFUND, 'revoke', work)
        fields: list[tuple[str, Any]] = [
            ('pg_status', 'ok' if op.status == SUCCESS else 'error'),
            ('pg_revoke_payment_id', str(op.op_id)),
        ]
        if op.status != SUCCESS:
            fields += [('pg_failure_code', op.failure_code), ('pg_failure_description', op.failure_description)]
        if key:
            self.gw.store.put_idempotent(merchant.merchant_id, 'revoke', key, {'fields': fields}, iso(self.gw.now()))
        return fields
