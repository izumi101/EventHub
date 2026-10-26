"""Regression tests for payment/booking issues listed in REVIEW.md."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from bookings.models import Booking, BookingSeat
from events.billing import to_minor_units
from events.models import Event, Registration
from payments.models import Payment


def _session(session_id='cs_test_1', url='https://checkout.stripe.test/x'):
    return SimpleNamespace(id=session_id, url=url)


class PaymentBase(APITestCase):
    def setUp(self):
        self.organizer = User.objects.create_user('org', 'org@example.com', 'Str0ng-pass!')
        self.organizer.profile.role = 'organizer'
        self.organizer.profile.save()
        self.buyer = User.objects.create_user('buyer', 'buyer@example.com', 'Str0ng-pass!')
        self.event = Event.objects.create(
            title='Gig', description='d', organizer=self.organizer,
            date=timezone.now() + timedelta(days=5), location='Club',
            price=Decimal('5000.00'), currency='KZT', max_participants=50, status='published',
        )

    def pending(self, **kw):
        data = dict(user=self.buyer, event=self.event, status='pending',
                    seat_held_until=timezone.now() + timedelta(minutes=10))
        data.update(kw)
        return Registration.objects.create(**data)

    def checkout(self, reg):
        self.client.force_authenticate(self.buyer)
        return self.client.post(f'/api/payments/create-checkout/{reg.id}/')

    def webhook(self, session):
        # A real stripe.Event, not a dict: since stripe-python 15 Stripe
        # objects have no .get(), which broke every real webhook.
        event = stripe.Event.construct_from(
            {'type': 'checkout.session.completed', 'data': {'object': session}}, 'sk_test_x',
        )
        with patch('stripe.Webhook.construct_event', return_value=event):
            return self.client.post('/api/payments/webhook/', data={}, content_type='application/json')


@override_settings(STRIPE_MOCK_MODE=False)
class CheckoutStateTests(PaymentBase):
    def test_cancelled_registration_cannot_be_paid(self):
        # K2: any non-completed registration used to get a checkout session.
        reg = self.pending(status='cancelled')
        with patch('stripe.checkout.Session.create') as create:
            response = self.checkout(reg)
        self.assertEqual(response.status_code, 400)
        create.assert_not_called()

    def test_expired_hold_cannot_be_paid(self):
        reg = self.pending(seat_held_until=timezone.now() - timedelta(minutes=1))
        with patch('stripe.checkout.Session.create') as create:
            response = self.checkout(reg)
        self.assertEqual(response.status_code, 400)
        create.assert_not_called()

    def test_session_uses_event_currency_and_expires_with_the_hold(self):
        # K3: everything used to be charged in USD.
        reg = self.pending()
        with patch('stripe.checkout.Session.create', return_value=_session()) as create:
            self.assertEqual(self.checkout(reg).status_code, 200)
        params = create.call_args.kwargs
        price = params['line_items'][0]['price_data']
        self.assertEqual(price['currency'], 'kzt')
        self.assertEqual(price['unit_amount'], 500000)
        reg.refresh_from_db()
        self.assertGreaterEqual(reg.seat_held_until.timestamp(), params['expires_at'])
        self.assertEqual(Payment.objects.get(registration=reg).currency, 'kzt')

    def test_minor_units(self):
        self.assertEqual(to_minor_units(Decimal('19.99'), 'usd'), 1999)
        self.assertEqual(to_minor_units(Decimal('5000'), 'JPY'), 5000)
        self.assertEqual(to_minor_units(Decimal('1.234'), 'KWD'), 1230)
        self.assertEqual(to_minor_units(Decimal('0.105'), 'EUR'), 11)  # rounds, never truncates


@override_settings(STRIPE_MOCK_MODE=False)
class LatePaymentTests(PaymentBase):
    def test_payment_for_released_hold_is_refunded_not_confirmed(self):
        # K2: a late payment used to confirm a ticket whose seat was resold.
        reg = self.pending(status='cancelled')
        Payment.objects.create(registration=reg, amount=5000, stripe_checkout_session_id='cs_late')
        with patch('stripe.Refund.create') as refund:
            response = self.webhook({'id': 'cs_late', 'payment_intent': 'pi_late',
                                     'payment_status': 'paid',
                                     'metadata': {'registration_id': str(reg.id)}})
        self.assertEqual(response.status_code, 200)
        refund.assert_called_once()
        self.assertEqual(refund.call_args.kwargs['payment_intent'], 'pi_late')
        reg.refresh_from_db()
        self.assertEqual(reg.status, 'cancelled')
        self.assertEqual(Payment.objects.get(registration=reg).status, 'refunded')

    def test_paid_webhook_confirms_pending_ticket(self):
        reg = self.pending()
        Payment.objects.create(registration=reg, amount=5000, stripe_checkout_session_id='cs_ok')
        response = self.webhook({'id': 'cs_ok', 'payment_intent': 'pi_ok', 'payment_status': 'paid',
                                 'metadata': {'registration_id': str(reg.id)}})
        self.assertEqual(response.status_code, 200)
        reg.refresh_from_db()
        self.assertEqual(reg.status, 'confirmed')

    def test_success_page_verification_handles_stripe_objects(self):
        reg = self.pending()
        Payment.objects.create(registration=reg, amount=5000, stripe_checkout_session_id='cs_v')
        session = stripe.checkout.Session.construct_from(
            {'id': 'cs_v', 'payment_intent': 'pi_v', 'payment_status': 'paid',
             'metadata': {'registration_id': str(reg.id)}}, 'sk_test_x')
        self.client.force_authenticate(self.buyer)
        with patch('stripe.checkout.Session.retrieve', return_value=session):
            response = self.client.get('/api/payments/verify/?session_id=cs_v')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'completed')

    def test_older_session_of_a_paid_ticket_is_refunded(self):
        reg = self.pending(status='confirmed', seat_held_until=None)
        Payment.objects.create(registration=reg, amount=5000, status='completed',
                               stripe_checkout_session_id='cs_new', stripe_payment_intent_id='pi_new')
        with patch('stripe.Refund.create') as refund:
            self.webhook({'id': 'cs_old', 'payment_intent': 'pi_old', 'payment_status': 'paid',
                          'metadata': {'registration_id': str(reg.id)}})
        self.assertEqual(refund.call_args.kwargs['payment_intent'], 'pi_old')

    def test_expired_group_booking_payment_is_refunded(self):
        booking = Booking.objects.create(owner=self.buyer, event=self.event, status=Booking.Status.EXPIRED,
                                         stripe_session_id='cs_group')
        with patch('stripe.Refund.create') as refund:
            self.webhook({'id': 'cs_group', 'payment_intent': 'pi_group', 'payment_status': 'paid',
                          'metadata': {'booking_id': str(booking.id)}})
        refund.assert_called_once()
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.EXPIRED)


class OrganizerMoneyTests(PaymentBase):
    def setUp(self):
        super().setUp()
        self.reg = self.pending(status='confirmed', seat_held_until=None)
        self.payment = Payment.objects.create(registration=self.reg, amount=Decimal('100'), status='completed')
        self.client.force_authenticate(self.organizer)

    def test_garbage_refund_amount_is_a_400(self):
        # Important #14: Decimal('abc') raised InvalidOperation → 500.
        response = self.client.post(f'/api/payments/refund/{self.reg.id}/', {'amount': 'abc'})
        self.assertEqual(response.status_code, 400)

    def test_second_full_refund_is_refused(self):
        self.assertEqual(self.client.post(f'/api/payments/refund/{self.reg.id}/').status_code, 200)
        self.assertEqual(self.client.post(f'/api/payments/refund/{self.reg.id}/').status_code, 400)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.refunded_amount, Decimal('100'))

    def test_offline_payment_is_validated(self):
        # Important #15.
        pending = self.pending(user=User.objects.create_user('cash', 'c@example.com', 'Str0ng-pass!'))
        url = f'/api/payments/mark-offline/{pending.id}/'
        self.assertEqual(self.client.post(url, {'amount': '-5'}).status_code, 400)
        self.assertEqual(self.client.post(url, {'amount': 'lots'}).status_code, 400)
        pending.status = 'cancelled'
        pending.save()
        self.assertEqual(self.client.post(url, {'amount': '10'}).status_code, 400)

    def test_verify_is_owner_only(self):
        self.payment.stripe_checkout_session_id = 'cs_mine'
        self.payment.save()
        response = self.client.get('/api/payments/verify/?session_id=cs_mine')
        self.assertEqual(response.status_code, 404)


class SharedBookingTests(PaymentBase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.organizer)
        self.client.post(f'/api/events/{self.event.id}/seat-map/create/', {'rows': 2, 'cols': 2}, format='json')
        seats = list(self.event.seat_map.seats.all()[:2])
        self.booking = Booking.objects.create(owner=self.buyer, event=self.event, status=Booking.Status.CONFIRMED)
        for seat in seats:
            BookingSeat.objects.create(booking=self.booking, seat=seat, price=10)
        self.url = f'/api/bookings/shared/{self.booking.share_token}/'
        self.friend = User.objects.create_user('friend', 'f@example.com', 'Str0ng-pass!')
        self.stranger = User.objects.create_user('stranger', 's@example.com', 'Str0ng-pass!')
        self.client.force_authenticate(None)

    def test_invite_link_does_not_expose_tickets(self):
        # K5: the anonymous share view used to return every seat's QR UUID.
        data = self.client.get(self.url).data
        self.assertTrue(all(s['ticket_uuid'] is None for s in data['seats']))

    def test_claimer_sees_only_their_ticket_and_cannot_be_overwritten(self):
        seat_id = self.booking.seats.first().seat_id
        self.client.force_authenticate(self.friend)
        self.assertEqual(self.client.post(self.url + 'claim/', {'seat_id': seat_id, 'name': 'Friend'}).status_code, 200)
        mine = [s for s in self.client.get(self.url).data['seats'] if s['ticket_uuid']]
        self.assertEqual([s['seat_id'] for s in mine], [seat_id])

        self.client.force_authenticate(self.stranger)
        response = self.client.post(self.url + 'claim/', {'seat_id': seat_id, 'name': 'Me now'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.booking.seats.get(seat_id=seat_id).claimed_by, self.friend)

    def test_owner_still_sees_all_tickets(self):
        self.client.force_authenticate(self.buyer)
        data = self.client.get(f'/api/bookings/{self.booking.id}/').data
        self.assertTrue(all(s['ticket_uuid'] for s in data['seats']))


@override_settings(STRIPE_MOCK_MODE=False)
class OrganizerBookingRefundTests(PaymentBase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.organizer)
        self.client.post(f'/api/events/{self.event.id}/seat-map/create/', {'rows': 1, 'cols': 3}, format='json')
        self.seats = list(self.event.seat_map.seats.all()[:2])
        self.booking = Booking.objects.create(
            owner=self.buyer, event=self.event, status=Booking.Status.CONFIRMED,
            stripe_payment_intent_id='pi_group', amount_paid=Decimal('2000.00'),
        )
        for seat in self.seats:
            BookingSeat.objects.create(booking=self.booking, seat=seat, price=1000)
            seat.is_available = False
            seat.save()

    def test_organizer_refunds_a_group_booking(self):
        with patch('stripe.Refund.create') as refund:
            response = self.client.post(f'/api/bookings/{self.booking.id}/refund/', {'reason': 'Venue change'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(refund.call_args.kwargs['payment_intent'], 'pi_group')
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.REFUNDED)
        # Seats are back on sale and the tickets are gone.
        self.assertTrue(all(s.is_available for s in self.event.seat_map.seats.filter(id__in=[x.id for x in self.seats])))
        self.assertFalse(self.booking.seats.exists())
        # Refunding twice is refused.
        response = self.client.post(f'/api/bookings/{self.booking.id}/refund/')
        self.assertEqual(response.status_code, 400)

    def test_only_the_event_team_can_refund_or_list(self):
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.post(f'/api/bookings/{self.booking.id}/refund/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/bookings/event/{self.event.id}/').status_code, 403)

    def test_team_list_hides_tickets(self):
        data = self.client.get(f'/api/bookings/event/{self.event.id}/').data
        self.assertEqual(len(data), 1)
        self.assertTrue(all(s['ticket_uuid'] is None for s in data[0]['seats']))

    def test_analytics_include_group_bookings(self):
        from events.analytics import event_analytics
        kpis = event_analytics(self.event)['kpis']
        self.assertEqual((kpis['group_bookings'], kpis['group_seats'], kpis['tickets_sold']), (1, 2, 2))
        self.assertEqual(kpis['gross_revenue'], 2000.0)
        with patch('stripe.Refund.create'):
            self.client.post(f'/api/bookings/{self.booking.id}/refund/')
        kpis = event_analytics(self.event)['kpis']
        self.assertEqual((kpis['refunded'], kpis['net_revenue'], kpis['tickets_sold']), (2000.0, 0.0, 0))

    def test_dashboard_stats_report_money_taken_not_price_times_registrations(self):
        stats = self.client.get(f'/api/events/{self.event.id}/stats/').data
        self.assertEqual((stats['net_revenue'], stats['currency']), ('2000.00', self.event.currency))
        with patch('stripe.Refund.create'):
            self.client.post(f'/api/bookings/{self.booking.id}/refund/')
        self.assertEqual(self.client.get(f'/api/events/{self.event.id}/stats/').data['net_revenue'], '0.00')
