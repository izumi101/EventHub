"""Check and Result callbacks, strict replies, retries and restart persistence."""

from __future__ import annotations

import re

import pytest

from . import merchant as fm
from .conftest import Emu, field

RESULT = '/payments/freedompay/result'
CHECK = '/payments/freedompay/check'
BUSINESS_SKIP = {'pg_salt', 'pg_sig', 'pg_can_reject'}


async def start(emu: Emu, **init: str) -> str:
    params = {'pg_result_url': emu.merchant.url(RESULT), 'booking': 'B-7'}
    params.update(init)
    return field(await emu.init(**params), 'pg_payment_id')


def business(call: fm.Received) -> dict[str, str]:
    return {k: v for k, v in call.fields().items() if k not in BUSINESS_SKIP}


async def test_result_after_success_has_all_documented_fields(emu: Emu) -> None:
    payment_id = await start(emu, pg_user_phone='77777777777', pg_user_contact_email='b@example.com')
    state = await emu.complete(payment_id)
    [call] = emu.merchant.calls(RESULT)
    assert call.method == 'POST'
    assert call.signature_ok
    f = call.fields()
    assert f['pg_payment_id'] == payment_id
    assert f['pg_order_id'] == 'ORD-1'
    assert (f['pg_amount'], f['pg_currency'], f['pg_result']) == ('1500', 'KZT', '1')
    assert f['pg_net_amount'] == '1462.5'  # 2.5 % commission paid by the merchant
    assert (f['pg_ps_amount'], f['pg_ps_full_amount'], f['pg_ps_currency']) == ('1500', '1500', 'KZT')
    assert f['pg_can_reject'] == '1'
    assert f['pg_testing_mode'] == '1'
    assert f['pg_captured'] == '1'
    assert re.match(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$', f['pg_payment_date'])
    assert f['pg_card_pan'] == '4716-04XX-XXXX-1981'
    assert (f['pg_card_brand'], f['pg_card_exp'], f['pg_payment_method']) == ('VI', '12/30', 'bankcard')
    assert f['pg_user_contact_email'] == 'b@example.com'
    assert f['pg_user_phone'] == '77777777777'
    assert f['booking'] == 'B-7'
    assert 'pg_failure_code' not in f
    assert len(f['pg_reference']) == 12
    assert [d['verdict'] for d in state['deliveries']] == ['ok']
    assert state['callback_jobs'][0]['state'] == 'delivered'
    assert field(await emu.status(payment_id), 'pg_can_reject') == '0'


async def test_commission_paid_by_the_client(make_emu) -> None:
    emu = await make_emu(FPAY_COMMISSION_PERCENT='3', FPAY_COMMISSION_PAYER='client')
    payment_id = await start(emu)
    await emu.complete(payment_id)
    f = emu.merchant.calls(RESULT)[0].fields()
    assert (f['pg_net_amount'], f['pg_ps_full_amount']) == ('1500', '1545')


async def test_payment_date_time_zone(make_emu) -> None:
    emu = await make_emu(FPAY_TIMEZONE='UTC')
    payment_id = await start(emu)
    state = await emu.complete(payment_id)
    date = emu.merchant.calls(RESULT)[0].fields()['pg_payment_date']
    assert date == state['paid_at'][:19].replace('T', ' ')


async def test_result_after_decline(make_emu) -> None:
    emu = await make_emu()
    payment_id = await start(emu)
    await emu.complete(payment_id, scenario='decline', failure_code='10009')
    f = emu.merchant.calls(RESULT)[0].fields()
    assert (f['pg_result'], f['pg_can_reject'], f['pg_net_amount']) == ('0', '0', '0')
    assert 'pg_ps_amount' not in f
    assert 'pg_failure_code' not in f
    status = await emu.status(payment_id)
    assert (field(status, 'pg_payment_status'), field(status, 'pg_failure_code')) == ('error', '10009')


async def test_failure_fields_switch(make_emu) -> None:
    emu = await make_emu(FPAY_RESULT_FAILURE_FIELDS='1')
    payment_id = await start(emu)
    await emu.complete(payment_id, scenario='3ds_fail')
    f = emu.merchant.calls(RESULT)[0].fields()
    assert f['pg_failure_code'] == '10004'
    assert f['pg_failure_description']


@pytest.mark.parametrize('method', ['GET', 'XML'])
async def test_result_request_methods(emu: Emu, method: str) -> None:
    url = emu.merchant.url(RESULT) + ('?route=freedompay' if method == 'GET' else '')
    payment_id = field(await emu.init(pg_result_url=url, pg_request_method=method), 'pg_payment_id')
    await emu.complete(payment_id)
    [call] = emu.merchant.calls(RESULT)
    assert call.signature_ok
    if method == 'GET':
        assert call.method == 'GET'
        assert call.query[0] == ('route', 'freedompay')
    else:
        assert call.xml is not None
        assert call.fields()['pg_result'] == '1'


async def test_get_callback_without_url_query_signature(make_emu) -> None:
    emu = await make_emu(FPAY_CALLBACK_SIGN_URL_QUERY='never')
    url = emu.merchant.url(RESULT) + '?route=freedompay'
    payment_id = field(await emu.init(pg_result_url=url, pg_request_method='GET'), 'pg_payment_id')
    await emu.complete(payment_id)
    # A merchant verifying over its whole $_GET now fails, as documented for this switch.
    assert not emu.merchant.calls(RESULT)[0].signature_ok


# -- strict replies ---------------------------------------------------------------


@pytest.mark.parametrize(
    ('behaviour', 'verdict'),
    [
        (fm.WRONG_SIG, 'invalid'),
        (fm.PLAIN, 'invalid'),
        (fm.NO_ECHO, 'invalid'),
        (fm.NO_DESCRIPTION, 'invalid'),
        (fm.HTTP500, 'http_error'),
        (fm.CLOSE, 'connection_error'),
        (fm.ERROR, 'error'),
    ],
)
async def test_unaccepted_replies_are_retried(emu: Emu, behaviour: str, verdict: str) -> None:
    emu.merchant.plan(RESULT, behaviour, default=fm.OK)
    payment_id = await start(emu)
    state = await emu.complete(payment_id)
    assert [d['verdict'] for d in state['deliveries']] == [verdict]
    assert state['callback_jobs'][0]['state'] == 'pending'
    assert state['can_reject'] is False
    await emu.advance(1)
    state = await emu.state(payment_id)
    assert [d['verdict'] for d in state['deliveries']] == [verdict, 'ok']
    assert state['callback_jobs'][0]['state'] == 'delivered'


async def test_lenient_mode_accepts_any_200(make_emu) -> None:
    emu = await make_emu(FPAY_REPLY_MODE='lenient')
    emu.merchant.plan(RESULT, fm.PLAIN)
    payment_id = await start(emu)
    state = await emu.complete(payment_id)
    assert [d['verdict'] for d in state['deliveries']] == ['ok']
    emu.merchant.plan(RESULT, fm.WRONG_SIG)
    second = await start(emu, pg_order_id='ORD-2')
    assert [d['verdict'] for d in (await emu.complete(second))['deliveries']] == ['ok']


async def test_salt_echo_switch(make_emu) -> None:
    emu = await make_emu(FPAY_REPLY_SALT_MUST_ECHO='0')
    emu.merchant.plan(RESULT, fm.NO_ECHO)
    state = await emu.complete(await start(emu))
    assert [d['verdict'] for d in state['deliveries']] == ['ok']


async def test_error_reply_not_retried_when_switched_off(make_emu) -> None:
    emu = await make_emu(FPAY_RETRY_ON_ERROR_REPLY='0')
    emu.merchant.plan(RESULT, fm.ERROR)
    state = await emu.complete(await start(emu))
    assert state['callback_jobs'][0]['state'] == 'delivered'


async def test_timeout_is_a_failed_attempt(make_emu) -> None:
    emu = await make_emu(FPAY_CALLBACK_TIMEOUT_SECONDS='0.2')
    emu.merchant.slow_seconds = 0.6
    emu.merchant.plan(RESULT, fm.SLOW)
    state = await emu.complete(await start(emu))
    assert [d['verdict'] for d in state['deliveries']] == ['timeout']


# -- retries ---------------------------------------------------------------------------


async def test_500_then_recovery_flips_can_reject_and_keeps_business_data(emu: Emu) -> None:
    emu.merchant.plan(RESULT, fm.HTTP500, fm.HTTP500, fm.OK)
    payment_id = await start(emu)
    await emu.complete(payment_id)
    await emu.advance(0.5)
    assert len(emu.merchant.calls(RESULT)) == 1  # the next slot is 1 s after the first attempt
    await emu.advance(0.5)
    await emu.advance(1)
    calls = emu.merchant.calls(RESULT)
    assert [c.fields()['pg_can_reject'] for c in calls] == ['1', '0', '0']
    assert business(calls[0]) == business(calls[1]) == business(calls[2])
    assert len({c.fields()['pg_salt'] for c in calls}) == 3
    assert all(c.signature_ok for c in calls)
    state = await emu.state(payment_id)
    assert [d['attempt'] for d in state['deliveries']] == [1, 2, 3]
    assert state['callback_jobs'][0]['state'] == 'delivered'


async def test_retry_window_is_exhausted(emu: Emu) -> None:
    emu.merchant.plan(RESULT, default=fm.HTTP500)
    payment_id = await start(emu)
    await emu.complete(payment_id)
    tick = await emu.advance(100)
    assert tick['tick']['callback_attempts'] == 4  # slots at 1, 2, 3 and 4 s; the window is 4 s
    state = await emu.state(payment_id)
    assert len(state['deliveries']) == 5
    assert state['deliveries'][-1]['outcome'] == 'gave_up'
    assert state['callback_jobs'][0]['state'] == 'failed'


async def test_default_schedule_is_every_30_minutes_for_2_hours(make_emu, tmp_path) -> None:
    emu = await make_emu(
        FPAY_RETRY_INTERVAL_SECONDS='1800', FPAY_RETRY_WINDOW_SECONDS='7200', FPAY_DB_PATH=str(tmp_path / 'd.db')
    )
    emu.merchant.plan(RESULT, default=fm.HTTP500)
    payment_id = await start(emu)
    await emu.complete(payment_id)
    await emu.advance(1799)
    assert len(emu.merchant.calls(RESULT)) == 1
    await emu.advance(1)
    assert len(emu.merchant.calls(RESULT)) == 2
    await emu.advance(7200)
    assert len(emu.merchant.calls(RESULT)) == 5


async def test_retries_survive_a_restart(make_emu) -> None:
    first = await make_emu()
    first.merchant.plan(RESULT, fm.HTTP500, fm.OK)
    payment_id = await start(first)
    await first.complete(payment_id)
    await first.app.emulator.stop()
    second = await make_emu()  # same database file
    assert (await second.state(payment_id))['callback_jobs'][0]['state'] == 'pending'
    await second.advance(1)
    state = await second.state(payment_id)
    assert [d['verdict'] for d in state['deliveries']] == ['http_error', 'ok']


async def test_background_scheduler_delivers_retries(make_emu) -> None:
    emu = await make_emu(FPAY_SCHEDULER_TICK_SECONDS='0.05')
    emu.merchant.plan(RESULT, fm.HTTP500, fm.OK)
    payment_id = await start(emu)
    await emu.complete(payment_id)
    await emu.app.emulator.start()
    await emu.merchant.wait_for(RESULT, 2, timeout=5)


# -- rejection ---------------------------------------------------------------------------


async def test_rejected_with_can_reject_rolls_the_payment_back(emu: Emu) -> None:
    emu.merchant.plan(RESULT, fm.REJECTED)
    payment_id = await start(emu)
    state = await emu.complete(payment_id)
    assert state['merchant_rejected'] is True
    assert state['deliveries'][0]['outcome'] == 'rejected'
    status = await emu.status(payment_id)
    assert field(status, 'pg_payment_status') == 'success'  # cancelled payments keep success
    assert field(status, 'pg_revoked_amount') == '-1500.00'


async def test_rejected_after_a_failed_first_attempt_is_ignored(emu: Emu) -> None:
    emu.merchant.plan(RESULT, fm.HTTP500, fm.REJECTED)
    payment_id = await start(emu)
    await emu.complete(payment_id)
    await emu.advance(1)
    state = await emu.state(payment_id)
    assert state['merchant_rejected'] is False
    assert state['deliveries'][-1]['outcome'] == 'rejected_ignored'
    assert state['callback_jobs'][0]['state'] == 'delivered'
    assert field(await emu.status(payment_id), 'pg_revoked_amount') is None


async def test_replay_sends_the_same_business_data(emu: Emu) -> None:
    payment_id = await start(emu)
    await emu.complete(payment_id)
    emu.merchant.plan(RESULT, fm.REJECTED)
    response = await emu.control('POST', f'/replay-callback/{payment_id}')
    assert response.status_code == 200
    assert response.json()['delivery']['outcome'] == 'rejected_ignored'
    first, replay = emu.merchant.calls(RESULT)
    assert business(first) == business(replay)
    assert replay.fields()['pg_can_reject'] == '0'
    assert (await emu.state(payment_id))['merchant_rejected'] is False


async def test_replay_without_a_result_url(emu: Emu) -> None:
    payment_id = field(await emu.init(), 'pg_payment_id')
    response = await emu.control('POST', f'/replay-callback/{payment_id}')
    assert response.status_code == 409


# -- check -------------------------------------------------------------------------------


async def test_check_is_called_first_when_enabled(make_emu) -> None:
    emu = await make_emu(FPAY_CHECK_ENABLED='1')
    payment_id = await start(emu, pg_check_url=emu.merchant.url(CHECK))
    state = await emu.complete(payment_id)
    assert [c.path for c in emu.merchant.received] == [CHECK, RESULT]
    check = emu.merchant.calls(CHECK)[0]
    assert check.signature_ok
    assert set(check.fields()) == {
        'pg_order_id', 'pg_payment_id', 'pg_amount', 'pg_currency', 'pg_ps_amount', 'pg_ps_currency',
        'pg_ps_full_amount', 'booking', 'pg_salt', 'pg_sig',
    }  # fmt: skip
    assert state['status'] == 'success'
    assert [d['kind'] for d in state['deliveries']] == ['check', 'result']


@pytest.mark.parametrize('behaviour', [fm.REJECTED, fm.ERROR, fm.WRONG_SIG, fm.HTTP500, fm.PLAIN, fm.SLOW])
async def test_check_refusal_declines_the_payment(make_emu, behaviour: str) -> None:
    emu = await make_emu(FPAY_CHECK_ENABLED='1', FPAY_CHECK_TIMEOUT_SECONDS='0.2')
    emu.merchant.slow_seconds = 0.6
    emu.merchant.plan(CHECK, behaviour)
    payment_id = await start(emu, pg_check_url=emu.merchant.url(CHECK))
    state = await emu.complete(payment_id)
    assert state['status'] == 'error'
    assert state['failure_code'] == '99999'
    result = emu.merchant.calls(RESULT)[0].fields()
    assert result['pg_result'] == '0'
    if behaviour == fm.REJECTED:
        assert state['failure_description'] == 'reply rejected'


async def test_check_is_skipped_when_disabled(emu: Emu) -> None:
    payment_id = await start(emu, pg_check_url=emu.merchant.url(CHECK))
    await emu.complete(payment_id)
    assert emu.merchant.calls(CHECK) == []


# -- expiry ---------------------------------------------------------------------------------


async def test_lifetime_expiry_sends_a_failure_result(emu: Emu) -> None:
    payment_id = await start(emu, pg_lifetime='300')
    await emu.advance(299)
    assert field(await emu.status(payment_id), 'pg_payment_status') == 'new'
    tick = await emu.advance(2)
    assert tick['tick']['expired'] == 1
    status = await emu.status(payment_id)
    assert (field(status, 'pg_payment_status'), field(status, 'pg_failure_code')) == ('error', '10018')
    assert emu.merchant.calls(RESULT)[0].fields()['pg_result'] == '0'
    late = await emu.control('POST', f'/payments/{payment_id}/complete', json={})
    assert late.status_code == 409


async def test_expiry_result_switches(make_emu, tmp_path) -> None:
    emu = await make_emu(FPAY_EXPIRY_PG_RESULT='2')
    payment_id = await start(emu, pg_lifetime='300')
    await emu.advance(400)
    assert emu.merchant.calls(RESULT)[0].fields()['pg_result'] == '2'
    assert field(await emu.status(payment_id), 'pg_failure_code') == '10018'
    silent = await make_emu(FPAY_RESULT_ON_EXPIRY='0', FPAY_DB_PATH=str(tmp_path / 's.db'))
    other = await start(silent, pg_lifetime='300', pg_order_id='S-1')
    await silent.advance(400)
    assert field(await silent.status(other), 'pg_payment_status') == 'error'
    assert len(emu.merchant.calls(RESULT)) == 1
