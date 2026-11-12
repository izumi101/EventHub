"""Gateway contract: the same checks against the emulator and the real test API.

Read-only and request-error checks always run. Paying and refunding are
destructive: they run against the emulator (driven by its control API) and,
on a gateway without ``/_emulator``, only with ``FPAY_CONTRACT_ALLOW_DESTRUCTIVE=1``
and a person paying in the browser.
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal

import httpx
import pytest

from .conftest import Target
from .fpay_client import Reply


def order_id() -> str:
    return f'contract-{uuid.uuid4().hex[:20]}'


def assert_unsigned_error(reply: Reply, *codes: str) -> None:
    assert reply.http_status == 200, 'API errors are answered with HTTP 200'
    assert reply.content_type.startswith('text/xml')
    assert reply.get('pg_status') == 'error'
    assert reply.get('pg_error_code') in codes, reply.raw
    assert reply.get('pg_sig') is None, 'error answers are unsigned'


def init(target: Target, oid: str, **extra: str) -> Reply:
    reply = target.gateway.call(
        '/init_payment',
        {
            'pg_order_id': oid,
            'pg_amount': target.amount,
            'pg_currency': target.currency,
            'pg_description': f'EventHub contract test {oid}',
            'pg_testing_mode': '1',
            'pg_lifetime': '1800',
            **extra,
        },
    )
    assert reply.ok, reply.raw
    assert reply.signature_valid('init_payment', target.gateway.secret), 'init_payment answer must be signed'
    return reply


def status(target: Target, payment_id: str) -> Reply:
    reply = target.gateway.call('/get_status3.php', {'pg_payment_id': payment_id})
    assert reply.ok, reply.raw
    assert reply.signature_valid('get_status3.php', target.gateway.secret), 'get_status3 answer must be signed'
    return reply


def test_healthcheck(target: Target) -> None:
    response = httpx.get(f'{target.gateway.base_url}/status/healthcheck', timeout=10)
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_bad_signature_is_an_unsigned_error(target: Target) -> None:
    reply = target.gateway.call(
        '/init_payment', {'pg_amount': target.amount, 'pg_description': 'bad signature'}, secret='not-the-secret'
    )
    assert_unsigned_error(reply, '9998')


def test_script_name_must_match_the_path(target: Target) -> None:
    reply = target.gateway.call(
        '/init_payment', {'pg_amount': target.amount, 'pg_description': 'wrong script'}, script='init_payment.php'
    )
    assert_unsigned_error(reply, '9998')


def test_status_bad_signature(target: Target) -> None:
    reply = target.gateway.call('/get_status3.php', {'pg_payment_id': '1'}, secret='not-the-secret')
    assert_unsigned_error(reply, '1100', '9998')


def test_status_needs_an_id(target: Target) -> None:
    assert_unsigned_error(target.gateway.call('/get_status3.php', {}), '1200')


def test_status_of_an_unknown_payment(target: Target) -> None:
    assert_unsigned_error(target.gateway.call('/get_status3.php', {'pg_payment_id': '1'}), '11068')


def test_init_payment_then_status(target: Target) -> None:
    oid = order_id()
    created = init(target, oid)
    payment_id = created.get('pg_payment_id')
    assert payment_id and payment_id.isdigit()
    assert created.get('pg_redirect_url', '').startswith('http')
    reply = status(target, payment_id)
    assert reply.get('pg_payment_id') == payment_id
    assert reply.get('pg_payment_status') in ('new', 'waiting', 'process')
    assert Decimal(reply.get('pg_amount')) == Decimal(target.amount)
    assert reply.get('pg_currency') == target.currency
    by_order = target.gateway.call('/get_status3.php', {'pg_order_id': oid})
    assert by_order.ok and by_order.get('pg_payment_id') == payment_id


def _pay(target: Target, payment_id: str, redirect_url: str) -> None:
    if target.is_emulator:
        response = target.control('POST', f'/payments/{payment_id}/complete', json={'scenario': 'success'})
        assert response.status_code == 200, response.text
        return
    print(f'\nPay this test payment in a browser (test card 4716047261941981, 12/30, CVV 123):\n  {redirect_url}\n')
    deadline = time.monotonic() + target.manual_timeout
    while time.monotonic() < deadline:
        if status(target, payment_id).get('pg_payment_status') in ('success', 'error'):
            return
        time.sleep(5)
    pytest.fail('the payment was not completed in time')


def test_pay_status_and_refund(target: Target) -> None:
    if not target.is_emulator and not target.allow_destructive:
        pytest.skip('no /_emulator control API: set FPAY_CONTRACT_ALLOW_DESTRUCTIVE=1 to pay and refund by hand')
    oid = order_id()
    created = init(target, oid)
    payment_id = created.get('pg_payment_id')
    _pay(target, payment_id, created.get('pg_redirect_url'))
    paid = status(target, payment_id)
    assert paid.get('pg_payment_status') == 'success'
    amount = Decimal(paid.get('pg_amount'))

    part = (amount / 2).quantize(Decimal('0.01'))
    refund = target.gateway.call(
        '/revoke', {'pg_payment_id': payment_id, 'pg_refund_amount': str(part), 'pg_idempotency_key': f'{oid}-r1'}
    )
    assert refund.ok, refund.raw
    assert refund.signature_valid('revoke', target.gateway.secret)
    assert refund.get('pg_revoke_payment_id')

    after = status(target, payment_id)
    assert after.get('pg_payment_status') == 'success', 'a refunded payment keeps the success status'
    assert Decimal(after.get('pg_refund_amount')) == -part

    rest = target.gateway.call('/revoke', {'pg_payment_id': payment_id, 'pg_idempotency_key': f'{oid}-r2'})
    assert rest.ok, rest.raw
    final = status(target, payment_id)
    assert Decimal(final.get('pg_refund_amount')) == -amount
    refunds = final.get('pg_refund_payments') or []
    assert len(refunds) == 2
