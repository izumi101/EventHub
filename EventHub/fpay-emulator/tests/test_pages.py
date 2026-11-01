"""Hosted payment page, 3-D Secure and the success/failure redirects."""

from __future__ import annotations

import html
import re
from urllib.parse import parse_qsl, urlsplit

import pytest

from fpay_emulator.signature import Pairs, script_name, verify_signature

from .conftest import BASE_URL, SECRET, Emu, field

CARD = {'exp_month': '12', 'exp_year': '30', 'cvv': '123', 'owner': 'Test Cardholder'}


async def open_page(emu: Emu, **init: str) -> tuple[str, str]:
    reply = await emu.init(**init)
    url = field(reply, 'pg_redirect_url')
    customer = url.split('customer=')[1]
    response = await emu.client.get(url.removeprefix(BASE_URL))
    assert response.status_code == 200
    return field(reply, 'pg_payment_id'), customer


async def pay_card(emu: Emu, customer: str, pan: str, **overrides: str) -> str:
    data = {**CARD, 'pan': pan, **overrides}
    response = await emu.client.post(f'/pay/{customer}/card', data=data)
    assert response.status_code == 303, response.text
    return response.headers['location']


def links(page: str) -> list[str]:
    return [html.unescape(h) for h in re.findall(r'href="([^"]+)"', page)]


async def test_page_shows_order_and_marks_waiting(emu: Emu) -> None:
    payment_id, customer = await open_page(emu, pg_description='Concert in Almaty')
    page = (await emu.client.get(f'/pay.html?customer={customer}')).text
    assert 'Concert in Almaty' in page
    assert '1500.00 KZT' in page
    assert 'Test payment' in page
    assert '<html lang="en">' in page
    assert field(await emu.status(payment_id), 'pg_payment_status') == 'waiting'
    response = await emu.client.get(f'/pay.html?customer={customer}')
    assert "default-src 'self'" in response.headers['content-security-policy']


@pytest.mark.parametrize('customer', ['nope', '00000000-0000-0000-0000-000000000000'])
async def test_unknown_customer(emu: Emu, customer: str) -> None:
    assert (await emu.client.get(f'/pay.html?customer={customer}')).status_code == 404
    assert (await emu.client.post(f'/pay/{customer}/card', data=CARD)).status_code == 404
    assert (await emu.client.get(f'/pay/{customer}/result')).status_code == 404
    assert (await emu.client.get(f'/pay/{customer}/3ds')).status_code == 404
    assert (await emu.client.get(f'/pay/{customer}/processing')).status_code == 404
    assert (await emu.client.post(f'/pay/{customer}/scenario', data={'scenario': 'success'})).status_code == 404


async def test_card_success(emu: Emu) -> None:
    payment_id, customer = await open_page(emu)
    location = await pay_card(emu, customer, '4716 0472 6194 1981')
    assert location == f'/pay/{customer}/result'
    page = (await emu.client.get(location)).text
    assert 'Payment successful' in page
    status = await emu.status(payment_id)
    assert field(status, 'pg_payment_status') == 'success'
    assert field(status, 'pg_card_pan') == '4716-04XX-XXXX-1981'
    assert field(status, 'pg_card_name') == 'TEST CARDHOLDER'
    # A final payment's page leads to the result.
    again = await emu.client.get(f'/pay.html?customer={customer}')
    assert again.status_code == 303


@pytest.mark.parametrize(
    ('pan', 'code'),
    [
        ('5335215945367703', '99999'),
        ('4916109830832246', '100066'),
        ('5548398681700148', '10009'),
        ('5475102935853613', '11036'),
        ('5555555555555557', '11024'),
        ('4444444444444422', '10001'),
        ('4444444411111111', '10022'),
        ('4444444499999999', '10018'),
        ('5484458131482832', '10004'),
        ('4242424242424242', '10005'),  # valid but not a test card: refused in test mode
    ],
)
async def test_decline_cards(emu: Emu, pan: str, code: str) -> None:
    payment_id, customer = await open_page(emu)
    await pay_card(emu, customer, pan)
    status = await emu.status(payment_id)
    assert (field(status, 'pg_payment_status'), field(status, 'pg_failure_code')) == ('error', code)
    page = (await emu.client.get(f'/pay/{customer}/result')).text
    assert 'Payment failed' in page
    assert f'code {code}' in page


@pytest.mark.parametrize('pan', ['6224466455690681278', '623275279933273424', '62528733472390953', '4111111111111111'])
async def test_other_success_cards(emu: Emu, pan: str) -> None:
    payment_id, customer = await open_page(emu)
    await pay_card(emu, customer, pan)
    assert field(await emu.status(payment_id), 'pg_payment_status') == 'success'


async def test_any_card_works_outside_test_mode(make_emu) -> None:
    emu = await make_emu(FPAY_MERCHANT_TEST_MODE='0')
    payment_id, customer = await open_page(emu)
    await pay_card(emu, customer, '4242424242424242')
    status = await emu.status(payment_id)
    assert field(status, 'pg_payment_status') == 'success'
    assert field(status, 'pg_testing_mode') is None


async def test_expired_card_is_declined(emu: Emu) -> None:
    payment_id, customer = await open_page(emu)
    await pay_card(emu, customer, '4716047261941981', exp_year='20')
    assert field(await emu.status(payment_id), 'pg_failure_code') == '10017'


@pytest.mark.parametrize(
    ('overrides', 'problem'),
    [
        ({'pan': '1234'}, 'pan-error'),
        ({'pan': '4716047261941982'}, 'pan-error'),  # Luhn
        ({'exp_month': '13'}, 'exp_month-error'),
        ({'exp_year': '2030'}, 'exp_year-error'),
        ({'cvv': '12'}, 'cvv-error'),
        ({'owner': 'Madonna'}, 'owner-error'),
    ],
)
async def test_form_validation(emu: Emu, overrides: dict[str, str], problem: str) -> None:
    payment_id, customer = await open_page(emu)
    data = {**CARD, 'pan': '4716047261941981', **overrides}
    response = await emu.client.post(f'/pay/{customer}/card', data=data)
    assert response.status_code == 422
    assert f'id="{problem}"' in response.text
    assert 'aria-invalid="true"' in response.text
    assert '4716047261941981' not in response.text.split('Test cards')[0]  # the PAN is never echoed back
    assert field(await emu.status(payment_id), 'pg_payment_status') == 'waiting'


async def test_three_ds_success_and_failure(emu: Emu) -> None:
    payment_id, customer = await open_page(emu)
    location = await pay_card(emu, customer, '4916307416334310')
    assert location == f'/pay/{customer}/3ds'
    assert field(await emu.status(payment_id), 'pg_payment_status') == 'process'
    page = await emu.client.get(location)
    assert 'Test password: 12345678' in page.text
    assert (await emu.client.get(f'/pay.html?customer={customer}')).headers['location'] == location
    response = await emu.client.post(location, data={'password': '12345678', 'action': 'confirm'})
    assert response.headers['location'] == f'/pay/{customer}/result'
    assert field(await emu.status(payment_id), 'pg_payment_status') == 'success'

    failed_id, failed_customer = await open_page(emu, pg_order_id='ORD-2')
    await pay_card(emu, failed_customer, '4916307416334310')
    await emu.client.post(f'/pay/{failed_customer}/3ds', data={'password': 'wrong', 'action': 'confirm'})
    assert field(await emu.status(failed_id), 'pg_failure_code') == '10004'

    cancelled_id, cancelled_customer = await open_page(emu, pg_order_id='ORD-3')
    await pay_card(emu, cancelled_customer, '4916307416334310')
    await emu.client.post(f'/pay/{cancelled_customer}/3ds', data={'action': 'cancel'})
    assert field(await emu.status(cancelled_id), 'pg_failure_code') == '10004'
    # After the payment is final the challenge page leads to the result.
    assert (await emu.client.get(f'/pay/{cancelled_customer}/3ds')).headers['location'].endswith('/result')


async def test_three_ds_page_without_challenge(emu: Emu) -> None:
    _, customer = await open_page(emu)
    response = await emu.client.get(f'/pay/{customer}/3ds')
    assert response.headers['location'] == f'/pay.html?customer={customer}'


@pytest.mark.parametrize(
    ('scenario', 'location', 'status'),
    [
        ('success', 'result', 'success'),
        ('decline', 'result', 'error'),
        ('3ds', '3ds', 'process'),
        ('hang', 'processing', 'process'),
    ],
)
async def test_scenario_buttons(emu: Emu, scenario: str, location: str, status: str) -> None:
    payment_id, customer = await open_page(emu)
    response = await emu.client.post(f'/pay/{customer}/scenario', data={'scenario': scenario})
    assert response.headers['location'] == f'/pay/{customer}/{location}'
    assert field(await emu.status(payment_id), 'pg_payment_status') == status


async def test_abandon_and_unknown_scenario(emu: Emu) -> None:
    payment_id, customer = await open_page(emu)
    response = await emu.client.post(f'/pay/{customer}/scenario', data={'scenario': 'abandon'})
    assert 'You left the payment page' in response.text
    assert field(await emu.status(payment_id), 'pg_payment_status') == 'waiting'
    unknown = await emu.client.post(f'/pay/{customer}/scenario', data={'scenario': 'teleport'})
    assert unknown.headers['location'] == f'/pay.html?customer={customer}'


async def test_hang_then_lifetime_makes_the_payment_unpayable(emu: Emu) -> None:
    payment_id, customer = await open_page(emu, pg_lifetime='600')
    await emu.client.post(f'/pay/{customer}/scenario', data={'scenario': 'hang'})
    processing = await emu.client.get(f'/pay/{customer}/processing')
    assert 'Processing your payment' in processing.text
    assert '<meta http-equiv="refresh" content="5">' in processing.text
    assert (await emu.client.get(f'/pay/{customer}/result')).headers['location'] == f'/pay/{customer}/processing'
    await emu.advance(601)
    assert field(await emu.status(payment_id), 'pg_failure_code') == '10018'
    assert (await emu.client.get(f'/pay/{customer}/processing')).headers['location'] == f'/pay/{customer}/result'
    assert 'Payment expired' in (await emu.client.get(f'/pay/{customer}/result')).text
    late = await emu.client.post(f'/pay/{customer}/card', data={**CARD, 'pan': '4716047261941981'})
    assert late.headers['location'] == f'/pay/{customer}/result'


async def test_page_expires_lazily_without_a_tick(emu: Emu) -> None:
    _, customer = await open_page(emu, pg_lifetime='300')
    emu.gw.clock.advance(301)
    response = await emu.client.get(f'/pay.html?customer={customer}')
    assert response.headers['location'] == f'/pay/{customer}/result'


async def test_unpaid_result_page_goes_back_to_the_form(emu: Emu) -> None:
    _, customer = await open_page(emu)
    response = await emu.client.get(f'/pay/{customer}/result')
    assert response.headers['location'] == f'/pay.html?customer={customer}'


async def test_preset_scenario_overrides_the_card(emu: Emu) -> None:
    payment_id, customer = await open_page(emu)
    await emu.control('POST', f'/payments/{payment_id}/scenario', json={'scenario': 'decline', 'failure_code': '10001'})
    assert 'pre-set' in (await emu.client.get(f'/pay.html?customer={customer}')).text
    await pay_card(emu, customer, '4716047261941981')
    assert field(await emu.status(payment_id), 'pg_failure_code') == '10001'


# -- redirects back to the shop -----------------------------------------------------------


async def test_success_redirect_get_is_signed(emu: Emu) -> None:
    success = 'https://shop.example/payments/freedompay/success?lang=en'
    payment_id, customer = await open_page(emu, pg_success_url=success, booking='B-1')
    await pay_card(emu, customer, '4716047261941981')
    page = (await emu.client.get(f'/pay/{customer}/result')).text
    [back] = [link for link in links(page) if link.startswith('https://shop.example')]
    query = Pairs(parse_qsl(urlsplit(back).query, keep_blank_values=True))
    names = [k for k, _ in query]
    assert names == ['lang', 'pg_order_id', 'pg_payment_id', 'booking', 'pg_salt', 'pg_sig']
    assert dict(query)['pg_payment_id'] == payment_id
    assert verify_signature(script_name(back), query, SECRET, dict(query)['pg_sig'])


async def test_success_redirect_post_form_is_signed(emu: Emu) -> None:
    success = 'https://shop.example/ok'
    _, customer = await open_page(emu, pg_success_url=success, pg_success_url_method='POST')
    await pay_card(emu, customer, '4716047261941981')
    page = (await emu.client.get(f'/pay/{customer}/result')).text
    assert f'action="{success}"' in page
    fields = Pairs((k, html.unescape(v)) for k, v in re.findall(r'name="([^"]+)" value="([^"]*)"', page))
    assert verify_signature('ok', fields, SECRET, dict(fields)['pg_sig'])
    assert 'data-autosubmit' not in page


async def test_autopost_and_autoget(emu: Emu) -> None:
    _, customer = await open_page(
        emu, pg_success_url='https://shop.example/ok', pg_success_url_method='AUTOPOST', pg_timeout_after_payment='4'
    )
    await pay_card(emu, customer, '4716047261941981')
    page = (await emu.client.get(f'/pay/{customer}/result')).text
    assert 'data-autosubmit="4"' in page
    assert '/static/autosubmit.js' in page

    _, delayed = await open_page(
        emu, pg_order_id='O2', pg_success_url='https://shop.example/ok', pg_success_url_method='AUTOGET'
    )
    await pay_card(emu, delayed, '4716047261941981')
    assert (
        '<meta http-equiv="refresh" content="10;url=https://shop.example/ok?'
        in (await emu.client.get(f'/pay/{delayed}/result')).text
    )

    _, instant = await open_page(
        emu,
        pg_order_id='O3',
        pg_success_url='https://shop.example/ok',
        pg_success_url_method='AUTOGET',
        pg_timeout_after_payment='0',
    )
    await pay_card(emu, instant, '4716047261941981')
    response = await emu.client.get(f'/pay/{instant}/result')
    assert response.status_code == 302
    assert response.headers['location'].startswith('https://shop.example/ok?pg_order_id=O3')


async def test_failure_redirect_is_unsigned(emu: Emu) -> None:
    payment_id, customer = await open_page(emu, pg_failure_url='https://shop.example/fail', booking='B-2')
    await pay_card(emu, customer, '5548398681700148')
    page = (await emu.client.get(f'/pay/{customer}/result')).text
    [back] = [link for link in links(page) if link.startswith('https://shop.example')]
    query = dict(parse_qsl(urlsplit(back).query))
    assert query['pg_failure_code'] == '10009'
    assert query['pg_payment_id'] == payment_id
    assert query['booking'] == 'B-2'
    assert 'pg_sig' not in query and 'pg_salt' not in query


async def test_merchant_rejection_sends_the_buyer_to_the_failure_url(emu: Emu) -> None:
    emu.merchant.plan('/r/result', 'rejected')
    _, customer = await open_page(
        emu,
        pg_result_url=emu.merchant.url('/r/result'),
        pg_success_url='https://shop.example/ok',
        pg_failure_url='https://shop.example/fail',
        pg_failure_url_method='POST',
    )
    await pay_card(emu, customer, '4716047261941981')
    page = (await emu.client.get(f'/pay/{customer}/result')).text
    assert 'Payment failed' in page
    assert 'action="https://shop.example/fail"' in page
    assert 'value="99999"' in page
    assert 'reply rejected' in page


async def test_result_page_without_return_urls(emu: Emu) -> None:
    _, customer = await open_page(emu)
    await pay_card(emu, customer, '4716047261941981')
    assert 'You can close this window' in (await emu.client.get(f'/pay/{customer}/result')).text


async def test_static_assets(emu: Emu) -> None:
    css = await emu.client.get('/static/style.css')
    assert css.status_code == 200
    assert 'prefers-color-scheme: dark' in css.text
