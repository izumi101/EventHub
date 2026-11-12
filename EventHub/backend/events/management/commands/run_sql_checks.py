"""Run the SQL data checks (backend/sql/checks) and print what they found.

    python manage.py run_sql_checks                    # all checks, table output
    python manage.py run_sql_checks --show-rows 3      # plus the first offending rows
    python manage.py run_sql_checks --format json      # machine readable
    python manage.py run_sql_checks --check capacity_overrun --check stale_holds

Runs as the read-only role (POSTGRES_READONLY_USER) when it is configured,
otherwise on the app's own connection inside read-only transactions. Exits
with status 1 when a CRITICAL check finds rows (or any check with
--fail-on warning) and when a check cannot run at all.

--inject-defects (DJANGO_DEBUG=1 only) proves the checks work: it runs every
check, injects one known defect per check (common/sql_check_defects.py),
runs them again and reports whether each check caught its defect. Everything
happens in one transaction that is rolled back. Dropping the unique index
for the duplicate-registration defect needs the schema owner: run it with
DJANGO_DB_AS_OWNER=1, otherwise that one defect is reported as skipped.
"""

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from common.sql_check_defects import DEFECTS, inject_all
from common.sql_checks import CheckDefinitionError, DjangoConnectionExecutor, load_checks, make_executor, run_checks

FAIL_ON = {'critical': {'CRITICAL'}, 'warning': {'CRITICAL', 'WARNING'}, 'never': set()}


class Command(BaseCommand):
    help = 'Run the SQL data-integrity checks in backend/sql/checks and report what they found.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check', action='append', dest='only', default=[], help='Run only this check (repeatable).'
        )
        parser.add_argument('--format', choices=['text', 'json'], default='text')
        parser.add_argument('--show-rows', type=int, default=0, help='Print up to N offending rows per check.')
        parser.add_argument(
            '--fail-on',
            choices=sorted(FAIL_ON),
            default='critical',
            help='Exit with status 1 when checks of this severity (or higher) find rows. Default: critical.',
        )
        parser.add_argument(
            '--use-default-connection',
            action='store_true',
            help='Use the app connection (read-only transactions) even when the read-only role is configured.',
        )
        parser.add_argument(
            '--inject-defects',
            action='store_true',
            help='DEBUG only: inject one known defect per check in a rolled-back transaction and show each is caught.',
        )

    def handle(self, *args, **options):
        try:
            checks = load_checks(only=options['only'])
        except CheckDefinitionError as exc:
            raise CommandError(str(exc)) from exc
        if options['inject_defects']:
            return self.inject_defects(checks, options)

        executor = make_executor(use_default_connection=options['use_default_connection'])
        try:
            results = run_checks(checks, executor)
        finally:
            executor.close()

        if options['format'] == 'json':
            self.stdout.write(
                json.dumps(
                    {
                        'connection': executor.description,
                        'results': [r.as_dict(options['show_rows'] or 5) for r in results],
                    },
                    indent=2,
                )
            )
        else:
            self.print_table(results, executor.description, options['show_rows'])

        failing = FAIL_ON[options['fail_on']]
        errors = [r for r in results if r.error]
        bad = [r for r in results if r.rows and r.check.severity in failing]
        if errors or bad:
            parts = []
            if bad:
                parts.append(f'{len(bad)} check(s) at or above {options["fail_on"].upper()} found problems')
            if errors:
                parts.append(f'{len(errors)} check(s) could not run')
            raise CommandError('; '.join(parts) + '.', returncode=1)

    # ------------------------------------------------------------------ #

    def print_table(self, results, description, show_rows):
        self.stdout.write(f'Connection: {description}')
        width = max(len(r.check.name) for r in results)
        header = f'{"check":<{width}}  {"severity":<8}  {"rows":>5}  {"ms":>6}  sample ids'
        self.stdout.write(header)
        self.stdout.write('-' * len(header))
        for r in results:
            sample = f'ERROR: {r.error}' if r.error else (', '.join(r.samples()) or '-')
            line = f'{r.check.name:<{width}}  {r.check.severity:<8}  {r.found:>5}  {r.seconds * 1000:>6.1f}  {sample}'
            if r.error or (r.rows and r.check.severity == 'CRITICAL'):
                line = self.style.ERROR(line)
            elif r.rows:
                line = self.style.WARNING(line)
            self.stdout.write(line)
            if show_rows and r.rows:
                self.stdout.write(f'    columns: {", ".join(r.columns)}')
                for row in r.rows[:show_rows]:
                    self.stdout.write('    ' + ' | '.join('' if v is None else str(v) for v in row))
        total = sum(1 for r in results if r.rows)
        self.stdout.write(f'{len(results)} checks, {total} with findings, {sum(r.found for r in results)} rows.')

    def inject_defects(self, checks, options):
        if not settings.DEBUG:
            raise CommandError('--inject-defects writes (and rolls back) test rows; run it only with DJANGO_DEBUG=1.')
        missing = [c.name for c in checks if c.name not in DEFECTS]
        if missing:
            raise CommandError(f'No defect defined for: {", ".join(missing)}')
        wanted = {c.name for c in checks}
        with transaction.atomic():
            executor = DjangoConnectionExecutor()
            before = {r.check.name: r for r in run_checks(checks, executor)}
            skipped = {name: why for name, why in inject_all().items() if name in wanted}
            after = {r.check.name: r for r in run_checks(checks, executor)}
            transaction.set_rollback(True)

        rows, missed = [], []
        for check in checks:
            name, b, a = check.name, before[check.name], after[check.name]
            if skipped.get(name):
                verdict = f'SKIPPED ({skipped[name]})'
            elif a.error:
                verdict = f'ERROR: {a.error}'
            elif a.found > b.found:
                verdict = 'CAUGHT'
            else:
                verdict = 'MISSED'
            if verdict in ('MISSED',) or verdict.startswith('ERROR'):
                missed.append(name)
            rows.append((name, check.severity, b.found, a.found, verdict, a.samples(3)))

        if options['format'] == 'json':
            payload = [
                {'name': n, 'severity': s, 'rows_before': b, 'rows_after': a, 'verdict': v, 'samples': smp}
                for n, s, b, a, v, smp in rows
            ]
            self.stdout.write(
                json.dumps({'connection': connection.settings_dict['USER'], 'results': payload}, indent=2)
            )
        else:
            self.stdout.write(f'Injected defects as "{connection.settings_dict["USER"]}" (rolled back afterwards).')
            width = max(len(r[0]) for r in rows)
            self.stdout.write(f'{"check":<{width}}  {"severity":<8}  {"before":>6}  {"after":>5}  verdict')
            for name, severity, b, a, verdict, _ in rows:
                line = f'{name:<{width}}  {severity:<8}  {b:>6}  {a:>5}  {verdict}'
                ok = verdict == 'CAUGHT'
                self.stdout.write(self.style.SUCCESS(line) if ok else self.style.WARNING(line))
            caught = sum(1 for r in rows if r[4] == 'CAUGHT')
            self.stdout.write(f'{caught} of {len(rows)} injected defects caught; nothing was committed.')
        if missed:
            raise CommandError(f'Defects not caught: {", ".join(missed)}', returncode=1)
