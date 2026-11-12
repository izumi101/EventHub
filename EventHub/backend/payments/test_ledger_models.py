"""Database rules of the payment ledger (ADR 0001): Payment targets, provider
session uniqueness, the Refund ledger and the PaymentEvent log."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from bookings.models import Booking
from events.models import Event, Registration
from payments.models import Payment, PaymentEvent, Refund


class LedgerBase(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user('org', 'org@example.com', 'Str0ng-pass!')
        self.buyer = User.objects.create_user('buyer', 'buyer@example.com', 'Str0ng-pass!')
        self.event = Event.objects.create(
            title='Gig',
            description='d',
            organizer=self.organizer,
            date=timezone.now() + timedelta(days=5),
            location='Club',
            price=Decimal('5000.00'),
            currency='KZT',
            max_participants=50,
            status='published',
        )

    def registration(self, **kw):
        data = {'user': self.buyer, 'event': self.event, 'status': 'pending'}
        data.update(kw)
        return Registration.objects.create(**data)

    def booking(self, **kw):
        return Booking.objects.create(owner=self.buyer, event=self.event, **kw)

    def assertRejected(self, create):
        with self.assertRaises(IntegrityError), transaction.atomic():
            create()


class PaymentTargetTests(LedgerBase):
    def test_a_registration_payment_is_valid(self):
        payment = Payment.objects.create(registration=self.registration(), amount=Decimal('10.00'))
        self.assertIsNone(payment.booking)
        self.assertEqual(payment.provider, '')
        self.assertEqual(payment.attempt, 0)
        self.assertEqual(payment.provider_payload, {})

    def test_a_booking_payment_is_valid(self):
        booking = self.booking()
        payment = Payment.objects.create(booking=booking, amount=Decimal('10.00'))
        self.assertEqual(booking.payment, payment)

    def test_a_payment_needs_a_target(self):
        self.assertRejected(lambda: Payment.objects.create(amount=Decimal('10.00')))

    def test_a_payment_cannot_belong_to_both(self):
        self.assertRejected(
            lambda: Payment.objects.create(
                registration=self.registration(), booking=self.booking(), amount=Decimal('10.00')
            )
        )

    def test_large_amounts_fit(self):
        # Group bookings store up to Decimal(12, 2); the copy must not overflow.
        payment = Payment.objects.create(booking=self.booking(), amount=Decimal('9999999999.99'))
        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal('9999999999.99'))

    def test_code_without_the_new_columns_can_still_insert(self):
        # Rolling deploy: the previous release inserts rows without the new
        # columns, which then take their database defaults.
        reg = self.registration()
        now = timezone.now()
        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO payments_payment (registration_id, stripe_payment_intent_id, '
                'stripe_checkout_session_id, amount, currency, status, method, refunded_amount, '
                'refund_reason, created_at, updated_at) '
                "VALUES (%s, '', 'cs_old', 10, 'kzt', 'pending', 'card', 0, '', %s, %s)",
                [reg.pk, now, now],
            )
        payment = Payment.objects.get(registration=reg)
        self.assertEqual(
            (payment.provider, payment.provider_session_id, payment.provider_payment_id, payment.attempt),
            ('', '', '', 0),
        )
        self.assertEqual(payment.provider_payload, {})


class ProviderSessionUniquenessTests(LedgerBase):
    def test_a_provider_session_belongs_to_one_payment(self):
        Payment.objects.create(
            registration=self.registration(), amount=1, provider='stripe', provider_session_id='cs_1'
        )
        other = self.registration(status='cancelled')
        self.assertRejected(
            lambda: Payment.objects.create(registration=other, amount=1, provider='stripe', provider_session_id='cs_1')
        )

    def test_the_same_id_at_another_provider_is_allowed(self):
        Payment.objects.create(registration=self.registration(), amount=1, provider='stripe', provider_session_id='abc')
        Payment.objects.create(booking=self.booking(), amount=1, provider='freedompay', provider_session_id='abc')

    def test_empty_session_ids_are_not_unique(self):
        Payment.objects.create(registration=self.registration(), amount=1, provider='offline')
        Payment.objects.create(booking=self.booking(), amount=1, provider='offline')
        self.assertEqual(Payment.objects.filter(provider='offline', provider_session_id='').count(), 2)


class RefundLedgerTests(LedgerBase):
    def setUp(self):
        super().setUp()
        self.payment = Payment.objects.create(
            registration=self.registration(),
            amount=Decimal('100.00'),
            currency='kzt',
            status='completed',
            provider='stripe',
            provider_payment_id='pi_1',
        )

    def refund(self, **kw):
        data = {
            'payment': self.payment,
            'amount': Decimal('40.00'),
            'currency': 'KZT',
            'kind': Refund.Kind.ORGANIZER,
            'provider': 'stripe',
            'provider_payment_id': 'pi_1',
        }
        data.update(kw)
        return Refund.objects.create(**data)

    def test_idempotency_key_comes_from_the_row_id(self):
        refund = self.refund()
        self.assertEqual(refund.idempotency_key, f'refund-{refund.pk}')
        self.assertEqual(refund.status, Refund.Status.PENDING)
        # Saving again (e.g. after the provider answered) keeps the key.
        refund.status = Refund.Status.SUCCEEDED
        refund.processed_at = timezone.now()
        refund.save()
        refund.refresh_from_db()
        self.assertEqual(refund.idempotency_key, f'refund-{refund.pk}')
        self.assertIn(refund, self.payment.refunds.all())

    def test_two_refunds_of_the_same_amount_get_different_keys(self):
        first, second = self.refund(), self.refund()
        self.assertNotEqual(first.idempotency_key, second.idempotency_key)

    def test_idempotency_key_is_unique(self):
        first = self.refund()
        self.assertRejected(lambda: self.refund(idempotency_key=first.idempotency_key))

    def test_amount_must_be_positive(self):
        self.assertRejected(lambda: self.refund(amount=Decimal('0.00')))
        self.assertRejected(lambda: self.refund(amount=Decimal('-1.00')))

    def test_currency_is_upper_case_iso(self):
        self.assertRejected(lambda: self.refund(currency='kzt'))
        self.assertRejected(lambda: self.refund(currency='K1'))

    def test_a_finished_refund_records_when(self):
        self.assertRejected(lambda: self.refund(status=Refund.Status.SUCCEEDED))
        self.assertRejected(lambda: self.refund(status=Refund.Status.FAILED))
        self.refund(status=Refund.Status.FAILED, processed_at=timezone.now(), error='card closed')

    def test_only_an_orphan_refund_may_lack_a_payment(self):
        self.assertRejected(lambda: self.refund(payment=None))
        self.assertRejected(lambda: self.refund(payment=None, kind=Refund.Kind.ORPHAN, provider_payment_id=''))
        self.assertRejected(lambda: self.refund(payment=None, kind=Refund.Kind.ORPHAN, provider=''))
        orphan = self.refund(payment=None, kind=Refund.Kind.ORPHAN, provider_payment_id='pi_unknown')
        self.assertIsNone(orphan.payment)

    def test_a_payment_with_refunds_cannot_be_deleted(self):
        from django.db.models import ProtectedError

        self.refund()
        with self.assertRaises(ProtectedError):
            self.payment.delete()


class PaymentEventLogTests(LedgerBase):
    def test_a_provider_event_is_stored_once(self):
        PaymentEvent.objects.create(provider='stripe', event_id='evt_1', kind='paid')
        self.assertRejected(lambda: PaymentEvent.objects.create(provider='stripe', event_id='evt_1', kind='paid'))

    def test_the_same_event_id_at_another_provider_is_a_different_event(self):
        PaymentEvent.objects.create(provider='stripe', event_id='evt_1', kind='paid')
        PaymentEvent.objects.create(provider='freedompay', event_id='evt_1', kind='paid')

    def test_event_id_is_required(self):
        self.assertRejected(lambda: PaymentEvent.objects.create(provider='stripe', event_id='', kind='paid'))

    def test_orphans_have_no_payment(self):
        event = PaymentEvent.objects.create(
            provider='stripe', event_id='evt_2', kind='paid', outcome=PaymentEvent.Outcome.ORPHAN
        )
        self.assertIsNone(event.payment)
        self.assertEqual(str(event), 'stripe paid evt_2')


class AdminTests(LedgerBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser('root', 'root@example.com', 'Str0ng-pass!')
        self.client.force_login(self.admin)
        self.payment = Payment.objects.create(registration=self.registration(), amount=Decimal('10.00'))
        self.refund = Refund.objects.create(
            payment=self.payment, amount=Decimal('5.00'), currency='KZT', kind=Refund.Kind.ORGANIZER
        )
        self.event_row = PaymentEvent.objects.create(provider='stripe', event_id='evt_a', kind='paid')

    def test_pages_render(self):
        for url in (
            '/admin/payments/payment/',
            f'/admin/payments/payment/{self.payment.pk}/change/',
            '/admin/payments/refund/',
            f'/admin/payments/refund/{self.refund.pk}/change/',
            '/admin/payments/paymentevent/',
            f'/admin/payments/paymentevent/{self.event_row.pk}/change/',
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_money_cannot_be_edited_or_created_in_the_admin(self):
        from django.contrib import admin

        payment_admin = admin.site._registry[Payment]
        for field in ('amount', 'currency', 'refunded_amount', 'status', 'provider_payment_id'):
            self.assertIn(field, payment_admin.readonly_fields)
        refund_admin = admin.site._registry[Refund]
        for field in ('amount', 'currency', 'status', 'idempotency_key', 'provider_refund_id'):
            self.assertIn(field, refund_admin.readonly_fields)
        self.assertEqual(self.client.get('/admin/payments/payment/add/').status_code, 403)
        self.assertEqual(self.client.get('/admin/payments/refund/add/').status_code, 403)
        self.assertEqual(self.client.get('/admin/payments/paymentevent/add/').status_code, 403)
        self.client.post(f'/admin/payments/payment/{self.payment.pk}/change/', {'amount': '1.00'})
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, Decimal('10.00'))
