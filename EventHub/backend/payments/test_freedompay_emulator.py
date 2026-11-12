"""End to end against the real Freedom Pay emulator (fpay-emulator/).

Skipped unless FPAY_EMULATOR_URL is set. The emulator must reach this test
process for the Result callback, so the test server listens on all
interfaces and FPAY_CALLBACK_HOST names this container on a shared network
(POSTGRES_CONN_MAX_AGE=0 so the live server's request threads do not keep
the test database open at teardown):

    docker run -d --name ehfp-emu --network ehfp-net \
        -e FPAY_MERCHANTS=12345:emulator-secret-for-tests ehfp-emu
    docker run --rm --network ehfp-net --name ehfp-test \
        -e FPAY_EMULATOR_URL=http://ehfp-emu:8080 -e FPAY_CALLBACK_HOST=ehfp-test \
        -e FPAY_MERCHANT_ID=12345 -e FPAY_SECRET=emulator-secret-for-tests \
        -e POSTGRES_CONN_MAX_AGE=0 \
        <backend image> python manage.py test payments.test_freedompay_emulator
"""

import base64
import os
import time
import unittest
from datetime import timedelta
from decimal import Decimal

import requests
from django.contrib.auth.models import User
from django.test import LiveServerTestCase, override_settings
from django.utils import timezone

from events.models import Category, Event, Registration
from payments.freedompay_flow import provider, start_checkout
from payments.models import Payment, PaymentEvent, Refund
from payments.providers.base import CallbackKind
from payments.services import refund_payment

EMULATOR = os.environ.get('FPAY_EMULATOR_URL', '').rstrip('/')
CALLBACK_HOST = os.environ.get('FPAY_CALLBACK_HOST', 'localhost')
MERCHANT = os.environ.get('FPAY_MERCHANT_ID', '12345')
SECRET = os.environ.get('FPAY_SECRET', '')
CONTROL_TOKEN = os.environ.get('FPAY_CONTROL_TOKEN', '')


@unittest.skipUnless(EMULATOR and SECRET, 'set FPAY_EMULATOR_URL and FPAY_SECRET to run against the emulator')
class EmulatorEndToEndTests(LiveServerTestCase):
    host = '0.0.0.0'  # noqa: S104 - the emulator container calls back into this test server

    def control(self, method, path, **kwargs):
        headers = {'X-Emulator-Token': CONTROL_TOKEN} if CONTROL_TOKEN else {}
        response = requests.request(method, f'{EMULATOR}/_emulator{path}', headers=headers, timeout=10, **kwargs)
        response.raise_for_status()
        return response.json()

    def setUp(self):
        # Idempotency keys (payment-<id>-attempt-<n>) repeat across test
        # databases: start from an empty emulator.
        self.control('POST', '/reset')

    def test_pay_confirm_and_refund_through_the_emulator(self):
        port = self.server_thread.port
        result_url = f'http://{CALLBACK_HOST}:{port}/api/v1/payments/callback/freedompay/'
        with override_settings(
            ALLOWED_HOSTS=['*'],
            PAYMENT_PROVIDERS_ENABLED=['stripe', 'freedompay'],
            FREEDOMPAY_API_URL=EMULATOR,
            FREEDOMPAY_MERCHANT_ID=MERCHANT,
            FREEDOMPAY_SECRET_KEY=SECRET,
            FREEDOMPAY_RESULT_URL=result_url,
            FREEDOMPAY_TESTING_MODE=True,
            FRONTEND_URL='http://frontend.test',
            JOBS_RUN_INLINE=False,
        ):
            organizer = User.objects.create_user(username='org', password='password123')
            buyer = User.objects.create_user(username='buyer', email='buyer@example.com', password='password123')
            event = Event.objects.create(
                title='Almaty Product Conference',
                description='Talks',
                organizer=organizer,
                category=Category.objects.create(name='Tech', icon='cpu'),
                date=timezone.now() + timedelta(days=14),
                location='Almaty',
                price=Decimal('5000.00'),
                currency='KZT',
                max_participants=100,
                status='published',
            )
            registration = Registration.objects.create(
                user=buyer, event=event, status='pending', seat_held_until=timezone.now() + timedelta(minutes=10)
            )

            checkout = start_checkout(registration)
            pg_id = checkout.result.session_id
            self.assertTrue(checkout.result.redirect_url.startswith('http'))
            self.assertTrue(base64.b64decode(checkout.result.raw['redirect_qr']).startswith(b'\x89PNG'))

            # The buyer pays on the emulator's page (driven by its control API).
            self.control('POST', f'/payments/{pg_id}/complete', json={})
            payment = checkout.payment
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                payment.refresh_from_db()
                if payment.status == 'completed':
                    break
                time.sleep(0.5)
            self.assertEqual(payment.status, 'completed')
            registration.refresh_from_db()
            self.assertEqual(registration.status, 'confirmed')
            self.assertEqual(PaymentEvent.objects.get(payment=payment).outcome, 'processed')
            # The emulator judged our signed XML reply valid (strict mode).
            deliveries = self.control('GET', f'/payments/{pg_id}')['deliveries']
            self.assertIn('ok', [entry.get('verdict') for entry in deliveries])

            # Partial, then full refund through `revoke`.
            refund_payment(payment=payment, amount='1500', reason='partial')
            self.assertEqual(provider().get_status(payment).state, CallbackKind.PAID)
            refund_payment(payment=Payment.objects.get(pk=payment.pk), reason='the rest')
            payment.refresh_from_db()
            self.assertEqual((payment.status, payment.refunded_amount), ('refunded', Decimal('5000.00')))
            self.assertEqual(provider().get_status(payment).state, CallbackKind.REFUNDED)
            self.assertEqual(Refund.objects.filter(payment=payment, status='succeeded').count(), 2)

    def test_group_booking_pay_confirm_and_refund_through_the_emulator(self):
        from bookings.models import Booking
        from bookings.services import create_booking, refund_booking
        from events.models import EventSeat, SeatMap

        port = self.server_thread.port
        result_url = f'http://{CALLBACK_HOST}:{port}/api/v1/payments/callback/freedompay/'
        with override_settings(
            ALLOWED_HOSTS=['*'],
            PAYMENT_PROVIDERS_ENABLED=['stripe', 'freedompay'],
            PAYMENTS_MOCK_MODE=True,  # must not shortcut a KZT booking
            STRIPE_MOCK_MODE=True,
            FREEDOMPAY_API_URL=EMULATOR,
            FREEDOMPAY_MERCHANT_ID=MERCHANT,
            FREEDOMPAY_SECRET_KEY=SECRET,
            FREEDOMPAY_RESULT_URL=result_url,
            FREEDOMPAY_TESTING_MODE=True,
            FRONTEND_URL='http://frontend.test',
            JOBS_RUN_INLINE=False,
        ):
            organizer = User.objects.create_user(username='org', password='password123')
            buyer = User.objects.create_user(username='buyer', email='buyer@example.com', password='password123')
            event = Event.objects.create(
                title='Almaty Jazz Night',
                description='Music',
                organizer=organizer,
                category=Category.objects.create(name='Music', icon='music'),
                date=timezone.now() + timedelta(days=14),
                location='Almaty',
                price=Decimal('7500.00'),
                currency='KZT',
                max_participants=100,
                status='published',
            )
            seat_map = SeatMap.objects.create(event=event, rows=1, cols=3)
            seats = [EventSeat.objects.create(seat_map=seat_map, row=1, col=col) for col in (1, 2, 3)]
            booking = create_booking(user=buyer, event=event, seat_ids=[s.pk for s in seats])

            from bookings.payments import create_booking_checkout

            answer = create_booking_checkout(booking)
            self.assertEqual((answer['provider'], answer['amount']), ('freedompay', '22500.00'))
            self.assertTrue(answer['qr_code'].startswith('data:image/png;base64,'))
            payment = Payment.objects.get(pk=answer['payment_id'])
            self.control('POST', f'/payments/{payment.provider_session_id}/complete', json={})
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                booking.refresh_from_db()
                if booking.status == Booking.Status.CONFIRMED:
                    break
                time.sleep(0.5)
            self.assertEqual(booking.status, Booking.Status.CONFIRMED)
            self.assertEqual(booking.amount_paid, Decimal('22500.00'))
            payment.refresh_from_db()
            self.assertEqual(payment.status, 'completed')

            refund_booking(booking, actor=organizer, reason='Venue change')
            payment.refresh_from_db()
            self.assertEqual((payment.status, payment.refunded_amount), ('refunded', Decimal('22500.00')))
            self.assertEqual(provider().get_status(payment).state, CallbackKind.REFUNDED)
