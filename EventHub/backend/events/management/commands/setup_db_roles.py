"""Create / update the least-privilege PostgreSQL roles (docs/DATABASE_ROLES.md).

Runs as the schema owner (settings.DB_OWNER_COMMANDS) right after `migrate`
in entrypoint.sh, on every start: idempotent, so it works on a fresh volume
and on one that already has data.
"""

from django.core.management.base import BaseCommand, CommandError

from common.db_roles import RoleSetupError, setup_roles


class Command(BaseCommand):
    help = 'Create or update the app and read-only database roles and grant their privileges (idempotent).'

    def handle(self, *args, **options):
        try:
            setup_roles(log=self.stdout.write)
        except RoleSetupError as exc:
            raise CommandError(str(exc)) from exc
