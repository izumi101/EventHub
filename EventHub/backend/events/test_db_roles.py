"""Least-privilege database roles (common/db_roles.py, docs/DATABASE_ROLES.md).

The roles are cluster-wide, so every test uses throwaway role names and drops
them again; running the suite against a development cluster never touches
the real eventhub_app / eventhub_readonly roles.
"""

import os
import secrets
import subprocess
import sys
from io import StringIO
from pathlib import Path

import psycopg
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from psycopg import errors, sql

from common.db_roles import (
    ALLOWED,
    DENIED,
    RoleSetupError,
    connect_as,
    setup_roles,
    verify_roles,
)
from common.sql_checks import ReadonlyRoleExecutor, load_checks, run_checks


def _role_name(kind):
    return f'ehtest_{kind}_{secrets.token_hex(4)}'


class DatabaseRolesTests(TransactionTestCase):
    def setUp(self):
        self.app, self.ro = _role_name('app'), _role_name('ro')
        self.app_password, self.ro_password = secrets.token_urlsafe(18), secrets.token_urlsafe(18)
        override = override_settings(
            DB_APP_USER=self.app,
            DB_APP_PASSWORD=self.app_password,
            DB_READONLY_USER=self.ro,
            DB_READONLY_PASSWORD=self.ro_password,
        )
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(self.drop_roles)
        connection.ensure_connection()

    def drop_roles(self):
        connection.ensure_connection()
        with connection.connection.cursor() as cur:
            for role in (self.app, self.ro):
                if cur.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', [role]).fetchone():
                    cur.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
                    cur.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))

    def role_attributes(self, role):
        with connection.cursor() as cur:
            cur.execute(
                'SELECT rolsuper, rolcreatedb, rolcreaterole, rolcanlogin, rolconfig FROM pg_roles WHERE rolname = %s',
                [role],
            )
            return cur.fetchone()

    def test_setup_creates_least_privilege_roles_and_is_idempotent(self):
        out = StringIO()
        call_command('setup_db_roles', stdout=out)
        call_command('setup_db_roles', stdout=out)
        self.assertIn(f'app role "{self.app}": created', out.getvalue())
        self.assertIn(f'app role "{self.app}": updated', out.getvalue())
        for role in (self.app, self.ro):
            is_super, createdb, createrole, can_login, _ = self.role_attributes(role)
            self.assertEqual((is_super, createdb, createrole, can_login), (False, False, False, True))
        self.assertIn('default_transaction_read_only=on', self.role_attributes(self.ro)[4])

    def test_app_role_can_use_data_but_not_change_the_schema(self):
        setup_roles()
        with connect_as(self.app, self.app_password) as conn:
            conn.execute('SELECT count(*) FROM events_event').fetchone()
            with conn.transaction(force_rollback=True):
                conn.execute(
                    "INSERT INTO events_category (name, description, icon, created_at) VALUES ('x', '', '', now())"
                )
            for statement in (
                'CREATE TABLE roles_test (id integer)',
                'DROP TABLE events_category',
                'ALTER TABLE events_event ADD COLUMN roles_test integer',
                'TRUNCATE events_category',
                'DELETE FROM django_migrations',
            ):
                with (
                    self.subTest(statement=statement),
                    self.assertRaises(errors.InsufficientPrivilege),
                    conn.transaction(force_rollback=True),
                ):
                    conn.execute(statement)

    def test_readonly_role_cannot_write_or_read_secrets(self):
        setup_roles()
        with connect_as(self.ro, self.ro_password) as conn:
            self.assertEqual(conn.execute('SHOW default_transaction_read_only').fetchone()[0], 'on')
            conn.execute('SELECT username, email FROM auth_user').fetchall()
            conn.execute('SET default_transaction_read_only = off')  # test the grants, not just the default
            for statement in (
                "INSERT INTO events_category (name, description, icon, created_at) VALUES ('x', '', '', now())",
                'UPDATE events_event SET title = title',
                'DELETE FROM events_event',
                'SELECT password FROM auth_user',
                'SELECT * FROM django_session',
                'SELECT * FROM token_blacklist_outstandingtoken',
                'SELECT secret FROM events_webhook',
            ):
                with (
                    self.subTest(statement=statement),
                    self.assertRaises(errors.InsufficientPrivilege),
                    conn.transaction(force_rollback=True),
                ):
                    conn.execute(statement)

    def test_tables_created_after_setup_are_usable_through_default_privileges(self):
        setup_roles()
        table = sql.Identifier(f'roles_later_{secrets.token_hex(3)}')
        raw = connection.connection
        with raw.cursor() as cur:  # the owner, as a later migration would
            cur.execute(
                sql.SQL('CREATE TABLE {} (id bigint GENERATED BY DEFAULT AS IDENTITY, note text)').format(table)
            )
        try:
            with connect_as(self.app, self.app_password) as conn:
                conn.execute(sql.SQL("INSERT INTO {} (note) VALUES ('ok')").format(table))
                self.assertEqual(conn.execute(sql.SQL('SELECT count(*) FROM {}').format(table)).fetchone()[0], 1)
            with connect_as(self.ro, self.ro_password) as conn:
                self.assertEqual(conn.execute(sql.SQL('SELECT count(*) FROM {}').format(table)).fetchone()[0], 1)
                conn.execute('SET default_transaction_read_only = off')
                with self.assertRaises(errors.InsufficientPrivilege):
                    conn.execute(sql.SQL("INSERT INTO {} (note) VALUES ('no')").format(table))
        finally:
            with raw.cursor() as cur:
                cur.execute(sql.SQL('DROP TABLE {}').format(table))

    def test_verify_db_roles_command_passes(self):
        setup_roles()
        probes = verify_roles()
        self.assertGreaterEqual(len(probes), 20)
        self.assertEqual([p for p in probes if not p.ok], [])
        self.assertTrue(any(p.expected == DENIED for p in probes))
        self.assertTrue(any(p.expected == ALLOWED for p in probes))
        out = StringIO()
        call_command('verify_db_roles', stdout=out)
        self.assertIn('role probes passed', out.getvalue())

    def test_every_sql_check_runs_as_the_readonly_role(self):
        setup_roles()
        executor = ReadonlyRoleExecutor()
        try:
            results = run_checks(load_checks(), executor)
        finally:
            executor.close()
        self.assertEqual({r.check.name: r.error for r in results if r.error}, {})

    def test_password_rotation(self):
        setup_roles()
        old = self.app_password
        with override_settings(DB_APP_PASSWORD='rotated-' + secrets.token_urlsafe(12)):
            setup_roles()
            with connect_as(self.app, settings.DB_APP_PASSWORD) as conn:
                conn.execute('SELECT 1')
            with self.assertRaises(psycopg.OperationalError):
                connect_as(self.app, old)

    def test_refuses_owner_or_superuser_as_app_role(self):
        with override_settings(DB_APP_USER=connection.settings_dict['USER']), self.assertRaises(CommandError):
            call_command('setup_db_roles', stdout=StringIO())
        with connection.cursor() as cur:
            cur.execute('SELECT rolname FROM pg_roles WHERE rolsuper AND rolname <> current_user LIMIT 1')
            other_superuser = cur.fetchone()
        if other_superuser:
            with override_settings(DB_APP_USER=other_superuser[0]), self.assertRaises(RoleSetupError):
                setup_roles()

    def test_nothing_happens_without_passwords(self):
        with override_settings(DB_APP_PASSWORD='', DB_READONLY_PASSWORD=''):
            out = StringIO()
            call_command('setup_db_roles', stdout=out)
        self.assertIn('skipped', out.getvalue())
        self.assertIsNone(self.role_attributes(self.app))


class DatabaseUserSelectionTests(SimpleTestCase):
    """settings.py: which role the process connects as."""

    def connect_user(self, argv, **env):
        base = {k: v for k, v in os.environ.items() if not k.startswith(('POSTGRES_', 'DJANGO_DB_'))}
        base.update({'DJANGO_DEBUG': '1', 'POSTGRES_USER': 'owner_role', 'POSTGRES_PASSWORD': 'owner-pw'}, **env)
        code = (
            'import sys; sys.argv = ' + repr(argv) + '; '
            'import eventhub_backend.settings as s; '
            "print(s.DATABASES['default']['USER'])"
        )
        result = subprocess.run(  # noqa: S603 - fixed interpreter and code
            [sys.executable, '-c', code],
            cwd=Path(settings.BASE_DIR),
            env=base,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip(), result.stderr

    def test_app_processes_use_the_app_role(self):
        user, _ = self.connect_user(['gunicorn', 'eventhub_backend.asgi:application'], POSTGRES_APP_PASSWORD='x')
        self.assertEqual(user, 'eventhub_app')
        user, _ = self.connect_user(['manage.py', 'run_worker'], POSTGRES_APP_PASSWORD='x', POSTGRES_APP_USER='svc')
        self.assertEqual(user, 'svc')

    def test_migrations_tests_and_explicit_override_use_the_owner(self):
        for argv, env in (
            (['manage.py', 'migrate'], {}),
            (['manage.py', 'setup_db_roles'], {}),
            (['manage.py', 'test'], {}),
            (['manage.py', 'shell'], {'DJANGO_DB_AS_OWNER': '1'}),
        ):
            with self.subTest(argv=argv, env=env):
                user, _ = self.connect_user(argv, POSTGRES_APP_PASSWORD='x', **env)
                self.assertEqual(user, 'owner_role')

    def test_without_app_password_the_owner_is_used_with_a_warning(self):
        user, stderr = self.connect_user(['manage.py', 'runserver'])
        self.assertEqual(user, 'owner_role')
        self.assertIn('POSTGRES_APP_PASSWORD is not set', stderr)
