#!/usr/bin/env bash
# Database checks against a running stack (docs/TEST_REPORT.md, "Database"):
#
#   1. every table lives in its domain schema       manage.py db_schemas --check
#   2. least-privilege roles behave as designed     manage.py verify_db_roles
#   3. the running backend really uses the app role, and that role cannot run DDL
#   4. data invariants hold                         manage.py run_sql_checks
#
#   scripts/qa-db-checks.sh                       # the default compose project
#   COMPOSE="docker compose -p ehqa --env-file /path/.env -f docker-compose.yml -f docker-compose.qa.yml" \
#     scripts/qa-db-checks.sh                     # the isolated QA stack
#
# Exits non-zero on the first failing step. CRITICAL run_sql_checks findings
# fail the run, WARNING ones only with STRICT_SQL_CHECKS=1 (demo data has known
# WARNING findings, see docs/HANDOFF.md).
set -euo pipefail
cd "$(dirname "$0")/.."
read -r -a compose <<< "${COMPOSE:-docker compose}"
manage() { "${compose[@]}" exec -T backend python manage.py "$@"; }

echo "== 1. db_schemas --check"
manage db_schemas --check

echo "== 2. verify_db_roles"
manage verify_db_roles | tail -n 1

echo "== 3. the backend's own connection: app role, no DDL"
manage shell -c "
import os, sys
from django.db import DatabaseError, connection, transaction
with connection.cursor() as cursor:
    cursor.execute('SELECT current_user')
    user = cursor.fetchone()[0]
    try:
        with transaction.atomic():
            cursor.execute('CREATE TABLE events.qa_ddl_probe (id integer)')
        denied = False
    except DatabaseError as exc:
        denied = 'permission denied' in str(exc)
expected = os.environ.get('POSTGRES_APP_USER', 'eventhub_app')
print(f'connected as {user} (expected {expected}); CREATE TABLE denied: {denied}')
sys.exit(0 if user == expected and denied else 1)
"

echo "== 4. run_sql_checks"
if [ "${STRICT_SQL_CHECKS:-0}" = 1 ]; then
  manage run_sql_checks --fail-on warning
else
  manage run_sql_checks
fi
