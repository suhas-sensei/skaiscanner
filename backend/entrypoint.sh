#!/usr/bin/env sh
set -eu

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --no-input
fi

if [ "${COLLECT_STATIC:-0}" = "1" ]; then
  python manage.py collectstatic --no-input
fi

exec "$@"
