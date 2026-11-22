"""payments/0008 (`Payment.paid_at`) and bookings/0004 (`Booking.confirmed_at`)
on a database that holds payments written before the columns existed.

Same pattern as test_migrations.py: rows are written with the historical
models of the state before the migration, then the real migration runs
forward, backward and forward again."""

from datetime import timedelta
from decimal import Decimal
from importlib import import_module

from django.core.exceptions import FieldDoesNotExist
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from payments.test_migrations import _migrate

BEFORE = [('payments', '0007_resync_legacy_payments'), ('bookings', '0003_booking_refunds')]
PAYMENTS_DONE = [('payments', '0008_payment_paid_at')]
BOOKINGS_DONE = [('bookings', '0004_booking_confirmed_at')]

paid_at_module = import_module('payments.migrations.0008_payment_paid_at')
confirmed_at_module = import_module('bookings.migrations.0004_booking_confirmed_at')


class PaidAtBackfillTests(TransactionTestCase):
    def setUp(self):
        self.t0 = timezone.now() - timedelta(days=10)
        self.old = _migrate(BEFORE)
        self.seed(self.old)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    # ── rows written by the previous release ──

    def seed(self, apps):
        User = apps.get_model('auth', 'User')
        Event = apps.get_model('events', 'Event')
        Registration = apps.get_model('events', 'Registration')
        Payment = apps.get_model('payments', 'Payment')
        PaymentEvent = apps.get_model('payments', 'PaymentEvent')
        Booking = apps.get_model('bookings', 'Booking')

        organizer = User.objects.create(username='org', email='org@example.com')
        event = Event.objects.create(
            title='Gig',
            description='d',
            organizer=organizer,
            date=timezone.now() + timedelta(days=5),
            location='Club',
            price=Decimal('5000.00'),
            currency='KZT',
        )
        self.counter = 0

        def payment(status, *, callbacks=(), **extra):
            self.counter += 1
            buyer = User.objects.create(username=f'buyer{self.counter}', email=f'b{self.counter}@example.com')
            reg = Registration.objects.create(user=buyer, event=event, status='confirmed')
            row = Payment.objects.create(registration=reg, amount=Decimal('100.00'), status=status, **extra)
            Payment.objects.filter(pk=row.pk).update(created_at=self.t0)
            for kind, outcome, processed_at, received_at in callbacks:
                callback = PaymentEvent.objects.create(
                    provider='freedompay',
                    event_id=f'e{self.counter}-{kind}-{outcome}-{processed_at}',
                    kind=kind,
                    payment=row,
                    outcome=outcome,
                    processed_at=processed_at,
                )
                PaymentEvent.objects.filter(pk=callback.pk).update(received_at=received_at)
            return row.pk

        minute = timedelta(minutes=1)
        self.first_callback = payment(
            'completed',
            callbacks=[
                ('paid', 'processed', self.t0 + 3 * 60 * minute, self.t0 + 3 * 60 * minute),
                ('paid', 'processed', self.t0 + 10 * minute, self.t0 + 9 * minute),  # the earliest processed
                ('paid', 'ignored', self.t0 + 1 * minute, self.t0 + 1 * minute),  # not a processed success
                ('failed', 'processed', self.t0 + 2 * minute, self.t0 + 2 * minute),  # not a paid callback
            ],
        )
        self.only_received = payment(
            'refunded', callbacks=[('paid', 'processed', None, self.t0 + 5 * minute)], refunded_amount=Decimal('100.00')
        )
        self.only_unprocessed = payment('completed', callbacks=[('paid', 'orphan', self.t0 + minute, self.t0 + minute)])
        self.plain = payment('completed')
        self.disputed = payment('disputed')
        self.pending = payment('pending')
        self.failed = payment('failed')
        self.expired = payment('expired')

        # Bookings: with a ledger payment, without one, and unpaid.
        def booking(status, *, paid_at=None):
            self.counter += 1
            owner = User.objects.create(username=f'owner{self.counter}', email=f'o{self.counter}@example.com')
            row = Booking.objects.create(owner=owner, event=event, status=status)
            Booking.objects.filter(pk=row.pk).update(created_at=self.t0)
            if paid_at is not None:
                Payment.objects.create(booking=row, amount=Decimal('50.00'), status='completed')
                Payment.objects.filter(booking=row).update(created_at=self.t0)
            return row.pk

        self.booking_paid_later = booking('confirmed', paid_at=True)
        self.booking_plain = booking('confirmed')
        self.booking_refunded = booking('refunded')
        self.booking_holding = booking('holding')
        self.booking_expired = booking('expired')

    def migrate_payments(self):
        return _migrate(PAYMENTS_DONE)

    def paid_at(self, apps, pk):
        return apps.get_model('payments', 'Payment').objects.get(pk=pk).paid_at

    # ── payments ──

    def test_backfill_uses_the_earliest_processed_paid_callback_else_created_at(self):
        apps = self.migrate_payments()
        minute = timedelta(minutes=1)
        self.assertEqual(self.paid_at(apps, self.first_callback), self.t0 + 10 * minute)
        self.assertEqual(self.paid_at(apps, self.only_received), self.t0 + 5 * minute)  # received_at
        self.assertEqual(self.paid_at(apps, self.only_unprocessed), self.t0)  # created_at
        self.assertEqual(self.paid_at(apps, self.plain), self.t0)
        self.assertEqual(self.paid_at(apps, self.disputed), self.t0)

    def test_unpaid_payments_stay_empty(self):
        apps = self.migrate_payments()
        for pk in (self.pending, self.failed, self.expired):
            self.assertIsNone(self.paid_at(apps, pk))

    def test_the_backfill_keeps_updated_at(self):
        before = dict(self.old.get_model('payments', 'Payment').objects.values_list('pk', 'updated_at'))
        apps = self.migrate_payments()
        after = dict(apps.get_model('payments', 'Payment').objects.values_list('pk', 'updated_at'))
        self.assertEqual(after, before)

    def test_a_rerun_changes_nothing(self):
        apps = self.migrate_payments()
        before = list(apps.get_model('payments', 'Payment').objects.order_by('pk').values_list('pk', 'paid_at'))
        self.assertEqual(paid_at_module.backfill_paid_at(apps), 0)
        self.assertEqual(
            list(apps.get_model('payments', 'Payment').objects.order_by('pk').values_list('pk', 'paid_at')), before
        )

    def test_the_index_exists_and_there_is_no_check_yet(self):
        self.migrate_payments()
        with connection.cursor() as cursor:
            cursor.execute("SELECT indexname FROM pg_indexes WHERE indexname = 'payment_paid_at_idx'")
            self.assertEqual(len(cursor.fetchall()), 1)
            cursor.execute("SELECT conname FROM pg_constraint WHERE conname = 'payment_paid_at_when_paid'")
            self.assertEqual(cursor.fetchall(), [])
        # Old code completing a payment without paid_at is accepted (rollback safety).
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE payments_payment SET status = 'completed', paid_at = NULL WHERE id = %s", [self.pending]
            )
            self.assertEqual(cursor.rowcount, 1)

    def test_reverse_drops_the_column_and_forward_again_backfills_again(self):
        apps = self.migrate_payments()
        self.assertIsNotNone(self.paid_at(apps, self.plain))
        back = _migrate(BEFORE)
        with self.assertRaises(FieldDoesNotExist):
            back.get_model('payments', 'Payment')._meta.get_field('paid_at')
        with connection.cursor() as cursor:
            cursor.execute("SELECT indexname FROM pg_indexes WHERE indexname = 'payment_paid_at_idx'")
            self.assertEqual(cursor.fetchall(), [])
        again = self.migrate_payments()
        self.assertEqual(self.paid_at(again, self.plain), self.t0)

    # ── bookings ──

    def test_bookings_are_confirmed_when_their_payment_was_paid_else_when_created(self):
        _migrate(PAYMENTS_DONE)
        apps = _migrate(BOOKINGS_DONE)
        Booking = apps.get_model('bookings', 'Booking')
        Payment = apps.get_model('payments', 'Payment')
        paid = Payment.objects.get(booking=self.booking_paid_later).paid_at
        self.assertEqual(Booking.objects.get(pk=self.booking_paid_later).confirmed_at, paid)
        self.assertEqual(Booking.objects.get(pk=self.booking_plain).confirmed_at, self.t0)
        self.assertEqual(Booking.objects.get(pk=self.booking_refunded).confirmed_at, self.t0)
        self.assertIsNone(Booking.objects.get(pk=self.booking_holding).confirmed_at)
        self.assertIsNone(Booking.objects.get(pk=self.booking_expired).confirmed_at)
        self.assertEqual(confirmed_at_module.backfill_confirmed_at(apps), 0)

    def test_bookings_reverse_drops_the_column(self):
        apps = _migrate(BOOKINGS_DONE)
        self.assertIsNotNone(apps.get_model('bookings', 'Booking').objects.get(pk=self.booking_plain).confirmed_at)
        back = _migrate(BEFORE)
        with self.assertRaises(FieldDoesNotExist):
            back.get_model('bookings', 'Booking')._meta.get_field('confirmed_at')
