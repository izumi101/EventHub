"""Prove what the database roles may and may not do (docs/DATABASE_ROLES.md).

Connects as each configured role and runs probes inside transactions that
are rolled back: reads and writes the app needs, DDL it must be denied, and
writes the read-only role must be denied. Then the owner creates a throwaway
table (as a new migration would) to show that ALTER DEFAULT PRIVILEGES gives
the roles access to it without another GRANT. Exits non-zero when any probe
has an unexpected outcome.
"""

from django.core.management.base import BaseCommand, CommandError

from common.db_roles import configured_roles, verify_roles


class Command(BaseCommand):
    help = 'Connect as the app and read-only roles and check what they may and may not do.'

    def handle(self, *args, **options):
        if not configured_roles():
            raise CommandError('No database roles configured: set POSTGRES_APP_PASSWORD / POSTGRES_READONLY_PASSWORD.')
        probes = verify_roles()
        width = max(len(p.action) for p in probes)
        role_width = max(len(p.role) for p in probes)
        for p in probes:
            mark = 'PASS' if p.ok else 'FAIL'
            line = f'{mark}  {p.role:<{role_width}}  {p.action:<{width}}  expected {p.expected:<7}  got {p.outcome}'
            if p.detail:
                line += f'  ({p.detail})'
            self.stdout.write(self.style.SUCCESS(line) if p.ok else self.style.ERROR(line))
        failed = [p for p in probes if not p.ok]
        if failed:
            raise CommandError(f'{len(failed)} of {len(probes)} role probes had an unexpected outcome.')
        self.stdout.write(self.style.SUCCESS(f'All {len(probes)} role probes passed.'))
