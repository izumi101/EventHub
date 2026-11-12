"""SQL data checks (backend/sql/checks), their runner and the KZ demo seed."""

import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from bookings.models import Booking, BookingSeat
from common.sql_check_defects import DEFECTS, inject_all
from common.sql_checks import SEVERITIES, DjangoConnectionExecutor, load_checks, run_checks
from events.models import CheckInLog, Event, Registration, Review, WaitlistEntry
from payments.models import Payment, Refund


class CheckDefinitionTests(SimpleTestCase):
    def test_every_check_is_documented_and_has_a_defect(self):
        checks = load_checks()
        self.assertGreaterEqual(len(checks), 15)
        for check in checks:
            with self.subTest(check=check.name):
                self.assertIn(check.severity, SEVERITIES)
                self.assertTrue(check.invariant and check.why)
                self.assertIn('SELECT', check.sql.upper())
        self.assertEqual({c.name for c in checks}, set(DEFECTS))


class ChecksCatchInjectedDefectsTests(TestCase):
    def test_each_check_catches_its_defect(self):
        checks = load_checks()
        executor = DjangoConnectionExecutor()
        before = {r.check.name: r for r in run_checks(checks, executor)}
        self.assertEqual({n: r.error for n, r in before.items() if r.error}, {})
        skipped = {name: why for name, why in inject_all().items() if why}
        self.assertEqual(skipped, {})  # the test runner is the schema owner
        for result in run_checks(checks, executor):
            with self.subTest(check=result.check.name):
                self.assertEqual(result.error, '')
                self.assertGreater(result.found, before[result.check.name].found)


class RunSqlChecksCommandTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command('run_sql_checks', *args, stdout=out)
        return out.getvalue()

    def test_clean_database_passes(self):
        output = self.run_command()
        self.assertIn('capacity_overrun', output)
        self.assertIn('0 with findings', output)

    def test_critical_finding_fails_with_status_1(self):
        from common.sql_check_defects import Factory, capacity_overrun

        capacity_overrun(Factory())
        with self.assertRaises(CommandError) as ctx:
            self.run_command('--check', 'capacity_overrun', '--show-rows', '2')
        self.assertEqual(ctx.exception.returncode, 1)
        # --fail-on never only reports.
        data = json.loads(self.run_command('--check', 'capacity_overrun', '--format', 'json', '--fail-on', 'never'))
        self.assertEqual(data['results'][0]['rows'], 1)

    def test_warning_does_not_fail_by_default(self):
        from common.sql_check_defects import Factory, outbox_jobs_stuck

        outbox_jobs_stuck(Factory())
        output = self.run_command('--check', 'outbox_jobs_stuck')
        self.assertIn('1 with findings', output)
        with self.assertRaises(CommandError):
            self.run_command('--check', 'outbox_jobs_stuck', '--fail-on', 'warning')

    def test_unknown_check_is_an_error(self):
        with self.assertRaises(CommandError):
            self.run_command('--check', 'no_such_check')

    @override_settings(DEBUG=True)
    def test_inject_defects_catches_all_and_rolls_back(self):
        events = Event.objects.count()
        data = json.loads(self.run_command('--inject-defects', '--format', 'json'))
        verdicts = {r['name']: r['verdict'] for r in data['results']}
        self.assertEqual({n: v for n, v in verdicts.items() if v != 'CAUGHT'}, {})
        self.assertEqual(Event.objects.count(), events)

    def test_inject_defects_needs_debug(self):
        with self.assertRaises(CommandError):
            self.run_command('--inject-defects')


class SeedDemoKzTests(TestCase):
    def test_refuses_without_debug(self):
        with self.assertRaises(CommandError):
            call_command('seed_demo_kz', stdout=StringIO())

    @override_settings(DEBUG=True)
    def test_seed_is_realistic_clean_and_idempotent(self):
        call_command('seed_demo_kz', stdout=StringIO())
        counts = self.counts()

        self.assertEqual(Event.objects.filter(currency='KZT', title='Almaty Jazz Festival 2026').count(), 1)
        self.assertGreaterEqual(counts['events'], 20)
        self.assertGreaterEqual(counts['registrations'], 2000)
        self.assertEqual(
            set(Registration.objects.values_list('status', flat=True).distinct()), {'pending', 'confirmed', 'cancelled'}
        )
        self.assertTrue(Registration.objects.filter(status='pending', seat_held_until__isnull=False).exists())
        self.assertTrue(
            {'completed', 'pending', 'failed', 'expired', 'refunded'}
            <= set(Payment.objects.values_list('status', flat=True).distinct())
        )
        self.assertTrue(Payment.objects.filter(status='completed', refunded_amount__gt=0).exists())  # partial
        self.assertEqual(
            set(Booking.objects.values_list('status', flat=True).distinct()),
            {'confirmed', 'holding', 'expired', 'refunded'},
        )
        self.assertTrue(CheckInLog.objects.exists())
        self.assertTrue(Review.objects.exists())
        self.assertTrue(WaitlistEntry.objects.filter(status='waiting').exists())
        self.assertTrue(Refund.objects.filter(kind='event_cancelled').exists())

        results = run_checks(load_checks(), DjangoConnectionExecutor())
        findings = {r.check.name: (r.error or r.rows[:3]) for r in results if r.rows or r.error}
        self.assertEqual(findings, {})

        call_command('seed_demo_kz', stdout=StringIO())
        self.assertEqual(self.counts(), counts)

    def counts(self):
        return {
            'events': Event.objects.count(),
            'registrations': Registration.objects.count(),
            'payments': Payment.objects.count(),
            'refunds': Refund.objects.count(),
            'bookings': Booking.objects.count(),
            'booking_seats': BookingSeat.objects.count(),
            'reviews': Review.objects.count(),
        }
