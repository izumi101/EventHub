"""One PostgreSQL schema per domain (docs/DATABASE_SCHEMAS.md).

`APP_SCHEMAS` is the single source of truth: Django app label -> schema.
Table names do not change, only the schema they live in, and every
connection uses `SEARCH_PATH`, so unqualified names (the ORM, raw SQL,
`sql/checks`, reports, psql, DataGrip) keep resolving.

How tables get there:

* Django creates a new table in the first schema of the search path,
  `public`. `arrange()` runs after every `migrate` (a `post_migrate`
  handler, connected in events/apps.py) and moves every application table
  that is not in its schema yet: existing databases on their first migrate,
  fresh and test databases, and tables added by later migrations.
  `ALTER TABLE ... SET SCHEMA` takes the table's indexes, constraints,
  owned sequences (serial and identity) and privileges with it.
* It also persists the search path for clients that do not go through
  settings.py (`ALTER DATABASE` and `ALTER ROLE ... IN DATABASE` for the
  owner); `setup_db_roles` does the same for the app and read-only roles.
* `restore_public()` is the rollback: everything back into `public`, the
  domain schemas dropped and the persisted search paths reset.

Schema names are module constants checked against a strict pattern and
always sent as quoted identifiers (`psycopg.sql`); nothing user-supplied
reaches the search path or a DDL statement.
"""

import re
from dataclasses import dataclass, field

from django.apps import apps as global_apps
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from psycopg import sql

PUBLIC = 'public'
IDENTITY = 'identity'
EVENTS = 'events'
BOOKINGS = 'bookings'
PAYMENTS = 'payments'
JOBS = 'jobs'
NOTIFICATIONS = 'notifications'
PLATFORM = 'platform'

# The domain schemas, in search-path order.
DOMAIN_SCHEMAS = (IDENTITY, EVENTS, BOOKINGS, PAYMENTS, JOBS, NOTIFICATIONS, PLATFORM)

# Django app label -> schema. Every app with models must be listed here
# (common/test_db_schemas.py fails otherwise); an app that is listed but not
# installed (yet) costs nothing.
APP_SCHEMAS = {
    # Accounts, credentials, one-time codes, refresh tokens, second factors.
    'auth': IDENTITY,
    'accounts': IDENTITY,
    'token_blacklist': IDENTITY,
    'mfa': IDENTITY,
    'events': EVENTS,
    'bookings': BOOKINGS,
    'payments': PAYMENTS,
    'jobs': JOBS,
    'notifications': NOTIFICATIONS,
    # Django internals.
    'admin': PLATFORM,
    'contenttypes': PLATFORM,
    'sessions': PLATFORM,
}
# Tables that belong to no model. django_migrations is found through
# introspection that honours the search path (pg_table_is_visible), so it can
# live outside public; common/test_db_schemas.py proves `migrate` still sees it.
TABLE_SCHEMAS = {
    'django_migrations': PLATFORM,
}

# `public` first: Django's CREATE TABLE and CREATE EXTENSION land there (and
# are moved by arrange()), and the extensions (vector) stay resolvable. No
# "$user": a role-named schema must never shadow the application's tables.
SEARCH_PATH = (PUBLIC, *DOMAIN_SCHEMAS)

# Waiting longer than this for a table lock fails the migrate instead of
# blocking every query queued behind ALTER TABLE ... SET SCHEMA.
LOCK_TIMEOUT = '30s'

_SCHEMA_NAME = re.compile(r'^[a-z][a-z0-9_]{0,62}$')
for _name in SEARCH_PATH:
    if not _SCHEMA_NAME.match(_name) or _name.startswith('pg_'):
        raise ValueError(f'Invalid schema name in common/db_schemas.py: {_name!r}')
_unknown = (set(APP_SCHEMAS.values()) | set(TABLE_SCHEMAS.values())) - set(DOMAIN_SCHEMAS)
if _unknown:
    raise ValueError(f'Mapped to schemas missing from DOMAIN_SCHEMAS: {sorted(_unknown)}')

# Only real tables move (partitioned ones too); views and the like are none of ours.
_TABLE_KINDS = ['r', 'p']


class SchemaLayoutError(Exception):
    pass


def _cursor(connection):
    """A raw psycopg cursor on Django's connection (runs psycopg.sql Composed statements)."""
    connection.ensure_connection()
    return connection.connection.cursor()


def search_path_value():
    """The search path as PostgreSQL stores it: `public, identity, ...`."""
    return ', '.join(SEARCH_PATH)


def connection_options():
    """libpq `options` that set the search path for a new connection."""
    return '-c search_path=' + ','.join(SEARCH_PATH)


def _search_path_sql():
    return sql.SQL(', ').join(sql.Identifier(name) for name in SEARCH_PATH)


def _normalise(value):
    return tuple(part.strip().strip('"') for part in (value or '').split(','))


def schema_for_app(app_label):
    return APP_SCHEMAS.get(app_label)


def _models(app_registry):
    for model in app_registry.get_models(include_auto_created=True):
        opts = model._meta
        if opts.managed and not opts.proxy:
            yield opts


def unmapped_apps(app_registry=global_apps):
    """Labels of installed apps that have tables but no schema in APP_SCHEMAS."""
    return sorted({opts.app_label for opts in _models(app_registry) if opts.app_label not in APP_SCHEMAS})


def expected_tables(app_registry=global_apps):
    """{table: schema} for every table the installed apps own, plus TABLE_SCHEMAS.

    Tables of unmapped apps are left out (they stay where they are); the test
    suite fails on them, so they never reach production unnoticed.
    """
    tables = {}
    for opts in _models(app_registry):
        schema = APP_SCHEMAS.get(opts.app_label)
        if schema is not None:
            tables[opts.db_table] = schema
    tables.update(TABLE_SCHEMAS)
    return tables


def table_locations(cursor, tables=None):
    """{table: [schemas]} for tables in public or a domain schema."""
    query = (
        'SELECT c.relname, n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace '
        'WHERE c.relkind = ANY(%s) AND n.nspname = ANY(%s)'
    )
    params = [_TABLE_KINDS, list(SEARCH_PATH)]
    if tables is not None:
        query += ' AND c.relname = ANY(%s)'
        params.append(list(tables))
    cursor.execute(query + ' ORDER BY n.nspname, c.relname', params)
    locations = {}
    for table, schema in cursor.fetchall():
        locations.setdefault(table, []).append(schema)
    return locations


def existing_schemas(cursor, names=SEARCH_PATH):
    cursor.execute('SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)', [list(names)])
    return {row[0] for row in cursor.fetchall()}


@dataclass
class ArrangeResult:
    created_schemas: list = field(default_factory=list)
    moved: list = field(default_factory=list)  # (table, from_schema, to_schema)
    settings_changed: list = field(default_factory=list)

    @property
    def changed(self):
        return bool(self.created_schemas or self.moved or self.settings_changed)


def plan_moves(locations, expected):
    """[(table, current, target)] for every table not in its schema."""
    moves = []
    for table, target in sorted(expected.items()):
        found = locations.get(table, [])
        if len(found) > 1:
            raise SchemaLayoutError(
                f'Table "{table}" exists in several schemas ({", ".join(found)}); '
                'resolve it by hand before running migrate again (docs/DATABASE_SCHEMAS.md).'
            )
        if found and found[0] != target:
            moves.append((table, found[0], target))
    return moves


def _db_role_setting(cursor, role_sql, dbname):
    """The stored search_path for (role, current database); role_sql picks the role oid."""
    cursor.execute(
        sql.SQL(
            'SELECT cfg FROM pg_db_role_setting s, unnest(s.setconfig) cfg '
            'WHERE s.setdatabase = (SELECT oid FROM pg_database WHERE datname = %s) AND s.setrole = {} '
            "AND cfg LIKE 'search_path=%%'"
        ).format(role_sql),
        [dbname],
    )
    row = cursor.fetchone()
    return row[0].split('=', 1)[1] if row else None


def persist_search_path(cursor, dbname, role=None):
    """`ALTER DATABASE / ALTER ROLE ... IN DATABASE ... SET search_path`, when it differs.

    role=None sets the database default (every role, every client). Returns
    True when something was written.
    """
    if role is None:
        current = _db_role_setting(cursor, sql.SQL('0'), dbname)
        statement = sql.SQL('ALTER DATABASE {} SET search_path TO {}').format(
            sql.Identifier(dbname), _search_path_sql()
        )
    else:
        current = _db_role_setting(
            cursor, sql.SQL('(SELECT oid FROM pg_roles WHERE rolname = {})').format(sql.Literal(role)), dbname
        )
        statement = sql.SQL('ALTER ROLE {} IN DATABASE {} SET search_path TO {}').format(
            sql.Identifier(role), sql.Identifier(dbname), _search_path_sql()
        )
    if _normalise(current) == SEARCH_PATH:
        return False
    cursor.execute(statement)
    return True


def _mirror_schema_usage(cursor, schemas):
    """Give every role with USAGE on public USAGE on the domain schemas too.

    Moved tables keep their own privileges; only the schema-level USAGE is
    new. Without it the app role would lose sight of a moved table between
    `migrate` and `setup_db_roles` (or after a manual migrate). PUBLIC, the
    schema owner and pg_* roles are not copied.
    """
    cursor.execute(
        'SELECT DISTINCT r.rolname FROM pg_namespace n, aclexplode(n.nspacl) a JOIN pg_roles r ON r.oid = a.grantee '
        "WHERE n.nspname = %s AND a.privilege_type = 'USAGE' AND a.grantee <> n.nspowner "
        "AND r.rolname NOT LIKE 'pg\\_%%' ORDER BY 1",
        [PUBLIC],
    )
    grantees = [row[0] for row in cursor.fetchall()]
    for schema in sorted(schemas):
        for role in grantees:
            if not _has_schema_usage(cursor, role, schema):
                cursor.execute(
                    sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(schema), sql.Identifier(role))
                )


def _has_schema_usage(cursor, role, schema):
    cursor.execute("SELECT has_schema_privilege(%s, %s, 'USAGE')", [role, schema])
    return cursor.fetchone()[0]


def arrange(using=DEFAULT_DB_ALIAS, app_registry=global_apps):
    """Create the domain schemas and move every application table into its schema.

    Idempotent: a second run finds nothing to do and writes nothing. Must run
    as the owner of the tables (migrate does).
    """
    connection = connections[using]
    result = ArrangeResult()
    if connection.vendor != 'postgresql':
        return result
    expected = expected_tables(app_registry)
    dbname = connection.settings_dict['NAME']
    with transaction.atomic(using=using), _cursor(connection) as cursor:
        moves = plan_moves(table_locations(cursor, expected), expected)
        targets = {target for _, _, target in moves}
        present = existing_schemas(cursor, DOMAIN_SCHEMAS)
        if moves:
            cursor.execute(sql.SQL('SET LOCAL lock_timeout = {}').format(sql.Literal(LOCK_TIMEOUT)))
        for schema in sorted(targets - present):
            cursor.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(schema)))
            # Nothing for PUBLIC: access comes from setup_db_roles.
            cursor.execute(sql.SQL('REVOKE ALL ON SCHEMA {} FROM PUBLIC').format(sql.Identifier(schema)))
            result.created_schemas.append(schema)
        if moves or result.created_schemas:
            _mirror_schema_usage(cursor, present | targets)
        for table, current, target in moves:
            cursor.execute(
                sql.SQL('ALTER TABLE {}.{} SET SCHEMA {}').format(
                    sql.Identifier(current), sql.Identifier(table), sql.Identifier(target)
                )
            )
            result.moved.append((table, current, target))
        if persist_search_path(cursor, dbname):
            result.settings_changed.append(f'database {dbname}')
        cursor.execute('SELECT current_user')
        owner = cursor.fetchone()[0]
        if persist_search_path(cursor, dbname, role=owner):
            result.settings_changed.append(f'role {owner}')
    return result


def arrange_after_migrate(sender, using=DEFAULT_DB_ALIAS, verbosity=1, stdout=None, **kwargs):
    """post_migrate receiver (events/apps.py); also runs after `flush`."""
    result = arrange(using=using)
    if result.changed and verbosity >= 1 and stdout is not None:
        stdout.write(
            f'  Database schemas: {len(result.moved)} table(s) moved, '
            f'{len(result.created_schemas)} schema(s) created, '
            f'search_path persisted for {", ".join(result.settings_changed) or "nothing new"}.\n'
        )


def schema_summary(using=DEFAULT_DB_ALIAS):
    """[(schema, table count)] for public and the domain schemas that exist."""
    with _cursor(connections[using]) as cursor:
        cursor.execute(
            'SELECT n.nspname, count(c.oid) FROM pg_namespace n '
            'LEFT JOIN pg_class c ON c.relnamespace = n.oid AND c.relkind = ANY(%s) '
            'WHERE n.nspname = ANY(%s) GROUP BY n.nspname',
            [_TABLE_KINDS, list(SEARCH_PATH)],
        )
        counts = dict(cursor.fetchall())
    return [(schema, counts[schema]) for schema in SEARCH_PATH if schema in counts]


def misplaced_tables(using=DEFAULT_DB_ALIAS, app_registry=global_apps):
    """[(table, current, target)] that `arrange()` would move."""
    expected = expected_tables(app_registry)
    with _cursor(connections[using]) as cursor:
        return plan_moves(table_locations(cursor, expected), expected)


@dataclass
class RollbackResult:
    moved: list = field(default_factory=list)  # (table, from_schema)
    dropped_schemas: list = field(default_factory=list)
    settings_reset: list = field(default_factory=list)


def restore_public(using=DEFAULT_DB_ALIAS):
    """Rollback: move every table of the domain schemas back into public.

    Then drops the (now empty) domain schemas and resets the persisted
    search paths of the database and of every role in it, so the previous
    release, which knows only `public`, finds every table. The search path
    of the running process still lists the domain schemas, which no longer
    exist; PostgreSQL ignores missing schemas in a search path.

    Run it, then deploy the previous release: while this release is
    deployed, its next `migrate` moves the tables back into the domain
    schemas.
    """
    connection = connections[using]
    dbname = connection.settings_dict['NAME']
    result = RollbackResult()
    with transaction.atomic(using=using), _cursor(connection) as cursor:
        cursor.execute(sql.SQL('SET LOCAL lock_timeout = {}').format(sql.Literal(LOCK_TIMEOUT)))
        locations = table_locations(cursor)
        clashes = sorted(table for table, schemas in locations.items() if len(schemas) > 1)
        if clashes:
            raise SchemaLayoutError(f'These tables exist in public and a domain schema: {", ".join(clashes)}')
        for table, (schema,) in sorted(locations.items()):
            if schema == PUBLIC:
                continue
            cursor.execute(
                sql.SQL('ALTER TABLE {}.{} SET SCHEMA {}').format(
                    sql.Identifier(schema), sql.Identifier(table), sql.Identifier(PUBLIC)
                )
            )
            result.moved.append((table, schema))
        for schema in DOMAIN_SCHEMAS:
            if schema not in existing_schemas(cursor, [schema]):
                continue
            # RESTRICT: refuses if anything but the moved tables was in it.
            # Default privileges (setup_db_roles) go with the schema.
            cursor.execute(sql.SQL('DROP SCHEMA {} RESTRICT').format(sql.Identifier(schema)))
            result.dropped_schemas.append(schema)
        cursor.execute(
            'SELECT s.setrole, r.rolname FROM pg_db_role_setting s LEFT JOIN pg_roles r ON r.oid = s.setrole, '
            'unnest(s.setconfig) cfg '
            "WHERE s.setdatabase = (SELECT oid FROM pg_database WHERE datname = %s) AND cfg LIKE 'search_path=%%'",
            [dbname],
        )
        for role_oid, role in cursor.fetchall():
            if role_oid == 0:
                cursor.execute(sql.SQL('ALTER DATABASE {} RESET search_path').format(sql.Identifier(dbname)))
                result.settings_reset.append(f'database {dbname}')
            else:
                cursor.execute(
                    sql.SQL('ALTER ROLE {} IN DATABASE {} RESET search_path').format(
                        sql.Identifier(role), sql.Identifier(dbname)
                    )
                )
                result.settings_reset.append(f'role {role}')
    return result
