"""StripeProvider against a local fake Stripe API (real SDK, real HTTP).

A tiny HTTP server on 127.0.0.1 answers with Stripe-shaped JSON and records
every request, so the tests check what really goes over the wire: paths,
form-encoded parameters and headers (API version, idempotency key). Webhooks
are signed for real with HMAC-SHA256 over `<timestamp>.<payload>`.
"""

import hashlib
import hmac
import json
import socket
import threading
import time
from collections import deque
from datetime import timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import stripe
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import timezone

from events import billing
from payments.providers import registry
from payments.providers import stripe as stripe_provider
from payments.providers.base import (
    CallbackKind,
    InvalidCallback,
    OrderLine,
    PaymentOrder,
    ProviderRejected,
    ProviderUnavailable,
)
from payments.providers.stripe import StripeProvider, from_minor_units, to_minor_units

SECRET_KEY = 'sk_test_fake_123'
WEBHOOK_SECRET = 'whsec_test_fake_456'


class FakeStripe:
    """Records requests and replays queued (status, body, headers) answers."""

    def __init__(self):
        self.requests = []
        self.answers = deque()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self):
                length = int(self.headers.get('Content-Length') or 0)
                body = self.rfile.read(length).decode() if length else ''
                url = urlsplit(self.path)
                fake.requests.append(
                    {
                        'method': self.command,
                        'path': url.path,
                        'query': parse_qs(url.query),
                        'headers': {key.lower(): value for key, value in self.headers.items()},
                        'form': {key: values[0] for key, values in parse_qs(body, keep_blank_values=True).items()},
                    }
                )
                if fake.answers:
                    status, payload, headers = fake.answers.popleft()
                else:
                    status, payload, headers = 500, {'error': {'type': 'api_error', 'message': 'no answer'}}, {}
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Request-Id', f'req_{len(fake.requests)}')
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_DELETE = _serve

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'

    def answer(self, status, payload, headers=None):
        self.answers.append((status, payload, headers or {}))

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def session_json(**kw):
    data = {
        'id': 'cs_test_a1',
        'object': 'checkout.session',
        'amount_total': 500000,
        'currency': 'kzt',
        'client_reference_id': '42',
        'expires_at': int((timezone.now() + timedelta(minutes=31)).timestamp()),
        'livemode': False,
        'metadata': {'payment_id': '42'},
        'mode': 'payment',
        'payment_intent': None,
        'payment_status': 'unpaid',
        'status': 'open',
        'url': 'https://checkout.stripe.com/c/pay/cs_test_a1',
    }
    data.update(kw)
    return data


def refund_json(**kw):
    data = {
        'id': 're_test_1',
        'object': 'refund',
        'amount': 250000,
        'currency': 'kzt',
        'payment_intent': 'pi_test_1',
        'status': 'succeeded',
        'metadata': {'payment_id': '42'},
    }
    data.update(kw)
    return data


def error_json(error_type, message='Something went wrong', code=None):
    error = {'type': error_type, 'message': message}
    if code:
        error['code'] = code
    return {'error': error}


def order(**kw):
    data = {
        'reference': '42',
        'amount': Decimal('5000.00'),
        'currency': 'KZT',
        'description': 'Gig',
        'success_url': 'https://eventhub.example/payment/success',
        'cancel_url': 'https://eventhub.example/payment/cancel',
        'expires_at': timezone.now() + timedelta(minutes=31),
        'idempotency_key': 'payment-42-attempt-1',
        'customer_email': 'buyer@example.com',
    }
    data.update(kw)
    return PaymentOrder(**data)


class FakePayment:
    def __init__(self, **kw):
        self.pk = kw.get('pk', 42)
        self.provider_session_id = kw.get('provider_session_id', 'cs_test_a1')
        self.provider_payment_id = kw.get('provider_payment_id', 'pi_test_1')
        self.amount = kw.get('amount', Decimal('5000.00'))
        self.currency = kw.get('currency', 'kzt')


class StripeHttpBase(SimpleTestCase):
    def setUp(self):
        self.fake = FakeStripe()
        self.addCleanup(self.fake.close)
        overrides = override_settings(
            STRIPE_SECRET_KEY=SECRET_KEY,
            STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET,
            STRIPE_API_BASE=self.fake.url,
            STRIPE_MAX_NETWORK_RETRIES=0,
        )
        overrides.enable()
        self.addCleanup(overrides.disable)
        self.provider = StripeProvider()

    def last(self):
        return self.fake.requests[-1]


class CheckoutTests(StripeHttpBase):
    def test_a_session_is_created_with_the_order(self):
        stripe_expiry = int((timezone.now() + timedelta(minutes=31)).timestamp())
        self.fake.answer(200, session_json(expires_at=stripe_expiry))
        result = self.provider.create_payment(order())

        request = self.last()
        self.assertEqual((request['method'], request['path']), ('POST', '/v1/checkout/sessions'))
        form = request['form']
        self.assertEqual(form['mode'], 'payment')
        self.assertEqual(form['payment_method_types[0]'], 'card')
        self.assertEqual(form['line_items[0][price_data][currency]'], 'kzt')
        self.assertEqual(form['line_items[0][price_data][unit_amount]'], '500000')
        self.assertEqual(form['line_items[0][price_data][product_data][name]'], 'Gig')
        self.assertEqual(form['line_items[0][quantity]'], '1')
        self.assertEqual(
            form['success_url'], 'https://eventhub.example/payment/success?session_id={CHECKOUT_SESSION_ID}'
        )
        self.assertEqual(form['cancel_url'], 'https://eventhub.example/payment/cancel')
        self.assertEqual(form['client_reference_id'], '42')
        self.assertEqual(form['metadata[payment_id]'], '42')
        self.assertEqual(form['payment_intent_data[metadata][payment_id]'], '42')
        self.assertEqual(form['customer_email'], 'buyer@example.com')
        self.assertNotIn('locale', form)

        headers = request['headers']
        self.assertEqual(headers['idempotency-key'], 'payment-42-attempt-1')
        self.assertEqual(headers['stripe-version'], stripe_provider.API_VERSION)
        self.assertEqual(headers['authorization'], f'Bearer {SECRET_KEY}')
        self.assertTrue(headers['content-type'].startswith('application/x-www-form-urlencoded'))
        self.assertIn('EventHub', headers['user-agent'])

        self.assertEqual(result.session_id, 'cs_test_a1')
        self.assertEqual(result.redirect_url, 'https://checkout.stripe.com/c/pay/cs_test_a1')
        self.assertEqual(int(result.expires_at.timestamp()), stripe_expiry)
        self.assertIsNone(result.immediate)

    def test_one_line_per_seat_and_the_booking_query_is_kept(self):
        self.fake.answer(200, session_json())
        lines = (
            OrderLine('Gig — Seat 1-1', Decimal('2500.00'), description='Vip zone'),
            OrderLine('Gig — Seat 1-2', Decimal('2500.00')),
        )
        self.provider.create_payment(
            order(lines=lines, success_url='https://eventhub.example/payment/success?booking_id=b1', locale='ru')
        )
        form = self.last()['form']
        self.assertEqual(
            form['success_url'],
            'https://eventhub.example/payment/success?booking_id=b1&session_id={CHECKOUT_SESSION_ID}',
        )
        self.assertEqual(form['line_items[0][price_data][product_data][name]'], 'Gig — Seat 1-1')
        self.assertEqual(form['line_items[0][price_data][product_data][description]'], 'Vip zone')
        self.assertEqual(form['line_items[1][price_data][unit_amount]'], '250000')
        self.assertNotIn('line_items[1][price_data][product_data][description]', form)
        self.assertEqual(form['locale'], 'ru')

    def test_zero_and_three_decimal_currencies(self):
        for currency, amount, minor in (('JPY', '1500', '1500'), ('KWD', '12.34', '12340'), ('USD', '19.99', '1999')):
            with self.subTest(currency=currency):
                self.fake.answer(200, session_json(currency=currency.lower()))
                self.provider.create_payment(order(currency=currency, amount=Decimal(amount)))
                form = self.last()['form']
                self.assertEqual(form['line_items[0][price_data][currency]'], currency.lower())
                self.assertEqual(form['line_items[0][price_data][unit_amount]'], minor)

    def test_the_session_lifetime_stays_within_stripes_limits(self):
        for wanted, low, high in (
            (timedelta(minutes=10), timedelta(minutes=31), timedelta(minutes=32)),
            (timedelta(minutes=45), timedelta(minutes=45), timedelta(minutes=46)),
            (timedelta(hours=48), timedelta(hours=23, minutes=54), timedelta(hours=24)),
        ):
            with self.subTest(wanted=wanted):
                self.fake.answer(200, session_json())
                now = timezone.now()
                self.provider.create_payment(order(expires_at=now + wanted))
                expires = int(self.last()['form']['expires_at'])
                self.assertGreaterEqual(expires, int((now + low).timestamp()) - 1)
                self.assertLessEqual(expires, int((now + high).timestamp()) + 1)

    @override_settings(STRIPE_MAX_NETWORK_RETRIES=1)
    def test_a_retry_after_a_server_error_reuses_the_idempotency_key(self):
        self.fake.answer(500, error_json('api_error'), {'Stripe-Should-Retry': 'true'})
        self.fake.answer(200, session_json())
        result = self.provider.create_payment(order())
        self.assertEqual(result.session_id, 'cs_test_a1')
        self.assertEqual(len(self.fake.requests), 2)
        keys = {request['headers']['idempotency-key'] for request in self.fake.requests}
        self.assertEqual(keys, {'payment-42-attempt-1'})

    def test_errors_are_mapped(self):
        cases = [
            (400, error_json('invalid_request_error', 'No such price', 'resource_missing'), ProviderRejected),
            (401, error_json('invalid_request_error', 'Invalid API Key'), ProviderRejected),
            (429, error_json('invalid_request_error', 'Too many requests', 'rate_limit'), ProviderUnavailable),
            (500, error_json('api_error'), ProviderUnavailable),
            (503, error_json('api_error'), ProviderUnavailable),
        ]
        for status, payload, expected in cases:
            with self.subTest(status=status):
                self.fake.answer(status, payload)
                with self.assertRaises(expected) as raised:
                    self.provider.create_payment(order())
                self.assertEqual(raised.exception.provider, 'stripe')

    def test_global_sdk_state_is_left_alone(self):
        # The legacy services still use the module-level API.
        before = (stripe.api_key, stripe.api_version, stripe.max_network_retries, stripe.api_base)
        self.fake.answer(200, session_json())
        self.provider.create_payment(order())
        self.assertEqual((stripe.api_key, stripe.api_version, stripe.max_network_retries, stripe.api_base), before)


class ConnectionTests(SimpleTestCase):
    def test_an_unreachable_stripe_is_unavailable(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        with override_settings(
            STRIPE_SECRET_KEY=SECRET_KEY, STRIPE_API_BASE=f'http://127.0.0.1:{port}', STRIPE_MAX_NETWORK_RETRIES=0
        ):
            with self.assertRaises(ProviderUnavailable):
                StripeProvider().create_payment(order())
            with self.assertRaises(ProviderUnavailable):
                StripeProvider().refund(FakePayment(), Decimal('1.00'), idempotency_key='refund-x', reason='')

    @override_settings(STRIPE_SECRET_KEY='', STRIPE_WEBHOOK_SECRET='')
    def test_without_keys_nothing_is_sent(self):
        provider = StripeProvider()
        self.assertFalse(provider.is_configured())
        with self.assertRaises(ProviderRejected):
            provider.create_payment(order())


class RefundTests(StripeHttpBase):
    def test_a_partial_refund(self):
        self.fake.answer(200, refund_json())
        result = self.provider.refund(
            FakePayment(), Decimal('2500.00'), idempotency_key='refund-7f3a', reason='Organizer refund'
        )
        request = self.last()
        self.assertEqual((request['method'], request['path']), ('POST', '/v1/refunds'))
        self.assertEqual(request['form']['payment_intent'], 'pi_test_1')
        self.assertEqual(request['form']['amount'], '250000')
        self.assertEqual(request['form']['metadata[payment_id]'], '42')
        self.assertEqual(request['form']['metadata[reason]'], 'Organizer refund')
        self.assertEqual(request['headers']['idempotency-key'], 'refund-7f3a')
        self.assertEqual(
            (result.provider_refund_id, result.status, result.amount, result.currency),
            ('re_test_1', 'succeeded', Decimal('2500.00'), 'KZT'),
        )

    def test_a_full_refund_sends_no_amount(self):
        self.fake.answer(200, refund_json(amount=500000, status='pending'))
        result = self.provider.refund(FakePayment(), None, idempotency_key='refund-full', reason='')
        self.assertNotIn('amount', self.last()['form'])
        self.assertEqual((result.status, result.amount), ('pending', Decimal('5000.00')))

    def test_refund_currencies(self):
        for currency, amount, minor in (('jpy', '1500', '1500'), ('kwd', '12.34', '12340')):
            with self.subTest(currency=currency):
                self.fake.answer(200, refund_json(amount=int(minor), currency=currency))
                result = self.provider.refund(
                    FakePayment(currency=currency, amount=Decimal(amount)),
                    Decimal(amount),
                    idempotency_key=f'refund-{currency}',
                    reason='',
                )
                self.assertEqual(self.last()['form']['amount'], minor)
                self.assertEqual((result.amount, result.currency), (Decimal(amount), currency.upper()))

    def test_failed_and_cancelled_refunds(self):
        for status in ('failed', 'canceled'):
            with self.subTest(status=status):
                self.fake.answer(200, refund_json(status=status, failure_reason='expired_or_canceled_card'))
                result = self.provider.refund(FakePayment(), Decimal('1.00'), idempotency_key=f'k-{status}', reason='')
                self.assertEqual(result.status, 'failed')
                self.assertEqual(result.raw['failure_reason'], 'expired_or_canceled_card')

    def test_refund_errors_are_mapped(self):
        cases = [
            (
                400,
                error_json('invalid_request_error', 'Charge already refunded', 'charge_already_refunded'),
                ProviderRejected,
            ),
            (
                400,
                error_json('idempotency_error', 'Keys for idempotent requests can only be used once'),
                ProviderRejected,
            ),
            (402, error_json('card_error', 'Your card was declined', 'card_declined'), ProviderRejected),
            (403, error_json('invalid_request_error', 'Forbidden'), ProviderRejected),
            (404, error_json('invalid_request_error', 'No such payment_intent', 'resource_missing'), ProviderRejected),
            (429, error_json('rate_limit_error', 'Too many requests'), ProviderUnavailable),
            (500, error_json('api_error', 'Internal error'), ProviderUnavailable),
            (502, error_json('api_error', 'Bad gateway'), ProviderUnavailable),
        ]
        for status, payload, expected in cases:
            with self.subTest(status=status, error=payload['error']['type']):
                self.fake.answer(status, payload)
                with self.assertRaises(expected) as raised:
                    self.provider.refund(FakePayment(), Decimal('1.00'), idempotency_key='refund-err', reason='')
                self.assertEqual(raised.exception.code, payload['error'].get('code', '') or '')

    def test_a_payment_without_intent_is_refused_without_a_request(self):
        with self.assertRaises(ProviderRejected):
            self.provider.refund(FakePayment(provider_payment_id=''), Decimal('1.00'), idempotency_key='k', reason='')
        self.assertEqual(self.fake.requests, [])


class StatusTests(StripeHttpBase):
    def intent(self, **kw):
        data = {
            'id': 'pi_test_1',
            'object': 'payment_intent',
            'amount': 500000,
            'currency': 'kzt',
            'status': 'succeeded',
            'latest_charge': {'id': 'ch_1', 'object': 'charge', 'refunded': False, 'disputed': False},
        }
        data.update(kw)
        return data

    def test_paid(self):
        self.fake.answer(200, session_json(status='complete', payment_status='paid', payment_intent='pi_test_1'))
        self.fake.answer(200, self.intent())
        status = self.provider.get_status(FakePayment(provider_payment_id=''))
        session_request, intent_request = self.fake.requests
        self.assertEqual(
            (session_request['method'], session_request['path']), ('GET', '/v1/checkout/sessions/cs_test_a1')
        )
        self.assertEqual(intent_request['path'], '/v1/payment_intents/pi_test_1')
        self.assertEqual(intent_request['query'], {'expand[0]': ['latest_charge']})
        self.assertEqual(
            (status.state, status.provider_payment_id, status.amount, status.currency),
            ('paid', 'pi_test_1', Decimal('5000.00'), 'KZT'),
        )
        self.assertEqual(status.as_callback(reference='42').kind, CallbackKind.PAID)

    def test_refunded_and_disputed_charges(self):
        for charge, state in (({'refunded': True}, 'refunded'), ({'disputed': True}, 'dispute_opened')):
            with self.subTest(state=state):
                self.fake.answer(
                    200, session_json(status='complete', payment_status='paid', payment_intent='pi_test_1')
                )
                self.fake.answer(200, self.intent(latest_charge={'id': 'ch_1', 'object': 'charge', **charge}))
                self.assertEqual(self.provider.get_status(FakePayment()).state, state)

    def test_open_and_expired_sessions(self):
        self.fake.answer(200, session_json())
        self.assertEqual(self.provider.get_status(FakePayment(provider_payment_id='')).state, 'pending')
        self.assertEqual(len(self.fake.requests), 1)  # no intent yet: nothing else to ask
        self.fake.answer(200, session_json(status='expired'))
        self.assertEqual(self.provider.get_status(FakePayment(provider_payment_id='')).state, 'expired')

    def test_a_cancelled_intent_is_failed(self):
        self.fake.answer(200, self.intent(status='canceled', latest_charge=None))
        status = self.provider.get_status(FakePayment(provider_session_id=''))
        self.assertEqual((status.state, status.amount), ('failed', Decimal('5000.00')))

    def test_errors(self):
        self.fake.answer(404, error_json('invalid_request_error', 'No such checkout.session', 'resource_missing'))
        with self.assertRaises(ProviderRejected):
            self.provider.get_status(FakePayment())


class CancelSessionTests(StripeHttpBase):
    def test_an_open_session_is_expired(self):
        self.fake.answer(200, session_json(status='expired'))
        self.assertIsNone(self.provider.cancel_session(FakePayment()))
        self.assertEqual(
            (self.last()['method'], self.last()['path']), ('POST', '/v1/checkout/sessions/cs_test_a1/expire')
        )

    def test_failures_are_swallowed(self):
        self.fake.answer(400, error_json('invalid_request_error', 'Session is already complete'))
        self.assertIsNone(self.provider.cancel_session(FakePayment()))

    def test_non_stripe_ids_are_skipped(self):
        self.provider.cancel_session(FakePayment(provider_session_id='mock_sess_1'))
        self.provider.cancel_session(FakePayment(provider_session_id=''))
        self.assertEqual(self.fake.requests, [])


def signed(payload: str, secret=WEBHOOK_SECRET, timestamp=None) -> str:
    timestamp = int(time.time()) if timestamp is None else timestamp
    signature = hmac.new(secret.encode(), f'{timestamp}.{payload}'.encode(), hashlib.sha256).hexdigest()
    return f't={timestamp},v1={signature}'


def event(event_type, obj, event_id='evt_1'):
    return json.dumps(
        {
            'id': event_id,
            'object': 'event',
            'api_version': stripe_provider.API_VERSION,
            'created': int(time.time()),
            'livemode': False,
            'type': event_type,
            'data': {'object': obj},
        }
    )


@override_settings(STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET, STRIPE_SECRET_KEY=SECRET_KEY)
class WebhookTests(SimpleTestCase):
    def setUp(self):
        self.provider = StripeProvider()
        self.factory = RequestFactory()

    def deliver(self, payload, signature=None):
        headers = {} if signature is False else {'HTTP_STRIPE_SIGNATURE': signature or signed(payload)}
        request = self.factory.post('/api/payments/webhook/', data=payload, content_type='application/json', **headers)
        return self.provider.handle_callback(request)

    def session(self, **kw):
        return session_json(status='complete', payment_status='paid', payment_intent='pi_test_1', **kw)

    def test_a_paid_session(self):
        result = self.deliver(event('checkout.session.completed', self.session(), 'evt_paid'))
        self.assertEqual(result.event_id, 'evt_paid')
        self.assertEqual(result.kind, CallbackKind.PAID)
        self.assertEqual(
            (result.reference, result.provider_session_id, result.provider_payment_id),
            ('42', 'cs_test_a1', 'pi_test_1'),
        )
        self.assertEqual((result.amount, result.currency), (Decimal('5000.00'), 'KZT'))
        self.assertEqual(result.raw['type'], 'checkout.session.completed')
        self.assertEqual(json.loads(self.provider.callback_response(result, 'processed').content), {'received': True})

    def test_every_event_kind(self):
        dispute = {'id': 'dp_1', 'object': 'dispute', 'amount': 500000, 'currency': 'kzt', 'charge': 'ch_1',
                   'payment_intent': 'pi_test_1', 'reason': 'fraudulent'}  # fmt: skip
        charge = {'id': 'ch_1', 'object': 'charge', 'amount': 500000, 'amount_refunded': 250000, 'currency': 'kzt',
                  'payment_intent': 'pi_test_1', 'refunded': False, 'metadata': {'payment_id': '42'}}  # fmt: skip
        cases = [
            ('checkout.session.completed', self.session(), 'paid'),
            ('checkout.session.completed', session_json(status='complete', payment_status='unpaid'), 'ignored'),
            ('checkout.session.async_payment_succeeded', self.session(), 'paid'),
            ('checkout.session.async_payment_failed', session_json(status='complete'), 'failed'),
            ('checkout.session.expired', session_json(status='expired'), 'expired'),
            ('charge.refunded', charge, 'refunded'),
            ('charge.dispute.created', {**dispute, 'status': 'needs_response'}, 'dispute_opened'),
            ('charge.dispute.closed', {**dispute, 'status': 'won'}, 'dispute_won'),
            ('charge.dispute.closed', {**dispute, 'status': 'warning_closed'}, 'dispute_won'),
            ('charge.dispute.closed', {**dispute, 'status': 'lost'}, 'dispute_lost'),
            ('payment_intent.created', {'id': 'pi_test_1', 'object': 'payment_intent'}, 'ignored'),
            ('customer.created', {'id': 'cus_1', 'object': 'customer'}, 'ignored'),
        ]
        for number, (event_type, obj, kind) in enumerate(cases):
            with self.subTest(event_type=event_type, kind=kind):
                result = self.deliver(event(event_type, obj, f'evt_{number}'))
                self.assertEqual(result.kind, kind)
                self.assertEqual(result.event_id, f'evt_{number}')

        refunded = self.deliver(event('charge.refunded', charge, 'evt_r'))
        self.assertEqual((refunded.provider_payment_id, refunded.reference), ('pi_test_1', '42'))
        self.assertEqual((refunded.amount, refunded.currency), (Decimal('2500.00'), 'KZT'))
        lost = self.deliver(event('charge.dispute.closed', {**dispute, 'status': 'lost'}, 'evt_l'))
        self.assertEqual((lost.provider_payment_id, lost.amount, lost.raw['reason']), ('pi_test_1', 5000, 'fraudulent'))

    def test_amounts_in_zero_and_three_decimal_currencies(self):
        for currency, minor, amount in (('jpy', 1500, Decimal('1500')), ('kwd', 12340, Decimal('12.34'))):
            with self.subTest(currency=currency):
                obj = self.session(currency=currency, amount_total=minor)
                result = self.deliver(event('checkout.session.completed', obj, f'evt_{currency}'))
                self.assertEqual((result.amount, result.currency), (amount, currency.upper()))
        # 12.345 KWD does not fit the ledger: reported as unknown, never rounded.
        odd = self.deliver(event('checkout.session.completed', self.session(currency='kwd', amount_total=12345), 'e3'))
        self.assertIsNone(odd.amount)

    def test_a_bad_signature_is_rejected(self):
        payload = event('checkout.session.completed', self.session())
        for signature in (signed(payload, secret='whsec_other'), signed(payload + ' '), 't=1,v1=00', 'garbage'):
            with self.subTest(signature=signature[:20]), self.assertRaises(InvalidCallback) as raised:
                self.deliver(payload, signature)
            self.assertEqual(raised.exception.code, 'signature')

    def test_a_missing_signature_is_rejected(self):
        with self.assertRaises(InvalidCallback):
            self.deliver(event('checkout.session.completed', self.session()), signature=False)

    def test_a_replayed_old_delivery_is_rejected(self):
        payload = event('checkout.session.completed', self.session())
        with self.assertRaises(InvalidCallback) as raised:
            self.deliver(payload, signed(payload, timestamp=int(time.time()) - 600))
        self.assertIn('tolerance', str(raised.exception).lower())
        # Within the tolerance it is accepted.
        self.assertEqual(self.deliver(payload, signed(payload, timestamp=int(time.time()) - 60)).kind, 'paid')

    def test_malformed_but_signed_payloads_are_rejected(self):
        for payload in ('not json', json.dumps({'id': 'evt_1'}), json.dumps({'id': 'evt_1', 'data': {'object': 1}})):
            with self.subTest(payload=payload[:20]), self.assertRaises(InvalidCallback):
                self.deliver(payload)

    @override_settings(STRIPE_WEBHOOK_SECRET='')
    def test_without_a_secret_nothing_is_accepted(self):
        with self.assertRaises(InvalidCallback):
            self.deliver(event('checkout.session.completed', self.session()))


class UnitsAndRegistrationTests(SimpleTestCase):
    def test_minor_units(self):
        for amount, currency, minor in (
            ('50.00', 'usd', 5000),
            ('19.999', 'EUR', 2000),
            ('1500', 'JPY', 1500),
            ('1500.5', 'jpy', 1501),
            ('12.34', 'KWD', 12340),
            ('5000.00', 'KZT', 500000),
        ):
            with self.subTest(currency=currency, amount=amount):
                self.assertEqual(to_minor_units(Decimal(amount), currency), minor)
        self.assertEqual(from_minor_units(500000, 'kzt'), Decimal('5000.00'))
        self.assertEqual(from_minor_units(1500, 'JPY'), Decimal('1500'))
        self.assertEqual(from_minor_units(12340, 'KWD'), Decimal('12.34'))
        self.assertIsNone(from_minor_units(12345, 'KWD'))
        self.assertIsNone(from_minor_units(None, 'USD'))
        self.assertIsNone(from_minor_units('x', 'USD'))

    def test_billing_keeps_working_for_old_callers(self):
        self.assertIs(billing.to_minor_units, to_minor_units)
        self.assertIs(billing.ZERO_DECIMAL_CURRENCIES, stripe_provider.ZERO_DECIMAL_CURRENCIES)
        self.assertIs(billing.THREE_DECIMAL_CURRENCIES, stripe_provider.THREE_DECIMAL_CURRENCIES)

    def test_the_api_version_is_the_one_of_the_pinned_sdk(self):
        # An SDK upgrade that moves the API version must update API_VERSION
        # (and be reviewed against Stripe's changelog) deliberately.
        self.assertEqual(stripe_provider.API_VERSION, stripe.api_version)

    @override_settings(
        PAYMENT_PROVIDERS_ENABLED=['stripe'],
        PAYMENTS_MOCK_MODE=False,
        STRIPE_SECRET_KEY=SECRET_KEY,
        STRIPE_WEBHOOK_SECRET='',
    )
    def test_registration_and_configuration(self):
        self.assertIn('stripe', registry.registered_codes())
        self.assertIsInstance(registry.get('stripe'), StripeProvider)
        self.assertEqual(registry.configured(), [])  # the webhook secret is missing
        with override_settings(STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET):
            self.assertEqual([p.code for p in registry.configured()], ['stripe'])
