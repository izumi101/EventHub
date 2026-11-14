# Database schemas (one per domain)

The application tables live in one PostgreSQL schema per domain instead of
all in `public`. Table names are unchanged; only the schema differs, and the
search path keeps every unqualified name working.

## Agent Entry

- Purpose: where each table lives, how it gets there, how to add an app, how to roll back.
- Read when: adding a Django app, writing raw SQL or a migration with `RunSQL`, restoring a backup, connecting DataGrip/psql.
- Canonical: Yes. Code: `backend/common/db_schemas.py`; command `manage.py db_schemas`; tests `backend/common/test_db_schemas.py`.
- Related: `DATABASE_ROLES.md` (privileges per schema).

## Layout

| Schema | Django apps | Tables |
|--------|-------------|--------|
| `identity` | `auth`, `accounts`, `token_blacklist`, `mfa` | `auth_*`, `accounts_*`, `token_blacklist_*`, `mfa_*` |
| `events` | `events` | `events_*` |
| `bookings` | `bookings` | `bookings_*` |
| `payments` | `payments` | `payments_*` |
| `jobs` | `jobs` | `jobs_job` |
| `notifications` | `notifications` (once the app exists) | `notifications_*` |
| `platform` | `admin`, `contenttypes`, `sessions` + the `django_migrations` table | `django_*` |
| `public` | — | no application tables: only extensions (`vector`) |

A schema is created the first time one of its tables exists, so
`notifications` (and `mfa` tables in `identity`) appear only once those apps
are merged.

The mapping is in exactly one place, `APP_SCHEMAS` (app label -> schema) and
`TABLE_SCHEMAS` (`django_migrations`) in `backend/common/db_schemas.py`.

## Why

- DataGrip / psql show one folder per domain instead of 41+ tables in one list.
- Ownership boundaries are visible in the database itself, and grants,
  backups or future moves (a separate database per service) can be done per schema.

## How it works

```text
every connection        search_path = public, identity, events, bookings, payments, jobs, notifications, platform
  Django                settings.py DATABASES OPTIONS: -c search_path=...
  psql, DataGrip, ...   ALTER DATABASE <db> SET search_path ...            (written by migrate)
                        ALTER ROLE <owner> IN DATABASE <db> SET ...        (written by migrate)
                        ALTER ROLE <app|readonly> IN DATABASE <db> SET ... (written by setup_db_roles)
migrate                 Django creates new tables in the first schema of the path: public
  post_migrate          common.db_schemas.arrange(): create missing schemas, then
                        ALTER TABLE public.<t> SET SCHEMA <domain> for every table not yet in its schema
setup_db_roles          USAGE + table/sequence privileges + ALTER DEFAULT PRIVILEGES in every schema
```

- **Order of the search path.** `public` comes first: Django's `CREATE TABLE`
  and `CREATE EXTENSION` land there (and the tables are moved right after
  the migrations), and extension types/functions (`vector`) stay
  resolvable. There is no `"$user"` entry, so a schema named after a role
  can never shadow application tables. Every table name is unique across
  the schemas, so lookup order does not change which table a name means.
- **What moves with a table.** `ALTER TABLE ... SET SCHEMA` takes its
  indexes, constraints, owned sequences (serial and identity, including the
  auto-created M2M tables' ids) and its privileges along; tested in
  `test_sequences_and_indexes_moved_with_their_tables`.
- **When it runs.** The `post_migrate` handler (connected in
  `events/apps.py`) runs once per `migrate` after all migrations: on the
  first migrate of an existing database it moves all tables; on a fresh or
  test database it moves the tables the migrations just created; later it
  moves only tables added by new migrations. A second `migrate` finds
  nothing to do and writes nothing (`test_migrate_twice_is_a_no_op`). It
  also runs after `flush` (tests), where it is a no-op.
- **Who runs it.** `migrate` connects as the schema owner
  (`DB_OWNER_COMMANDS`), which may create schemas, move its tables and set
  the database default. The owner also persists the search path for itself.
  `setup_db_roles` (also the owner, right after `migrate` in
  `entrypoint.sh`) persists it for the app and read-only roles and grants
  them access to every schema.
- **No gap for the app role.** Moved tables keep their privileges; a newly
  created schema immediately gets `USAGE` for every role that has `USAGE`
  on `public` (not `PUBLIC`), so a manual `migrate` without
  `setup_db_roles` does not cut the running app off.
- **Locks.** The moves run in one transaction with `lock_timeout = 30s`;
  `ALTER TABLE ... SET SCHEMA` is a catalog change (no data is rewritten)
  but needs an `ACCESS EXCLUSIVE` lock on each table. If a long query holds
  a lock, `migrate` fails instead of queueing all traffic behind it; run it again.
- **Safety.** Schema names are constants validated at import
  (`^[a-z][a-z0-9_]*$`, not `pg_*`) and always sent as quoted identifiers via
  `psycopg.sql`; nothing user-supplied reaches the search path or DDL. A
  table found in two schemas stops the move with an error instead of guessing.

### `django_migrations` in `platform`

Django finds its migration table through `introspection.table_names()`,
which on PostgreSQL filters with `pg_table_is_visible()` and so honours the
search path. On a fresh database Django first creates it in `public`, then
the post_migrate step moves it. Proven by
`test_django_migrations_lives_in_platform_and_migrate_finds_it` (recorder
finds it, the migration plan is empty) and by the upgrade run below. The
one way to break this is a client that runs `migrate` with a search path
that does not include `platform`: Django would then create an empty
`public.django_migrations` and try to apply every migration again. That is
why the search path is also persisted on the database itself, which covers
every client that does not override it.

## Day-to-day

| Task | Command |
|------|---------|
| Show the layout (tables per schema, misplaced tables, unmapped apps) | `docker compose exec backend python manage.py db_schemas` |
| Same, exit 1 on any problem (CI / deploy check) | `docker compose exec backend python manage.py db_schemas --check` |
| Apply by hand (what every `migrate` does) | `docker compose exec backend python manage.py db_schemas apply` |
| Roll back to `public` | see *Rollback* |

Raw SQL keeps using unqualified names (`SELECT ... FROM events_event`). Do not
write `public.events_event`. Qualify with the domain schema only where it
helps a reader, e.g. in ad-hoc analysis (`events.events_event`).

### Adding an app

1. Add its label to `APP_SCHEMAS` in `backend/common/db_schemas.py` (an
   existing schema or a new one; a new schema also goes into
   `DOMAIN_SCHEMAS`, which is the search path order).
2. `manage.py test` fails with *"App(s) … create tables but have no
   schema"* until you do (`test_every_installed_app_with_tables_has_a_schema`);
   at runtime an unmapped app's tables stay in `public` and
   `db_schemas --check` reports it.
3. Nothing else: `migrate` creates the schema and moves the tables,
   `setup_db_roles` grants the roles access on the next start.

A function or trigger created by `RunSQL` with an unqualified name lands in
`public` (the first schema of the path); `CREATE OR REPLACE` keeps finding it
there. That is fine; there are none today.

## DataGrip

After the upgrade DataGrip still shows its cached `public`. In the database
explorer: right-click the data source → **Diagnostics → Forget Cached
Schemas**, then **Refresh** (Ctrl/Cmd+F5), and under **Properties → Schemas**
tick the new schemas (or *All schemas*). New consoles use the persisted
search path, so unqualified queries work as before.

## Upgrading an existing installation

Nothing manual: the backend container runs `migrate` and `setup_db_roles` on
start. The first start after this change prints

```text
  Database schemas: 41 table(s) moved, 6 schema(s) created, search_path persisted for database eventhub, role eventhub_user.
```

The worker of the previous release keeps its old connections (search path
`"$user", public`) until it is recreated a few seconds later (it starts
after the backend is healthy); jobs it picks up in between fail and are
retried. Stop the worker first (`docker compose stop worker`) for a
zero-error upgrade.

Backups: `pg_dump` / `pg_restore` carry the schemas. A plain restore into a
new database does not carry `ALTER DATABASE ... SET`; the next `migrate`
(container start) writes it again.

## Rollback

```bash
docker compose stop worker
docker compose exec backend python manage.py db_schemas rollback
# then deploy the previous release (its entrypoint runs its own migrate)
```

`rollback` moves every table of the domain schemas back into `public`,
drops the then empty schemas (`RESTRICT`: it refuses if something else is in
them) and resets the persisted search paths of the database and of every
role in it. The previous release, which knows only `public`, then works
unchanged. Do not restart this release after a rollback: its next `migrate`
moves the tables into the domain schemas again. Tested in
`test_rollback_moves_everything_back_and_apply_restores_it` and once on the
restored 2026-11-12 backup with the previous release (`origin/main` at
`119f1d3`): health, events list, `run_sql_checks` and `verify_db_roles` all passed.
