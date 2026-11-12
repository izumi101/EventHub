"""Hosted payment page (``/pay.html?customer=<uuid>``) and its 3-D Secure step.

The page recognises the spec's test cards and also offers explicit scenario
buttons for demos. After settlement it sends the buyer back with the
documented success/failure redirect methods (GET, POST, AUTOGET, AUTOPOST)
after ``pg_timeout_after_payment`` seconds. A pre-set control-API scenario
overrides the outcome of whatever card is typed in (useful for browser e2e).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from . import cards, errors
from .gateway import Gateway
from .models import ERROR, PROCESS, SUCCESS, Payment
from .money import two_places
from .protocol import signed_for_url, with_query

_OWNER_RE = re.compile(r"^[A-Za-z]+(?:[ '\-][A-Za-z]+)+$")
_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
BUTTON_SCENARIOS = {
    'success': (cards.SUCCESS, cards.DEFAULT_CARD, None),
    'decline': (cards.DECLINE, '5548398681700148', errors.INSUFFICIENT_FUNDS),
    '3ds': (cards.THREE_DS_SUCCESS, '4916307416334310', None),
    'hang': (cards.HANG, None, None),
    'abandon': (cards.ABANDON, None, None),
}


# The test cards and the details that go with them, shown under the card form.
_TEST_CARDS = {'cards': cards.known_cards(), 'test_card': cards.TEST_CARD_DETAILS}


class PaymentPages:
    def __init__(self, gateway: Gateway, templates: Jinja2Templates) -> None:
        self.gw = gateway
        self.settings = gateway.settings
        self.templates = templates

    def routes(self) -> list[Route]:
        return [
            Route('/pay.html', self.page, methods=['GET']),
            Route('/pay/{customer}/card', self.submit_card, methods=['POST']),
            Route('/pay/{customer}/scenario', self.submit_scenario, methods=['POST']),
            Route('/pay/{customer}/3ds', self.challenge, methods=['GET', 'POST']),
            Route('/pay/{customer}/result', self.result, methods=['GET']),
            Route('/pay/{customer}/processing', self.processing, methods=['GET']),
        ]

    # -- helpers ------------------------------------------------------------

    def _load(self, customer: str | None) -> Payment | None:
        if not customer or not _UUID_RE.match(customer):
            return None
        payment = self.gw.store.get_payment_by_customer(customer)
        if payment is not None:
            self.gw.expire_if_due(payment)
        return payment

    def _context(self, payment: Payment, **extra: Any) -> dict[str, Any]:
        merchant = self.gw.merchant_of(payment)
        return {
            'payment': payment,
            'merchant_name': merchant.display_name if merchant else payment.merchant_id,
            'amount': f'{two_places(payment.amount)} {payment.currency}',
            'expires_at': self.gw.local_time(payment.expires_at),
            'timezone': self.settings.timezone,
            'base': f'/pay/{payment.customer}',
            **extra,
        }

    def _render(self, request: Request, name: str, context: dict[str, Any], status: int = 200) -> Response:
        return self.templates.TemplateResponse(request, name, context, status_code=status)

    def _not_found(self, request: Request) -> Response:
        return self._render(
            request,
            'message.html',
            {'title': 'Payment not found', 'text': 'This payment link is not valid.', 'payment': None},
            status=404,
        )

    def _go(self, payment: Payment, step: str) -> Response:
        target = {'result': 'result', '3ds': '3ds', 'processing': 'processing', 'waiting': 'processing'}[step]
        return RedirectResponse(f'/pay/{payment.customer}/{target}', status_code=303)

    @staticmethod
    def _back_to_page(payment: Payment) -> Response:
        return RedirectResponse(f'/pay.html?customer={payment.customer}', status_code=303)

    def _route_final(self, payment: Payment) -> Response | None:
        if payment.is_final:
            return self._go(payment, 'result')
        if payment.challenge is not None:
            return self._go(payment, '3ds')
        if payment.status == PROCESS:
            return self._go(payment, 'processing')
        return None

    # -- the page -----------------------------------------------------------

    async def page(self, request: Request) -> Response:
        payment = self._load(request.query_params.get('customer'))
        if payment is None:
            return self._not_found(request)
        if (redirect := self._route_final(payment)) is not None:
            return redirect
        self.gw.mark_waiting(payment)
        return self._render(request, 'pay.html', self._context(payment, form={}, problems={}, **_TEST_CARDS))

    async def submit_card(self, request: Request) -> Response:
        payment = self._load(request.path_params['customer'])
        if payment is None:
            return self._not_found(request)
        if (redirect := self._route_final(payment)) is not None:
            return redirect
        form = await request.form()
        data = {k: str(form.get(k, '')).strip() for k in ('pan', 'exp_month', 'exp_year', 'cvv', 'owner')}
        pan = cards.normalise_pan(data['pan'])
        problems: dict[str, str] = {}
        if not cards.valid_pan(pan):
            problems['pan'] = 'Enter a valid card number (12 to 19 digits).'
        if not re.match(r'^(0[1-9]|1[0-2])$', data['exp_month']):
            problems['exp_month'] = 'Enter the month as two digits, 01 to 12.'
        if not re.match(r'^\d{2}$', data['exp_year']):
            problems['exp_year'] = 'Enter the year as two digits.'
        if not re.match(r'^\d{3}$', data['cvv']):
            problems['cvv'] = 'Enter the three-digit security code.'
        if not _OWNER_RE.match(data['owner']):
            problems['owner'] = 'Enter the cardholder name as printed on the card: at least two Latin words.'
        if problems:
            safe = {k: v for k, v in data.items() if k in ('exp_month', 'exp_year', 'owner')}
            context = self._context(payment, form=safe, problems=problems, **_TEST_CARDS)
            return self._render(request, 'pay.html', context, status=422)
        record = cards.card_record(pan, data['exp_month'], data['exp_year'], data['owner'].upper())
        if payment.scenario:
            scenario, code = payment.scenario['scenario'], payment.scenario.get('failure_code')
        elif self._expired_card(data['exp_month'], data['exp_year']):
            scenario, code = cards.DECLINE, errors.CARD_EXPIRED
        else:
            scenario, code = cards.scenario_for_card(pan, payment.testing_mode)
        async with self.gw.lock(payment.payment_id):
            payment = self.gw.store.get_payment(payment.payment_id) or payment
            step = await self.gw.start(payment, scenario, card=record, failure_code=code)
        return self._go(payment, step)

    @staticmethod
    def _expired_card(month: str, year: str) -> bool:
        now = datetime.now(UTC)
        return (2000 + int(year), int(month)) < (now.year, now.month)

    async def submit_scenario(self, request: Request) -> Response:
        payment = self._load(request.path_params['customer'])
        if payment is None:
            return self._not_found(request)
        if (redirect := self._route_final(payment)) is not None:
            return redirect
        form = await request.form()
        choice = BUTTON_SCENARIOS.get(str(form.get('scenario', '')))
        if choice is None:
            return self._back_to_page(payment)
        scenario, pan, code = choice
        record = cards.card_record(pan, '12', '30', 'TEST CARDHOLDER') if pan else None
        if scenario == cards.ABANDON:
            self.gw.mark_waiting(payment)
            return self._render(
                request,
                'message.html',
                {
                    'title': 'You left the payment page',
                    'text': 'Nothing was charged. The payment stays open until its lifetime ends.',
                    'payment': payment,
                },
            )
        async with self.gw.lock(payment.payment_id):
            payment = self.gw.store.get_payment(payment.payment_id) or payment
            step = await self.gw.start(payment, scenario, card=record, failure_code=code)
        return self._go(payment, step)

    # -- 3-D Secure ---------------------------------------------------------

    async def challenge(self, request: Request) -> Response:
        payment = self._load(request.path_params['customer'])
        if payment is None:
            return self._not_found(request)
        if payment.challenge is None:
            return self._go(payment, 'result') if payment.is_final else self._back_to_page(payment)
        if request.method == 'GET':
            return self._render(
                request, 'threeds.html', self._context(payment, tds_password=self.settings.three_ds_password)
            )
        form = await request.form()
        if form.get('action') == 'cancel':
            passed = False
        else:
            passed = str(form.get('password', '')) == self.settings.three_ds_password
            passed = passed and payment.challenge.get('expected') != 'fail'
        async with self.gw.lock(payment.payment_id):
            payment = self.gw.store.get_payment(payment.payment_id) or payment
            await self.gw.finish_challenge(payment, passed)
        return self._go(payment, 'result')

    # -- after the payment --------------------------------------------------

    async def processing(self, request: Request) -> Response:
        payment = self._load(request.path_params['customer'])
        if payment is None:
            return self._not_found(request)
        if payment.is_final:
            return self._go(payment, 'result')
        return self._render(request, 'processing.html', self._context(payment))

    def redirect_for(self, payment: Payment) -> dict[str, Any] | None:
        """The way back to the shop: method, URL and fields (spec section 4.3)."""
        succeeded = payment.status == SUCCESS and not payment.merchant_rejected
        if succeeded:
            url, method = payment.success_url, payment.success_url_method
        else:
            url, method = payment.failure_url, payment.failure_url_method
        if not url:
            return None
        fields: list[tuple[str, str]] = []
        if payment.order_id is not None:
            fields.append(('pg_order_id', payment.order_id))
        fields.append(('pg_payment_id', str(payment.payment_id)))
        if succeeded:
            fields += [(k, v) for k, v in payment.custom_params]
            merchant = self.gw.merchant_of(payment)
            secret = merchant.secret if merchant else ''
            via_query = method in ('GET', 'AUTOGET')
            include_query = self.settings.callback_sign_url_query == 'always' or (
                self.settings.callback_sign_url_query == 'get_only' and via_query
            )
            fields = list(signed_for_url(url, secret, fields, include_url_query=include_query)[0])
        else:
            code, description = self.failure_of(payment)
            fields += [('pg_failure_code', code), ('pg_failure_description', description)]
            fields += [(k, v) for k, v in payment.custom_params]
        get_like = method in ('GET', 'AUTOGET')
        return {
            'method': method,
            'auto': method.startswith('AUTO'),
            'http_method': 'get' if get_like else 'post',
            'url': with_query(url, fields) if get_like else url,
            'fields': [] if get_like else fields,
            'delay': payment.timeout_after_payment,
        }

    def failure_of(self, payment: Payment) -> tuple[str, str]:
        if payment.merchant_rejected:
            code = self.settings.reject_failure_code
            return code, payment.merchant_reply_description or errors.failure_text(code)
        code = payment.failure_code or errors.UNKNOWN_PS_ERROR
        return code, payment.failure_description or errors.failure_text(code)

    async def result(self, request: Request) -> Response:
        payment = self._load(request.path_params['customer'])
        if payment is None:
            return self._not_found(request)
        if not payment.is_final:
            return self._route_final(payment) or self._back_to_page(payment)
        back = self.redirect_for(payment)
        if back and back['method'] == 'AUTOGET' and back['delay'] == 0:
            return RedirectResponse(back['url'], status_code=302)
        succeeded = payment.status == SUCCESS and not payment.merchant_rejected
        failure = None if succeeded else self.failure_of(payment)
        expired = payment.failure_code == errors.LIFETIME_EXPIRED and payment.card is None
        status = 'success' if succeeded else ('expired' if expired else ERROR)
        return self._render(request, 'result.html', self._context(payment, back=back, outcome=status, failure=failure))
