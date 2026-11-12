#!/bin/sh
set -e

# Schema changes and role setup run as the schema owner (POSTGRES_USER):
# settings.py connects `migrate` and `setup_db_roles` as the owner. Every
# other process (gunicorn below, the worker container) connects as the
# least-privilege POSTGRES_APP_USER once POSTGRES_APP_PASSWORD is set
# (docs/DATABASE_ROLES.md).
python manage.py migrate --noinput

# Idempotent: creates or updates the app / read-only roles, resets their
# passwords from the environment and re-grants privileges on every table,
# including the ones the migrations above just created. Without
# POSTGRES_APP_PASSWORD it only prints that the roles are not configured.
python manage.py setup_db_roles

# Demo data is opt-in (it creates accounts with known passwords) and the
# command itself refuses to run unless DJANGO_DEBUG=1.
if [ "${DJANGO_SEED_DATA:-0}" = "1" ]; then
  python manage.py seed_data --noinput
fi

if [ "${DJANGO_COLLECTSTATIC:-0}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
