#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

.venv/bin/python -u manage.py scrape_yatra \
  --random-routes \
  --airport-pool major \
  --route-count "${ROUTE_COUNT:-5}" \
  --start-date "${START_DATE:-2026-05-22}" \
  --end-date "${END_DATE:-2026-06-22}" \
  --trip-types one_way round_trip \
  --return-after-days "${RETURN_AFTER_DAYS:-7}" \
  --delay "${SCRAPE_DELAY:-0}" \
  --page-timeout "${PAGE_TIMEOUT:-22}" \
  --skip-existing
