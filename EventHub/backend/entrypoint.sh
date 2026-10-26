#!/bin/sh
set -e

python manage.py migrate --noinput

# Demo data is opt-in (it creates accounts with known passwords) and the
# command itself refuses to run unless DJANGO_DEBUG=1.
if [ "${DJANGO_SEED_DATA:-0}" = "1" ]; then
  python manage.py seed_data --noinput
fi

if [ "${DJANGO_COLLECTSTATIC:-0}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
