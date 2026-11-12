"""Merchant API: authentication, request formats, init_payment and get_status3."""

from __future__ import annotations

import json

import pytest

from fpay_emulator import xmlio
from fpay_emulator.signature import Pairs, make_signature

from .conftest import MERCHANT_ID, OTHER_ID, OTHER_SECRET, SECRET, Emu, assert_signed, field


def error_code(reply: Pairs) -> str:
    assert field(reply, 'pg_status') == 'error'
    assert field(reply, 'pg_sig') is None, 'request errors are unsigned'
    return field(reply, 'pg_error_code')


# -- authentication -----------------------------------------------------------


async def test_init_payment_success_is_signed(emu: Emu) -> None:
    response = await emu.raw('/init_payment', {'pg_amount': '100', 'pg_description': 'Ticket'})
    assert response.headers['content-type'] == 'text/xml; charset=utf-8'
    assert response.text.startswith('<?xml version="1.0" encoding="utf-8"?>\n<response>\n    <pg_status>ok')
    reply = xmlio.parse(response.content)
    assert_signed(reply, 'init_payment')
    assert len(field(reply, 'pg_payment_id')) == 13
    assert field(reply, 'pg_redirect_url').startswith('http://fpay.test/pay.html?customer=')
    assert field(reply, 'pg_redirect_url_type') == 'need data'
    assert 'x-request-id' in response.headers


@pytest.mark.parametrize('path', ['/init_payment', '/init_payment.php'])
async def test_script_name_is_the_path_as_called(emu: Emu, path: str) -> None:
    reply = await emu.call(path, {'pg_amount': '100', 'pg_description': 'x'})
    assert_signed(reply, path[1:])
    other = 'init_payment.php' if path == '/init_payment' else 'init_payment'
    wrong = await emu.call(path, {'pg_amount': '100', 'pg_description': 'x'}, script=other)
    assert error_code(wrong) == '9998'


async def test_error_document_is_one_line(emu: Emu) -> None:
    response = await emu.raw('/init_payment', {'pg_amount': '100', 'pg_description': 'x'}, secret='wrong')
    assert response.status_code == 200
    assert response.text == (
        '<?xml version="1.0" encoding="utf-8"?>\n<response><pg_status>error</pg_status>'
        '<pg_error_code>9998</pg_error_code><pg_error_description>Некорректная подпись запроса'
        '</pg_error_description></response>'
    )


@pytest.mark.parametrize('path', ['/init_payment', '/do_capture.php', '/cancel', '/revoke', '/get_status3.php'])
async def test_missing_merchant_id_is_1100(emu: Emu, path: str) -> None:
    response = await emu.client.post(path, data={'pg_salt': 'x'})
    assert error_code(xmlio.parse(response.content)) == '1100'
    empty = await emu.client.post(path)
    assert error_code(xmlio.parse(empty.content)) == '1100'


@pytest.mark.parametrize(
    ('path', 'code'), [('/init_payment', '9998'), ('/revoke', '9998'), ('/get_status3.php', '1100')]
)
async def test_unknown_merchant(emu: Emu, path: str, code: str) -> None:
    reply = await emu.call(path, {'pg_merchant_id': '1', 'pg_payment_id': '1'}, secret='x')
    assert error_code(reply) == code


@pytest.mark.parametrize(
    ('path', 'code'),
    [
        ('/init_payment', '9998'),
        ('/payment.php', None),
        ('/do_capture.php', '9998'),
        ('/cancel.php', '9998'),
        ('/revoke.php', '9998'),
        ('/get_status3.php', '1100'),
        ('/get_status2.php', '1100'),
        ('/get_status.php', '1100'),
    ],
)
async def test_bad_signature_codes(emu: Emu, path: str, code: str | None) -> None:
    params = {'pg_amount': '100', 'pg_description': 'x', 'pg_payment_id': '1'}
    response = await emu.raw(path, params, secret='not-the-secret')
    if code is None:  # payment.php renders errors as HTML
        assert 'Error code 9998' in response.text
        return
    assert error_code(xmlio.parse(response.content)) == code
    unsigned = await emu.raw(path, params, sign=False)
    assert error_code(xmlio.parse(unsigned.content)) == code


async def test_tampered_parameter_breaks_signature(emu: Emu) -> None:
    params = {'pg_merchant_id': MERCHANT_ID, 'pg_amount': '100', 'pg_description': 'x', 'pg_salt': 'abc'}
    params['pg_sig'] = make_signature('init_payment', params, SECRET)
    params['pg_amount'] = '1'
    reply = xmlio.parse((await emu.client.post('/init_payment', data=params)).content)
    assert error_code(reply) == '9998'
    added = {**params, 'pg_amount': '100', 'extra': 'added after signing'}
    reply = xmlio.parse((await emu.client.post('/init_payment', data=added)).content)
    assert error_code(reply) == '9998'


async def test_uppercase_signature_is_refused(emu: Emu) -> None:
    params = {'pg_merchant_id': MERCHANT_ID, 'pg_amount': '100', 'pg_description': 'x', 'pg_salt': 'abc'}
    params['pg_sig'] = make_signature('init_payment', params, SECRET).upper()
    reply = xmlio.parse((await emu.client.post('/init_payment', data=params)).content)
    assert error_code(reply) == '9998'


@pytest.mark.parametrize('salt', ['', 'has space', 'semi;colon'])
async def test_salt_is_required_latin_and_digits(emu: Emu, salt: str) -> None:
    reply = await emu.call('/init_payment', {'pg_amount': '100', 'pg_description': 'x', 'pg_salt': salt})
    assert error_code(reply) == '94031'


async def test_lenient_salt_switch(make_emu) -> None:
    emu = await make_emu(FPAY_SALT_STRICT='0')
    reply = await emu.call('/init_payment', {'pg_amount': '100', 'pg_description': 'x', 'pg_salt': 'a-b_c'})
    assert field(reply, 'pg_status') == 'ok'


# -- request formats ----------------------------------------------------------


async def test_get_query_string(emu: Emu) -> None:
    reply = await emu.call('/init_payment', {'pg_amount': '100', 'pg_description': 'x'}, method='GET')
    assert field(reply, 'pg_status') == 'ok'


async def test_post_ignores_query_parameters(emu: Emu) -> None:
    params = {'pg_merchant_id': MERCHANT_ID, 'pg_amount': '100', 'pg_description': 'x', 'pg_salt': 'abc'}
    sig = make_signature('init_payment', params, SECRET)
    response = await emu.client.post('/init_payment', params={'pg_sig': sig}, data=params)
    assert error_code(xmlio.parse(response.content)) == '9998'


async def test_multipart(emu: Emu) -> None:
    params = {'pg_merchant_id': MERCHANT_ID, 'pg_amount': '100', 'pg_description': 'x', 'pg_salt': 'abc'}
    params['pg_sig'] = make_signature('init_payment', params, SECRET)
    response = await emu.client.post('/init_payment', data=params, files={'ignored': ('a.txt', b'file')})
    assert response.headers['content-type'].startswith('text/xml')
    assert field(xmlio.parse(response.content), 'pg_status') == 'ok'


async def test_nested_form_receipt(emu: Emu) -> None:
    params = {
        'pg_merchant_id': MERCHANT_ID,
        'pg_amount': '900',
        'pg_description': 'Ticket',
        'pg_salt': 'a1b2c3d4',
        'pg_receipt_positions[0][count]': '1',
        'pg_receipt_positions[0][name]': 'Ticket A',
        'pg_receipt_positions[0][tax_type]': '0',
        'pg_receipt_positions[0][price]': '900',
    }
    nested = {
        **{k: v for k, v in params.items() if '[' not in k},
        'pg_receipt_positions': [{'count': '1', 'name': 'Ticket A', 'tax_type': '0', 'price': '900'}],
    }
    params['pg_sig'] = make_signature('init_payment', nested, SECRET)
    response = await emu.client.post('/init_payment', data=params)
    reply = xmlio.parse(response.content)
    assert field(reply, 'pg_status') == 'ok'
    payment = emu.gw.store.get_payment(int(field(reply, 'pg_payment_id')))
    assert payment.receipt_positions == [{'count': '1', 'name': 'Ticket A', 'tax_type': '0', 'price': '900'}]


@pytest.mark.parametrize(
    ('position', 'problem'),
    [
        ({'name': 'A', 'price': '1'}, 'count'),
        ({'count': '1', 'name': 'A', 'price': 'x'}, 'price'),
        ({'count': 'one', 'name': 'A', 'price': '1'}, 'count'),
        ({'count': '1', 'name': 'A', 'price': '1', 'tax_type': '2'}, 'tax_type'),
    ],
)
async def test_invalid_receipt_positions(emu: Emu, position: dict[str, str], problem: str) -> None:
    params = {'pg_amount': '1', 'pg_description': 'x'}
    params.update({f'pg_receipt_positions[0][{k}]': v for k, v in position.items()})
    response = await emu.client.post(
        '/init_payment',
        data={
            **{k: v for k, v in params.items() if '[' in k},
            **_signed_nested(params, position),
        },
    )
    reply = xmlio.parse(response.content)
    assert error_code(reply) == '94031'
    assert problem in field(reply, 'pg_error_description')


def _signed_nested(params: dict[str, str], position: dict[str, str]) -> dict[str, str]:
    base = {k: v for k, v in params.items() if '[' not in k}
    base.update({'pg_merchant_id': MERCHANT_ID, 'pg_salt': 'abc'})
    tree = {**base, 'pg_receipt_positions': [position]}
    return {**base, 'pg_sig': make_signature('init_payment', tree, SECRET)}


async def test_json_with_string_values(emu: Emu) -> None:
    body = {'pg_merchant_id': MERCHANT_ID, 'pg_amount': '100.50', 'pg_description': 'x', 'pg_salt': 'abc'}
    body['pg_sig'] = make_signature('init_payment', body, SECRET)
    response = await emu.client.post(
        '/init_payment', content=json.dumps(body), headers={'content-type': 'application/json'}
    )
    assert field(xmlio.parse(response.content), 'pg_status') == 'ok'


async def test_json_number_is_normalised_before_the_check(emu: Emu) -> None:
    """S1: ``100.50`` as a JSON number is signed by the gateway as ``100.5``."""
    signed_as_sent = {'pg_merchant_id': MERCHANT_ID, 'pg_amount': '100.50', 'pg_description': 'x', 'pg_salt': 'abc'}
    sig = make_signature('init_payment', signed_as_sent, SECRET)
    raw = '{"pg_merchant_id": "12345", "pg_amount": 100.50, "pg_description": "x", "pg_salt": "abc", "pg_sig": "%s"}'
    response = await emu.client.post('/init_payment', content=raw % sig, headers={'content-type': 'application/json'})
    assert error_code(xmlio.parse(response.content)) == '9998'


async def test_json_nested_receipt_and_scalars(emu: Emu) -> None:
    body = {
        'pg_merchant_id': MERCHANT_ID,
        'pg_amount': '900',
        'pg_description': 'Ticket',
        'pg_salt': 'a1b2c3d4',
        'pg_receipt_positions': [{'count': '1', 'name': 'Ticket A', 'tax_type': '0', 'price': '900'}],
        'pg_testing_mode': None,
        'flag': True,
    }
    body['pg_sig'] = make_signature('init_payment', {**body, 'pg_testing_mode': '', 'flag': '1'}, SECRET)
    headers = {'content-type': 'application/json'}
    response = await emu.client.post('/init_payment', content=json.dumps(body), headers=headers)
    reply = xmlio.parse(response.content)
    assert field(reply, 'pg_status') == 'ok', response.text
    payment = emu.gw.store.get_payment(int(field(reply, 'pg_payment_id')))
    assert payment.receipt_positions[0]['name'] == 'Ticket A'


@pytest.mark.parametrize('body', ['{not json', '[1, 2]'])
async def test_json_malformed(emu: Emu, body: str) -> None:
    response = await emu.client.post('/init_payment', content=body, headers={'content-type': 'application/json'})
    assert error_code(xmlio.parse(response.content)) == '94031'


async def test_pg_xml_request(emu: Emu) -> None:
    fields = Pairs(
        [('pg_merchant_id', MERCHANT_ID), ('pg_amount', '100'), ('pg_description', 'Ticket & more'), ('pg_salt', 'abc')]
    )
    fields.append(('pg_sig', make_signature('init_payment.php', fields, SECRET)))
    document = xmlio.render('request', fields).decode()
    response = await emu.client.post('/init_payment.php', data={'pg_xml': document})
    reply = xmlio.parse(response.content)
    assert field(reply, 'pg_status') == 'ok'
    assert_signed(reply, 'init_payment.php')


async def test_pg_xml_malformed(emu: Emu) -> None:
    response = await emu.client.post('/init_payment', data={'pg_xml': '<request><pg_amount>'})
    assert error_code(xmlio.parse(response.content)) == '94031'
    wrong_root = await emu.client.post('/init_payment', data={'pg_xml': '<response><a>1</a></response>'})
    assert error_code(xmlio.parse(wrong_root.content)) == '94031'


async def test_unknown_content_type_is_an_empty_request(emu: Emu) -> None:
    response = await emu.client.post(
        '/init_payment', content=b'pg_merchant_id=1', headers={'content-type': 'text/plain'}
    )
    assert error_code(xmlio.parse(response.content)) == '1100'


# -- init_payment validation ---------------------------------------------------


@pytest.mark.parametrize(
    'params',
    [
        {'pg_description': 'x'},
        {'pg_amount': '0', 'pg_description': 'x'},
        {'pg_amount': '100,50', 'pg_description': 'x'},
        {'pg_amount': '1.234', 'pg_description': 'x'},
        {'pg_amount': '100000000', 'pg_description': 'x'},
        {'pg_amount': '-5', 'pg_description': 'x'},
        {'pg_amount': '1'},
        {'pg_amount': '1', 'pg_description': 'x' * 1025},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_order_id': 'o' * 51},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_currency': 'XXX'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_currency': 'kzt'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_result_url': 'ftp://shop/result'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_success_url': 'https://s/' + 'a' * 300},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_request_method': 'PUT'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_success_url_method': 'REDIRECT'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_lifetime': 'soon'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_language': 'de'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_user_id': 'a b'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_user_phone': '+7 777'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_user_contact_email': 'nope'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_user_ip': '999.1.1.1'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_testing_mode': 'yes'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_auto_clearing': '2'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_timeout_after_payment': '-1'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_payment_method': 'crypto'},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_idempotency_key': 'k' * 256},
        {'pg_amount': '1', 'pg_description': 'x', 'pg_receipt_positions': 'flat'},
    ],
)
async def test_init_payment_invalid_parameters(emu: Emu, params: dict[str, str]) -> None:
    assert error_code(await emu.call('/init_payment', params)) == '94031'


async def test_init_payment_stores_all_documented_parameters(emu: Emu) -> None:
    reply = await emu.init(
        pg_currency='USD',
        pg_check_url='https://shop.example/check',
        pg_result_url='https://shop.example/result',
        pg_request_method='xml',
        pg_success_url='https://shop.example/ok',
        pg_success_url_method='AUTOPOST',
        pg_failure_url='https://shop.example/fail',
        pg_failure_url_method='AUTOGET',
        pg_language='en',
        pg_user_id='user_1',
        pg_user_phone='77777777777',
        pg_user_contact_email='buyer@example.com',
        pg_user_ip='10.0.0.1',
        pg_testing_mode='1',
        pg_auto_clearing='0',
        pg_timeout_after_payment='3',
        pg_payment_method='bankcard',
        pg_param1='p1',
        booking='B-7',
    )
    payment = emu.gw.store.get_payment(int(field(reply, 'pg_payment_id')))
    assert payment.currency == 'USD'
    assert payment.request_method == 'XML'
    assert payment.success_url_method == 'AUTOPOST'
    assert not payment.auto_clearing
    assert payment.timeout_after_payment == 3
    assert payment.custom_params == [['booking', 'B-7']]
    assert payment.pg_params == {'pg_param1': 'p1'}
    assert payment.user_email == 'buyer@example.com'


@pytest.mark.parametrize(('given', 'expected'), [('1', 300), ('60', 300), ('3600', 3600), ('9999999', 604800)])
async def test_lifetime_is_clamped(emu: Emu, given: str, expected: int) -> None:
    reply = await emu.init(pg_lifetime=given)
    assert emu.gw.store.get_payment(int(field(reply, 'pg_payment_id'))).lifetime == expected


async def test_lifetime_minimum_is_configurable(make_emu) -> None:
    emu = await make_emu(FPAY_LIFETIME_MIN_SECONDS='60')
    reply = await emu.init(pg_lifetime='60')
    assert emu.gw.store.get_payment(int(field(reply, 'pg_payment_id'))).lifetime == 60


async def test_qr_code(emu: Emu) -> None:
    import base64

    reply = await emu.init(pg_generate_qr='1')
    png = base64.b64decode(field(reply, 'pg_redirect_qr'))
    assert png.startswith(b'\x89PNG')
    assert_signed(reply, 'init_payment')


async def test_idempotency_key_returns_the_same_payment(emu: Emu) -> None:
    first = await emu.init(pg_idempotency_key='idem-1')
    again = await emu.init(pg_idempotency_key='idem-1', pg_amount='999')
    assert field(first, 'pg_payment_id') == field(again, 'pg_payment_id')
    assert field(first, 'pg_redirect_url') == field(again, 'pg_redirect_url')
    assert field(first, 'pg_salt') != field(again, 'pg_salt')
    other = await emu.init(pg_idempotency_key='idem-2')
    assert field(other, 'pg_payment_id') != field(first, 'pg_payment_id')


async def test_order_id_not_unique_by_default(emu: Emu) -> None:
    first = await emu.init(pg_order_id='same')
    second = await emu.init(pg_order_id='same')
    assert field(first, 'pg_payment_id') != field(second, 'pg_payment_id')
    latest = await emu.call('/get_status3.php', {'pg_order_id': 'same'})
    assert field(latest, 'pg_payment_id') == field(second, 'pg_payment_id')


async def test_order_id_uniqueness_modes(make_emu) -> None:
    existing = await make_emu(FPAY_ORDER_ID_UNIQUENESS='return_existing')
    first = await existing.init(pg_order_id='u1')
    assert field(await existing.init(pg_order_id='u1'), 'pg_payment_id') == field(first, 'pg_payment_id')
    strict = await make_emu(FPAY_ORDER_ID_UNIQUENESS='reject', FPAY_DB_PATH=str(existing.settings.db_path) + '2')
    await strict.init(pg_order_id='u2')
    assert (
        error_code(await strict.call('/init_payment', {'pg_amount': '1', 'pg_description': 'x', 'pg_order_id': 'u2'}))
        == '9908'
    )


async def test_merchant_defaults_and_explicit_empty_url(make_emu) -> None:
    emu = await make_emu(**{f'FPAY_MERCHANT_{MERCHANT_ID}_RESULT_URL': 'https://shop.example/default-result'})
    defaulted = await emu.init()
    payment = emu.gw.store.get_payment(int(field(defaulted, 'pg_payment_id')))
    assert payment.result_url == 'https://shop.example/default-result'
    emptied = await emu.init(pg_result_url='')
    assert emu.gw.store.get_payment(int(field(emptied, 'pg_payment_id'))).result_url is None


async def test_payment_php_redirects_the_browser(emu: Emu) -> None:
    response = await emu.raw('/payment.php', {'pg_amount': '10', 'pg_description': 'x'})
    assert response.status_code == 302
    assert response.headers['location'].startswith('http://fpay.test/pay.html?customer=')
    invalid = await emu.raw('/payment.php', {'pg_description': 'x'})
    assert invalid.status_code == 200
    assert 'text/html' in invalid.headers['content-type']
    assert 'Error code 94031' in invalid.text


# -- get_status3.php ------------------------------------------------------------


async def test_status_of_a_new_payment(emu: Emu) -> None:
    payment_id = field(await emu.init(), 'pg_payment_id')
    response = await emu.raw('/get_status3.php', {'pg_payment_id': payment_id})
    assert response.headers['content-type'] == 'text/xml'
    reply = xmlio.parse(response.content)
    assert_signed(reply, 'get_status3.php')
    assert field(reply, 'pg_payment_status') == 'new'
    assert field(reply, 'pg_payment_method') == 'none'
    assert field(reply, 'pg_captured') == '0'
    assert field(reply, 'pg_clearing_amount') == '0'
    assert field(reply, 'pg_testing_mode') == '1'
    assert field(reply, 'pg_amount') == '1500'
    assert field(reply, 'pg_create_date').endswith('Z')


async def test_status_element_order_is_not_alphabetical(emu: Emu) -> None:
    payment_id = field(await emu.init(), 'pg_payment_id')
    names = [k for k, _ in await emu.status(payment_id)]
    assert names != sorted(names)
    assert names.index('pg_salt') < names.index('pg_payment_status')
    assert names.index('pg_sig') < names.index('pg_payment_status')


@pytest.mark.parametrize('path', ['/get_status2.php', '/get_status.php'])
async def test_legacy_status_aliases(emu: Emu, path: str) -> None:
    payment_id = field(await emu.init(), 'pg_payment_id')
    reply = await emu.call(path, {'pg_payment_id': payment_id})
    assert_signed(reply, path[1:])


async def test_legacy_status_aliases_can_be_disabled(make_emu) -> None:
    emu = await make_emu(FPAY_LEGACY_STATUS_ENDPOINTS='0')
    response = await emu.raw('/get_status2.php', {'pg_payment_id': '1'})
    assert response.status_code == 404


async def test_status_errors(emu: Emu) -> None:
    assert error_code(await emu.call('/get_status3.php', {})) == '1200'
    assert error_code(await emu.call('/get_status3.php', {'pg_payment_id': '1'})) == '11068'
    assert error_code(await emu.call('/get_status3.php', {'pg_payment_id': 'abc'})) == '11068'
    assert error_code(await emu.call('/get_status3.php', {'pg_order_id': 'nope'})) == '11068'
    payment_id = field(await emu.init(), 'pg_payment_id')
    foreign = await emu.call(
        '/get_status3.php', {'pg_merchant_id': OTHER_ID, 'pg_payment_id': payment_id}, secret=OTHER_SECRET
    )
    assert error_code(foreign) == '11068'


async def test_payment_id_takes_precedence_over_order_id(emu: Emu) -> None:
    first = field(await emu.init(pg_order_id='a'), 'pg_payment_id')
    await emu.init(pg_order_id='b')
    reply = await emu.status(first, pg_order_id='b')
    assert field(reply, 'pg_payment_id') == first


async def test_status_json_payment_id_must_be_a_number(emu: Emu) -> None:
    payment_id = field(await emu.init(), 'pg_payment_id')
    as_string = {'pg_merchant_id': MERCHANT_ID, 'pg_payment_id': payment_id, 'pg_salt': 'abc'}
    as_string['pg_sig'] = make_signature('get_status3.php', as_string, SECRET)
    headers = {'content-type': 'application/json'}
    response = await emu.client.post('/get_status3.php', content=json.dumps(as_string), headers=headers)
    assert error_code(xmlio.parse(response.content)) == '9999'
    as_number = {**as_string, 'pg_payment_id': int(payment_id)}
    response = await emu.client.post('/get_status3.php', content=json.dumps(as_number), headers=headers)
    reply = xmlio.parse(response.content)
    assert field(reply, 'pg_payment_id') == payment_id
    assert_signed(reply, 'get_status3.php')


async def test_healthcheck_and_index(emu: Emu) -> None:
    response = await emu.client.get('/status/healthcheck')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'
    assert 'time' in response.json()
    assert (await emu.client.get('/')).json()['service'] == 'Freedom Pay gateway emulator'
