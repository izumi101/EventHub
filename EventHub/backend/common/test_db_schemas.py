"""One schema per domain (common/db_schemas.py, docs/DATABASE_SCHEMAS.md).

The test database is built by `migrate`, so it went through the same
post_migrate step as a real deployment. Layout changes made here run inside
the test transaction (PostgreSQL DDL is transactional) and are rolled back.
"""

from io import StringIO
from types import SimpleNamespace

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.db import connection, models
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import SimpleTestCase, TestCase
from django.test.utils import isolate_apps

from common import db_schemas
from common.db_schemas import (
    APP_SCHEMAS,
    DOMAIN_SCHEMAS,
    PUBLIC,
    SEARCH_PATH,
    SchemaLayoutError,
    arrange,
    expected_tables,
    restore_public,
    table_locations,
    unmapped_apps,
)
from events.models import Category, Event


def _fake_registry(*labels):
    """A stand-in app registry with one managed model per app label."""
    metas = [SimpleNamespace(app_label=label, db_table=f'{label}_thing', managed=True, proxy=False) for label in labels]
    return SimpleNamespace(get_models=lambda include_auto_created=False: [SimpleNamespace(_meta=m) for m in metas])


class MappingTests(SimpleTestCase):
    def test_every_installed_app_with_tables_has_a_schema(self):
        missing = unmapped_apps()
        self.assertEqual(
            missing,
            [],
            f'App(s) {", ".join(missing)} create tables but have no schema: add them to APP_SCHEMAS in '
            'common/db_schemas.py (docs/DATABASE_SCHEMAS.md, "Adding an app").',
        )

    def test_an_unmapped_app_is_reported_and_left_alone(self):
        registry = _fake_registry('events', 'brand_new_app')
        self.assertEqual(unmapped_apps(registry), ['brand_new_app'])
        self.assertNotIn('brand_new_app_thing', expected_tables(registry))
        self.assertEqual(expected_tables(registry)['events_thing'], 'events')

    def test_every_model_table_and_auto_m2m_table_maps_to_a_domain_schema(self):
        tables = expected_tables()
        for model in apps.get_models(include_auto_created=True):
            if model._meta.managed and not model._meta.proxy:
                with self.subTest(table=model._meta.db_table):
                    self.assertIn(tables[model._meta.db_table], DOMAIN_SCHEMAS)
        self.assertEqual(tables['auth_user_groups'], 'identity')  # an auto-created M2M table
        self.assertEqual(tables['django_migrations'], 'platform')

    def test_expected_layout(self):
        self.assertEqual(
            {label: APP_SCHEMAS[label] for label in ('auth', 'accounts', 'token_blacklist', 'mfa')},
            dict.fromkeys(('auth', 'accounts', 'token_blacklist', 'mfa'), 'identity'),
        )
        for label in ('events', 'bookings', 'payments', 'jobs', 'notifications'):
            self.assertEqual(APP_SCHEMAS[label], label)
        for label in ('admin', 'contenttypes', 'sessions'):
            self.assertEqual(APP_SCHEMAS[label], 'platform')

    def test_search_path_is_constant_and_starts_with_public(self):
        self.assertEqual(SEARCH_PATH[0], PUBLIC)
        self.assertEqual(SEARCH_PATH[1:], DOMAIN_SCHEMAS)
        self.assertNotIn('$user', SEARCH_PATH)
        self.assertEqual(
            settings.DATABASES['default']['OPTIONS']['options'],
            '-c search_path=public,identity,events,bookings,payments,jobs,notifications,platform',
        )


class LayoutTests(TestCase):
    def locations(self):
        with connection.cursor() as cursor:
            return table_locations(cursor)

    def scalar(self, query, params=None):
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()[0]

    def test_every_table_is_in_its_schema_and_public_has_none(self):
        locations = self.locations()
        for table, schema in expected_tables().items():
            with self.subTest(table=table):
                self.assertEqual(locations.get(table), [schema])
        self.assertEqual([t for t, schemas in locations.items() if PUBLIC in schemas], [])

    def test_public_holds_only_extension_objects(self):
        self.assertEqual(
            self.scalar("SELECT extnamespace::regnamespace::text FROM pg_extension WHERE extname = 'vector'"), PUBLIC
        )
        own = (
            "SELECT count(*) FROM {catalog} o WHERE o.{ns} = 'public'::regnamespace AND NOT EXISTS ("
            "SELECT 1 FROM pg_depend d WHERE d.classid = '{catalog}'::regclass AND d.objid = o.oid AND d.deptype = 'e')"
        )
        self.assertEqual(self.scalar(own.format(catalog='pg_class', ns='relnamespace')), 0)
        self.assertEqual(self.scalar(own.format(catalog='pg_proc', ns='pronamespace')), 0)

    def test_sequences_and_indexes_moved_with_their_tables(self):
        self.assertEqual(
            self.scalar("SELECT pg_get_serial_sequence('events_event', 'id')"), 'events.events_event_id_seq'
        )
        self.assertEqual(
            self.scalar("SELECT pg_get_serial_sequence('auth_user_groups', 'id')"), 'identity.auth_user_groups_id_seq'
        )
        self.assertEqual(
            self.scalar("SELECT count(*) FROM pg_indexes WHERE tablename = 'events_event' AND schemaname <> 'events'"),
            0,
        )
        self.assertGreater(self.scalar("SELECT count(*) FROM pg_indexes WHERE schemaname = 'events'"), 20)

    def test_migrate_twice_is_a_no_op(self):
        arrange()  # a cloned test database (--parallel) starts without the database setting
        self.assertFalse(arrange().changed)
        out = StringIO()
        call_command('migrate', verbosity=1, stdout=out)
        self.assertIn('No migrations to apply', out.getvalue())
        self.assertNotIn('Database schemas', out.getvalue())

    def test_django_migrations_lives_in_platform_and_migrate_finds_it(self):
        self.assertEqual(self.locations()['django_migrations'], ['platform'])
        self.assertTrue(MigrationRecorder(connection).has_table())
        self.assertIn(('events', '0001_initial'), MigrationRecorder(connection).applied_migrations())
        executor = MigrationExecutor(connection)
        self.assertEqual(executor.migration_plan(executor.loader.graph.leaf_nodes()), [])

    def test_unqualified_raw_sql_and_orm_work(self):
        category = Category.objects.create(name='Schemas', description='', icon='')
        self.assertEqual(self.scalar('SELECT name FROM events_category WHERE id = %s', [category.pk]), 'Schemas')
        self.assertEqual(
            self.scalar(
                'SELECT count(*) FROM events_event e JOIN auth_user u ON u.id = e.organizer_id '
                'JOIN django_content_type ct ON true WHERE false'
            ),
            0,
        )
        self.assertEqual(Event.objects.count(), self.scalar('SELECT count(*) FROM events.events_event'))
        self.assertEqual(
            self.scalar('SHOW search_path').replace(' ', ''),
            'public,identity,events,bookings,payments,jobs,notifications,platform',
        )

    def test_search_path_is_persisted_for_other_clients(self):
        arrange()  # a cloned test database (--parallel) starts without database settings
        rows = self.scalar(
            "SELECT array_agg(coalesce(r.rolname, '*') || ' ' || cfg ORDER BY r.rolname NULLS FIRST) "
            'FROM pg_db_role_setting s LEFT JOIN pg_roles r ON r.oid = s.setrole, unnest(s.setconfig) cfg '
            'WHERE s.setdatabase = (SELECT oid FROM pg_database WHERE datname = current_database()) '
            "AND cfg LIKE 'search_path=%%' AND (s.setrole = 0 OR r.rolname = current_user)"
        )
        value = 'search_path=public, identity, events, bookings, payments, jobs, notifications, platform'
        self.assertEqual(rows, [f'* {value}', f'{connection.settings_dict["USER"]} {value}'])

    @isolate_apps('events')
    def test_a_new_table_created_in_public_is_moved_with_its_m2m_table(self):
        class Gadget(models.Model):
            name = models.CharField(max_length=10)
            tags = models.ManyToManyField('self', symmetrical=False)

            class Meta:
                app_label = 'events'
                db_table = 'events_schema_test_gadget'

            def __str__(self):
                return self.name

        registry = Gadget._meta.apps
        with connection.schema_editor() as editor:
            editor.create_model(Gadget)  # what a new migration does: lands in public
        through = Gadget.tags.through._meta.db_table
        self.assertEqual(self.locations()[Gadget._meta.db_table], [PUBLIC])
        self.assertEqual(self.locations()[through], [PUBLIC])

        result = arrange(app_registry=registry)

        self.assertIn((Gadget._meta.db_table, PUBLIC, 'events'), result.moved)
        self.assertIn((through, PUBLIC, 'events'), result.moved)
        self.assertEqual(self.locations()[Gadget._meta.db_table], ['events'])
        self.assertEqual(
            self.scalar("SELECT pg_get_serial_sequence('events_schema_test_gadget', 'id')"),
            'events.events_schema_test_gadget_id_seq',
        )
        Gadget.objects.create(name='ok')  # the ORM finds it unqualified
        self.assertFalse(arrange(app_registry=registry).changed)

    def test_a_table_in_two_schemas_stops_the_move(self):
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE public.jobs_job (id integer)')
        with self.assertRaisesMessage(SchemaLayoutError, 'jobs_job'):
            arrange()

    def test_rollback_moves_everything_back_and_apply_restores_it(self):
        with connection.cursor() as cursor:
            # Default privileges reference the schema (setup_db_roles sets them).
            cursor.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA events GRANT SELECT ON TABLES TO PUBLIC')
        total = len(expected_tables())
        with connection.cursor() as cursor:
            cursor.execute('SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)', [list(DOMAIN_SCHEMAS)])
            existing = sorted(row[0] for row in cursor.fetchall())
        category = Category.objects.create(name='Rollback', description='', icon='')

        result = restore_public()

        self.assertEqual(len(result.moved), total)
        self.assertEqual(sorted(result.dropped_schemas), existing)
        self.assertEqual({tuple(s) for s in self.locations().values()}, {(PUBLIC,)})
        self.assertEqual(
            self.scalar('SELECT count(*) FROM pg_namespace WHERE nspname = ANY(%s)', [list(DOMAIN_SCHEMAS)]), 0
        )
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())

        result = arrange()

        self.assertEqual(len(result.moved), total)
        self.assertEqual(self.locations()['events_category'], ['events'])
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())

    def test_db_schemas_command(self):
        out = StringIO()
        call_command('db_schemas', '--check', stdout=out)
        self.assertIn('identity', out.getvalue())
        self.assertNotIn('misplaced', out.getvalue())
        with connection.cursor() as cursor:
            cursor.execute('ALTER TABLE jobs.jobs_job SET SCHEMA public')
        with self.assertRaisesMessage(Exception, '1 misplaced table'):
            call_command('db_schemas', '--check', stdout=StringIO())
        out = StringIO()
        call_command('db_schemas', 'apply', stdout=out)
        self.assertIn('moved public.jobs_job -> jobs.jobs_job', out.getvalue())

    def test_schema_names_are_validated(self):
        self.assertRegex(db_schemas.connection_options(), r'^-c search_path=[a-z_,]+$')
