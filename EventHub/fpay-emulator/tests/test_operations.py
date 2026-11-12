"""Capture, cancel and refund (spec section 6)."""

from __future__ import annotations

import asyncio

import pytest

from fpay_emulator.signature import Pairs

from .conftest import OTHER_ID, OTHER_SECRET, Emu, assert_signed, field


def error_code(reply: Pairs) -> str:
    assert field(reply, 'pg_sig') is None
    return field(reply, 'pg_error_code')


async def paid(emu: Emu, **init: str) -> str:
    payment_id = field(await emu.init(**init), 'pg_payment_id')
    state = await emu.complete(payment_id)
    assert state['status'] == 'success'
    return payment_id


def refund_list(status: Pairs) -> list[dict[str, str]]:
    refunds = field(status, 'pg_refund_payments')
    return [dict(entry) for _, entry in refunds] if refunds else []


# -- capture --------------------------------------------------------------------


async def test_two_step_full_capture(emu: Emu) -> None:
    payment_id = await paid(emu, pg_auto_clearing='0')
    status = await emu.status(payment_id)
    assert field(status, 'pg_captured') == '0'
    assert field(status, 'pg_clearing_amount') == '0'
    reply = await emu.call('/do_capture.php', {'pg_payment_id': payment_id})
    assert_signed(reply, 'do_capture.php')
    assert (field(reply, 'pg_amount'), field(reply, 'pg_clearing_amount')) == ('1500', '1500')
    status = await emu.status(payment_id)
    assert field(status, 'pg_captured') == '1'
    assert field(status, 'pg_payment_status') == 'success'


async def test_partial_capture_once_then_repeat_returns_it(emu: Emu) -> None:
    payment_id = await paid(emu, pg_auto_clearing='0')
    first = await emu.call('/do_capture.php', {'pg_payment_id': payment_id, 'pg_clearing_amount': '1000.999'})
    assert field(first, 'pg_clearing_amount') == '1000.99'  # extra digits dropped (S10)
    again = await emu.call('/do_capture.php', {'pg_payment_id': payment_id, 'pg_clearing_amount': '1500'})
    assert field(again, 'pg_clearing_amount') == '1000.99'
    status = await emu.status(payment_id)
    assert field(status, 'pg_clearing_amount') == '1000.99'


async def test_capture_of_a_one_step_payment_returns_the_captured_amount(emu: Emu) -> None:
    payment_id = await paid(emu)
    reply = await emu.call('/do_capture.php', {'pg_payment_id': payment_id})
    assert field(reply, 'pg_clearing_amount') == '1500'


async def test_capture_after_hold_release_captures_nothing(emu: Emu) -> None:
    payment_id = await paid(emu, pg_auto_clearing='0')
    assert field(await emu.call('/cancel', {'pg_payment_id': payment_id}), 'pg_status') == 'ok'
    reply = await emu.call('/do_capture.php', {'pg_payment_id': payment_id})
    assert field(reply, 'pg_status') == 'ok'
    assert field(reply, 'pg_clearing_amount') == '0'


async def test_capture_errors(emu: Emu) -> None:
    assert error_code(await emu.call('/do_capture.php', {})) == '94031'
    assert error_code(await emu.call('/do_capture.php', {'pg_payment_id': '1'})) == '340'
    assert error_code(await emu.call('/do_capture.php', {'pg_payment_id': 'x'})) == '340'
    unpaid = field(await emu.init(), 'pg_payment_id')
    assert error_code(await emu.call('/do_capture.php', {'pg_payment_id': unpaid})) == '340'
    held = await paid(emu, pg_auto_clearing='0')
    assert error_code(await emu.call('/do_capture.php', {'pg_payment_id': held, 'pg_clearing_amount': '2000'})) == (
        '11074'
    )
    assert error_code(await emu.call('/do_capture.php', {'pg_payment_id': held, 'pg_clearing_amount': '-1'})) == (
        '94031'
    )
    foreign = await emu.call(
        '/do_capture.php', {'pg_merchant_id': OTHER_ID, 'pg_payment_id': held}, secret=OTHER_SECRET
    )
    assert error_code(foreign) == '340'


# -- refund (revoke) -------------------------------------------------------------


@pytest.mark.parametrize('path', ['/revoke', '/revoke.php'])
async def test_partial_then_remaining_refund(emu: Emu, path: str) -> None:
    payment_id = await paid(emu)
    first = await emu.call(path, {'pg_payment_id': payment_id, 'pg_refund_amount': '500'})
    assert_signed(first, path[1:])
    assert field(first, 'pg_status') == 'ok'
    status = await emu.status(payment_id)
    assert field(status, 'pg_payment_status') == 'success'  # stays success after refunds
    assert field(status, 'pg_refund_amount') == '-500.00'
    rest = await emu.call(path, {'pg_payment_id': payment_id})  # omitted amount: the remainder
    assert field(rest, 'pg_status') == 'ok'
    status = await emu.status(payment_id)
    assert field(status, 'pg_refund_amount') == '-1500.00'
    assert [(r['pg_payment_status'], r['pg_amount']) for r in refund_list(status)] == [
        ('success', '-500.00'),
        ('success', '-1000.00'),
    ]
    assert refund_list(status)[0]['pg_payment_id'] == field(first, 'pg_revoke_payment_id')
    assert_signed(status, 'get_status3.php')
    over = await emu.call(path, {'pg_payment_id': payment_id, 'pg_refund_amount': '0'})
    assert field(over, 'pg_status') == 'error'
    assert field(over, 'pg_failure_code') == '900811'
    assert_signed(over, path[1:])


async def test_refund_over_the_remainder_is_declined_and_listed(emu: Emu) -> None:
    payment_id = await paid(emu)
    reply = await emu.call('/revoke', {'pg_payment_id': payment_id, 'pg_refund_amount': '1500.01'})
    assert field(reply, 'pg_status') == 'error'
    assert field(reply, 'pg_failure_code') == '900811'
    assert field(reply, 'pg_revoke_payment_id')
    entries = refund_list(await emu.status(payment_id))
    assert entries[0]['pg_payment_status'] == 'error'
    assert entries[0]['pg_failure_code'] == '900811'


async def test_refund_idempotency_key(emu: Emu) -> None:
    payment_id = await paid(emu)
    params = {'pg_payment_id': payment_id, 'pg_refund_amount': '100', 'pg_idempotency_key': 'r-1'}
    first = await emu.call('/revoke', params)
    again = await emu.call('/revoke', params)
    assert field(first, 'pg_revoke_payment_id') == field(again, 'pg_revoke_payment_id')
    assert_signed(again, 'revoke')
    assert field(await emu.status(payment_id), 'pg_refund_amount') == '-100.00'


async def test_refund_of_an_uncaptured_two_step_payment_captures_first(emu: Emu) -> None:
    payment_id = await paid(emu, pg_auto_clearing='0')
    reply = await emu.call('/revoke', {'pg_payment_id': payment_id, 'pg_refund_amount': '100'})
    assert field(reply, 'pg_status') == 'ok'
    status = await emu.status(payment_id)
    assert field(status, 'pg_captured') == '1'
    assert field(status, 'pg_clearing_amount') == '1500'


async def test_refund_errors(make_emu) -> None:
    emu = await make_emu()
    assert error_code(await emu.call('/revoke', {})) == '94031'
    assert error_code(await emu.call('/revoke', {'pg_payment_id': '1'})) == '94031'
    payment_id = await paid(emu)
    assert error_code(await emu.call('/revoke', {'pg_payment_id': payment_id, 'pg_refund_amount': '-1'})) == '94031'
    assert error_code(await emu.call('/revoke', {'pg_payment_id': payment_id, 'pg_refund_amount': '1.001'})) == (
        '94031'
    )
    foreign = await emu.call('/revoke', {'pg_merchant_id': OTHER_ID, 'pg_payment_id': payment_id}, secret=OTHER_SECRET)
    assert error_code(foreign) == '340'
    unpaid = field(await emu.init(), 'pg_payment_id')
    assert error_code(await emu.call('/revoke', {'pg_payment_id': unpaid})) == '110691'
    held = await paid(emu, pg_auto_clearing='0')
    await emu.call('/cancel', {'pg_payment_id': held})
    assert error_code(await emu.call('/revoke', {'pg_payment_id': held})) == '9014'
    await emu.advance(181 * 86400)
    assert error_code(await emu.call('/revoke', {'pg_payment_id': payment_id})) == '11054'


async def test_refunds_disabled(make_emu) -> None:
    emu = await make_emu(FPAY_REFUNDS_ENABLED='0')
    payment_id = await paid(emu)
    assert error_code(await emu.call('/revoke', {'pg_payment_id': payment_id})) == '9994'
    assert error_code(await emu.call('/cancel', {'pg_payment_id': payment_id})) == '9994'


async def test_concurrent_refund_is_in_progress(emu: Emu) -> None:
    payment_id = await paid(emu)
    await emu.control('POST', '/faults', json={'endpoint': 'revoke', 'mode': 'latency', 'latency_ms': 300, 'count': 1})
    slow = asyncio.create_task(emu.call('/revoke', {'pg_payment_id': payment_id, 'pg_refund_amount': '1'}))
    await asyncio.sleep(0.05)
    second = await emu.call('/revoke', {'pg_payment_id': payment_id, 'pg_refund_amount': '1'})
    third = await emu.call('/cancel', {'pg_payment_id': payment_id})
    assert error_code(second) == '91021'
    assert error_code(third) == '91021'
    assert field(await slow, 'pg_status') == 'ok'


async def test_concurrent_cancel_is_in_progress(emu: Emu) -> None:
    payment_id = await paid(emu)
    await emu.control('POST', '/faults', json={'endpoint': 'cancel', 'mode': 'latency', 'latency_ms': 300, 'count': 1})
    slow = asyncio.create_task(emu.call('/cancel', {'pg_payment_id': payment_id}))
    await asyncio.sleep(0.05)
    assert error_code(await emu.call('/revoke', {'pg_payment_id': payment_id})) == '91031'
    assert field(await slow, 'pg_status') == 'ok'


# -- cancel ------------------------------------------------------------------------


@pytest.mark.parametrize('path', ['/cancel', '/cancel.php'])
async def test_cancel_releases_a_hold(emu: Emu, path: str) -> None:
    payment_id = await paid(emu, pg_auto_clearing='0')
    reply = await emu.call(path, {'pg_payment_id': payment_id})
    assert_signed(reply, path[1:])
    assert field(reply, 'pg_status') == 'ok'
    status = await emu.status(payment_id)
    assert field(status, 'pg_payment_status') == 'success'
    assert field(status, 'pg_captured') == '0'
    assert field(status, 'pg_revoked_amount') == '-1500.00'
    revoked = [dict(e) for _, e in field(status, 'pg_revoked_payments')]
    assert revoked == [{'pg_payment_id': field(reply, 'pg_cancel_payment_id'), 'pg_payment_status': 'success'}]
    again = await emu.call(path, {'pg_payment_id': payment_id})
    assert (field(again, 'pg_status'), field(again, 'pg_failure_code')) == ('error', '10033')


async def test_cancel_of_a_captured_payment_is_a_full_refund(emu: Emu) -> None:
    payment_id = await paid(emu)
    assert field(await emu.call('/cancel', {'pg_payment_id': payment_id}), 'pg_status') == 'ok'
    over = await emu.call('/revoke', {'pg_payment_id': payment_id})
    assert field(over, 'pg_failure_code') == '900811'


async def test_cancel_failures(emu: Emu) -> None:
    unpaid = field(await emu.init(), 'pg_payment_id')
    reply = await emu.call('/cancel', {'pg_payment_id': unpaid})
    assert (field(reply, 'pg_status'), field(reply, 'pg_failure_code')) == ('error', '90131')
    partly_refunded = await paid(emu)
    await emu.call('/revoke', {'pg_payment_id': partly_refunded, 'pg_refund_amount': '1'})
    assert field(await emu.call('/cancel', {'pg_payment_id': partly_refunded}), 'pg_failure_code') == '900811'
    partly_captured = await paid(emu, pg_auto_clearing='0')
    await emu.call('/do_capture.php', {'pg_payment_id': partly_captured, 'pg_clearing_amount': '10'})
    assert field(await emu.call('/cancel', {'pg_payment_id': partly_captured}), 'pg_failure_code') == '900811'


async def test_cancel_request_errors_and_idempotency(emu: Emu) -> None:
    assert error_code(await emu.call('/cancel', {})) == '94031'
    assert error_code(await emu.call('/cancel', {'pg_payment_id': '5'})) == '340'
    payment_id = await paid(emu)
    first = await emu.call('/cancel', {'pg_payment_id': payment_id, 'pg_idempotency_key': 'c-1'})
    again = await emu.call('/cancel', {'pg_payment_id': payment_id, 'pg_idempotency_key': 'c-1'})
    assert field(first, 'pg_cancel_payment_id') == field(again, 'pg_cancel_payment_id')
    assert field(again, 'pg_status') == 'ok'
    long_key = await emu.call('/cancel', {'pg_payment_id': payment_id, 'pg_idempotency_key': 'k' * 256})
    assert error_code(long_key) == '94031'


async def test_receipt_positions_on_refund_are_validated(emu: Emu) -> None:
    payment_id = await paid(emu)
    reply = await emu.call('/revoke', {'pg_payment_id': payment_id, 'pg_receipt_positions': 'oops'})
    assert error_code(reply) == '94031'


# -- auto capture ----------------------------------------------------------------------


async def test_auto_capture_after_the_period_for_live_payments(make_emu) -> None:
    emu = await make_emu(FPAY_MERCHANT_TEST_MODE='0')
    payment_id = await paid(emu, pg_auto_clearing='0')
    await emu.advance(4 * 86400)
    assert field(await emu.status(payment_id), 'pg_captured') == '0'
    result = await emu.advance(1 * 86400 + 1)
    assert result['tick']['auto_processed'] == 1
    assert field(await emu.status(payment_id), 'pg_captured') == '1'


async def test_auto_cancel_and_test_payments_are_not_auto_processed(make_emu, tmp_path) -> None:
    emu = await make_emu(FPAY_AUTO_CAPTURE_ACTION='cancel')
    test_payment = await paid(emu, pg_auto_clearing='0')
    await emu.advance(6 * 86400)
    assert field(await emu.status(test_payment), 'pg_revoked_amount') is None
    live = await make_emu(
        FPAY_AUTO_CAPTURE_ACTION='cancel', FPAY_MERCHANT_TEST_MODE='0', FPAY_DB_PATH=str(tmp_path / 'live.sqlite3')
    )
    live_payment = await paid(live, pg_auto_clearing='0')
    await live.advance(6 * 86400)
    status = await live.status(live_payment)
    assert field(status, 'pg_revoked_amount') == '-1500.00'
    assert field(status, 'pg_testing_mode') is None
