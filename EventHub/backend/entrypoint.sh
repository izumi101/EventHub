#!/bin/sh
set -e

python manage.py migrate --noinput

if [ "${DJANGO_SEED_DATA:-1}" = "1" ]; then
  python manage.py seed_data --noinput
fi

if [ "${DJANGO_COLLECTSTATIC:-0}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
