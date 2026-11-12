"""Control API (``/_emulator``)."""

from __future__ import annotations

import pytest

from .conftest import Emu, field


async def test_token_protection(make_emu) -> None:
    emu = await make_emu(FPAY_CONTROL_TOKEN='s3cret')
    assert (await emu.control('GET', '/payments')).status_code == 401
    assert (await emu.control('GET', '/payments', headers={'X-Emulator-Token': 'nope'})).status_code == 401
    assert (await emu.control('GET', '/payments', headers={'X-Emulator-Token': 's3cret'})).status_code == 200


async def test_control_can_be_disabled(make_emu) -> None:
    emu = await make_emu(FPAY_CONTROL_ENABLED='0')
    assert (await emu.control('POST', '/reset')).status_code == 404


async def test_list_get_and_reset(emu: Emu) -> None:
    first = field(await emu.init(pg_order_id='A'), 'pg_payment_id')
    await emu.init(pg_order_id='B')
    listed = (await emu.control('GET', '/payments', params={'order_id': 'A'})).json()['payments']
    assert [p['payment_id'] for p in listed] == [int(first)]
    assert len((await emu.control('GET', '/payments', params={'status': 'new', 'limit': '1'})).json()['payments']) == 1
    assert (await emu.control('GET', '/payments', params={'limit': 'x'})).status_code == 400
    state = await emu.state(first)
    assert state['status_response']['pg_payment_status'] == 'new'
    by_customer = await emu.state(state['customer'])
    assert by_customer['payment_id'] == int(first)
    assert (await emu.control('GET', '/payments/1')).status_code == 404
    await emu.advance(10)
    assert (await emu.control('POST', '/reset')).json() == {'status': 'ok'}
    assert (await emu.control('GET', '/payments')).json()['payments'] == []
    clock = (await emu.control('GET', '/clock')).json()
    assert clock['offset_seconds'] == 0
    after = field(await emu.init(), 'pg_payment_id')
    assert int(after) > int(first)  # ids are never reused


@pytest.mark.parametrize(
    ('scenario', 'status', 'code'),
    [
        ('success', 'success', None),
        ('decline', 'error', '10009'),
        ('3ds_success', 'success', None),
        ('3ds_fail', 'error', '10004'),
        ('hang', 'process', None),
        ('abandon', 'waiting', None),
    ],
)
async def test_complete_scenarios(emu: Emu, scenario: str, status: str, code: str | None) -> None:
    payment_id = field(await emu.init(), 'pg_payment_id')
    state = await emu.complete(payment_id, scenario=scenario)
    assert state['status'] == status
    assert state['failure_code'] == code


async def test_preset_scenario_is_used_by_complete(emu: Emu) -> None:
    payment_id = field(await emu.init(), 'pg_payment_id')
    response = await emu.control(
        'POST', f'/payments/{payment_id}/scenario', json={'scenario': 'decline', 'failure_code': '11024'}
    )
    assert response.json()['scenario']['failure_code'] == '11024'
    state = await emu.complete(payment_id)
    assert (state['status'], state['failure_code']) == ('error', '11024')
    assert (
        await emu.control('POST', f'/payments/{payment_id}/scenario', json={'scenario': 'success'})
    ).status_code == 409


async def test_complete_finishes_a_browser_challenge(emu: Emu) -> None:
    reply = await emu.init()
    payment_id = field(reply, 'pg_payment_id')
    customer = field(reply, 'pg_redirect_url').split('customer=')[1]
    await emu.client.post(f'/pay/{customer}/scenario', data={'scenario': '3ds'})
    assert (await emu.complete(payment_id))['status'] == 'success'


@pytest.mark.parametrize(
    'body',
    [
        {'scenario': 'teleport'},
        {'scenario': 'decline', 'failure_code': 10009},
        {'scenario': 'decline', 'failure_code': 'x'},
    ],
)
async def test_scenario_validation(emu: Emu, body: dict) -> None:
    payment_id = field(await emu.init(), 'pg_payment_id')
    assert (await emu.control('POST', f'/payments/{payment_id}/scenario', json=body)).status_code == 400
    assert (await emu.control('POST', f'/payments/{payment_id}/complete', json=body)).status_code == 400


async def test_body_validation(emu: Emu) -> None:
    payment_id = field(await emu.init(), 'pg_payment_id')
    assert (await emu.control('POST', f'/payments/{payment_id}/scenario', content=b'{')).status_code == 400
    assert (await emu.control('POST', f'/payments/{payment_id}/scenario', json=[1])).status_code == 400
    assert (await emu.control('POST', f'/payments/{payment_id}/scenario', json={})).status_code == 400
    assert (await emu.control('POST', '/clock', json={'advance_seconds': -1})).status_code == 400
    assert (await emu.control('POST', '/clock', json={'advance_seconds': True})).status_code == 400


async def test_clock_and_tick(emu: Emu) -> None:
    before = (await emu.control('GET', '/clock')).json()
    after = await emu.advance(3600)
    assert after['offset_seconds'] == before['offset_seconds'] + 3600
    assert after['now'] > before['now']
    tick = (await emu.control('POST', '/tick')).json()
    assert tick['tick'] == {'expired': 0, 'auto_processed': 0, 'callback_attempts': 0}
