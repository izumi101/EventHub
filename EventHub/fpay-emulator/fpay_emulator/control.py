"""Control API for tests, e2e and failure injection (``/_emulator/...``).

Not part of the Freedom Pay protocol. JSON in, JSON out. Protected by the
``X-Emulator-Token`` header when ``FPAY_CONTROL_TOKEN`` is set, and absent
entirely when ``FPAY_CONTROL_ENABLED=0``.
"""

from __future__ import annotations

import hmac
import json
import logging
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from . import cards
from .api import MerchantApi
from .errors import failure_text
from .gateway import Gateway
from .models import Payment, iso
from .signature import Pairs

log = logging.getLogger('fpay.control')
_STATUS_LISTS = ('pg_refund_payments', 'pg_revoked_payments')


class ControlError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _plain(value: Any) -> Any:
    if isinstance(value, Pairs):
        return [[k, _plain(v)] for k, v in value]
    return value


class ControlApi:
    def __init__(self, gateway: Gateway, api: MerchantApi) -> None:
        self.gw = gateway
        self.api = api
        self.settings = gateway.settings

    def routes(self) -> list[Route]:
        p = '/_emulator'
        return [
            Route(f'{p}/reset', self._wrap(self.reset), methods=['POST']),
            Route(f'{p}/payments', self._wrap(self.list_payments), methods=['GET']),
            Route(f'{p}/payments/{{ref}}', self._wrap(self.get_payment), methods=['GET']),
            Route(f'{p}/payments/{{ref}}/scenario', self._wrap(self.set_scenario), methods=['POST']),
            Route(f'{p}/payments/{{ref}}/complete', self._wrap(self.complete), methods=['POST']),
            Route(f'{p}/faults', self._wrap(self.faults), methods=['GET', 'POST', 'DELETE']),
            Route(f'{p}/clock', self._wrap(self.clock), methods=['GET', 'POST']),
            Route(f'{p}/tick', self._wrap(self.tick), methods=['POST']),
            Route(f'{p}/replay-callback/{{ref}}', self._wrap(self.replay), methods=['POST']),
        ]

    def _wrap(self, handler: Any) -> Any:
        async def endpoint(request: Request) -> Response:
            request.scope.setdefault('state', {})['endpoint'] = 'control'
            token = self.settings.control_token
            if token:
                given = request.headers.get('x-emulator-token', '')
                if not hmac.compare_digest(given.encode(), token.encode()):
                    return JSONResponse({'error': 'missing or invalid X-Emulator-Token'}, status_code=401)
            try:
                result = await handler(request)
            except ControlError as exc:
                return JSONResponse({'error': exc.message}, status_code=exc.status)
            return JSONResponse(result)

        return endpoint

    @staticmethod
    async def _body(request: Request) -> dict[str, Any]:
        raw = await request.body()
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise ControlError(400, 'the body must be JSON') from exc
        if not isinstance(data, dict):
            raise ControlError(400, 'the body must be a JSON object')
        return data

    def _payment(self, ref: str) -> Payment:
        payment = self.gw.store.get_payment(int(ref)) if ref.isdigit() else self.gw.store.get_payment_by_customer(ref)
        if payment is None:
            raise ControlError(404, f'payment {ref} not found')
        self.gw.expire_if_due(payment)
        return payment

    def state(self, payment: Payment) -> dict[str, Any]:
        data = payment.to_dict()
        money = self.gw.money(payment)
        status = {k: _plain(v) for k, v in self.api.status_fields(payment) if k not in ('pg_salt', 'pg_sig')}
        data.update(
            {
                'redirect_url': self.gw.redirect_url(payment),
                'refunded_amount': str(money.refunded),
                'cancelled_amount': str(money.cancelled),
                'is_cancelled': money.is_cancelled,
                'status_response': status,
                'operations': [op.to_dict() for op in self.gw.store.operations(payment.payment_id)],
                'callback_jobs': self.gw.store.jobs(payment.payment_id),
                'deliveries': self.gw.store.deliveries(payment.payment_id),
            }
        )
        return data

    # -- endpoints ----------------------------------------------------------

    async def reset(self, request: Request) -> dict[str, Any]:
        self.gw.store.reset()
        self.gw.clock.reload()
        self.gw.busy.clear()
        log.info('emulator reset')
        return {'status': 'ok'}

    async def list_payments(self, request: Request) -> dict[str, Any]:
        q = request.query_params
        try:
            limit = min(max(int(q.get('limit', '100')), 1), 1000)
        except ValueError as exc:
            raise ControlError(400, 'limit must be an integer') from exc
        payments = self.gw.store.list_payments(
            merchant_id=q.get('merchant_id'), order_id=q.get('order_id'), status=q.get('status'), limit=limit
        )
        return {
            'payments': [
                {
                    'payment_id': p.payment_id,
                    'merchant_id': p.merchant_id,
                    'order_id': p.order_id,
                    'status': p.status,
                    'amount': str(p.amount),
                    'currency': p.currency,
                    'customer': p.customer,
                    'created_at': iso(p.created_at),
                    'redirect_url': self.gw.redirect_url(p),
                }
                for p in payments
            ]
        }

    async def get_payment(self, request: Request) -> dict[str, Any]:
        return self.state(self._payment(request.path_params['ref']))

    @staticmethod
    def _scenario(body: dict[str, Any], default: str | None) -> dict[str, Any] | None:
        name = body.get('scenario', default)
        if name is None:
            return None
        if name not in cards.SCENARIOS:
            raise ControlError(400, f'scenario must be one of {", ".join(cards.SCENARIOS)}')
        code = body.get('failure_code')
        if code is not None and (not isinstance(code, str) or not code.isdigit()):
            raise ControlError(400, 'failure_code must be a string of digits')
        if name == cards.DECLINE and code is None:
            code = '10009'
        return {'scenario': name, 'failure_code': code, 'failure_description': failure_text(code) if code else None}

    async def set_scenario(self, request: Request) -> dict[str, Any]:
        body = await self._body(request)
        payment = self._payment(request.path_params['ref'])
        if payment.is_final:
            raise ControlError(409, f'payment is already final ({payment.status})')
        payment.scenario = self._scenario(body, None)
        if payment.scenario is None:
            raise ControlError(400, 'scenario is required')
        self.gw.store.save_payment(payment)
        return self.state(payment)

    async def complete(self, request: Request) -> dict[str, Any]:
        body = await self._body(request)
        payment = self._payment(request.path_params['ref'])
        if payment.is_final:
            raise ControlError(409, f'payment is already final ({payment.status})')
        preset = payment.scenario['scenario'] if payment.scenario else cards.SUCCESS
        scenario = self._scenario(body, preset)
        if scenario is None:  # pragma: no cover - default is always set
            raise ControlError(400, 'scenario is required')
        if scenario['scenario'] == cards.DECLINE and 'failure_code' not in body and payment.scenario:
            scenario['failure_code'] = payment.scenario.get('failure_code') or scenario['failure_code']
        name = scenario['scenario']
        async with self.gw.lock(payment.payment_id):
            payment = self.gw.store.get_payment(payment.payment_id) or payment
            if payment.challenge is not None:
                await self.gw.finish_challenge(payment, name != cards.THREE_DS_FAIL)
            else:
                step = await self.gw.start(payment, name, failure_code=scenario['failure_code'])
                if step == '3ds':
                    payment = self.gw.store.get_payment(payment.payment_id) or payment
                    await self.gw.finish_challenge(payment, name == cards.THREE_DS_SUCCESS)
        refreshed = self.gw.store.get_payment(payment.payment_id) or payment
        return self.state(refreshed)

    async def faults(self, request: Request) -> dict[str, Any]:
        if request.method == 'GET':
            return {'faults': self.gw.faults.list()}
        if request.method == 'DELETE':
            return {'removed': self.gw.faults.clear()}
        body = await self._body(request)
        specs = body.get('faults') if 'faults' in body else [body]
        if not isinstance(specs, list) or not specs:
            raise ControlError(400, 'send one fault object or {"faults": [...]}')
        added = []
        for spec in specs:
            if not isinstance(spec, dict):
                raise ControlError(400, 'each fault must be an object')
            try:
                added.append(self.gw.faults.add(spec))
            except ValueError as exc:
                raise ControlError(400, str(exc)) from exc
        return {'faults': added}

    async def clock(self, request: Request) -> dict[str, Any]:
        ticked: dict[str, int] | None = None
        if request.method == 'POST':
            body = await self._body(request)
            seconds = body.get('advance_seconds', 0)
            if not isinstance(seconds, int | float) or isinstance(seconds, bool) or seconds < 0:
                raise ControlError(400, 'advance_seconds must be a non-negative number')
            self.gw.clock.advance(float(seconds))
            ticked = await self.gw.tick()
        return {
            'now': iso(self.gw.now()),
            'offset_seconds': self.gw.clock.offset_seconds,
            'tick': ticked,
        }

    async def tick(self, request: Request) -> dict[str, Any]:
        return {'tick': await self.gw.tick(), 'now': iso(self.gw.now())}

    async def replay(self, request: Request) -> dict[str, Any]:
        payment = self._payment(request.path_params['ref'])
        try:
            entry = await self.gw.notifier.replay_result(payment)
        except LookupError as exc:
            raise ControlError(409, str(exc)) from exc
        return {'delivery': entry}
