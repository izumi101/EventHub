"""The payment state machine: every pair of the 6x6 status matrix, in Python
and in the (not yet installed) PostgreSQL trigger."""

from datetime import timedelta
from decimal import Decimal
from itertools import product

from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from bookings.models import Booking
from common.choices import PaymentStatusChoices as Status
from events.models import Event
from payments.models import Payment
from payments.state import (
    DROP_STATUS_TRIGGER_SQL,
    TRANSITIONS,
    TRIGGER_NAME,
    IllegalPaymentTransition,
    can_transition,
    status_trigger_sql,
    transition,
)

# ADR 0001, section 2, written out independently of payments/state.py.
ADR_TABLE = {
    ('pending', 'completed'),
    ('pending', 'failed'),
    ('pending', 'expired'),
    ('failed', 'pending'),
    ('failed', 'completed'),
    ('expired', 'pending'),
    ('expired', 'completed'),
    ('completed', 'refunded'),
    ('completed', 'disputed'),
    ('disputed', 'completed'),
    ('disputed', 'refunded'),
}
STATUSES = ['pending', 'completed', 'failed', 'expired', 'refunded', 'disputed']
ALL_PAIRS = list(product(STATUSES, STATUSES))


class StateBase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@example.com', 'Str0ng-pass!')
        self.event = Event.objects.create(
            title='Gig',
            description='d',
            organizer=self.owner,
            date=timezone.now() + timedelta(days=5),
            location='Club',
            price=Decimal('10.00'),
            currency='KZT',
        )

    def payment(self, status):
        booking = Booking.objects.create(owner=self.owner, event=self.event)
        return Payment.objects.create(booking=booking, amount=Decimal('10.00'), status=status)


class TransitionTableTests(TestCase):
    def test_the_statuses_are_the_six_of_the_adr(self):
        self.assertEqual(sorted(Status.values), sorted(STATUSES))
        self.assertEqual(sorted(TRANSITIONS), sorted(STATUSES))

    def test_the_table_is_the_adr_table(self):
        implemented = {(source, target) for source, targets in TRANSITIONS.items() for target in targets}
        self.assertEqual(implemented, ADR_TABLE)

    def test_can_transition_for_every_pair(self):
        self.assertEqual(len(ALL_PAIRS), 36)
        for source, target in ALL_PAIRS:
            with self.subTest(source=source, target=target):
                self.assertEqual(can_transition(source, target), (source, target) in ADR_TABLE)

    def test_refunded_is_terminal_and_unknown_states_go_nowhere(self):
        self.assertEqual(TRANSITIONS['refunded'], frozenset())
        self.assertFalse(can_transition('refunded', 'completed'))
        self.assertFalse(can_transition('bogus', 'completed'))
        self.assertFalse(can_transition('pending', 'bogus'))


class TransitionFunctionTests(StateBase):
    def test_every_allowed_move_is_persisted(self):
        for source, target in sorted(ADR_TABLE):
            with self.subTest(source=source, target=target):
                payment = self.payment(source)
                returned = transition(payment, target, reason='test')
                self.assertIs(returned, payment)
                self.assertEqual(payment.status, target)
                payment.refresh_from_db()
                self.assertEqual(payment.status, target)

    def test_every_other_move_is_rejected_and_nothing_is_written(self):
        for source, target in ALL_PAIRS:
            if (source, target) in ADR_TABLE:
                continue
            with self.subTest(source=source, target=target):
                payment = self.payment(source)
                with self.assertRaises(IllegalPaymentTransition) as raised:
                    transition(payment, target)
                self.assertEqual((raised.exception.from_status, raised.exception.to_status), (source, target))
                self.assertEqual(payment.status, source)
                payment.refresh_from_db()
                self.assertEqual(payment.status, source)

    def test_only_the_status_is_written(self):
        payment = self.payment('pending')
        Payment.objects.filter(pk=payment.pk).update(refunded_amount=Decimal('3.00'))
        transition(payment, 'completed')
        payment.refresh_from_db()
        self.assertEqual(payment.refunded_amount, Decimal('3.00'))

    def test_a_stale_object_cannot_overwrite_a_concurrent_change(self):
        payment = self.payment('pending')
        Payment.objects.filter(pk=payment.pk).update(status='completed')  # another worker
        with self.assertRaises(IllegalPaymentTransition) as raised:
            transition(payment, 'expired')  # allowed from what this object believes
        self.assertIn('stored status is completed', str(raised.exception))
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'completed')


class StatusTriggerTests(StateBase):
    """The trigger SQL WP1b will install. DDL is transactional in PostgreSQL,
    so it disappears again with this test's transaction."""

    def setUp(self):
        super().setUp()
        with connection.cursor() as cursor:
            cursor.execute(status_trigger_sql())

    def update(self, payment, status):
        with transaction.atomic():
            Payment.objects.filter(pk=payment.pk).update(status=status)

    def test_the_trigger_enforces_the_same_table(self):
        for source, target in ALL_PAIRS:
            with self.subTest(source=source, target=target):
                payment = self.payment(source)
                if source == target or (source, target) in ADR_TABLE:
                    self.update(payment, target)
                    payment.refresh_from_db()
                    self.assertEqual(payment.status, target)
                else:
                    with self.assertRaises(IntegrityError):
                        self.update(payment, target)
                    payment.refresh_from_db()
                    self.assertEqual(payment.status, source)

    def test_other_columns_stay_writable(self):
        payment = self.payment('refunded')
        Payment.objects.filter(pk=payment.pk).update(refund_reason='note')
        payment.refund_reason = 'other'
        payment.save()  # a full save rewrites the unchanged status
        payment.refresh_from_db()
        self.assertEqual(payment.refund_reason, 'other')

    def test_the_trigger_can_be_dropped_again(self):
        with connection.cursor() as cursor:
            cursor.execute(DROP_STATUS_TRIGGER_SQL)
            cursor.execute('SELECT count(*) FROM pg_trigger WHERE tgname = %s', [TRIGGER_NAME])
            self.assertEqual(cursor.fetchone()[0], 0)
        payment = self.payment('refunded')
        self.update(payment, 'pending')
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')
