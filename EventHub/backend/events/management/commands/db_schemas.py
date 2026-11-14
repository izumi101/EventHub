"""Inspect, apply or roll back the per-domain schema layout (docs/DATABASE_SCHEMAS.md).

    manage.py db_schemas              # status: tables per schema, misplaced tables
    manage.py db_schemas --check      # status, exits 1 when a table is not in its schema
    manage.py db_schemas apply        # what every `migrate` does at the end
    manage.py db_schemas rollback     # everything back into public (then deploy the previous release)

Runs as the schema owner (settings.DB_OWNER_COMMANDS).
"""

from django.core.management.base import BaseCommand, CommandError

from common.db_schemas import (
    APP_SCHEMAS,
    SchemaLayoutError,
    arrange,
    misplaced_tables,
    restore_public,
    schema_summary,
    search_path_value,
    unmapped_apps,
)


class Command(BaseCommand):
    help = 'Show, apply or roll back the one-schema-per-domain database layout.'

    def add_arguments(self, parser):
        parser.add_argument('action', nargs='?', default='status', choices=('status', 'apply', 'rollback'))
        parser.add_argument('--check', action='store_true', help='status: exit 1 when any table is misplaced.')

    def handle(self, *args, action, check, **options):
        try:
            if action == 'apply':
                self._apply()
            elif action == 'rollback':
                self._rollback()
            self._status(check=check and action == 'status', show_misplaced=action != 'rollback')
        except SchemaLayoutError as exc:
            raise CommandError(str(exc)) from exc

    def _apply(self):
        result = arrange()
        for table, current, target in result.moved:
            self.stdout.write(f'moved {current}.{table} -> {target}.{table}')
        for schema in result.created_schemas:
            self.stdout.write(f'created schema {schema}')
        for target in result.settings_changed:
            self.stdout.write(f'search_path persisted for {target}')
        if not result.changed:
            self.stdout.write('Nothing to do: every table is in its schema.')

    def _rollback(self):
        result = restore_public()
        for table, schema in result.moved:
            self.stdout.write(f'moved {schema}.{table} -> public.{table}')
        for schema in result.dropped_schemas:
            self.stdout.write(f'dropped empty schema {schema}')
        for target in result.settings_reset:
            self.stdout.write(f'search_path reset for {target}')
        self.stdout.write(
            self.style.WARNING(
                f'{len(result.moved)} table(s) moved back to public. Deploy the previous release now: '
                "this release's next `migrate` moves them into the domain schemas again."
            )
        )

    def _status(self, *, check, show_misplaced=True):
        self.stdout.write(f'search_path: {search_path_value()}')
        for schema, count in schema_summary():
            apps = sorted(label for label, target in APP_SCHEMAS.items() if target == schema)
            self.stdout.write(f'  {schema:<14} {count:>3} table(s)  {", ".join(apps)}')
        misplaced = misplaced_tables() if show_misplaced else []
        for table, current, target in misplaced:
            self.stdout.write(self.style.WARNING(f'  misplaced: {current}.{table} (belongs in {target})'))
        unmapped = unmapped_apps()
        if unmapped:
            self.stdout.write(
                self.style.ERROR(f'  apps without a schema in common/db_schemas.py: {", ".join(unmapped)}')
            )
        if check and (misplaced or unmapped):
            raise CommandError(f'{len(misplaced)} misplaced table(s), {len(unmapped)} unmapped app(s).')
