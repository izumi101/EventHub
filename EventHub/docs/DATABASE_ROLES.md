# Database roles (least privilege)

The backend no longer has to talk to PostgreSQL as the user that owns the
schema. Three roles, each with only what its job needs:

| Role | Env (user / password) | Used by | May | May not |
|------|-----------------------|---------|-----|---------|
| `eventhub_user` (owner) | `POSTGRES_USER` / `POSTGRES_PASSWORD` | `migrate`, `setup_db_roles`, `verify_db_roles`, the test runner, anything started with `DJANGO_DB_AS_OWNER=1` | everything: owns every table, runs DDL, creates roles | — |
| `eventhub_app` | `POSTGRES_APP_USER` / `POSTGRES_APP_PASSWORD` | gunicorn (backend), `run_worker` (worker), every other `manage.py` command (`shell`, `seed_data`, `run_maintenance`, ...) | `CONNECT`; `USAGE` on `public` and every domain schema (`DATABASE_SCHEMAS.md`); `SELECT, INSERT, UPDATE, DELETE` on every table; `USAGE, SELECT, UPDATE` on sequences; `EXECUTE` on functions | `CREATE` / `ALTER` / `DROP` anything, `TRUNCATE`, `REFERENCES`, `TRIGGER`, temporary tables, `CREATE SCHEMA`, `CREATE` in any schema, writing `django_migrations`; not superuser, no `CREATEDB` / `CREATEROLE` / `REPLICATION` / `BYPASSRLS`, inherits no role |
| `eventhub_readonly` | `POSTGRES_READONLY_USER` / `POSTGRES_READONLY_PASSWORD` | `run_sql_checks`, the SQL in `backend/sql/reports` and `backend/sql/explain/hot_queries.sql`, analysts | `CONNECT`; `SELECT` on business tables | any write; reading credentials: `auth_user.password`, `events_webhook.secret`, `django_session`, `token_blacklist_*` (refresh tokens), `accounts_passwordresetcode`, `accounts_emailverificationcode`. Sessions default to read-only transactions, `statement_timeout = 60s`, at most 10 connections |

Code: `backend/common/db_roles.py`; commands `setup_db_roles` and
`verify_db_roles` (in `backend/events/management/commands/`); tests
`backend/events/test_db_roles.py`.

## Why

- A SQL injection or an RCE in the web process can no longer drop or alter
  tables, read password hashes through the reporting role, or rewrite the
  migration history: the role it runs as cannot.
- Reports and data checks cannot change data even when a query is wrong.
- The owner keeps all rights, so migrations work unchanged.

### Why the owner stays `POSTGRES_USER`

The postgres image creates `POSTGRES_USER` as a superuser, and on every
existing volume it owns all 41 tables. Moving ownership to a new,
non-superuser owner would need `REASSIGN OWNED` on a live database plus a
second set of credentials for the image's bootstrap user; keeping it is
zero-risk for existing installations, and it still never reaches the request
path once `POSTGRES_APP_PASSWORD` is set. The cost: the backend container
still receives the owner password because its entrypoint runs `migrate`
(see *Follow-ups*).

## How it works

```text
container start (entrypoint.sh)
  python manage.py migrate          -> connects as POSTGRES_USER (owner); moves new
                                       tables into their domain schema and
                                       persists the database search_path
                                       (DATABASE_SCHEMAS.md)
  python manage.py setup_db_roles   -> connects as owner; creates / updates
                                       eventhub_app + eventhub_readonly,
                                       resets their passwords from env,
                                       re-grants on all tables in public and
                                       every domain schema, sets ALTER DEFAULT
                                       PRIVILEGES per schema, persists their
                                       search_path (ALTER ROLE ... IN DATABASE)
  [seed_data if DJANGO_SEED_DATA=1] -> eventhub_app
  exec gunicorn                     -> eventhub_app
worker container: run_worker        -> eventhub_app (starts after the backend is healthy)
```

`settings.py` decides per process (the `# ---- Database roles` block):

- `DATABASES['default']` uses `POSTGRES_APP_USER` / `POSTGRES_APP_PASSWORD`
  when the password is set;
- it uses the owner for `manage.py test` (the test runner needs `CREATEDB`),
  for `manage.py migrate | setup_db_roles | verify_db_roles`
  (`DB_OWNER_COMMANDS`), and for any process with `DJANGO_DB_AS_OWNER=1`;
- without `POSTGRES_APP_PASSWORD` (an `.env` from before the roles existed)
  it connects as the owner exactly as before and prints
  `WARNING: POSTGRES_APP_PASSWORD is not set ...` on start;
  `setup_db_roles` then only prints `skipped`;
- with `DJANGO_DEBUG=0` it refuses to start when `POSTGRES_APP_USER` is the
  owner or the read-only user.

One process, one role: migrations do not run on a second connection alias,
because the data migrations (e.g. `payments/0005`) use the default manager
and must see the schema changes of their own transaction.

`setup_db_roles` is idempotent and safe on a fresh and on an existing
volume (`docker-entrypoint-initdb.d` runs only on an empty data directory, so
it is not used). Per run, in one transaction:

1. refuses when a configured role is the owner, starts with `pg_`, or is an
   existing superuser (it never demotes one);
2. `CREATE ROLE` or `ALTER ROLE ... LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
   NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD '<SCRAM verifier>'` and revokes
   every role membership;
3. `REVOKE CREATE ON SCHEMA <s> FROM PUBLIC` for `public` and every domain
   schema that exists, `REVOKE CONNECT, TEMPORARY ON DATABASE ... FROM
   PUBLIC`, then `GRANT CONNECT` to the two roles only, `USAGE` (never
   `CREATE`) on each of those schemas, and `ALTER ROLE <role> IN DATABASE
   <db> SET search_path` to the application search path, so psql and
   DataGrip sessions of the two roles resolve unqualified names too;
4. grants on all existing tables / sequences / functions in each schema,
   revokes what is not listed above (so manual drift is repaired on the next
   start);
5. `ALTER DEFAULT PRIVILEGES FOR ROLE <owner> IN SCHEMA <s> GRANT ... TO
   eventhub_app / eventhub_readonly` per schema, so tables created by later
   migrations (in `public`, then moved with their privileges) or directly in
   a domain schema are usable immediately, even before the next
   `setup_db_roles`;
6. hides the credential tables and columns from the read-only role
   (column-level grant on `auth_user` and `events_webhook`);
7. verifies the role attributes afterwards and fails the start if a role
   still has elevated rights.

Every identifier goes through `psycopg.sql.Identifier`, every value through
`sql.Literal`. The password itself is never sent: libpq computes a
SCRAM-SHA-256 verifier on the client (`PGconn.encrypt_password`), so a
statement log (`log_statement=ddl`) cannot leak it.

## Setting it up

`.env` (values in `.env.example` are development values):

```dotenv
POSTGRES_APP_USER=eventhub_app
POSTGRES_APP_PASSWORD=<long random>
POSTGRES_READONLY_USER=eventhub_readonly
POSTGRES_READONLY_PASSWORD=<long random>
```

Then rebuild and restart the backend and the worker
(`docker compose up -d --build backend worker`). The first start creates the
roles; the backend log shows `app role "eventhub_app": created, privileges
granted.` The variables are optional in `docker-compose.yml` on purpose: an
old `.env` keeps starting (as the owner, with the warning).

## Proving it

```bash
# all probes in transactions that are rolled back; exits 1 on any surprise
docker compose exec backend python manage.py verify_db_roles
```

prints PASS/FAIL per probe (74 on the demo database). Both roles connect
without a search path of their own, so the probes first prove the persisted
search path (`search_path persisted`) and that unqualified names resolve
across the schemas. Then: the app role can SELECT/INSERT/UPDATE/DELETE but
gets `permission denied` for CREATE TABLE, ALTER TABLE (`must be owner`),
DROP TABLE, TRUNCATE, CREATE SCHEMA, temporary tables and writes to
`django_migrations`; the read-only role can SELECT but cannot INSERT, UPDATE,
DELETE, CREATE or read `auth_user.password` / sessions / refresh tokens; per
domain schema both roles can read one of its tables but get `permission
denied for schema <s>` for `CREATE TABLE <s>.…`; and a table the owner
creates afterwards in `public` and in every domain schema (as a new
migration would) is immediately writable by the app role and readable, not
writable, by the read-only role.

Interactive, with `psql` inside the db container (use `-h db`: the image
trusts connections from `localhost` inside the container without a password):

```bash
cd EventHub   # load the two passwords from .env into this shell (do not `source` .env: it has unquoted values)
export POSTGRES_READONLY_PASSWORD="$(grep '^POSTGRES_READONLY_PASSWORD=' .env | cut -d= -f2-)"
export POSTGRES_APP_PASSWORD="$(grep '^POSTGRES_APP_PASSWORD=' .env | cut -d= -f2-)"

docker compose exec -e PGPASSWORD="$POSTGRES_READONLY_PASSWORD" db \
  psql -h db -U eventhub_readonly -d eventhub \
  -c "select count(*) from events_event" \
  -c "insert into events_category(name, description, icon, created_at) values ('x','','',now())" \
  -c "select password from auth_user limit 1"
# -> a count, then: cannot execute INSERT in a read-only transaction,
#    then: permission denied for table auth_user

docker compose exec -e PGPASSWORD="$POSTGRES_APP_PASSWORD" db \
  psql -h db -U eventhub_app -d eventhub -c "create table hack (id int)"
# -> ERROR: permission denied for schema public
```

From the host: `psql -h 127.0.0.1 -p ${POSTGRES_HOST_PORT:-5433} -U
eventhub_readonly eventhub` (the port is published on localhost only).

## Reports and checks as the read-only role

```bash
docker compose exec backend python manage.py run_sql_checks          # uses eventhub_readonly
docker compose exec -T -e PGPASSWORD="$POSTGRES_READONLY_PASSWORD" db \
  psql -h db -U eventhub_readonly -d eventhub -f - < backend/sql/reports/03_occupancy.sql
```

`run_sql_checks` connects as the read-only role whenever
`POSTGRES_READONLY_PASSWORD` is set and runs each check in a `READ ONLY`
transaction. Without it, it uses the app connection, still read-only.

## Rotating a password

1. Put the new value in `.env` (`POSTGRES_APP_PASSWORD` or
   `POSTGRES_READONLY_PASSWORD`).
2. `docker compose up -d backend worker` (recreates both with the new
   environment). The backend entrypoint runs `setup_db_roles`, which runs
   `ALTER ROLE ... PASSWORD` before gunicorn starts; the worker starts after
   the backend is healthy, so both connect with the new password. Existing
   sessions with the old password are not cut; the old password stops
   working for new connections at once.

Without a restart: `docker compose exec -e POSTGRES_APP_PASSWORD=<new> backend
python manage.py setup_db_roles`, then restart backend and worker.

The owner password (`POSTGRES_PASSWORD`) is only used by the image on the
first start of an empty volume; to change it later run `ALTER ROLE
eventhub_user PASSWORD ...` as the owner and update `.env`.

## Day-to-day commands

| Task | Command | Role |
|------|---------|------|
| Migrations | `docker compose exec backend python manage.py migrate` | owner (automatic) |
| Re-grant after a manual migrate | `docker compose exec backend python manage.py setup_db_roles` | owner (automatic) |
| Django shell | `docker compose exec backend python manage.py shell` | app: no DDL |
| One-off command that needs DDL | `docker compose exec -e DJANGO_DB_AS_OWNER=1 backend python manage.py <cmd>` | owner |
| Tests | `docker compose exec backend python manage.py test` | owner (needs CREATEDB) |

## Follow-ups (not done)

- Run `migrate` / `setup_db_roles` in a one-shot `migrate` service so the
  long-running backend container no longer receives `POSTGRES_PASSWORD`
  (and the worker never needs it).
- Make `POSTGRES_APP_PASSWORD` mandatory when `DJANGO_DEBUG=0` once every
  deployment has it; today it only warns, so an old production `.env` keeps
  working.
- Initialise new volumes with `POSTGRES_INITDB_ARGS=--auth-local=scram-sha-256
  --auth-host=scram-sha-256` so connections from inside the db container
  need a password too (changes `docker compose exec db psql` habits; existing
  volumes need `pg_hba.conf` edited by hand).
- A dedicated non-superuser owner role (`REASSIGN OWNED BY eventhub_user TO
  eventhub_owner`) so that even migrations run without superuser rights.
