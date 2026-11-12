"""Provider interface values, the registry, the start-up guard and the mock
provider (ADR 0001)."""

import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, override_settings

from payments.providers import conf, registry
from payments.providers.base import (
    CallbackKind,
    CallbackResult,
    InvalidCallback,
    OrderLine,
    PaymentOrder,
    PaymentProvider,
    ProviderRejected,
    RefundResult,
    StatusResult,
)
from payments.providers.mock import MockProvider

EXPIRES = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


def order(**kw):
    data = {
        'reference': '42',
        'amount': Decimal('5000.00'),
        'currency': 'KZT',
        'description': 'Gig',
        'success_url': 'https://eventhub.example/payment/success',
        'cancel_url': 'https://eventhub.example/payment/cancel',
        'expires_at': EXPIRES,
        'idempotency_key': 'payment-42-attempt-1',
    }
    data.update(kw)
    return PaymentOrder(**data)


class FakePayment:
    def __init__(self, **kw):
        self.pk = kw.get('pk', 42)
        self.provider_session_id = kw.get('provider_session_id', '')
        self.provider_payment_id = kw.get('provider_payment_id', '')
        self.amount = kw.get('amount', Decimal('5000.00'))
        self.currency = kw.get('currency', 'kzt')


class ValueTypeTests(SimpleTestCase):
    def test_an_order_is_frozen_and_its_metadata_read_only(self):
        o = order(metadata={'payment_id': '42'})
        with self.assertRaises(FrozenInstanceError):
            o.amount = Decimal('1.00')
        with self.assertRaises(TypeError):
            o.metadata['x'] = 'y'

    def test_money_must_be_a_decimal_with_at_most_two_places(self):
        with self.assertRaises(TypeError):
            order(amount=5000.0)
        with self.assertRaises(ValueError):
            order(amount=Decimal('1.005'))
        with self.assertRaises(ValueError):
            order(amount=Decimal('0'))
        with self.assertRaises(TypeError):
            order(amount=Decimal('NaN'))

    def test_currency_must_be_upper_case_iso(self):
        for bad in ('kzt', 'KZ', 'KZTT', ''):
            with self.subTest(currency=bad), self.assertRaises(ValueError):
                order(currency=bad)

    def test_lines_must_add_up(self):
        lines = (OrderLine('Seat 1-1', Decimal('2500.00')), OrderLine('Seat 1-2', Decimal('2500.00')))
        self.assertEqual(order(lines=lines).lines, lines)
        self.assertEqual(order(lines=[OrderLine('Seats', Decimal('2500.00'), quantity=2)]).lines[0].total, 5000)
        with self.assertRaises(ValueError):
            order(lines=(OrderLine('Seat', Decimal('1.00')),))

    def test_required_fields(self):
        with self.assertRaises(ValueError):
            order(reference='')
        with self.assertRaises(ValueError):
            order(idempotency_key='')
        with self.assertRaises(ValueError):
            order(expires_at=datetime(2030, 1, 1))  # naive

    def test_callback_kinds_are_the_normalised_set(self):
        self.assertEqual(
            sorted(CallbackKind.values),
            sorted(
                ['paid', 'failed', 'expired', 'refunded', 'dispute_opened', 'dispute_won', 'dispute_lost', 'ignored']
            ),
        )
        with self.assertRaises(ValueError):
            CallbackResult(provider='x', event_id='e', kind='checkout.session.completed')
        with self.assertRaises(ValueError):
            CallbackResult(provider='x', event_id='', kind='paid')

    def test_refund_result_status(self):
        with self.assertRaises(ValueError):
            RefundResult(provider_refund_id='r', status='done', amount=Decimal('1'), currency='USD')

    def test_a_status_poll_becomes_a_callback(self):
        status = StatusResult(
            provider='stripe',
            state='paid',
            provider_session_id='cs_1',
            provider_payment_id='pi_1',
            amount=Decimal('10.00'),
            currency='USD',
        )
        callback = status.as_callback(reference='42')
        self.assertEqual((callback.kind, callback.event_id, callback.reference), ('paid', 'status:pi_1:paid', '42'))
        pending = StatusResult(provider='stripe', state='pending', provider_session_id='cs_1')
        self.assertEqual(pending.as_callback().kind, CallbackKind.IGNORED)
        with self.assertRaises(ValueError):
            StatusResult(provider='stripe', state='open')

    def test_the_interface_is_abstract(self):
        with self.assertRaises(TypeError):
            PaymentProvider()


class ConfTests(SimpleTestCase):
    def values(self, **kw):
        return lambda name: kw.get(name, '')

    def test_parse_enabled(self):
        self.assertEqual(conf.parse_enabled(' Stripe, ,mock,stripe '), ['stripe', 'mock'])
        self.assertEqual(conf.parse_enabled(['stripe']), ['stripe'])
        self.assertEqual(conf.parse_enabled(''), [])

    def test_the_default_config_still_needs_the_stripe_keys(self):
        self.assertEqual(
            conf.production_problems(['stripe'], mock_mode=False, get_setting=self.values()),
            ['STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET must be set'],
        )
        self.assertEqual(
            conf.production_problems(
                ['stripe'], mock_mode=False, get_setting=self.values(STRIPE_SECRET_KEY='sk_your_key_here')
            ),
            ['STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET must be set'],
        )
        ok = self.values(STRIPE_SECRET_KEY='sk_live_1', STRIPE_WEBHOOK_SECRET='whsec_1')
        self.assertEqual(conf.production_problems(['stripe'], mock_mode=False, get_setting=ok), [])

    def test_at_least_one_real_provider(self):
        problems = conf.production_problems([], mock_mode=False, get_setting=self.values())
        self.assertEqual(problems, ['PAYMENT_PROVIDERS_ENABLED must list at least one payment provider'])

    def test_the_mock_provider_is_refused_in_production(self):
        for enabled, mock_mode in ((['stripe', 'mock'], False), (['stripe'], True), (['mock'], False)):
            with self.subTest(enabled=enabled, mock_mode=mock_mode):
                ok = self.values(STRIPE_SECRET_KEY='sk_live_1', STRIPE_WEBHOOK_SECRET='whsec_1')
                problems = conf.production_problems(enabled, mock_mode=mock_mode, get_setting=ok)
                self.assertTrue(any('mock payment provider' in problem for problem in problems), problems)

    def test_unknown_providers_are_reported(self):
        problems = conf.production_problems(['paypal'], mock_mode=False, get_setting=self.values())
        self.assertEqual(problems, ['PAYMENT_PROVIDERS_ENABLED lists unknown payment providers: paypal'])


class StartupGuardTests(SimpleTestCase):
    """settings.py, imported in a fresh interpreter with a given environment."""

    BASE_ENV = {
        'DJANGO_SETTINGS_MODULE': 'eventhub_backend.settings',
        'DJANGO_SECRET_KEY': 'test-only-secret-key-for-the-guard',
        'DJANGO_ALLOWED_HOSTS': 'eventhub.example',
        'EMAIL_HOST_USER': 'mailer',
        'EMAIL_HOST_PASSWORD': 'mail-password',
        'EMAIL_BACKEND': '',
        'DJANGO_DEBUG': '0',
        'STRIPE_SECRET_KEY': '',
        'STRIPE_WEBHOOK_SECRET': '',
        'STRIPE_MOCK_MODE': '',
        'PAYMENTS_MOCK_MODE': '',
        'UNLEASH_ENABLED': '0',
    }
    SCRIPT = (
        'import json\n'
        'from django.conf import settings\n'
        'print(json.dumps([\n'
        '    settings.PAYMENT_PROVIDERS_ENABLED, settings.PAYMENTS_MOCK_MODE, settings.STRIPE_MOCK_MODE\n'
        ']))\n'
    )

    def load(self, **env):
        environment = {key: value for key, value in os.environ.items() if key not in self.BASE_ENV}
        environment.update(self.BASE_ENV)
        environment.pop('PAYMENT_PROVIDERS_ENABLED', None)
        environment.pop('EMAIL_BACKEND')
        environment.update(env)
        done = subprocess.run(  # noqa: S603 - fixed interpreter and script
            [sys.executable, '-c', self.SCRIPT],
            cwd=Path(settings.BASE_DIR),
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return done.returncode, done.stdout.strip(), done.stderr

    def assertRefused(self, fragment, **env):
        code, _, stderr = self.load(**env)
        self.assertNotEqual(code, 0)
        self.assertIn('ImproperlyConfigured', stderr)
        self.assertIn(fragment, stderr)

    def test_the_default_config_without_stripe_keys_is_refused(self):
        self.assertRefused('STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET must be set')

    def test_the_default_config_with_stripe_keys_starts(self):
        code, out, stderr = self.load(STRIPE_SECRET_KEY='sk_live_x', STRIPE_WEBHOOK_SECRET='whsec_x')
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(out), [['stripe'], False, False])

    def test_mock_mode_is_refused_in_production(self):
        keys = {'STRIPE_SECRET_KEY': 'sk_live_x', 'STRIPE_WEBHOOK_SECRET': 'whsec_x'}
        self.assertRefused('only allowed together with DJANGO_DEBUG=1', PAYMENTS_MOCK_MODE='1', **keys)
        self.assertRefused('only allowed together with DJANGO_DEBUG=1', STRIPE_MOCK_MODE='1', **keys)
        self.assertRefused('mock payment provider', PAYMENT_PROVIDERS_ENABLED='stripe,mock', **keys)

    def test_an_empty_provider_list_is_refused(self):
        self.assertRefused('must list at least one payment provider', PAYMENT_PROVIDERS_ENABLED='')

    def test_unknown_providers_are_refused_even_in_debug(self):
        self.assertRefused('unknown payment providers: paypal', DJANGO_DEBUG='1', PAYMENT_PROVIDERS_ENABLED='paypal')

    def test_stripe_mock_mode_is_a_deprecated_alias(self):
        code, out, stderr = self.load(DJANGO_DEBUG='1', STRIPE_MOCK_MODE='1')
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(out), [['stripe'], True, True])
        # The new name wins when it is set.
        code, out, stderr = self.load(DJANGO_DEBUG='1', STRIPE_MOCK_MODE='1', PAYMENTS_MOCK_MODE='0')
        self.assertEqual(json.loads(out), [['stripe'], False, False])
        code, out, stderr = self.load(DJANGO_DEBUG='1', PAYMENTS_MOCK_MODE='1')
        self.assertEqual(json.loads(out), [['stripe'], True, True])


class RegistryTests(SimpleTestCase):
    def test_builtins_are_registered(self):
        self.assertIn('mock', registry.registered_codes())

    def test_unknown_code(self):
        with self.assertRaises(registry.UnknownProvider):
            registry.get('paypal')

    @override_settings(PAYMENT_PROVIDERS_ENABLED=['stripe'], PAYMENTS_MOCK_MODE=False)
    def test_a_provider_that_is_not_enabled_is_not_handed_out(self):
        with self.assertRaises(registry.ProviderNotEnabled):
            registry.get('mock')
        self.assertIsInstance(registry.get('mock', require_enabled=False), MockProvider)
        self.assertNotIn('mock', [p.code for p in registry.enabled()])

    @override_settings(PAYMENT_PROVIDERS_ENABLED=['stripe'], PAYMENTS_MOCK_MODE=True)
    def test_mock_mode_enables_the_mock_provider(self):
        self.assertEqual(registry.enabled_codes(), ['stripe', 'mock'])
        self.assertIsInstance(registry.get('mock'), MockProvider)
        self.assertIn('mock', [p.code for p in registry.configured()])
        self.assertIn('mock', [p.code for p in registry.for_currency('KZT')])

    @override_settings(PAYMENT_PROVIDERS_ENABLED=['mock'], DEBUG=False, TESTING=False)
    def test_the_mock_provider_is_not_configured_outside_debug(self):
        self.assertEqual(registry.configured(), [])

    def test_codes_are_unique(self):
        class Other(MockProvider):
            pass

        with self.assertRaises(ValueError):
            registry.register(Other)

        class Nameless(MockProvider):
            code = ''

        with self.assertRaises(ValueError):
            registry.register(Nameless)


class MockProviderTests(SimpleTestCase):
    def setUp(self):
        self.provider = MockProvider()
        self.factory = RequestFactory()

    def test_checkout_redirects_to_the_success_page_and_reports_paid(self):
        result = self.provider.create_payment(order())
        self.assertTrue(result.session_id.startswith('mock_sess_'))
        self.assertEqual(result.redirect_url, f'/payment/success?session_id={result.session_id}')
        self.assertEqual(result.expires_at, EXPIRES)
        paid = result.immediate
        self.assertEqual((paid.kind, paid.reference), (CallbackKind.PAID, '42'))
        self.assertEqual((paid.amount, paid.currency), (Decimal('5000.00'), 'KZT'))
        self.assertEqual(paid.provider_session_id, result.session_id)
        self.assertEqual(paid.provider_payment_id, result.payment_id)

    def test_existing_query_parameters_are_kept(self):
        result = self.provider.create_payment(order(success_url='https://x.example/payment/success?booking_id=b1'))
        self.assertEqual(result.redirect_url, f'/payment/success?booking_id=b1&session_id={result.session_id}')

    def test_a_retry_returns_the_same_session(self):
        first = self.provider.create_payment(order())
        self.assertEqual(self.provider.create_payment(order()).session_id, first.session_id)
        other = self.provider.create_payment(order(idempotency_key='payment-42-attempt-2'))
        self.assertNotEqual(other.session_id, first.session_id)

    def test_refunds_succeed_idempotently(self):
        payment = FakePayment()
        first = self.provider.refund(payment, Decimal('100.00'), idempotency_key='refund-a', reason='test')
        again = self.provider.refund(payment, Decimal('100.00'), idempotency_key='refund-a', reason='test')
        self.assertEqual((first.status, first.amount, first.currency), ('succeeded', Decimal('100.00'), 'KZT'))
        self.assertEqual(first.provider_refund_id, again.provider_refund_id)
        with self.assertRaises(ProviderRejected):
            self.provider.refund(payment, Decimal('6000.00'), idempotency_key='refund-b', reason='')

    def test_status(self):
        self.assertEqual(self.provider.get_status(FakePayment(provider_session_id='mock_sess_1')).state, 'paid')
        self.assertEqual(self.provider.get_status(FakePayment()).state, 'pending')
        self.assertIsNone(self.provider.cancel_session(FakePayment()))

    def post(self, body):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        return self.factory.post('/api/v1/payments/callback/mock/', data=data, content_type='application/json')

    def test_simulated_callbacks(self):
        result = self.provider.handle_callback(
            self.post({'event_id': 'e1', 'kind': 'failed', 'reference': '42', 'amount': '10.00', 'currency': 'kzt'})
        )
        self.assertEqual((result.kind, result.reference, result.amount, result.currency), ('failed', '42', 10, 'KZT'))
        response = self.provider.callback_response(result, 'processed')
        self.assertEqual(json.loads(response.content), {'received': True, 'outcome': 'processed'})

    def test_malformed_callbacks_are_invalid(self):
        bodies = [
            b'not json',
            b'[1]',
            {'event_id': 'e', 'kind': 'bogus'},
            {'kind': 'paid'},
            {'event_id': 'e', 'kind': 'paid', 'amount': 'ten'},
            b'{"x": "' + b'a' * 20000 + b'"}',
        ]
        for body in bodies:
            with self.subTest(body=str(body)[:40]), self.assertRaises(InvalidCallback):
                self.provider.handle_callback(self.post(body))

    @override_settings(DEBUG=False, TESTING=False)
    def test_nothing_works_outside_debug(self):
        self.assertFalse(self.provider.is_configured())
        with self.assertRaises(ProviderRejected):
            self.provider.create_payment(order())
        with self.assertRaises(ProviderRejected):
            self.provider.refund(FakePayment(), Decimal('1.00'), idempotency_key='k', reason='')
        with self.assertRaises(InvalidCallback):
            self.provider.handle_callback(self.post({'event_id': 'e', 'kind': 'paid'}))
