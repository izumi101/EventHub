"""Freedom Pay for group bookings: checkout routing, the Result callback,
late / wrong / duplicate payments, the status endpoint and refunds.

Same fake gateway as test_freedompay.py: only `requests.post` is replaced,
the provider and its signatures run for real.
"""

import base64
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from bookings.models import Booking
from bookings.services import release_expired_bookings
from events.models import EventSeat, Notification, SeatMap
from events.services.lifecycle import cancel_event
from payments.models import Payment, PaymentEvent, Refund
from payments.test_freedompay import (
    CALLBACK_PATH,
    FP_SETTINGS,
    PNG,
    FakeGateway,
    FixturesMixin,
    callback_form,
    reply_fields,
)


class BookingFixtures(FixturesMixin):
    def make_seats(self, event, count=3):
        seat_map = SeatMap.objects.create(event=event, rows=1, cols=count)
        return [EventSeat.objects.create(seat_map=seat_map, row=1, col=col) for col in range(1, count + 1)]

    def make_booking(self, event=None, seats=2, user=None):
        event = event or self.event
        all_seats = self.make_seats(event, count=max(seats, 1) + 1)
        self.client.force_authenticate(user=user or self.buyer)
        response = self.client.post(
            '/api/v1/bookings/',
            {'event': event.pk, 'seat_ids': [s.pk for s in all_seats[:seats]]},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        return Booking.objects.get(pk=response.data['id'])


@override_settings(**FP_SETTINGS)
class FreedomPayBookingTests(BookingFixtures, APITestCase):
    def setUp(self):
        cache.clear()
        self.make_world()
        self.booking = self.make_booking()  # 2 seats x 5000 KZT
        self.gateway = FakeGateway()
        patcher = patch('payments.providers.freedompay.requests.post', self.gateway)
        patcher.start()
        self.addCleanup(patcher.stop)

    # helpers

    def checkout(self, booking=None, user=None):
        self.client.force_authenticate(user=user or self.buyer)
        return self.client.post(f'/api/v1/bookings/{(booking or self.booking).pk}/checkout/')

    def opened(self):
        response = self.checkout()
        self.assertEqual(response.status_code, 200, response.data)
        payment = Payment.objects.get(pk=response.data['payment_id'])
        return payment, payment.provider_session_id

    def notify(self, payment_id, order_id, **kw):
        kw.setdefault('amount', '10000')
        self.client.force_authenticate(user=None)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                CALLBACK_PATH,
                data=callback_form(payment_id, order_id, **kw),
                content_type='application/x-www-form-urlencoded',
            )
        return response, dict(reply_fields(response))

    def paid(self):
        payment, pid = self.opened()
        self.gateway.pay(pid)
        _, reply = self.notify(pid, payment.pk)
        self.assertEqual(reply['pg_status'], 'ok')
        payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)
        return payment, pid

    def seats_available(self):
        return list(EventSeat.objects.filter(booking_seat__booking=self.booking).values_list('is_available', flat=True))

    # checkout routing

    def test_a_kzt_booking_opens_freedom_pay_with_a_qr_code_even_in_mock_mode(self):
        with override_settings(PAYMENTS_MOCK_MODE=True, STRIPE_MOCK_MODE=True):
            response = self.checkout()
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data
        self.assertEqual((data['provider'], data['mock']), ('freedompay', False))
        self.assertEqual(data['checkout_url'], 'http://fpay.test/pay.html?customer=1030000000001')
        self.assertEqual(data['qr_code'], 'data:image/png;base64,' + base64.b64encode(PNG).decode())
        self.assertEqual((data['amount'], data['currency']), ('10000.00', 'KZT'))
        payment = Payment.objects.get(pk=data['payment_id'])
        self.assertEqual((payment.booking_id, payment.registration_id), (self.booking.pk, None))
        self.assertEqual(
            (payment.provider, payment.provider_session_id, payment.status, payment.attempt, payment.amount),
            ('freedompay', '1030000000001', 'pending', 1, Decimal('10000.00')),
        )
        # Not paid by the mock: the booking waits for the gateway.
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.HOLDING)
        params = self.gateway.calls[0][1]
        self.assertEqual((params['pg_order_id'], params['pg_amount']), (str(payment.pk), '10000.00'))
        self.assertIn('Almaty Product Conference', params['pg_description'])
        self.assertIn('2 seats', params['pg_description'])
        self.assertEqual(params['pg_generate_qr'], '1')
        self.assertEqual(
            params['pg_success_url'],
            f'http://frontend.test/payment/success?provider=freedompay&payment={payment.pk}'
            f'&booking_id={self.booking.pk}',
        )
        self.assertTrue(params['pg_failure_url'].startswith('http://frontend.test/payment/cancel?provider=freedompay'))
        # The hold covers the payment page's lifetime.
        lifetime = int(params['pg_lifetime'])
        self.assertGreaterEqual(self.booking.hold_expires_at, timezone.now() + timedelta(seconds=lifetime))

    def test_a_usd_booking_stays_on_the_mock_in_mock_mode(self):
        usd_event = self.make_event('Workshop', currency='USD', price=Decimal('10.00'))
        booking = self.make_booking(usd_event)
        with override_settings(PAYMENTS_MOCK_MODE=True, STRIPE_MOCK_MODE=True):
            response = self.checkout(booking)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['provider'], response.data['mock']), ('mock', True))
        self.assertEqual((response.data['payment_id'], response.data['qr_code']), (None, None))
        self.assertEqual((response.data['amount'], response.data['currency']), ('20.00', 'USD'))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertEqual(self.gateway.calls, [])

    def test_a_usd_booking_stays_on_stripe(self):
        usd_event = self.make_event('Workshop', currency='USD', price=Decimal('10.00'))
        booking = self.make_booking(usd_event)

        class Session:
            id = 'cs_group_1'
            url = 'https://checkout.stripe.com/pay/cs_group_1'

        with patch('stripe.checkout.Session.create', return_value=Session()) as create:
            response = self.checkout(booking)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['provider'], response.data['checkout_url']), ('stripe', Session.url))
        self.assertEqual(len(create.call_args.kwargs['line_items']), 2)
        self.assertEqual(self.gateway.calls, [])
        self.assertFalse(Payment.objects.filter(booking=booking).exists())

    def test_kzt_falls_back_to_the_legacy_path_when_freedom_pay_is_off(self):
        with override_settings(PAYMENT_PROVIDERS_ENABLED=['stripe'], PAYMENTS_MOCK_MODE=True, STRIPE_MOCK_MODE=True):
            response = self.checkout()
        self.assertEqual(response.data['provider'], 'mock')
        self.assertEqual(self.gateway.calls, [])

    def test_only_the_owner_can_check_out_and_an_ended_hold_cannot_be_paid(self):
        self.assertEqual(self.checkout(user=self.other).status_code, 404)
        Booking.objects.filter(pk=self.booking.pk).update(hold_expires_at=timezone.now() - timedelta(seconds=1))
        response = self.checkout()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.gateway.calls, [])
        self.assertFalse(Payment.objects.exists())

    def test_gateway_down_gives_502_and_the_owner_can_retry(self):
        self.gateway.fault = 'timeout'
        self.assertEqual(self.checkout().status_code, 502)
        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual((payment.status, payment.provider_session_id), ('pending', ''))
        self.gateway.fault = None
        response = self.checkout()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['payment_id'], payment.pk)

    # callbacks

    def test_a_paid_callback_confirms_the_booking(self):
        payment, pid = self.paid()
        self.assertEqual(self.gateway.scripts(), ['init_payment.php', 'get_status3.php'])
        self.assertEqual((payment.status, payment.provider_payment_id), ('completed', pid))
        self.assertEqual(self.booking.amount_paid, Decimal('10000.00'))
        self.assertIsNone(self.booking.hold_expires_at)
        self.assertEqual(self.booking.stripe_payment_intent_id, '')
        self.assertEqual(self.seats_available(), [False, False])
        event = PaymentEvent.objects.get()
        self.assertEqual((event.outcome, event.payment), ('processed', payment))
        self.assertEqual(Notification.objects.filter(user=self.buyer, type='ticket_purchased').count(), 1)
        self.assertFalse(Refund.objects.exists())

    def test_a_bad_signature_changes_nothing(self):
        payment, pid = self.opened()
        self.gateway.pay(pid)
        response, reply = self.notify(pid, payment.pk, secret='forged-secret')
        self.assertEqual((response.status_code, reply['pg_status']), (400, 'error'))
        payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual((payment.status, self.booking.status), ('pending', Booking.Status.HOLDING))
        self.assertFalse(PaymentEvent.objects.exists())

    def test_a_wrong_amount_does_not_confirm_and_is_refunded(self):
        payment, pid = self.opened()
        self.gateway.pay(pid)
        self.gateway.payments[pid]['amount'] = Decimal('5000')
        _, reply = self.notify(pid, payment.pk, amount='5000')
        self.assertEqual(reply['pg_status'], 'ok')
        payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual((payment.status, self.booking.status), ('failed', Booking.Status.HOLDING))
        refund = Refund.objects.get()
        self.assertEqual(
            (refund.kind, refund.amount, refund.status), ('amount_mismatch', Decimal('5000.00'), 'succeeded')
        )
        self.assertEqual(PaymentEvent.objects.get().outcome, 'amount_mismatch')

    def test_a_duplicate_callback_is_applied_once(self):
        payment, pid = self.paid()
        _, reply = self.notify(pid, payment.pk, salt='again2')
        self.assertEqual(reply['pg_status'], 'ok')
        self.assertEqual(PaymentEvent.objects.count(), 1)
        self.assertEqual(self.gateway.scripts().count('get_status3.php'), 1)
        self.assertEqual(Notification.objects.filter(user=self.buyer, type='ticket_purchased').count(), 1)
        self.assertFalse(Refund.objects.exists())

    def test_a_payment_after_the_hold_expired_is_refunded_and_not_confirmed(self):
        payment, pid = self.opened()
        Booking.objects.filter(pk=self.booking.pk).update(hold_expires_at=timezone.now() - timedelta(minutes=1))
        release_expired_bookings(self.event)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.EXPIRED)

        self.gateway.pay(pid)
        _, reply = self.notify(pid, payment.pk)
        self.assertEqual(reply['pg_status'], 'ok')
        payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.EXPIRED)
        self.assertIsNone(self.booking.amount_paid)
        self.assertEqual((payment.status, payment.refunded_amount), ('refunded', Decimal('10000.00')))
        refund = Refund.objects.get()
        self.assertEqual(
            (refund.kind, refund.status, refund.amount), ('late_payment', 'succeeded', Decimal('10000.00'))
        )
        self.assertEqual(self.gateway.payments[pid]['refunded'], Decimal('10000'))
        self.assertEqual(PaymentEvent.objects.get().outcome, 'late_payment')
        self.assertTrue(Notification.objects.filter(user=self.buyer, type='payment_failed').exists())
        self.assertFalse(Notification.objects.filter(user=self.buyer, type='ticket_purchased').exists())

    def test_a_payment_for_a_cancelled_hold_is_refunded(self):
        payment, pid = self.opened()
        self.client.force_authenticate(user=self.buyer)
        self.assertEqual(self.client.post(f'/api/v1/bookings/{self.booking.pk}/cancel/').status_code, 200)
        self.gateway.pay(pid)
        self.notify(pid, payment.pk)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)
        self.assertEqual(Refund.objects.get().kind, 'late_payment')

    def test_a_failed_result_fails_the_payment_and_keeps_the_hold(self):
        payment, pid = self.opened()
        self.booking.refresh_from_db()
        hold = self.booking.hold_expires_at
        _, reply = self.notify(pid, payment.pk, result='0')
        self.assertEqual(reply['pg_status'], 'ok')
        payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(payment.status, 'failed')
        self.assertEqual((self.booking.status, self.booking.hold_expires_at), (Booking.Status.HOLDING, hold))
        self.assertEqual(self.checkout().status_code, 200)
        payment.refresh_from_db()
        self.assertEqual((payment.status, payment.attempt), ('pending', 2))

    def test_a_paid_booking_cannot_be_checked_out_again(self):
        self.paid()
        response = self.checkout()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.gateway.scripts().count('init_payment.php'), 1)

    # status endpoint

    def test_the_status_endpoint_is_owner_only_for_bookings(self):
        payment, pid = self.opened()
        url = f'/api/v1/payments/status/{payment.pk}/'
        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(user=self.organizer)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_authenticate(user=self.buyer)
        data = self.client.get(url).data
        self.assertEqual(
            {k: data[k] for k in ('payment_id', 'provider', 'status', 'registration_id', 'registration_status')},
            {
                'payment_id': payment.pk,
                'provider': 'freedompay',
                'status': 'pending',
                'registration_id': None,
                'registration_status': None,
            },
        )
        self.assertEqual((str(data['booking_id']), data['booking_status']), (str(self.booking.pk), 'holding'))
        self.assertEqual((data['event_id'], data['event_title']), (self.event.pk, 'Almaty Product Conference'))
        self.assertEqual((data['amount'], data['currency']), ('10000.00', 'KZT'))

        # Polling settles a stale pending payment.
        self.gateway.pay(pid)
        Payment.objects.filter(pk=payment.pk).update(updated_at=timezone.now() - timedelta(seconds=30))
        with self.captureOnCommitCallbacks(execute=True):
            data = self.client.get(url).data
        self.assertEqual((data['status'], data['booking_status']), ('completed', 'confirmed'))

    # refunds go back through Freedom Pay

    def test_event_cancellation_refunds_the_booking_through_freedom_pay(self):
        payment, pid = self.paid()
        with patch('stripe.Refund.create') as stripe_refund, self.captureOnCommitCallbacks(execute=True):
            summary = cancel_event(event=self.event, actor=self.organizer)
        stripe_refund.assert_not_called()
        self.assertEqual((summary['refunded'], summary['refund_failed']), (1, 0))
        self.assertEqual(self.gateway.payments[pid]['refunded'], Decimal('10000'))
        payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual((payment.status, payment.refunded_amount), ('refunded', Decimal('10000.00')))
        self.assertEqual(self.booking.status, Booking.Status.REFUNDED)
        refund = Refund.objects.get()
        self.assertEqual((refund.kind, refund.status, refund.provider), ('event_cancelled', 'succeeded', 'freedompay'))
        self.assertEqual(self.seats_available(), [])  # seats released, tickets gone

    def test_an_organizer_refund_goes_through_freedom_pay(self):
        payment, pid = self.paid()
        self.client.force_authenticate(user=self.organizer)
        with patch('stripe.Refund.create') as stripe_refund:
            response = self.client.post(f'/api/v1/bookings/{self.booking.pk}/refund/', {'reason': 'Venue change'})
        self.assertEqual(response.status_code, 200, response.data)
        stripe_refund.assert_not_called()
        self.assertEqual(self.gateway.payments[pid]['refunded'], Decimal('10000'))
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'refunded')
        self.assertEqual(Refund.objects.get().kind, 'organizer')

    def test_a_refused_refund_leaves_the_booking_paid(self):
        payment, _ = self.paid()
        self.gateway.fault = 'http500'
        self.client.force_authenticate(user=self.organizer)
        response = self.client.post(f'/api/v1/bookings/{self.booking.pk}/refund/')
        self.assertEqual(response.status_code, 400)
        payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual((payment.status, payment.refunded_amount), ('completed', 0))
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)
        self.assertFalse(Refund.objects.exists())
