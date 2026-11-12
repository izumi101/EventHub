"""Signature vectors from the spec (sections 2.2 and 2.3) and edge cases."""

from __future__ import annotations

import hashlib

import pytest

from fpay_emulator import xmlio
from fpay_emulator.protocol import sign_fields, signed_for_url
from fpay_emulator.signature import (
    Pairs,
    find_sig,
    flatten,
    is_well_formed,
    make_signature,
    script_name,
    signature_base,
    verify_signature,
)

DOC_SECRET = 'test_secret_key'

# Section 2.2: published examples (S1, S2, S7, S8, S10, S9), reproduced.
PUBLISHED = [
    (
        'init_payment.php',
        {
            'pg_order_id': 'order_1001',
            'pg_merchant_id': '12345',
            'pg_amount': '100',
            'pg_currency': 'KZT',
            'pg_description': 'Order #1001',
            'pg_salt': 'a1b2c3d4',
        },
        'init_payment.php;100;KZT;Order #1001;12345;order_1001;a1b2c3d4;test_secret_key',
        'b9ad75871668ca040f80f5f6b530e6ed',
    ),
    (
        'init_payment',
        {'pg_merchant_id': '12345', 'pg_amount': '100', 'pg_description': 'Order #1001', 'pg_salt': 'a1b2c3d4'},
        'init_payment;100;Order #1001;12345;a1b2c3d4;test_secret_key',
        'ffda750b3bbc6a3475ac5ac8a246f739',
    ),
    (
        'get_status3.php',
        {'pg_merchant_id': '12345', 'pg_payment_id': '1022123803890', 'pg_salt': 'a1b2c3d4'},
        'get_status3.php;12345;1022123803890;a1b2c3d4;test_secret_key',
        '2586378f4f7d4ddd950fd1532eaf4fdd',
    ),
    (
        'revoke',
        {'pg_merchant_id': '12345', 'pg_payment_id': '1023122203651', 'pg_salt': 'a1b2c3d4'},
        'revoke;12345;1023122203651;a1b2c3d4;test_secret_key',
        'c9b6030e425d4d5a4d81cdb0ac09a4e5',
    ),
    (
        'cancel',
        {'pg_merchant_id': '12345', 'pg_payment_id': '1023122203626', 'pg_salt': 'a1b2c3d4'},
        'cancel;12345;1023122203626;a1b2c3d4;test_secret_key',
        'e91d9a1ffcd55f0aeb3dc149651410ea',
    ),
    (
        'do_capture.php',
        {'pg_merchant_id': '12345', 'pg_payment_id': '1023122203594', 'pg_salt': 'a1b2c3d4'},
        'do_capture.php;12345;1023122203594;a1b2c3d4;test_secret_key',
        '6904b1ae1e4017a4e1ba88732d8db7c8',
    ),
]


@pytest.mark.parametrize(('script', 'params', 'base', 'expected'), PUBLISHED, ids=[p[0] for p in PUBLISHED])
def test_published_vectors(script: str, params: dict[str, str], base: str, expected: str) -> None:
    assert signature_base(script, params, DOC_SECRET) == base
    assert make_signature(script, params, DOC_SECRET) == expected
    assert verify_signature(script, {**params, 'pg_sig': expected}, DOC_SECRET, expected)


def test_script_name_matters() -> None:
    """The same parameters signed for ``init_payment.php`` give the documented variant hash."""
    params = PUBLISHED[1][1]
    assert make_signature('init_payment.php', params, DOC_SECRET) == '4b979c3439ac142b79dd8617dfb09d5c'
    assert not verify_signature('init_payment.php', params, DOC_SECRET, PUBLISHED[1][3])


def test_callback_vector_and_reply() -> None:
    """Section 2.3: a Result callback to ``.../result`` and the merchant's reply."""
    params = {
        'pg_order_id': 'ORD-42',
        'pg_payment_id': '1022123803890',
        'pg_amount': '1500.00',
        'pg_currency': 'KZT',
        'pg_result': '1',
        'pg_can_reject': '1',
        'pg_testing_mode': '1',
        'pg_payment_date': '2026-10-31 12:00:00',
        'pg_salt': 'q1w2e3r4',
    }
    script = script_name('https://shop.example/payments/freedompay/result')
    assert script == 'result'
    assert (
        signature_base(script, params, 'demo_secret')
        == 'result;1500.00;1;KZT;ORD-42;2026-10-31 12:00:00;1022123803890;1;q1w2e3r4;1;demo_secret'
    )
    assert make_signature(script, params, 'demo_secret') == '1e007dc444f186ca0f4634232d97ea60'
    reply = {'pg_status': 'ok', 'pg_description': 'Order paid', 'pg_salt': 'z9y8x7'}
    assert signature_base(script, reply, 'demo_secret') == 'result;Order paid;z9y8x7;ok;demo_secret'
    assert make_signature(script, reply, 'demo_secret') == 'a80a6a0f3c446ef59eb45060b1af5a4a'


def test_nested_receipt_vector() -> None:
    params = {
        'pg_merchant_id': '12345',
        'pg_amount': '900',
        'pg_description': 'Ticket',
        'pg_salt': 'a1b2c3d4',
        'pg_receipt_positions': [{'count': '1', 'name': 'Ticket A', 'tax_type': '0', 'price': '900'}],
    }
    assert sorted(flatten(params)) == [
        'pg_amount002',
        'pg_description003',
        'pg_merchant_id001',
        'pg_receipt_positions0050001count001',
        'pg_receipt_positions0050001name002',
        'pg_receipt_positions0050001price004',
        'pg_receipt_positions0050001tax_type003',
        'pg_salt004',
    ]
    assert signature_base('init_payment.php', params, DOC_SECRET) == (
        'init_payment.php;900;Ticket;12345;1;Ticket A;900;0;a1b2c3d4;test_secret_key'
    )
    assert make_signature('init_payment.php', params, DOC_SECRET) == '51c5bcf8ec3172c2e8a1c6a18d06a008'
    # The PHP-style form tree (dict with "0" keys) and the XML pairs flatten the same way.
    as_form = {**params, 'pg_receipt_positions': {'0': params['pg_receipt_positions'][0]}}
    assert make_signature('init_payment.php', as_form, DOC_SECRET) == '51c5bcf8ec3172c2e8a1c6a18d06a008'


def test_unicode_is_hashed_as_utf8() -> None:
    params = {'pg_description': 'Билет на концерт «Алматы»', 'pg_salt': 'x'}
    base = 'init_payment;Билет на концерт «Алматы»;x;k'
    assert signature_base('init_payment', params, 'k') == base
    assert make_signature('init_payment', params, 'k') == hashlib.md5(base.encode('utf-8')).hexdigest()  # noqa: S324


def test_empty_values_are_kept() -> None:
    params = {'pg_a': '', 'pg_b': 'x', 'pg_c': None}
    assert signature_base('s', params, 'k') == 's;;x;;k'


def test_pg_sig_position_is_counted_but_skipped() -> None:
    """Positions count ``pg_sig`` like the references; the value never takes part."""
    with_sig = Pairs([('pg_a', '1'), ('pg_sig', 'zzz'), ('pg_b', '2')])
    assert flatten(with_sig) == {'pg_a001': '1', 'pg_b003': '2'}
    assert make_signature('s', with_sig, 'k') == make_signature('s', {'pg_a': '1', 'pg_b': '2'}, 'k')


def test_prefix_keys_follow_flattened_order() -> None:
    """Spec edge case: flatten-sort differs from plain sort for ``x1``/``x10``."""
    params = {'pg_param1': 'one', 'pg_param10': 'ten'}
    assert signature_base('s', params, 'k') == 's;ten;one;k'


def test_repeated_xml_tags_keep_document_order() -> None:
    pairs = xmlio.parse('<request><list><item>b</item><item>a</item></list><pg_salt>s</pg_salt></request>')
    assert signature_base('s', pairs, 'k') == 's;b;a;s;k'


def test_well_formed_and_constant_time_verification() -> None:
    sig = make_signature('s', {'a': '1'}, 'k')
    assert is_well_formed(sig)
    assert not is_well_formed(sig.upper())
    assert not is_well_formed(None)
    assert not verify_signature('s', {'a': '1'}, 'k', sig.upper())
    assert not verify_signature('s', {'a': '2'}, 'k', sig)
    assert find_sig({'pg_sig': 'x'}) == 'x'
    assert find_sig(Pairs([('pg_sig', 'a'), ('pg_sig', 'b')])) == 'b'


@pytest.mark.parametrize(
    ('url', 'expected'),
    [
        ('https://api.freedompay.kz/init_payment.php', 'init_payment.php'),
        ('https://api.freedompay.kz/init_payment', 'init_payment'),
        ('https://shop.example/index.php?route=extension/payment', 'index.php'),
        ('https://shop.example/?wc-api=freedompay', ''),
        ('https://shop.example/payments/freedompay/', ''),
        ('/get_status3.php', 'get_status3.php'),
    ],
)
def test_script_name(url: str, expected: str) -> None:
    assert script_name(url) == expected


def test_sign_fields_keeps_positions_and_fills_salt() -> None:
    fields = [('pg_status', 'ok'), ('pg_salt', None), ('pg_sig', None), ('pg_tail', 'z')]
    signed = sign_fields('get_status3.php', 'k', fields)
    assert [k for k, _ in signed] == ['pg_status', 'pg_salt', 'pg_sig', 'pg_tail']
    assert verify_signature('get_status3.php', signed, 'k', dict(signed)['pg_sig'])
    appended = sign_fields('x', 'k', [('pg_status', 'ok')])
    assert [k for k, _ in appended] == ['pg_status', 'pg_salt', 'pg_sig']


def test_signed_for_url_with_and_without_url_query() -> None:
    url = 'https://shop.example/index.php?route=pay'
    own, signature_input = signed_for_url(url, 'k', [('pg_a', '1')], include_url_query=True)
    assert [k for k, _ in own] == ['pg_a', 'pg_salt', 'pg_sig']
    assert signature_input[0][0] == 'route'
    assert verify_signature('index.php', signature_input, 'k', dict(own)['pg_sig'])
    plain, _ = signed_for_url(url, 'k', [('pg_a', '1')], include_url_query=False)
    assert verify_signature('index.php', plain, 'k', dict(plain)['pg_sig'])
