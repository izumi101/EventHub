"""`Payment.paid_at` and `Booking.confirmed_at`: set once, on the first move to
paid, by every path that takes money; never overwritten; enforced by the
database."""

from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone

from bookings.models import Booking
from bookings.services import confirm_booking
from events.models import Registration
from events.test_regressions import Base
from payments import services
from payments.models import Payment
from payments.state import PAID_STATUSES, mark_paid, transition


class PaidAtBase(Base):
    def setUp(self):
        super().setUp()
        self.registration = Registration.objects.create(user=self.attendee, event=self.event, status='pending')

    def payment(self, **kw):
        defaults = {'registration': self.registration, 'amount': Decimal('100.00'), 'currency': 'usd'}
        return Payment.objects.create(**{**defaults, **kw})

    def assertStampedNow(self, payment, before):
        payment.refresh_from_db()
        self.assertIsNotNone(payment.paid_at)
        self.assertGreaterEqual(payment.paid_at, before)
        self.assertLessEqual(payment.paid_at, timezone.now())


class PaymentPathTests(PaidAtBase):
    """One test per code path that moves a payment to a paid status."""

    def test_mock_checkout(self):
        before = timezone.now()
        _, payment = services.create_mock_checkout_session(registration=self.registration)
        self.assertEqual(payment.status, 'completed')
        self.assertStampedNow(payment, before)

    def test_stripe_confirmation_stamps_once(self):
        payment = self.payment(stripe_checkout_session_id='cs_1')
        before = timezone.now()
        services.confirm_stripe_checkout_session({'id': 'cs_1', 'payment_intent': 'pi_1'})
        self.assertStampedNow(payment, before)
        first = payment.paid_at
        # A repeated webhook changes nothing.
        services.confirm_stripe_checkout_session({'id': 'cs_1', 'payment_intent': 'pi_1'})
        payment.refresh_from_db()
        self.assertEqual(payment.paid_at, first)

    @override_settings(STRIPE_MOCK_MODE=True)
    def test_stripe_payment_arriving_after_the_hold_is_stamped_and_refunded(self):
        payment = self.payment(stripe_checkout_session_id='cs_late')
        Registration.objects.filter(pk=self.registration.pk).update(status='cancelled')
        before = timezone.now()
        services.confirm_stripe_checkout_session({'id': 'cs_late', 'payment_intent': 'pi_late'})
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'refunded')
        self.assertStampedNow(payment, before)

    def test_offline_marking_stamps_the_moment_it_is_marked(self):
        started = timezone.now() - timedelta(days=3)
        payment = self.payment()
        Payment.objects.filter(pk=payment.pk).update(created_at=started)
        before = timezone.now()
        services.mark_offline_paid(registration=self.registration, amount='80')
        self.assertStampedNow(payment, before)
        self.assertGreater(payment.paid_at - payment.created_at, timedelta(days=2, hours=23))

    def test_offline_marking_without_a_prior_payment_row(self):
        before = timezone.now()
        payment = services.mark_offline_paid(registration=self.registration, amount='80')
        self.assertEqual(payment.method, Payment.METHOD_OFFLINE)
        self.assertStampedNow(payment, before)

    def test_transition_to_completed_stamps_and_later_moves_keep_it(self):
        payment = self.payment()
        self.assertIsNone(payment.paid_at)
        before = timezone.now()
        transition(payment, 'completed')
        self.assertStampedNow(payment, before)
        paid_at = payment.paid_at
        transition(payment, 'disputed')
        transition(payment, 'completed')  # dispute won
        transition(payment, 'refunded')
        payment.refresh_from_db()
        self.assertEqual((payment.status, payment.paid_at), ('refunded', paid_at))

    def test_transition_never_overwrites_a_value_another_worker_wrote(self):
        payment = self.payment()  # this object still believes paid_at is empty
        early = timezone.now() - timedelta(days=2)
        Payment.objects.filter(pk=payment.pk).update(paid_at=early)
        transition(payment, 'completed')
        payment.refresh_from_db()
        self.assertEqual(payment.paid_at, early)

    def test_transition_to_unpaid_statuses_leaves_it_empty(self):
        for target in ('failed', 'expired'):
            with self.subTest(target=target):
                payment = Payment.objects.create(
                    booking=Booking.objects.create(owner=self.other, event=self.event),
                    amount=Decimal('5'),
                )
                transition(payment, target)
                payment.refresh_from_db()
                self.assertIsNone(payment.paid_at)

    def test_full_refund_keeps_the_original_time(self):
        payment = self.payment()
        transition(payment, 'completed')
        payment.refresh_from_db()
        paid_at = payment.paid_at
        with override_settings(STRIPE_MOCK_MODE=True):
            services.refund_payment(payment=payment)
        payment.refresh_from_db()
        self.assertEqual((payment.status, payment.paid_at), ('refunded', paid_at))


class ModelAndDatabaseTests(PaidAtBase):
    def test_creating_a_paid_payment_stamps_it(self):
        for status in sorted(PAID_STATUSES):
            with self.subTest(status=status):
                booking = Booking.objects.create(owner=self.other, event=self.event)
                payment = Payment.objects.create(booking=booking, amount=Decimal('5'), status=status)
                self.assertIsNotNone(payment.paid_at)

    def test_an_explicit_time_is_respected(self):
        moment = timezone.now() - timedelta(days=9)
        self.assertEqual(self.payment(status='completed', paid_at=moment).paid_at, moment)

    def test_save_with_update_fields_persists_the_stamp(self):
        payment = self.payment()
        payment.status = 'completed'
        payment.save(update_fields=['status'])
        payment.refresh_from_db()
        self.assertIsNotNone(payment.paid_at)

    def test_mark_paid_is_idempotent(self):
        payment = self.payment()
        first = mark_paid(payment).paid_at
        self.assertEqual(mark_paid(payment, timezone.now() + timedelta(days=1)).paid_at, first)

    def test_old_code_can_still_complete_a_payment_without_paid_at(self):
        # Expand step: no CHECK yet, so a code-only rollback keeps working.
        payment = self.payment()
        for status in sorted(PAID_STATUSES):
            with self.subTest(status=status):
                Payment.objects.filter(pk=payment.pk).update(status=status)
                payment.refresh_from_db()
                self.assertEqual((payment.status, payment.paid_at), (status, None))
        Payment.objects.bulk_create(
            [
                Payment(
                    booking=Booking.objects.create(owner=self.other, event=self.event),
                    amount=Decimal('5'),
                    status='completed',
                )
            ]
        )

    def test_unpaid_statuses_need_no_paid_at(self):
        for status in ('pending', 'failed', 'expired'):
            with self.subTest(status=status):
                booking = Booking.objects.create(owner=self.other, event=self.event)
                payment = Payment.objects.create(booking=booking, amount=Decimal('5'), status=status)
                self.assertIsNone(payment.paid_at)


class BookingConfirmedAtTests(PaidAtBase):
    def test_a_booking_is_confirmed_after_it_is_created(self):
        booking = Booking.objects.create(owner=self.attendee, event=self.event)  # holding
        self.assertIsNone(booking.confirmed_at)
        Booking.objects.filter(pk=booking.pk).update(created_at=timezone.now() - timedelta(minutes=9))
        before = timezone.now()
        confirm_booking(booking, amount_paid=Decimal('40'))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'confirmed')
        self.assertGreaterEqual(booking.confirmed_at, before)
        self.assertGreater(booking.confirmed_at - booking.created_at, timedelta(minutes=8))

    def test_confirming_again_keeps_the_time(self):
        booking = Booking.objects.create(owner=self.attendee, event=self.event)
        confirm_booking(booking, amount_paid=Decimal('40'))
        booking.refresh_from_db()
        first = booking.confirmed_at
        confirm_booking(booking, amount_paid=Decimal('40'))
        booking.refresh_from_db()
        self.assertEqual(booking.confirmed_at, first)

    def test_saving_a_confirmed_or_refunded_booking_stamps_it(self):
        for status in ('confirmed', 'refunded'):
            with self.subTest(status=status):
                self.assertIsNotNone(
                    Booking.objects.create(owner=self.attendee, event=self.event, status=status).confirmed_at
                )
        for status in ('holding', 'expired', 'cancelled'):
            with self.subTest(status=status):
                self.assertIsNone(
                    Booking.objects.create(owner=self.attendee, event=self.event, status=status).confirmed_at
                )

    def test_save_with_update_fields_persists_the_stamp(self):
        booking = Booking.objects.create(owner=self.attendee, event=self.event)
        booking.status = 'confirmed'
        booking.save(update_fields=['status'])
        booking.refresh_from_db()
        self.assertIsNotNone(booking.confirmed_at)
