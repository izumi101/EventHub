"""payments/0004 + 0005 on a database holding legacy-shaped rows (ADR 0001).

The rows are written with the historical models of the state before the
expand step (payments 0003, bookings 0003), then the real migrations run
forward, backward and forward again through Django's MigrationExecutor.
"""

from datetime import timedelta
from decimal import Decimal
from importlib import import_module

from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from bookings.models import Booking
from events.models import Event, Registration
from payments.models import Payment

LEGACY = [('payments', '0003_payment_protect_registration'), ('bookings', '0003_booking_refunds')]
SCHEMA = [('payments', '0004_ledger_models')]
COPIED = [('payments', '0005_copy_legacy_payments')]

copy_module = import_module('payments.migrations.0005_copy_legacy_payments')


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


class LegacyCopyMigrationTests(TransactionTestCase):
    def setUp(self):
        old = _migrate(LEGACY)
        self.seed(old)
        self.apps = _migrate(COPIED)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    # ── legacy rows ──

    def seed(self, apps):
        UserModel = apps.get_model('auth', 'User')
        EventModel = apps.get_model('events', 'Event')
        RegistrationModel = apps.get_model('events', 'Registration')
        SeatMap = apps.get_model('events', 'SeatMap')
        EventSeat = apps.get_model('events', 'EventSeat')
        PaymentModel = apps.get_model('payments', 'Payment')
        BookingModel = apps.get_model('bookings', 'Booking')
        BookingSeatModel = apps.get_model('bookings', 'BookingSeat')

        organizer = UserModel.objects.create(username='org', email='org@example.com')
        event = EventModel.objects.create(
            title='Gig',
            description='d',
            organizer=organizer,
            date=timezone.now() + timedelta(days=5),
            location='Club',
            price=Decimal('5000.00'),
            currency='KZT',
            tax_percent=Decimal('10.00'),
            service_fee_percent=Decimal('5.00'),
            fees_passed_to_buyer=True,
        )
        seat_map = SeatMap.objects.create(event=event, rows=3, cols=3)
        seats = iter(EventSeat.objects.create(seat_map=seat_map, row=r, col=c) for r in range(3) for c in range(3))

        self.past = timezone.now() - timedelta(days=30)
        users = iter(UserModel.objects.create(username=f'buyer{i}') for i in range(20))

        def ticket(**kw):
            reg = RegistrationModel.objects.create(
                user=next(users), event=event, status=kw.pop('reg_status', 'confirmed')
            )
            data = {'registration': reg, 'amount': Decimal('100.00'), 'currency': 'kzt', 'status': 'completed'}
            data.update(kw)
            payment = PaymentModel.objects.create(**data)
            PaymentModel.objects.filter(pk=payment.pk).update(updated_at=self.past)
            return payment.pk

        self.t_stripe = ticket(stripe_checkout_session_id='cs_1', stripe_payment_intent_id='pi_1')
        self.t_session_only = ticket(status='pending', reg_status='pending', stripe_checkout_session_id='cs_2')
        self.t_mock = ticket(stripe_checkout_session_id='mock_sess_9_1700000000')
        self.t_offline = ticket(method='offline')
        self.t_offline_after_checkout = ticket(method='offline', stripe_checkout_session_id='cs_3')
        self.t_untouched = ticket(status='pending', reg_status='pending')
        self.t_late_refund = ticket(
            status='refunded',
            reg_status='cancelled',
            refunded_amount=Decimal('100.00'),
            refunded_at=self.past,
            stripe_checkout_session_id='cs_4',
            stripe_payment_intent_id='pi_4',
        )

        def booking(seat_prices=(), **kw):
            b = BookingModel.objects.create(owner=next(users), event=event, **kw)
            for price in seat_prices:
                BookingSeatModel.objects.create(booking=b, seat=next(seats), price=Decimal(price))
            return b.pk

        self.b_confirmed = booking(
            status='confirmed', stripe_session_id='cs_b1', stripe_payment_intent_id='pi_b1', amount_paid=Decimal('30')
        )
        # 2 seats x (10 + 10% tax + 5% fee) = 23.00
        self.b_mock = booking(('10.00', '10.00'), status='confirmed', stripe_session_id='mock_booking_x_1700000000')
        self.b_refunded = booking(
            status='refunded',
            stripe_session_id='cs_b3',
            stripe_payment_intent_id='pi_b3',
            amount_paid=Decimal('50.00'),
            refunded_at=self.past,
            refund_reason='Event cancelled',
        )
        self.b_holding = booking(('20.00',), status='holding', stripe_session_id='cs_b4')
        self.b_abandoned = booking(status='expired', stripe_session_id='cs_b5')
        self.b_no_attempt = booking(('20.00',), status='holding')
        self.b_cancelled_unpaid = booking(status='cancelled')
        self.b_paid_after_expiry = booking(
            status='expired', stripe_session_id='cs_b8', stripe_payment_intent_id='pi_b8'
        )
        self.b_confirmed_no_ids = booking(status='confirmed', amount_paid=Decimal('5.00'))
        self.b_session_clash = booking(status='confirmed', stripe_session_id='cs_1', amount_paid=Decimal('1.00'))

    # ── helpers ──

    def payment(self, pk):
        return self.apps.get_model('payments', 'Payment').objects.get(pk=pk)

    def booking_payment(self, booking_pk):
        return self.apps.get_model('payments', 'Payment').objects.get(booking_id=booking_pk)

    def note(self, payment):
        return payment.provider_payload['legacy_import']

    # ── tests ──

    def test_ticket_payments_get_provider_columns(self):
        expected = {
            self.t_stripe: ('stripe', 'cs_1', 'pi_1', 1),
            self.t_session_only: ('stripe', 'cs_2', '', 1),
            self.t_mock: ('mock', 'mock_sess_9_1700000000', '', 1),
            self.t_offline: ('offline', '', '', 0),
            self.t_offline_after_checkout: ('offline', '', '', 1),
            self.t_untouched: ('', '', '', 0),
            self.t_late_refund: ('stripe', 'cs_4', 'pi_4', 1),
        }
        for pk, row in expected.items():
            with self.subTest(pk=pk):
                p = self.payment(pk)
                self.assertEqual((p.provider, p.provider_session_id, p.provider_payment_id, p.attempt), row)
                self.assertEqual(self.note(p)['source'], 'payments.Payment')
                # Legacy columns, state and timestamps are untouched.
                self.assertIsNone(p.booking_id)
                self.assertIsNotNone(p.registration_id)
                self.assertEqual(p.updated_at, self.past)
        late = self.payment(self.t_late_refund)
        self.assertEqual((late.status, late.refunded_amount), ('refunded', Decimal('100.00')))
        self.assertEqual(late.stripe_payment_intent_id, 'pi_4')

    def test_a_cash_payment_never_points_at_stripe(self):
        p = self.payment(self.t_offline_after_checkout)
        self.assertEqual(p.provider, 'offline')
        self.assertEqual(p.provider_session_id, '')
        self.assertEqual(self.note(p)['stripe_checkout_session_id'], 'cs_3')

    def test_group_bookings_get_payment_rows(self):
        expected = {
            self.b_confirmed: ('stripe', 'cs_b1', 'pi_b1', 'completed', '30.00', '0.00', 'amount_paid'),
            self.b_mock: ('mock', 'mock_booking_x_1700000000', '', 'completed', '23.00', '0.00', 'seats'),
            self.b_refunded: ('stripe', 'cs_b3', 'pi_b3', 'refunded', '50.00', '50.00', 'amount_paid'),
            self.b_holding: ('stripe', 'cs_b4', '', 'pending', '23.00', '0.00', 'seats'),
            self.b_abandoned: ('stripe', 'cs_b5', '', 'expired', '0.00', '0.00', 'unknown'),
            self.b_paid_after_expiry: ('stripe', 'cs_b8', 'pi_b8', 'completed', '0.00', '0.00', 'unknown'),
            self.b_confirmed_no_ids: ('', '', '', 'completed', '5.00', '0.00', 'amount_paid'),
        }
        for booking_pk, row in expected.items():
            provider, session, intent, status, amount, refunded, source = row
            with self.subTest(booking=booking_pk):
                p = self.booking_payment(booking_pk)
                self.assertIsNone(p.registration_id)
                self.assertEqual(
                    (p.provider, p.provider_session_id, p.provider_payment_id), (provider, session, intent)
                )
                self.assertEqual(p.status, status)
                self.assertEqual(p.amount, Decimal(amount))
                self.assertEqual(p.refunded_amount, Decimal(refunded))
                self.assertEqual(p.currency, 'kzt')
                self.assertEqual(p.attempt, 1 if session else 0)
                self.assertEqual(self.note(p)['amount_source'], source)
                # Legacy columns are not filled on the new rows: the current
                # services look payments up by them.
                self.assertEqual((p.stripe_checkout_session_id, p.stripe_payment_intent_id), ('', ''))

        refunded = self.booking_payment(self.b_refunded)
        self.assertEqual((refunded.refunded_at, refunded.refund_reason), (self.past, 'Event cancelled'))
        self.assertTrue(self.note(self.booking_payment(self.b_paid_after_expiry))['needs_review'])
        self.assertFalse(self.note(self.booking_payment(self.b_confirmed))['needs_review'])

    def test_bookings_without_money_get_no_payment(self):
        Payment = self.apps.get_model('payments', 'Payment')
        for booking_pk in (self.b_no_attempt, self.b_cancelled_unpaid):
            self.assertFalse(Payment.objects.filter(booking_id=booking_pk).exists())
        self.assertEqual(Payment.objects.filter(booking__isnull=False).count(), 8)

    def test_a_session_id_is_never_given_to_two_payments(self):
        clash = self.booking_payment(self.b_session_clash)
        self.assertEqual(clash.provider_session_id, '')
        self.assertEqual(self.note(clash)['session_id_conflict'], 'cs_1')
        self.assertEqual(self.payment(self.t_stripe).provider_session_id, 'cs_1')

    def test_the_copy_is_idempotent(self):
        Payment = self.apps.get_model('payments', 'Payment')
        before = list(Payment.objects.order_by('pk').values())
        counters = copy_module.copy_legacy_payments(self.apps)
        self.assertEqual(
            counters,
            {
                'ticket_payments_updated': 0,
                'ticket_payments_kept': 0,
                'booking_payments_created': 0,
                'booking_payments_updated': 0,
                'booking_payments_kept': 0,
            },
        )
        self.assertEqual(list(Payment.objects.order_by('pk').values()), before)

    def test_a_rerun_catches_up_with_what_the_legacy_code_wrote_since(self):
        Payment = self.apps.get_model('payments', 'Payment')
        BookingModel = self.apps.get_model('bookings', 'Booking')
        # Legacy code: the session-only ticket got paid, the holding booking
        # got confirmed, a new ticket started checkout.
        Payment.objects.filter(pk=self.t_session_only).update(stripe_payment_intent_id='pi_2', status='completed')
        BookingModel.objects.filter(pk=self.b_holding).update(
            status='confirmed', stripe_payment_intent_id='pi_b4', amount_paid=Decimal('23.00')
        )
        reg = self.apps.get_model('events', 'Registration').objects.create(
            user=self.apps.get_model('auth', 'User').objects.create(username='late'),
            event_id=self.apps.get_model('events', 'Event').objects.get().pk,
            status='pending',
        )
        fresh = Payment.objects.create(registration=reg, amount=Decimal('100.00'), stripe_checkout_session_id='cs_new')
        # A booking payment written by newer code (no legacy marker) wins.
        newer = Payment.objects.get(booking_id=self.b_confirmed)
        Payment.objects.filter(pk=newer.pk).update(provider_payload={}, provider_payment_id='pi_newer')

        counters = copy_module.copy_legacy_payments(self.apps)

        self.assertEqual(self.payment(self.t_session_only).provider_payment_id, 'pi_2')
        holding = self.booking_payment(self.b_holding)
        self.assertEqual((holding.status, holding.provider_payment_id, holding.amount), ('completed', 'pi_b4', 23))
        self.assertEqual(self.payment(fresh.pk).provider_session_id, 'cs_new')
        self.assertEqual(self.booking_payment(self.b_confirmed).provider_payment_id, 'pi_newer')
        self.assertEqual(counters['booking_payments_kept'], 1)
        self.assertEqual(counters['booking_payments_updated'], 1)
        self.assertEqual(counters['ticket_payments_updated'], 2)

    def test_reverse_removes_only_the_copied_rows_and_forward_restores_them(self):
        old = _migrate(SCHEMA)
        Payment = old.get_model('payments', 'Payment')
        self.assertFalse(Payment.objects.filter(booking__isnull=False).exists())
        self.assertEqual(Payment.objects.count(), 7)

        old = _migrate(LEGACY)
        self.assertEqual(old.get_model('payments', 'Payment').objects.count(), 7)

        self.apps = _migrate(COPIED)
        self.assertEqual(self.booking_payment(self.b_refunded).status, 'refunded')
        self.assertEqual(self.payment(self.t_stripe).provider_payment_id, 'pi_1')

    def test_reverse_refuses_to_drop_booking_payments_written_by_newer_code(self):
        Payment = self.apps.get_model('payments', 'Payment')
        Payment.objects.filter(booking_id=self.b_confirmed).update(provider_payload={})
        with self.assertRaises(RuntimeError), transaction.atomic():
            copy_module.remove_copied_booking_payments(self.apps)
        self.assertEqual(Payment.objects.filter(booking__isnull=False).count(), 8)

    def test_the_target_constraint_holds_for_the_copied_rows(self):
        Payment = self.apps.get_model('payments', 'Payment')
        reg = self.apps.get_model('events', 'Registration').objects.create(
            user=self.apps.get_model('auth', 'User').objects.create(username='both'),
            event_id=self.apps.get_model('events', 'Event').objects.get().pk,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payment.objects.filter(booking_id=self.b_confirmed).update(registration_id=reg.pk)


class DashboardCountsBookingsOnceTests(APITestCase):
    """The admin dashboard still sums group bookings from the Booking row;
    the ledger copy of the same booking must not be added a second time."""

    def test_booking_revenue_is_not_counted_twice(self):
        organizer = User.objects.create_user('org', 'org@example.com', 'Str0ng-pass!')
        event = Event.objects.create(
            title='Gig',
            description='d',
            organizer=organizer,
            date=timezone.now() + timedelta(days=5),
            location='Club',
            price=Decimal('10.00'),
            currency='KZT',
            status='published',
        )
        booking = Booking.objects.create(
            owner=organizer, event=event, status=Booking.Status.CONFIRMED, amount_paid=Decimal('30.00')
        )
        Payment.objects.create(booking=booking, amount=Decimal('30.00'), currency='kzt', status='completed')
        reg = Registration.objects.create(user=organizer, event=event, status='confirmed')
        Payment.objects.create(registration=reg, amount=Decimal('10.00'), currency='kzt', status='completed')

        self.client.force_authenticate(User.objects.create_superuser('root', 'root@example.com', 'Str0ng-pass!'))
        data = self.client.get('/api/v1/admin-dashboard/').data
        self.assertEqual(data['revenue_by_currency'], [{'currency': 'KZT', 'amount': '40.00'}])
