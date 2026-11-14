"""Least-privilege PostgreSQL roles (docs/DATABASE_ROLES.md).

Three roles:

* owner (POSTGRES_USER): owns the schema, runs migrations, runs this code;
* app (POSTGRES_APP_USER): what gunicorn and the worker connect as. Reads
  and writes rows, uses sequences and functions, nothing else: no DDL, no
  TRUNCATE, cannot rewrite the migration history;
* readonly (POSTGRES_READONLY_USER): SELECT for reports and the data checks
  (`manage.py run_sql_checks`). It does not see credentials, one-time codes,
  sessions, refresh tokens or webhook signing secrets.

`setup_roles()` is idempotent and runs on every container start right after
`migrate` (entrypoint.sh): it creates missing roles, resets their passwords
from the environment, re-grants privileges on every existing table and sets
default privileges so that tables created by later migrations are usable at
once. It covers `public` and every domain schema that exists
(common/db_schemas.py, docs/DATABASE_SCHEMAS.md) and persists the search
path for both roles in this database. Every identifier and password goes
through `psycopg.sql`; passwords are sent as SCRAM-SHA-256 verifiers
computed by libpq, never in clear text, so they cannot leak into the server
log.
"""

import secrets
from dataclasses import dataclass, field

import psycopg
from django.conf import settings
from django.db import connection, transaction
from psycopg import errors, sql

from common.db_schemas import DOMAIN_SCHEMAS, SEARCH_PATH, connection_options, persist_search_path

# Tables the read-only role must not read at all: sessions, refresh tokens
# and one-time codes are credentials.
READONLY_HIDDEN_TABLES = (
    'django_session',
    'token_blacklist_outstandingtoken',
    'token_blacklist_blacklistedtoken',
    'accounts_passwordresetcode',
    'accounts_emailverificationcode',
    # 2FA: encrypted TOTP secrets and recovery-code hashes.
    'mfa_totpdevice',
    'mfa_recoverycode',
    'mfa_emailcode',
)
# Tables it may read except for these columns (column-level grants).
READONLY_HIDDEN_COLUMNS = {
    'auth_user': ('password',),
    'events_webhook': ('secret',),
}
# Tables the app may read but not write: the migration history belongs to the
# owner, so a compromised app cannot mark a migration as applied or undone.
APP_READ_ONLY_TABLES = ('django_migrations',)

READONLY_STATEMENT_TIMEOUT = '60s'
READONLY_CONNECTION_LIMIT = 10


class RoleSetupError(Exception):
    pass


@dataclass(frozen=True)
class RoleSpec:
    kind: str  # 'app' or 'readonly'
    name: str
    password: str = field(repr=False)


def configured_roles():
    """The roles whose password is set in the environment."""
    roles = []
    if settings.DB_APP_PASSWORD:
        roles.append(RoleSpec('app', settings.DB_APP_USER, settings.DB_APP_PASSWORD))
    if settings.DB_READONLY_PASSWORD:
        roles.append(RoleSpec('readonly', settings.DB_READONLY_USER, settings.DB_READONLY_PASSWORD))
    return roles


def _q(template, *args):
    return sql.SQL(template).format(*args)


def _ident(name):
    return sql.Identifier(name)


def _schemas(cur):
    """public and the domain schemas that exist, in search-path order."""
    rows = cur.execute('SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)', [list(SEARCH_PATH)]).fetchall()
    present = {row[0] for row in rows}
    return [schema for schema in SEARCH_PATH if schema in present]


def _existing_tables(cur, names):
    """[(schema, table)] for the named tables, wherever they live."""
    rows = cur.execute(
        'SELECT schemaname, tablename FROM pg_tables WHERE schemaname = ANY(%s) AND tablename = ANY(%s) ORDER BY 1, 2',
        [list(SEARCH_PATH), list(names)],
    ).fetchall()
    return [(schema, table) for schema, table in rows]


def _validate(roles, owner):
    names = [role.name for role in roles]
    if len(set(names)) != len(names):
        raise RoleSetupError('POSTGRES_APP_USER and POSTGRES_READONLY_USER must be different roles.')
    for role in roles:
        if role.name == owner:
            raise RoleSetupError(
                f'{role.kind} role "{role.name}" is the schema owner (POSTGRES_USER); it must be a separate role.'
            )
        if role.name.startswith('pg_'):
            raise RoleSetupError(f'Role names starting with "pg_" are reserved by PostgreSQL: "{role.name}".')


def _check_owner(cur, owner):
    row = cur.execute('SELECT rolsuper, rolcreaterole FROM pg_roles WHERE rolname = current_user').fetchone()
    if not row or not (row[0] or row[1]):
        raise RoleSetupError(
            f'"{owner}" may not create roles (needs SUPERUSER or CREATEROLE); run setup_db_roles as the schema owner.'
        )


def _upsert_role(cur, raw, role):
    row = cur.execute('SELECT rolsuper FROM pg_roles WHERE rolname = %s', [role.name]).fetchone()
    if row and row[0]:
        # Never demote (or hand the app) an existing superuser.
        raise RoleSetupError(
            f'Role "{role.name}" exists and is a superuser; refusing to use it as the {role.kind} role.'
        )
    verifier = raw.pgconn.encrypt_password(role.password.encode(), role.name.encode(), b'scram-sha-256').decode()
    limit = READONLY_CONNECTION_LIMIT if role.kind == 'readonly' else -1
    cur.execute(
        _q(
            '{} ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT '
            'CONNECTION LIMIT {} PASSWORD {}',
            sql.SQL('ALTER' if row else 'CREATE'),
            _ident(role.name),
            sql.Literal(limit),
            sql.Literal(verifier),
        )
    )
    # A dedicated role inherits nothing: drop any membership it was given.
    parents = cur.execute(
        'SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid '
        'JOIN pg_roles u ON u.oid = m.member WHERE u.rolname = %s',
        [role.name],
    ).fetchall()
    for (parent,) in parents:
        cur.execute(_q('REVOKE {} FROM {}', _ident(parent), _ident(role.name)))
    if role.kind == 'readonly':
        cur.execute(_q('ALTER ROLE {} SET default_transaction_read_only = on', _ident(role.name)))
        cur.execute(
            _q('ALTER ROLE {} SET statement_timeout = {}', _ident(role.name), sql.Literal(READONLY_STATEMENT_TIMEOUT))
        )
    return 'updated' if row else 'created'


def _grant_common(cur, dbname, schemas, role):
    name, db = _ident(role.name), _ident(dbname)
    cur.execute(_q('GRANT CONNECT ON DATABASE {} TO {}', db, name))
    cur.execute(_q('REVOKE CREATE, TEMPORARY ON DATABASE {} FROM {}', db, name))
    for schema in map(_ident, schemas):
        cur.execute(_q('GRANT USAGE ON SCHEMA {} TO {}', schema, name))
        cur.execute(_q('REVOKE CREATE ON SCHEMA {} FROM {}', schema, name))
    # psql, DataGrip and the probes below connect without settings.py's
    # options; the database default covers them too, this pins it per role.
    persist_search_path(cur, dbname, role=role.name)


def _grant_app(cur, owner, schemas, role):
    name, owner_id = _ident(role.name), _ident(owner)
    default = 'ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} '
    for schema in map(_ident, schemas):
        cur.execute(_q('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}', schema, name))
        cur.execute(_q('REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA {} FROM {}', schema, name))
        cur.execute(_q('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA {} TO {}', schema, name))
        cur.execute(_q('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {} TO {}', schema, name))
        # Tables, sequences and functions the owner creates later (new migrations).
        cur.execute(_q(default + 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}', owner_id, schema, name))
        cur.execute(_q(default + 'GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {}', owner_id, schema, name))
        cur.execute(_q(default + 'GRANT EXECUTE ON FUNCTIONS TO {}', owner_id, schema, name))
    for schema, table in _existing_tables(cur, APP_READ_ONLY_TABLES):
        cur.execute(_q('REVOKE INSERT, UPDATE, DELETE ON TABLE {}.{} FROM {}', _ident(schema), _ident(table), name))


def _grant_readonly(cur, owner, schemas, role):
    name, owner_id = _ident(role.name), _ident(owner)
    for schema in map(_ident, schemas):
        cur.execute(_q('GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}', schema, name))
        cur.execute(
            _q(
                'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA {} FROM {}',
                schema,
                name,
            )
        )
        cur.execute(_q('REVOKE ALL ON ALL SEQUENCES IN SCHEMA {} FROM {}', schema, name))
        cur.execute(
            _q('ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT SELECT ON TABLES TO {}', owner_id, schema, name)
        )
    for schema, table in _existing_tables(cur, READONLY_HIDDEN_TABLES):
        cur.execute(_q('REVOKE ALL ON TABLE {}.{} FROM {}', _ident(schema), _ident(table), name))
    for schema, table in _existing_tables(cur, READONLY_HIDDEN_COLUMNS):
        hidden = READONLY_HIDDEN_COLUMNS[table]
        visible = [
            row[0]
            for row in cur.execute(
                'SELECT column_name FROM information_schema.columns '
                'WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position',
                [schema, table],
            ).fetchall()
            if row[0] not in hidden
        ]
        target = _q('{}.{}', _ident(schema), _ident(table))
        cur.execute(_q('REVOKE SELECT ON TABLE {} FROM {}', target, name))
        cur.execute(_q('REVOKE SELECT ({}) ON TABLE {} FROM {}', sql.SQL(', ').join(map(_ident, hidden)), target, name))
        cur.execute(_q('GRANT SELECT ({}) ON TABLE {} TO {}', sql.SQL(', ').join(map(_ident, visible)), target, name))


def _verify_attributes(cur, dbname, schemas, role):
    row = cur.execute(
        'SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, '
        "has_database_privilege(rolname, %s, 'CREATE'), "
        "bool_or(has_schema_privilege(rolname, s, 'CREATE')) "
        'FROM pg_roles, unnest(%s::text[]) s WHERE rolname = %s '
        'GROUP BY rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolname',
        [dbname, list(schemas), role.name],
    ).fetchone()
    if row is None or any(row):
        raise RoleSetupError(f'Role "{role.name}" still has elevated privileges after setup: {row}')


def setup_roles(*, log=lambda message: None):
    """Create or update the configured roles and (re-)grant their privileges.

    Must run on a connection that belongs to the schema owner. Returns a list
    of (role, kind, 'created' | 'updated') tuples; empty when no role is
    configured.
    """
    roles = configured_roles()
    if not roles:
        log('No database roles configured (POSTGRES_APP_PASSWORD / POSTGRES_READONLY_PASSWORD are empty): skipped.')
        return []
    owner = connection.settings_dict['USER']
    dbname = connection.settings_dict['NAME']
    _validate(roles, owner)

    connection.ensure_connection()
    raw = connection.connection
    results = []
    with transaction.atomic(), raw.cursor() as cur:
        _check_owner(cur, owner)
        schemas = _schemas(cur)
        # Nobody gets CREATE in a schema or access to the database by default.
        for schema in schemas:
            cur.execute(_q('REVOKE CREATE ON SCHEMA {} FROM PUBLIC', _ident(schema)))
        cur.execute(_q('REVOKE CONNECT, TEMPORARY ON DATABASE {} FROM PUBLIC', _ident(dbname)))
        for role in roles:
            action = _upsert_role(cur, raw, role)
            _grant_common(cur, dbname, schemas, role)
            if role.kind == 'app':
                _grant_app(cur, owner, schemas, role)
            else:
                _grant_readonly(cur, owner, schemas, role)
            _verify_attributes(cur, dbname, schemas, role)
            results.append((role.name, role.kind, action))
            log(f'{role.kind} role "{role.name}": {action}, privileges granted in schemas {", ".join(schemas)}.')
    return results


# ---------------------------------------------------------------- proof ---- #

ALLOWED, DENIED = 'allowed', 'denied'


@dataclass
class Probe:
    role: str
    action: str
    expected: str
    outcome: str = ''
    detail: str = ''

    @property
    def ok(self):
        return self.outcome == self.expected


def connect_as(user, password, *, search_path=True, **overrides):
    """A psycopg connection to the current database as another role.

    search_path=False leaves the search path to the server (the persisted
    database / role setting), as psql or DataGrip would see it.
    """
    params = connection.settings_dict
    if search_path:
        overrides.setdefault('options', connection_options())
    return psycopg.connect(
        host=params['HOST'] or None,
        port=params['PORT'] or None,
        dbname=params['NAME'],
        user=user,
        password=password,
        connect_timeout=5,
        autocommit=True,
        application_name='eventhub-db-roles',
        **overrides,
    )


def _run_probe(conn, probe, statement, params=None):
    try:
        with conn.transaction(force_rollback=True):
            conn.execute(statement, params)
        probe.outcome = ALLOWED
    except errors.InsufficientPrivilege as exc:
        probe.outcome, probe.detail = DENIED, str(exc).splitlines()[0]
    except psycopg.Error as exc:
        probe.outcome, probe.detail = f'error {exc.sqlstate}', str(exc).splitlines()[0]
    return probe


APP_PROBES = (
    ('SELECT events_event', ALLOWED, 'SELECT count(*) FROM events_event'),
    (
        'INSERT events_category',
        ALLOWED,
        "INSERT INTO events_category (name, description, icon, created_at) VALUES ('__roles_probe__', '', '', now())",
    ),
    ('UPDATE events_event', ALLOWED, 'UPDATE events_event SET title = title WHERE id = -1'),
    ('DELETE events_category', ALLOWED, "DELETE FROM events_category WHERE name = '__roles_probe__'"),
    ('CREATE TABLE', DENIED, 'CREATE TABLE roles_probe (id integer)'),
    ('ALTER TABLE', DENIED, 'ALTER TABLE events_event ADD COLUMN roles_probe integer'),
    ('DROP TABLE', DENIED, 'DROP TABLE events_category'),
    ('TRUNCATE', DENIED, 'TRUNCATE events_category'),
    ('CREATE SCHEMA', DENIED, 'CREATE SCHEMA roles_probe'),
    ('CREATE TEMP TABLE', DENIED, 'CREATE TEMP TABLE roles_probe (id integer)'),
    ('write django_migrations', DENIED, 'DELETE FROM django_migrations WHERE id = -1'),
)
READONLY_PROBES = (
    ('SELECT events_event', ALLOWED, 'SELECT count(*) FROM events_event'),
    ('SELECT auth_user.username', ALLOWED, 'SELECT username FROM auth_user LIMIT 1'),
    ('SELECT auth_user.password', DENIED, 'SELECT password FROM auth_user LIMIT 1'),
    ('SELECT django_session', DENIED, 'SELECT count(*) FROM django_session'),
    ('SELECT refresh tokens', DENIED, 'SELECT count(*) FROM token_blacklist_outstandingtoken'),
    (
        'INSERT events_category',
        DENIED,
        "INSERT INTO events_category (name, description, icon, created_at) VALUES ('__roles_probe__', '', '', now())",
    ),
    ('UPDATE events_event', DENIED, 'UPDATE events_event SET title = title WHERE id = -1'),
    ('DELETE events_event', DENIED, 'DELETE FROM events_event WHERE id = -1'),
    ('CREATE TABLE', DENIED, 'CREATE TABLE roles_probe (id integer)'),
)


def _search_path_probe():
    """Fails (an error, not ALLOWED) unless the server-side search path is SEARCH_PATH."""
    return _q(
        'DO $$ BEGIN '
        "IF regexp_replace(current_setting('search_path'), '[[:space:]\"]', '', 'g') <> {} THEN "
        "RAISE EXCEPTION 'search_path is %', current_setting('search_path'); "
        'END IF; END $$',
        sql.Literal(','.join(SEARCH_PATH)),
    )


def _schema_probes(kind):
    """Per domain schema: USAGE works on one of its tables, CREATE is denied."""
    hidden = set(READONLY_HIDDEN_TABLES) | set(READONLY_HIDDEN_COLUMNS) if kind == 'readonly' else set()
    connection.ensure_connection()
    with connection.connection.cursor() as cur:
        rows = cur.execute(
            'SELECT schemaname, min(tablename) FROM pg_tables '
            'WHERE schemaname = ANY(%s) AND NOT (tablename = ANY(%s)) GROUP BY schemaname',
            [list(DOMAIN_SCHEMAS), sorted(hidden)],
        ).fetchall()
        sample = dict(rows)
        present = set(_schemas(cur))
    probes = []
    for schema in DOMAIN_SCHEMAS:
        if schema not in present:
            continue
        if schema in sample:
            table = sample[schema]
            probes.append(
                (
                    f'SELECT {schema}.{table}',
                    ALLOWED,
                    _q('SELECT count(*) FROM {}.{}', _ident(schema), _ident(table)),
                )
            )
        probes.append(
            (f'CREATE TABLE in {schema}', DENIED, _q('CREATE TABLE {}.roles_probe (id integer)', _ident(schema)))
        )
    return probes


def verify_roles():
    """Connect as each configured role and try what it may and may not do.

    Every probe runs in a transaction that is rolled back. The connections
    do not pass a search path, so the unqualified probes also prove the
    persisted search path (what psql and DataGrip get). Per domain schema:
    USAGE works, CREATE is denied. The last group proves ALTER DEFAULT
    PRIVILEGES: the owner creates a throwaway table in public and in every
    domain schema (as a new migration or a later move would), the app role
    writes and reads it, the read-only role reads it but cannot write; the
    tables are dropped afterwards.
    """
    roles = {role.kind: role for role in configured_roles()}
    probes = []
    for kind, table in (('app', APP_PROBES), ('readonly', READONLY_PROBES)):
        role = roles.get(kind)
        if role is None:
            continue
        checks = [('search_path persisted', ALLOWED, _search_path_probe()), *table, *_schema_probes(kind)]
        with connect_as(role.name, role.password, search_path=False) as conn:
            # The read-only role also defaults to read-only transactions; turn
            # that off here so the probes test the privileges themselves.
            conn.execute('SET default_transaction_read_only = off')
            for action, expected, statement in checks:
                probes.append(_run_probe(conn, Probe(role.name, action, expected), statement))
    if roles:
        probes += _verify_default_privileges(roles)
    return probes


def _verify_default_privileges(roles):
    probe_table = f'roles_probe_{secrets.token_hex(4)}'
    connection.ensure_connection()
    # The raw psycopg connection: Composed SQL, and outside any transaction
    # the CREATE commits at once, so the other roles can see the table.
    with connection.connection.cursor() as cur:
        schemas = _schemas(cur)
    targets = [(f'{schema}.{probe_table}', _q('{}.{}', _ident(schema), _ident(probe_table))) for schema in schemas]
    probes = []
    try:
        with connection.connection.cursor() as cur:
            for _, table in targets:
                cur.execute(
                    _q('CREATE TABLE {} (id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, note text)', table)
                )
        app, readonly = roles.get('app'), roles.get('readonly')
        if app is not None:
            with connect_as(app.name, app.password, search_path=False) as conn:
                for label, table in targets:
                    for action, statement in (
                        ('INSERT new table', _q("INSERT INTO {} (note) VALUES ('probe')", table)),
                        ('SELECT new table', _q('SELECT count(*) FROM {}', table)),
                    ):
                        probes.append(_run_probe(conn, Probe(app.name, f'{action} ({label})', ALLOWED), statement))
        if readonly is not None:
            with connect_as(readonly.name, readonly.password, search_path=False) as conn:
                conn.execute('SET default_transaction_read_only = off')
                for label, table in targets:
                    for action, expected, statement in (
                        ('SELECT new table', ALLOWED, _q('SELECT count(*) FROM {}', table)),
                        ('INSERT new table', DENIED, _q("INSERT INTO {} (note) VALUES ('probe')", table)),
                    ):
                        probes.append(
                            _run_probe(conn, Probe(readonly.name, f'{action} ({label})', expected), statement)
                        )
    finally:
        with connection.connection.cursor() as cur:
            for _, table in targets:
                cur.execute(_q('DROP TABLE IF EXISTS {}', table))
    return probes
