"""Freedom Pay: signatures, the provider against a fake HTTP layer, the
checkout / callback / status endpoints and the single-ticket money rules.

The fake gateway verifies our requests and signs its answers with an
independent copy of the spec's reference implementation (section 2.3), so a
mistake in our signature code cannot cancel itself out. Only the HTTP client
(`requests.post`) is replaced; the provider runs for real.
"""

import base64
import hashlib
import threading
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import urlencode
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import requests
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection, transaction
from django.test import RequestFactory, SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from common.choices import PaymentStatusChoices
from events.models import Category, Event, Notification, Registration
from events.services.holds import release_expired_seat_holds
from events.services.registration import attendee_cancel, cancel_registration
from mfa.testing import authenticate_with_recent_mfa
from payments.models import Payment, PaymentEvent, Refund
from payments.providers import conf
from payments.providers import freedompay_signature as sig
from payments.providers.base import (
    CallbackKind,
    InvalidCallback,
    PaymentOrder,
    ProviderRejected,
    ProviderUnavailable,
    StatusResult,
)
from payments.providers.freedompay import FreedomPayProvider, payment_id_ref

SECRET = 'fp-secret-for-tests'
MERCHANT = '12345'
CALLBACK_PATH = '/api/v1/payments/callback/freedompay/'
FP_SETTINGS = {
    'PAYMENT_PROVIDERS_ENABLED': ['stripe', 'freedompay'],
    'PAYMENTS_MOCK_MODE': False,
    'STRIPE_MOCK_MODE': False,
    'FREEDOMPAY_API_URL': 'http://fpay.test',
    'FREEDOMPAY_MERCHANT_ID': MERCHANT,
    'FREEDOMPAY_SECRET_KEY': SECRET,
    'FREEDOMPAY_RESULT_URL': f'http://backend.test{CALLBACK_PATH}',
    'FREEDOMPAY_TESTING_MODE': True,
    'FRONTEND_URL': 'http://frontend.test',
    'JOBS_RUN_INLINE': False,
}
PNG = b'\x89PNG\r\n\x1a\nfake-qr'


# ───────────────────────── independent reference (spec 2.3) ─────────────────────────


def ref_flatten(params, parent=''):
    flat = {}
    for i, (key, value) in enumerate(params.items(), 1):
        if key == 'pg_sig':
            continue
        name = f'{parent}{key}{i:03d}'
        if isinstance(value, dict):
            flat.update(ref_flatten(value, name))
        elif isinstance(value, list):
            flat.update(ref_flatten({str(j): v for j, v in enumerate(value)}, name))
        else:
            flat[name] = str(value)
    return flat


def ref_sig(script, params, secret):
    flat = ref_flatten(params)
    base = ';'.join([script] + [flat[n] for n in sorted(flat)] + [secret])
    return hashlib.md5(base.encode(), usedforsecurity=False).hexdigest()


def xml_doc(pairs):
    body = ''.join(f'<{key}>{escape(str(value))}</{key}>' for key, value in pairs)
    return f'<?xml version="1.0" encoding="utf-8"?><response>{body}</response>'.encode()


def reply_fields(response):
    root = ElementTree.fromstring(response.content)  # noqa: S314 - our own answer
    return [(child.tag, child.text or '') for child in root]


class FakeResponse:
    def __init__(self, content: bytes, status_code=200):
        self.content = content
        self.status_code = status_code
        self.headers = {'content-type': 'text/xml; charset=utf-8'}


class FakeGateway:
    """Enough of the Merchant API for the provider: init_payment.php,
    get_status3.php and revoke, with real signatures both ways."""

    def __init__(self):
        self.calls = []
        self.payments = {}
        self.idempotent = {}
        self.next_id = 1030000000001
        self.fault = None

    def __call__(self, url, data=None, timeout=None, allow_redirects=None, headers=None):
        script = url.rsplit('/', 1)[-1]
        params = dict(data)
        self.calls.append((script, params, timeout))
        if self.fault == 'timeout':
            raise requests.Timeout('read timed out')
        if self.fault == 'http500':
            return FakeResponse(b'<html>oops</html>', 500)
        if params.get('pg_merchant_id') != MERCHANT or params.get('pg_sig') != ref_sig(script, params, SECRET):
            return self._error('9998', 'bad signature')
        handler = {'init_payment.php': self._init, 'get_status3.php': self._status, 'revoke': self._revoke}[script]
        fields = handler(params)
        if fields[0] == ('pg_status', 'error') and fields[1][0] == 'pg_error_code':
            return FakeResponse(xml_doc(fields))
        # Like the real get_status3.php: salt and signature in the middle.
        fields = [*fields[:2], ('pg_salt', 'srvSalt42'), ('pg_sig', None), *fields[2:]]
        signature = ref_sig(script, dict(fields), SECRET)
        if self.fault == 'unsigned':
            fields = [(k, v) for k, v in fields if k != 'pg_sig']
        elif self.fault == 'wrong_signature':
            fields = [(k, '0' * 32 if k == 'pg_sig' else v) for k, v in fields]
        else:
            fields = [(k, signature if k == 'pg_sig' else v) for k, v in fields]
        return FakeResponse(xml_doc(fields))

    @staticmethod
    def _error(code, description):
        return FakeResponse(
            xml_doc([('pg_status', 'error'), ('pg_error_code', code), ('pg_error_description', description)])
        )

    def _init(self, params):
        payment_id = str(self.next_id)
        self.next_id += 1
        self.payments[payment_id] = {
            'amount': Decimal(params['pg_amount']),
            'currency': params['pg_currency'],
            'order_id': params['pg_order_id'],
            'status': 'new',
            'refunded': Decimal('0'),
            'failure_code': '',
        }
        return [
            ('pg_status', 'ok'),
            ('pg_payment_id', payment_id),
            ('pg_redirect_url', f'http://fpay.test/pay.html?customer={payment_id}'),
            ('pg_redirect_url_type', 'need data'),
            ('pg_redirect_qr', base64.b64encode(PNG).decode()),
        ]

    def _status(self, params):
        payment = self.payments.get(params.get('pg_payment_id', ''))
        if payment is None:
            return [('pg_status', 'error'), ('pg_error_code', '11068'), ('pg_error_description', 'not found')]
        fields = [
            ('pg_status', 'ok'),
            ('pg_payment_id', params['pg_payment_id']),
            ('pg_currency', payment['currency']),
            ('pg_amount', f'{payment["amount"].normalize():f}'),
            ('pg_payment_status', payment['status']),
        ]
        if payment['refunded']:
            fields.append(('pg_refund_amount', f'-{payment["refunded"]:.2f}'))
        if payment['failure_code']:
            fields.append(('pg_failure_code', payment['failure_code']))
        return fields

    def _revoke(self, params):
        key = params.get('pg_idempotency_key')
        if key in self.idempotent:
            return self.idempotent[key]
        payment = self.payments.get(params['pg_payment_id'])
        if payment is None:
            return [('pg_status', 'error'), ('pg_error_code', '94031'), ('pg_error_description', 'unknown payment')]
        remaining = payment['amount'] - payment['refunded']
        amount = Decimal(params['pg_refund_amount']) if params.get('pg_refund_amount') else remaining
        if amount > remaining:
            fields = [('pg_status', 'error'), ('pg_revoke_payment_id', '77'), ('pg_failure_code', '900811')]
        else:
            payment['refunded'] += amount
            fields = [('pg_status', 'ok'), ('pg_revoke_payment_id', f'9{len(self.idempotent) + 1:05d}')]
        self.idempotent[key] = fields
        return fields

    def pay(self, payment_id):
        self.payments[payment_id]['status'] = 'success'

    def scripts(self):
        return [script for script, _, _ in self.calls]


def callback_form(payment_id, order_id, *, amount='5000', currency='KZT', result='1', salt='cbSalt1', secret=SECRET):
    fields = [
        ('pg_order_id', str(order_id)),
        ('pg_payment_id', str(payment_id)),
        ('pg_amount', amount),
        ('pg_currency', currency),
        ('pg_net_amount', amount),
        ('pg_description', 'Ticket: Almaty Product Conference'),
        ('pg_result', result),
        ('pg_payment_date', '2026-11-12 18:00:00'),
        ('pg_can_reject', '1'),
        ('pg_testing_mode', '1'),
        ('pg_card_pan', '4716-04XX-XXXX-1981'),
        ('pg_salt', salt),
    ]
    # Our callback URL ends with '/': the script name is the empty string.
    return urlencode([*fields, ('pg_sig', ref_sig('', dict(fields), secret))])


# ───────────────────────── signatures ─────────────────────────


class SignatureTests(SimpleTestCase):
    """Vectors from docs/payments/freedompay-protocol.md, sections 2.2 / 2.3."""

    OVERVIEW = {
        'pg_merchant_id': '12345',
        'pg_amount': '100',
        'pg_currency': 'KZT',
        'pg_description': 'Order #1001',
        'pg_order_id': 'order_1001',
        'pg_salt': 'a1b2c3d4',
    }

    def test_the_documented_init_payment_example(self):
        self.assertEqual(
            sig.make_signature('init_payment.php', self.OVERVIEW, 'test_secret_key'), 'b9ad75871668ca040f80f5f6b530e6ed'
        )

    def test_other_documented_vectors(self):
        status = {'pg_merchant_id': '12345', 'pg_payment_id': '1022123803890', 'pg_salt': 'a1b2c3d4'}
        self.assertEqual(
            sig.make_signature('get_status3.php', status, 'test_secret_key'), '2586378f4f7d4ddd950fd1532eaf4fdd'
        )
        revoke = {'pg_merchant_id': '12345', 'pg_payment_id': '1023122203651', 'pg_salt': 'a1b2c3d4'}
        self.assertEqual(sig.make_signature('revoke', revoke, 'test_secret_key'), 'c9b6030e425d4d5a4d81cdb0ac09a4e5')
        # The script name is part of the signature.
        create = {'pg_merchant_id': '12345', 'pg_amount': '100', 'pg_description': 'Order #1001', 'pg_salt': 'a1b2c3d4'}
        self.assertEqual(
            sig.make_signature('init_payment', create, 'test_secret_key'), 'ffda750b3bbc6a3475ac5ac8a246f739'
        )
        self.assertEqual(
            sig.make_signature('init_payment.php', create, 'test_secret_key'), '4b979c3439ac142b79dd8617dfb09d5c'
        )

    def test_callback_and_reply_vectors(self):
        callback = {
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
        script = sig.script_name('https://shop.example/payments/freedompay/result')
        self.assertEqual(script, 'result')
        self.assertEqual(sig.make_signature(script, callback, 'demo_secret'), '1e007dc444f186ca0f4634232d97ea60')
        reply = [('pg_status', 'ok'), ('pg_description', 'Order paid'), ('pg_salt', 'z9y8x7')]
        self.assertEqual(sig.make_signature('result', reply, 'demo_secret'), 'a80a6a0f3c446ef59eb45060b1af5a4a')

    def test_nested_parameters_are_flattened(self):
        params = {
            'pg_merchant_id': '12345',
            'pg_amount': '900',
            'pg_description': 'Ticket',
            'pg_salt': 'a1b2c3d4',
            'pg_receipt_positions': [{'count': '1', 'name': 'Ticket A', 'tax_type': '0', 'price': '900'}],
        }
        self.assertEqual(
            sig.make_signature('init_payment.php', params, 'test_secret_key'), '51c5bcf8ec3172c2e8a1c6a18d06a008'
        )

    def test_verification_rejects_tampering(self):
        signed = dict(self.OVERVIEW, pg_sig='b9ad75871668ca040f80f5f6b530e6ed')
        self.assertTrue(sig.verify_signature('init_payment.php', signed, 'test_secret_key'))
        for name, tampered, script, secret in (
            ('amount', dict(signed, pg_amount='1000'), 'init_payment.php', 'test_secret_key'),
            ('added field', dict(signed, pg_extra='1'), 'init_payment.php', 'test_secret_key'),
            ('script', signed, 'init_payment', 'test_secret_key'),
            ('secret', signed, 'init_payment.php', 'other_key'),
            (
                'upper-case sig',
                dict(signed, pg_sig='B9AD75871668CA040F80F5F6B530E6ED'),
                'init_payment.php',
                'test_secret_key',
            ),
            ('no sig', self.OVERVIEW, 'init_payment.php', 'test_secret_key'),
            ('empty secret', signed, 'init_payment.php', ''),
        ):
            with self.subTest(name):
                self.assertFalse(sig.verify_signature(script, tampered, secret))

    def test_a_signature_in_the_middle_of_a_document_verifies(self):
        pairs = [('pg_status', 'ok'), ('pg_payment_id', '7'), ('pg_salt', 's1'), ('pg_sig', None), ('pg_amount', '5')]
        signature = ref_sig('get_status3.php', dict(pairs), 'k')
        pairs = [(k, signature if k == 'pg_sig' else v) for k, v in pairs]
        self.assertTrue(sig.verify_signature('get_status3.php', pairs, 'k'))

    def test_script_name_is_the_last_path_segment(self):
        self.assertEqual(sig.script_name('http://h/api/v1/payments/callback/freedompay/'), '')
        self.assertEqual(sig.script_name('http://h/a/init_payment.php?x=1'), 'init_payment.php')

    def test_xml_with_a_dtd_is_refused(self):
        bomb = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><response><pg_status>&a;</pg_status></response>'
        with self.assertRaises(sig.XmlError):
            sig.parse_xml(bomb)
        with self.assertRaises(sig.XmlError):
            sig.parse_xml(b'<request><a>1</a></request>')


# ───────────────────────── provider against a fake HTTP layer ─────────────────────────


def fp_order(**kw):
    data = {
        'reference': '42',
        'amount': Decimal('5000.00'),
        'currency': 'KZT',
        'description': 'Ticket; Almaty',
        'success_url': 'http://frontend.test/payment/success?provider=freedompay&payment=42',
        'cancel_url': 'http://frontend.test/payment/cancel?provider=freedompay&payment=42',
        'expires_at': timezone.now() + timedelta(minutes=10),
        'idempotency_key': 'payment-42-attempt-1',
        'customer_email': 'buyer@example.com',
    }
    data.update(kw)
    return PaymentOrder(**data)


@override_settings(**FP_SETTINGS)
class ProviderTests(SimpleTestCase):
    def setUp(self):
        self.gateway = FakeGateway()
        patcher = patch('payments.providers.freedompay.requests.post', self.gateway)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.provider = FreedomPayProvider()

    def test_create_payment_sends_a_signed_init_payment(self):
        result = self.provider.create_payment(fp_order())
        script, params, timeout = self.gateway.calls[0]
        self.assertEqual(script, 'init_payment.php')
        self.assertEqual(timeout, (5, 15))
        self.assertEqual(params['pg_order_id'], '42')
        self.assertEqual(params['pg_amount'], '5000.00')
        self.assertEqual(params['pg_currency'], 'KZT')
        self.assertEqual(params['pg_generate_qr'], '1')
        self.assertEqual(params['pg_testing_mode'], '1')
        self.assertEqual(params['pg_result_url'], FP_SETTINGS['FREEDOMPAY_RESULT_URL'])
        self.assertEqual(params['pg_request_method'], 'POST')
        self.assertTrue(params['pg_success_url'].startswith('http://frontend.test/payment/success?'))
        self.assertEqual(params['pg_idempotency_key'], 'payment-42-attempt-1')
        self.assertNotIn(';', params['pg_description'])
        self.assertTrue(595 <= int(params['pg_lifetime']) <= 600, params['pg_lifetime'])
        self.assertEqual(result.session_id, '1030000000001')
        self.assertEqual(result.redirect_url, 'http://fpay.test/pay.html?customer=1030000000001')
        self.assertEqual(base64.b64decode(result.raw['redirect_qr']), PNG)

    def test_the_lifetime_is_clamped_to_the_gateway_range(self):
        self.provider.create_payment(fp_order(expires_at=timezone.now() + timedelta(seconds=20)))
        self.provider.create_payment(fp_order(expires_at=timezone.now() + timedelta(days=30)))
        lifetimes = [params['pg_lifetime'] for _, params, _ in self.gateway.calls]
        self.assertEqual(lifetimes, ['300', '604800'])

    def test_only_kzt_is_charged(self):
        with self.assertRaises(ProviderRejected):
            self.provider.create_payment(fp_order(currency='USD'))
        self.assertEqual(self.gateway.calls, [])

    def test_unsigned_or_wrongly_signed_answers_are_not_trusted(self):
        for fault in ('unsigned', 'wrong_signature', 'http500', 'timeout'):
            with self.subTest(fault):
                self.gateway.fault = fault
                with self.assertRaises(ProviderUnavailable):
                    self.provider.create_payment(fp_order())

    def test_a_request_error_is_a_rejection(self):
        with override_settings(FREEDOMPAY_SECRET_KEY='wrong-secret-value'), self.assertRaises(ProviderRejected) as ctx:
            self.provider.create_payment(fp_order())
        self.assertEqual(ctx.exception.code, '9998')

    def test_status_mapping(self):
        result = self.provider.create_payment(fp_order())
        pid = result.session_id
        ref = payment_id_ref(pid)
        self.assertEqual(self.provider.get_status(ref).state, StatusResult.PENDING)
        self.gateway.pay(pid)
        status = self.provider.get_status(ref)
        self.assertEqual((status.state, status.amount, status.currency), (CallbackKind.PAID, Decimal('5000'), 'KZT'))
        self.gateway.payments[pid]['refunded'] = Decimal('5000')
        self.assertEqual(self.provider.get_status(ref).state, CallbackKind.REFUNDED)
        self.gateway.payments[pid].update(status='error', failure_code='10018', refunded=Decimal('0'))
        self.assertEqual(self.provider.get_status(ref).state, CallbackKind.EXPIRED)
        self.gateway.payments[pid]['failure_code'] = '10009'
        self.assertEqual(self.provider.get_status(ref).state, CallbackKind.FAILED)
        with self.assertRaises(ProviderRejected) as ctx:
            self.provider.get_status(payment_id_ref('999'))
        self.assertEqual(ctx.exception.code, '11068')

    def test_partial_and_full_refunds(self):
        pid = self.provider.create_payment(fp_order()).session_id
        self.gateway.pay(pid)
        ref = payment_id_ref(pid, amount=Decimal('5000.00'), currency='KZT')
        partial = self.provider.refund(ref, Decimal('1500.00'), idempotency_key='refund-a', reason='partial')
        self.assertEqual((partial.status, partial.amount), ('succeeded', Decimal('1500.00')))
        self.assertEqual(self.gateway.calls[-1][1]['pg_refund_amount'], '1500.00')
        # The same key again does not refund twice.
        self.provider.refund(ref, Decimal('1500.00'), idempotency_key='refund-a', reason='partial')
        self.assertEqual(self.gateway.payments[pid]['refunded'], Decimal('1500'))
        rest = self.provider.refund(ref, None, idempotency_key='refund-b', reason='the rest')
        self.assertNotIn('pg_refund_amount', self.gateway.calls[-1][1])
        self.assertEqual(rest.status, 'succeeded')
        self.assertEqual(self.gateway.payments[pid]['refunded'], Decimal('5000'))
        declined = self.provider.refund(ref, Decimal('1.00'), idempotency_key='refund-c', reason='too much')
        self.assertEqual(declined.status, 'failed')

    def test_cancel_session_is_a_no_op(self):
        self.assertIsNone(self.provider.cancel_session(payment_id_ref('1')))
        self.assertEqual(self.gateway.calls, [])

    def test_callback_parsing_and_signed_reply(self):
        request = RequestFactory().post(
            CALLBACK_PATH,
            data=callback_form('1030000000009', '42', salt='abcSalt9'),
            content_type='application/x-www-form-urlencoded',
        )
        result = self.provider.handle_callback(request)
        self.assertEqual(result.kind, CallbackKind.PAID)
        self.assertEqual((result.amount, result.currency, result.reference), (Decimal('5000'), 'KZT', '42'))
        self.assertEqual(result.event_id, 'result:1030000000009:1')
        self.assertNotIn('pg_card_pan', result.raw)
        response = self.provider.callback_response(result, 'processed')
        fields = reply_fields(response)
        self.assertEqual(response['Content-Type'], 'text/xml; charset=utf-8')
        self.assertEqual(dict(fields)['pg_status'], 'ok')
        self.assertEqual(dict(fields)['pg_salt'], 'abcSalt9')
        unsigned = [(k, v) for k, v in fields if k != 'pg_sig']
        self.assertEqual(dict(fields)['pg_sig'], ref_sig('', dict(unsigned), SECRET))

    def test_callbacks_with_a_bad_signature_are_refused(self):
        factory = RequestFactory()
        for name, body, path in (
            ('wrong secret', callback_form('1', '42', secret='nope'), CALLBACK_PATH),
            ('other script name', callback_form('1', '42'), '/api/v1/payments/callback/freedompay/result'),
            ('tampered amount', callback_form('1', '42').replace('pg_amount=5000', 'pg_amount=1'), CALLBACK_PATH),
            ('repeated field', callback_form('1', '42') + '&pg_amount=1', CALLBACK_PATH),
        ):
            with self.subTest(name), self.assertRaises(InvalidCallback):
                self.provider.handle_callback(
                    factory.post(path, data=body, content_type='application/x-www-form-urlencoded')
                )


class ProductionGuardTests(SimpleTestCase):
    def values(self, **settings):
        base = {
            'FREEDOMPAY_API_URL': 'https://api.freedompay.kz',
            'FREEDOMPAY_MERCHANT_ID': '554433',
            'FREEDOMPAY_SECRET_KEY': 'Zr8kQ2wP0aLx9TbV',
            'FREEDOMPAY_RESULT_URL': 'https://eventhub.example/api/v1/payments/callback/freedompay/',
            'FREEDOMPAY_DEMO_MODE': False,
        }
        base.update(settings)
        return base.get

    def test_the_real_gateway_with_real_keys_passes(self):
        self.assertEqual(conf.production_problems(['freedompay'], mock_mode=False, get_setting=self.values()), [])

    def test_the_emulator_and_demo_keys_need_the_demo_flag(self):
        demo = {'FREEDOMPAY_API_URL': 'http://fpay-emulator:8080', 'FREEDOMPAY_SECRET_KEY': 'demo_fpay_secret'}
        problems = conf.production_problems(['freedompay'], mock_mode=False, get_setting=self.values(**demo))
        self.assertTrue(any('FREEDOMPAY_API_URL must be the real' in p for p in problems), problems)
        self.assertTrue(any('FREEDOMPAY_SECRET_KEY looks like a demo value' in p for p in problems), problems)
        allowed = self.values(FREEDOMPAY_DEMO_MODE=True, **demo)
        self.assertEqual(conf.production_problems(['freedompay'], mock_mode=False, get_setting=allowed), [])

    def test_missing_settings_are_reported(self):
        problems = conf.production_problems(
            ['freedompay'], mock_mode=False, get_setting=self.values(FREEDOMPAY_SECRET_KEY='')
        )
        self.assertEqual(problems, ['FREEDOMPAY_SECRET_KEY must be set'])


# ───────────────────────── endpoints and money rules ─────────────────────────


class FixturesMixin:
    def make_world(self):
        self.organizer = User.objects.create_user(username='org', email='org@example.com', password='password123')
        self.buyer = User.objects.create_user(username='buyer', email='buyer@example.com', password='password123')
        self.other = User.objects.create_user(username='other', email='other@example.com', password='password123')
        self.category = Category.objects.create(name='Tech', icon='cpu')
        self.event = self.make_event('Almaty Product Conference', currency='KZT', price=Decimal('5000.00'))
        self.registration = Registration.objects.create(
            user=self.buyer,
            event=self.event,
            status='pending',
            seat_held_until=timezone.now() + timedelta(minutes=10),
        )

    def make_event(self, title, *, currency, price, status='published'):
        return Event.objects.create(
            title=title,
            description='Talks',
            organizer=self.organizer,
            category=self.category,
            date=timezone.now() + timedelta(days=14),
            location='Almaty',
            price=price,
            currency=currency,
            max_participants=100,
            status=status,
        )


@override_settings(**FP_SETTINGS)
class FreedomPayFlowTests(FixturesMixin, APITestCase):
    def setUp(self):
        cache.clear()
        self.make_world()
        self.gateway = FakeGateway()
        patcher = patch('payments.providers.freedompay.requests.post', self.gateway)
        patcher.start()
        self.addCleanup(patcher.stop)

    # helpers

    def checkout(self, registration=None, user=None):
        self.client.force_authenticate(user=user or self.buyer)
        registration = registration or self.registration
        return self.client.post(f'/api/v1/payments/create-checkout/{registration.pk}/')

    def opened(self):
        response = self.checkout()
        self.assertEqual(response.status_code, 200, response.data)
        payment = Payment.objects.get(pk=response.data['payment_id'])
        return payment, payment.provider_session_id

    def notify(self, payment_id, order_id, **kw):
        self.client.force_authenticate(user=None)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                CALLBACK_PATH,
                data=callback_form(payment_id, order_id, **kw),
                content_type='application/x-www-form-urlencoded',
            )
        return response, dict(reply_fields(response))

    def assertSignedReply(self, response, salt):
        fields = reply_fields(response)
        values = dict(fields)
        self.assertEqual(values['pg_salt'], salt)
        self.assertEqual(values['pg_sig'], ref_sig('', {k: v for k, v in fields if k != 'pg_sig'}, SECRET))

    # checkout

    def test_a_kzt_ticket_opens_a_freedom_pay_page_with_a_qr_code(self):
        response = self.checkout()
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data
        self.assertEqual(data['provider'], 'freedompay')
        self.assertEqual(data['checkout_url'], 'http://fpay.test/pay.html?customer=1030000000001')
        self.assertEqual(data['qr_code'], 'data:image/png;base64,' + base64.b64encode(PNG).decode())
        self.assertEqual((data['amount'], data['currency']), ('5000.00', 'KZT'))
        payment = Payment.objects.get(pk=data['payment_id'])
        self.assertEqual(payment.registration_id, self.registration.pk)
        self.assertEqual(
            (payment.provider, payment.provider_session_id, payment.status, payment.attempt),
            ('freedompay', '1030000000001', 'pending', 1),
        )
        self.assertEqual(payment.provider_payload['pg_payment_ids'], ['1030000000001'])
        self.assertEqual(self.gateway.calls[0][1]['pg_order_id'], str(payment.pk))
        self.assertIn(f'payment={payment.pk}', self.gateway.calls[0][1]['pg_success_url'])
        # The seat hold covers the payment page's lifetime.
        self.registration.refresh_from_db()
        lifetime = int(self.gateway.calls[0][1]['pg_lifetime'])
        self.assertGreaterEqual(self.registration.seat_held_until, timezone.now() + timedelta(seconds=lifetime))

    def test_a_second_attempt_remembers_both_gateway_payments(self):
        self.checkout()
        response = self.checkout()
        payment = Payment.objects.get(pk=response.data['payment_id'])
        self.assertEqual(payment.attempt, 2)
        self.assertEqual(payment.provider_payload['pg_payment_ids'], ['1030000000001', '1030000000002'])
        stamp = int(payment.created_at.timestamp())
        self.assertEqual(
            [params['pg_idempotency_key'] for _, params, _ in self.gateway.calls],
            [f'payment-{payment.pk}-{stamp}-attempt-1', f'payment-{payment.pk}-{stamp}-attempt-2'],
        )

    def test_usd_events_stay_on_stripe(self):
        usd_event = self.make_event('Workshop', currency='USD', price=Decimal('10.00'))
        registration = Registration.objects.create(user=self.buyer, event=usd_event, status='pending')

        class Session:
            id = 'cs_test_1'
            url = 'https://checkout.stripe.com/pay/cs_test_1'

        with patch('stripe.checkout.Session.create', return_value=Session()) as create:
            response = self.checkout(registration)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['provider'], response.data['qr_code']), ('stripe', None))
        self.assertEqual(response.data['checkout_url'], 'https://checkout.stripe.com/pay/cs_test_1')
        create.assert_called_once()
        self.assertEqual(self.gateway.calls, [])
        self.assertEqual(Payment.objects.get(registration=registration).stripe_checkout_session_id, 'cs_test_1')

    def test_kzt_falls_back_to_stripe_when_freedom_pay_is_not_enabled(self):
        class Session:
            id = 'cs_test_2'
            url = 'https://checkout.stripe.com/pay/cs_test_2'

        with (
            override_settings(PAYMENT_PROVIDERS_ENABLED=['stripe']),
            patch('stripe.checkout.Session.create', return_value=Session()),
        ):
            response = self.checkout()
        self.assertEqual(response.data['provider'], 'stripe')
        self.assertEqual(self.gateway.calls, [])

    def test_checkout_is_refused_for_an_event_that_is_not_published(self):
        usd_event = self.make_event('Workshop', currency='USD', price=Decimal('10.00'))
        usd_registration = Registration.objects.create(user=self.buyer, event=usd_event, status='pending')
        Event.objects.filter(pk__in=[self.event.pk, usd_event.pk]).update(status='cancelled')
        for registration in (self.registration, usd_registration):
            with self.subTest(currency=registration.event.currency), patch('stripe.checkout.Session.create') as create:
                response = self.checkout(registration)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data['error'], 'This event is not open for payment.')
                create.assert_not_called()
        with override_settings(PAYMENTS_MOCK_MODE=True, STRIPE_MOCK_MODE=True):
            self.assertEqual(self.checkout(usd_registration).status_code, 400)
        self.assertEqual(self.gateway.calls, [])
        self.assertFalse(Payment.objects.exists())
        usd_registration.refresh_from_db()
        self.assertEqual(usd_registration.status, 'pending')

    def test_another_users_registration_is_not_found(self):
        self.assertEqual(self.checkout(user=self.other).status_code, 404)

    def test_gateway_down_gives_502_and_the_buyer_can_retry(self):
        self.gateway.fault = 'timeout'
        response = self.checkout()
        self.assertEqual(response.status_code, 502)
        payment = Payment.objects.get(registration=self.registration)
        self.assertEqual((payment.status, payment.provider_session_id), ('pending', ''))
        self.gateway.fault = None
        self.assertEqual(self.checkout().status_code, 200)

    # callbacks

    def test_a_paid_callback_confirms_the_ticket_after_a_status_check(self):
        payment, pid = self.opened()
        self.gateway.pay(pid)
        response, reply = self.notify(pid, payment.pk, salt='okSalt1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(reply['pg_status'], 'ok')
        self.assertSignedReply(response, 'okSalt1')
        self.assertEqual(self.gateway.scripts(), ['init_payment.php', 'get_status3.php'])
        payment.refresh_from_db()
        self.registration.refresh_from_db()
        self.assertEqual((payment.status, payment.provider_payment_id), ('completed', pid))
        self.assertEqual(self.registration.status, 'confirmed')
        self.assertIsNone(self.registration.seat_held_until)
        event = PaymentEvent.objects.get()
        self.assertEqual(
            (event.provider, event.event_id, event.outcome), ('freedompay', f'result:{pid}:1', 'processed')
        )
        self.assertEqual(event.payment, payment)
        self.assertNotIn('pg_card_pan', event.payload)
        self.assertEqual(Notification.objects.filter(user=self.buyer, type='ticket_purchased').count(), 1)

    def test_a_duplicate_callback_is_applied_once_and_answered_alike(self):
        payment, pid = self.opened()
        self.gateway.pay(pid)
        _, reply1 = self.notify(pid, payment.pk, salt='first1')
        second, reply2 = self.notify(pid, payment.pk, salt='second2')
        self.assertEqual((reply1['pg_status'], reply2['pg_status']), ('ok', 'ok'))
        self.assertEqual(reply1['pg_description'], reply2['pg_description'])
        self.assertSignedReply(second, 'second2')
        self.assertEqual(PaymentEvent.objects.count(), 1)
        self.assertEqual(self.gateway.scripts().count('get_status3.php'), 1)
        self.assertEqual(Notification.objects.filter(user=self.buyer, type='ticket_purchased').count(), 1)

    def test_a_bad_signature_is_refused_and_changes_nothing(self):
        payment, pid = self.opened()
        self.gateway.pay(pid)
        response, reply = self.notify(pid, payment.pk, secret='forged-secret', salt='badSig1')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(reply['pg_status'], 'error')
        self.assertSignedReply(response, 'badSig1')
        payment.refresh_from_db()
        self.registration.refresh_from_db()
        self.assertEqual((payment.status, self.registration.status), ('pending', 'pending'))
        self.assertFalse(PaymentEvent.objects.exists())
        self.assertNotIn('get_status3.php', self.gateway.scripts())

    def test_an_unconfirmed_payment_is_answered_error_and_retried_later(self):
        payment, pid = self.opened()  # the gateway still says "new"
        response, reply = self.notify(pid, payment.pk)
        self.assertEqual((response.status_code, reply['pg_status']), (200, 'error'))
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')
        self.assertFalse(PaymentEvent.objects.exists())
        self.gateway.pay(pid)
        _, reply = self.notify(pid, payment.pk, salt='retry2')
        self.assertEqual(reply['pg_status'], 'ok')
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'completed')

    def test_a_wrong_amount_is_not_confirmed_and_refunded(self):
        payment, pid = self.opened()
        self.gateway.pay(pid)
        self.gateway.payments[pid]['amount'] = Decimal('50')  # the gateway agrees with the callback
        _, reply = self.notify(pid, payment.pk, amount='50')
        self.assertEqual(reply['pg_status'], 'ok')
        payment.refresh_from_db()
        self.registration.refresh_from_db()
        self.assertEqual(payment.status, 'failed')
        self.assertEqual(self.registration.status, 'pending')
        refund = Refund.objects.get()
        self.assertEqual(
            (refund.kind, refund.amount, refund.currency, refund.status, refund.provider_payment_id),
            ('amount_mismatch', Decimal('50.00'), 'KZT', 'succeeded', pid),
        )
        self.assertEqual(payment.refunded_amount, Decimal('0'))
        self.assertEqual(PaymentEvent.objects.get().outcome, 'amount_mismatch')
        self.assertEqual(self.gateway.payments[pid]['refunded'], Decimal('50'))

    def test_a_wrong_currency_is_not_confirmed_and_refunded(self):
        payment, pid = self.opened()
        self.gateway.pay(pid)
        self.gateway.payments[pid]['currency'] = 'USD'
        self.notify(pid, payment.pk, currency='USD')
        payment.refresh_from_db()
        self.registration.refresh_from_db()
        self.assertEqual((payment.status, self.registration.status), ('failed', 'pending'))
        refund = Refund.objects.get()
        self.assertEqual((refund.kind, refund.currency, refund.status), ('amount_mismatch', 'USD', 'succeeded'))

    def test_a_payment_after_the_hold_expired_is_refunded_automatically(self):
        payment, pid = self.opened()
        Registration.objects.filter(pk=self.registration.pk).update(
            seat_held_until=timezone.now() - timedelta(minutes=1)
        )
        release_expired_seat_holds(event=self.event)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, 'cancelled')

        self.gateway.pay(pid)
        _, reply = self.notify(pid, payment.pk)
        self.assertEqual(reply['pg_status'], 'ok')
        payment.refresh_from_db()
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, 'cancelled')
        self.assertEqual((payment.status, payment.refunded_amount), ('refunded', payment.amount))
        refund = Refund.objects.get()
        self.assertEqual((refund.kind, refund.status, refund.amount), ('late_payment', 'succeeded', payment.amount))
        self.assertTrue(refund.provider_refund_id)
        self.assertEqual(self.gateway.payments[pid]['refunded'], Decimal('5000'))
        self.assertEqual(PaymentEvent.objects.get().outcome, 'late_payment')
        self.assertTrue(Notification.objects.filter(user=self.buyer, type='payment_failed').exists())

    def test_a_late_refund_is_retried_by_the_job_when_the_gateway_is_down(self):
        from jobs.models import Job
        from jobs.queue import run_due_jobs

        payment, pid = self.opened()
        cancel_registration(registration=self.registration)
        self.gateway.pay(pid)
        real_revoke = self.gateway._revoke
        self.gateway._revoke = lambda params: [
            ('pg_status', 'error'),
            ('pg_error_code', '91021'),
            ('pg_error_description', 'busy'),
        ]
        self.notify(pid, payment.pk)
        refund = Refund.objects.get()
        self.assertEqual((refund.status, refund.attempts), ('pending', 1))
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'completed')
        self.gateway._revoke = real_revoke
        Job.objects.filter(kind='process_payment_refund').update(run_after=timezone.now())
        run_due_jobs()
        refund.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual((refund.status, payment.status), ('succeeded', 'refunded'))

    def test_a_second_payment_for_a_paid_ticket_is_refunded(self):
        payment, pid = self.opened()
        self.gateway.pay(pid)
        self.notify(pid, payment.pk)
        second = self.checkout()  # the ticket is paid: no new page
        self.assertEqual(second.status_code, 400)
        # A second gateway payment of an earlier attempt of the same order.
        payment.refresh_from_db()
        payload = payment.provider_payload
        payload['pg_payment_ids'].append('1030000000077')
        Payment.objects.filter(pk=payment.pk).update(provider_payload=payload)
        self.gateway.payments['1030000000077'] = dict(self.gateway.payments[pid], refunded=Decimal('0'))
        self.notify('1030000000077', payment.pk)
        refund = Refund.objects.get()
        self.assertEqual(
            (refund.kind, refund.status, refund.provider_payment_id), ('duplicate', 'succeeded', '1030000000077')
        )
        payment.refresh_from_db()
        self.assertEqual((payment.status, payment.refunded_amount, payment.provider_payment_id), ('completed', 0, pid))

    def test_a_failed_result_marks_the_payment_failed_and_keeps_the_hold(self):
        payment, pid = self.opened()
        self.registration.refresh_from_db()
        hold = self.registration.seat_held_until
        _, reply = self.notify(pid, payment.pk, result='0', amount='5000')
        self.assertEqual(reply['pg_status'], 'ok')
        payment.refresh_from_db()
        self.registration.refresh_from_db()
        self.assertEqual(payment.status, 'failed')
        self.assertEqual((self.registration.status, self.registration.seat_held_until), ('pending', hold))
        self.assertNotIn('get_status3.php', self.gateway.scripts())
        # The buyer can try again.
        self.assertEqual(self.checkout().status_code, 200)
        payment.refresh_from_db()
        self.assertEqual((payment.status, payment.attempt), ('pending', 2))

    def test_an_unknown_order_is_refunded_and_logged(self):
        self.gateway.payments['1030000000555'] = {
            'amount': Decimal('7000'),
            'currency': 'KZT',
            'order_id': '999999',
            'status': 'success',
            'refunded': Decimal('0'),
            'failure_code': '',
        }
        with self.assertLogs('payments.freedompay_flow', level='ERROR'):
            _, reply = self.notify('1030000000555', '999999', amount='7000')
        self.assertEqual(reply['pg_status'], 'ok')
        event = PaymentEvent.objects.get()
        self.assertEqual((event.outcome, event.payment), ('orphan', None))
        refund = Refund.objects.get()
        self.assertEqual(
            (refund.kind, refund.payment, refund.status, refund.amount), ('orphan', None, 'succeeded', Decimal('7000'))
        )

    # status endpoint

    def test_the_status_endpoint_is_owner_only(self):
        payment, _ = self.opened()
        url = f'/api/v1/payments/status/{payment.pk}/'
        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_authenticate(user=self.buyer)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {
                k: response.data[k]
                for k in ('payment_id', 'provider', 'status', 'registration_id', 'registration_status')
            },
            {
                'payment_id': payment.pk,
                'provider': 'freedompay',
                'status': 'pending',
                'registration_id': self.registration.pk,
                'registration_status': 'pending',
            },
        )
        self.assertEqual((response.data['amount'], response.data['currency']), ('5000.00', 'KZT'))
        # Fresh payment: no gateway call yet.
        self.assertEqual(self.gateway.scripts(), ['init_payment.php'])

    def test_a_stale_pending_payment_is_settled_by_polling_with_a_rate_limit(self):
        payment, pid = self.opened()
        Payment.objects.filter(pk=payment.pk).update(updated_at=timezone.now() - timedelta(seconds=30))
        self.client.force_authenticate(user=self.buyer)
        url = f'/api/v1/payments/status/{payment.pk}/'
        self.assertEqual(self.client.get(url).data['status'], 'pending')
        self.assertEqual(self.gateway.scripts().count('get_status3.php'), 1)
        self.gateway.pay(pid)
        # Within the rate limit: no second gateway call.
        self.assertEqual(self.client.get(url).data['status'], 'pending')
        self.assertEqual(self.gateway.scripts().count('get_status3.php'), 1)
        cache.clear()
        with self.captureOnCommitCallbacks(execute=True):
            data = self.client.get(url).data
        self.assertEqual((data['status'], data['registration_status']), ('completed', 'confirmed'))
        self.assertEqual(PaymentEvent.objects.get().event_id, f'status:{pid}:paid')
        # The Result notification arriving afterwards is a no-op.
        _, reply = self.notify(pid, payment.pk)
        self.assertEqual(reply['pg_status'], 'ok')
        self.assertEqual(Notification.objects.filter(user=self.buyer, type='ticket_purchased').count(), 1)

    # refunds by the organizer go through the gateway

    def test_an_organizer_refund_returns_the_money_through_freedom_pay(self):
        payment, pid = self.opened()
        self.gateway.pay(pid)
        self.notify(pid, payment.pk)
        authenticate_with_recent_mfa(self.client, self.organizer)  # refunds need step-up
        response = self.client.post(
            f'/api/v1/payments/refund/{self.registration.pk}/', {'amount': '2000'}, format='json'
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.gateway.payments[pid]['refunded'], Decimal('2000'))
        response = self.client.post(f'/api/v1/payments/refund/{self.registration.pk}/', {}, format='json')
        self.assertEqual(response.data['status'], 'refunded')
        self.assertEqual(self.gateway.payments[pid]['refunded'], Decimal('5000'))
        self.assertEqual(
            list(Refund.objects.values_list('kind', 'status', 'amount')),
            [('organizer', 'succeeded', Decimal('2000.00')), ('organizer', 'succeeded', Decimal('3000.00'))],
        )
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, 'cancelled')

    def test_a_refused_gateway_refund_leaves_the_books_alone(self):
        payment, pid = self.opened()
        self.gateway.pay(pid)
        self.notify(pid, payment.pk)
        self.gateway.fault = 'http500'
        authenticate_with_recent_mfa(self.client, self.organizer)
        response = self.client.post(f'/api/v1/payments/refund/{self.registration.pk}/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        payment.refresh_from_db()
        self.assertEqual((payment.status, payment.refunded_amount), ('completed', 0))
        self.assertFalse(Refund.objects.exists())


# ───────────────────────── cancel vs. confirm ─────────────────────────


@override_settings(**FP_SETTINGS)
class CancelRaceTests(FixturesMixin, APITestCase):
    def setUp(self):
        self.make_world()
        self.payment = Payment.objects.create(
            registration=self.registration, amount=Decimal('5000.00'), currency='kzt', provider='freedompay'
        )

    def test_a_payment_confirmed_after_the_unlocked_check_is_not_voided(self):
        stale = Registration.objects.select_related('payment').get(pk=self.registration.pk)
        self.assertEqual(stale.payment.status, 'pending')
        # The confirmation commits between attendee_cancel's checks and the lock.
        Payment.objects.filter(pk=self.payment.pk).update(status=PaymentStatusChoices.COMPLETED)
        with (
            patch('events.services.registration.get_active_registration', return_value=stale),
            self.assertRaisesMessage(ValueError, 'already paid'),
        ):
            attendee_cancel(user=self.buyer, event=self.event)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, 'pending')

    def test_an_unpaid_hold_is_still_released(self):
        self.client.force_authenticate(user=self.buyer)
        attendee_cancel(user=self.buyer, event=self.event)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, 'cancelled')

    def test_other_callers_still_cancel_confirmed_registrations(self):
        Registration.objects.filter(pk=self.registration.pk).update(status='confirmed')
        cancel_registration(registration=self.registration)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, 'cancelled')


@override_settings(**FP_SETTINGS)
class CancelConfirmConcurrencyTests(FixturesMixin, TransactionTestCase):
    """Real row locks: the confirmation holds Payment and Registration while
    the buyer presses "cancel"; the cancel waits and then refuses."""

    def test_cancel_waits_for_the_confirmation_and_refuses(self):
        self.make_world()
        payment = Payment.objects.create(
            registration=self.registration, amount=Decimal('5000.00'), currency='kzt', provider='freedompay'
        )
        stale = Registration.objects.get(pk=self.registration.pk)
        locked, release = threading.Event(), threading.Event()
        errors = []

        def confirm():
            try:
                with transaction.atomic():
                    Payment.objects.select_for_update().get(pk=payment.pk)
                    Registration.objects.select_for_update().get(pk=self.registration.pk)
                    locked.set()
                    release.wait(5)
                    Payment.objects.filter(pk=payment.pk).update(status='completed')
                    Registration.objects.filter(pk=self.registration.pk).update(status='confirmed')
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)
            finally:
                connection.close()

        worker = threading.Thread(target=confirm)
        worker.start()
        self.assertTrue(locked.wait(5))
        timer = threading.Timer(0.3, release.set)
        timer.start()
        started = time.monotonic()
        with self.assertRaises(ValueError):
            cancel_registration(registration=stale, only_unpaid_pending=True)
        self.assertGreaterEqual(time.monotonic() - started, 0.2)  # it really waited for the lock
        worker.join(5)
        self.assertEqual(errors, [])
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, 'confirmed')


class DateSanityTests(SimpleTestCase):
    def test_lifetime_helper_uses_the_hold(self):
        from payments.providers.freedompay import lifetime_seconds

        now = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
        self.assertEqual(lifetime_seconds(now + timedelta(minutes=10), now), 600)
        self.assertEqual(lifetime_seconds(now - timedelta(minutes=1), now), 300)
