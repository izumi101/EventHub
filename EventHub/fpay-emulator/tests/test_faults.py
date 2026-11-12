"""Failure injection (``POST /_emulator/faults``)."""

from __future__ import annotations

import random
import time

import pytest

from fpay_emulator import xmlio
from fpay_emulator.faults import ConnectionDropped, endpoint_for_path, mutate_body
from fpay_emulator.signature import verify_signature

from .conftest import SECRET, Emu, field

INIT = {'pg_amount': '100', 'pg_description': 'x', 'pg_order_id': 'F-1'}


async def add(emu: Emu, **spec: object) -> dict:
    response = await emu.control('POST', '/faults', json=spec)
    assert response.status_code == 200, response.text
    return response.json()['faults'][0]


async def test_http_500_before_processing(emu: Emu) -> None:
    await add(emu, endpoint='init_payment', mode='http_500', count=1)
    response = await emu.raw('/init_payment', INIT)
    assert response.status_code == 500
    assert response.headers['content-type'].startswith('text/html')
    assert (await emu.control('GET', '/payments')).json()['payments'] == []
    assert (await emu.raw('/init_payment', INIT)).status_code == 200  # count exhausted


async def test_http_502_after_processing_needs_reconciliation(emu: Emu) -> None:
    await add(emu, endpoint='init_payment', mode='http_502', phase='after', count=1)
    response = await emu.raw('/init_payment', INIT)
    assert response.status_code == 502
    # The payment exists: a client must look it up by pg_order_id before retrying (S1).
    reply = await emu.call('/get_status3.php', {'pg_order_id': 'F-1'})
    assert field(reply, 'pg_payment_status') == 'new'


async def test_timeout_and_latency(emu: Emu) -> None:
    await add(emu, endpoint='get_status', mode='timeout', latency_ms=100, count=1)
    started = time.perf_counter()
    response = await emu.raw('/get_status3.php', {'pg_payment_id': '1'})
    assert response.status_code == 504
    assert time.perf_counter() - started >= 0.1
    await add(emu, endpoint='init_payment', mode='latency', latency_ms=150, count=1)
    started = time.perf_counter()
    assert (await emu.raw('/init_payment', INIT)).status_code == 200
    assert time.perf_counter() - started >= 0.15


async def test_drop_without_a_real_transport_raises(emu: Emu) -> None:
    await add(emu, endpoint='revoke', mode='drop', count=1)
    with pytest.raises(ConnectionDropped):
        await emu.raw('/revoke', {'pg_payment_id': '1'})


class FakeTransport:
    def __init__(self) -> None:
        self.aborted = False

    def abort(self) -> None:
        self.aborted = True


async def test_drop_aborts_the_server_transport(emu: Emu) -> None:
    await add(emu, endpoint='healthcheck', mode='drop', count=1)
    transport = FakeTransport()
    sent: list[dict] = []

    async def receive() -> dict:
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {
        'type': 'http',
        'method': 'GET',
        'path': '/status/healthcheck',
        'raw_path': b'/status/healthcheck',
        'query_string': b'',
        'headers': [],
        'fpay.transport': transport,
    }
    await emu.app(scope, receive, send)
    assert transport.aborted
    assert sent == []


async def test_body_mutations(emu: Emu) -> None:
    await add(emu, endpoint='init_payment', mode='malformed_xml', count=1)
    broken = await emu.raw('/init_payment', INIT)
    with pytest.raises(xmlio.XmlError):
        xmlio.parse(broken.content)
    assert int(broken.headers['content-length']) == len(broken.content)

    await add(emu, endpoint='init_payment', mode='unsigned_success', count=1)
    unsigned = xmlio.parse((await emu.raw('/init_payment', INIT)).content)
    assert field(unsigned, 'pg_status') == 'ok'
    assert field(unsigned, 'pg_sig') is None

    await add(emu, endpoint='init_payment', mode='wrong_signature', count=1)
    wrong = xmlio.parse((await emu.raw('/init_payment', INIT)).content)
    assert field(wrong, 'pg_status') == 'ok'
    assert not verify_signature('init_payment', wrong, SECRET, field(wrong, 'pg_sig'))


def test_mutate_body_helpers() -> None:
    body = b'<response>\n    <pg_status>ok</pg_status>\n    <pg_sig>abc</pg_sig>\n</response>\n'
    assert b'pg_sig' not in mutate_body('unsigned_success', body)
    assert b'<pg_sig>00000000000000000000000000000000</pg_sig>' in mutate_body('wrong_signature', body)
    assert mutate_body('http_500', body) == body


async def test_wildcard_count_and_listing(emu: Emu) -> None:
    fault = await add(emu, endpoint='*', mode='http_500', count=2)
    assert fault['remaining'] == 2
    assert (await emu.client.get('/status/healthcheck')).status_code == 500
    listed = (await emu.control('GET', '/faults')).json()['faults']
    assert listed[0]['remaining'] == 1
    assert listed[0]['hits'] == 1
    assert (await emu.raw('/cancel', {'pg_payment_id': '1'})).status_code == 500
    assert (await emu.control('GET', '/faults')).json()['faults'] == []
    # The control API and the payment page are never faulted.
    await add(emu, endpoint='*', mode='http_500')
    assert (await emu.control('GET', '/faults')).status_code == 200
    assert (await emu.client.get('/pay.html?customer=x')).status_code == 404
    assert (await emu.control('DELETE', '/faults')).json() == {'removed': 1}


async def test_probability(emu: Emu) -> None:
    emu.app.emulator.faults._rng = random.Random(7)  # noqa: S311 - deterministic sampling
    await add(emu, endpoint='healthcheck', mode='http_502', probability=0.5)
    statuses = [(await emu.client.get('/status/healthcheck')).status_code for _ in range(40)]
    assert 0 < statuses.count(502) < 40
    assert set(statuses) == {200, 502}


async def test_batch_and_validation(emu: Emu) -> None:
    batch = await emu.control(
        'POST', '/faults', json={'faults': [{'mode': 'latency'}, {'endpoint': 'revoke', 'mode': 'timeout'}]}
    )
    assert [f['latency_ms'] for f in batch.json()['faults']] == [1000, 30000]
    for spec in [
        {'mode': 'explode'},
        {'mode': 'http_500', 'endpoint': 'nowhere'},
        {'mode': 'http_500', 'phase': 'during'},
        {'mode': 'http_500', 'count': 0},
        {'mode': 'http_500', 'count': True},
        {'mode': 'http_500', 'probability': 0},
        {'mode': 'http_500', 'probability': 'often'},
        {'mode': 'latency', 'latency_ms': -1},
        {'mode': 'latency', 'latency_ms': 1.5},
    ]:
        response = await emu.control('POST', '/faults', json=spec)
        assert response.status_code == 400, spec
    assert (await emu.control('POST', '/faults', json={'faults': []})).status_code == 400
    assert (await emu.control('POST', '/faults', json={'faults': [1]})).status_code == 400


@pytest.mark.parametrize(
    ('path', 'endpoint'),
    [
        ('/init_payment', 'init_payment'),
        ('/payment.php', 'payment'),
        ('/get_status2.php', 'get_status'),
        ('/status/healthcheck', 'healthcheck'),
        ('/_emulator/faults', None),
        ('/pay/x/card', None),
    ],
)
def test_endpoint_for_path(path: str, endpoint: str | None) -> None:
    assert endpoint_for_path(path) == endpoint
