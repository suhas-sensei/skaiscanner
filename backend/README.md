# Yatra Django Flight Price Scraper

Fresh Django/PostgreSQL project for scraping Yatra flight prices with Python Selenium.

## Setup

```bash
cd yatra_django_scraper
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d postgres redis
python3 manage.py migrate
```

## Email OTP Backend

The app uses Django's SMTP email backend for OTP sign-in emails.

For Gmail, create an app password and set these values in `.env`:

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-google-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com
```

For SendGrid, use:

```bash
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=your-sendgrid-api-key
DEFAULT_FROM_EMAIL=verified-sender@example.com
```

Send a test email:

```bash
python3 manage.py send_test_email you@example.com
```

If port `6379` is already in use, run Redis on another host port:

```bash
REDIS_PORT=6380 docker compose up -d redis
CACHE_URL=redis://127.0.0.1:6380/1 CELERY_BROKER_URL=redis://127.0.0.1:6380/0 CELERY_RESULT_BACKEND=redis://127.0.0.1:6380/0 python3 manage.py check
```

## Search Backend

Postgres remains the default search backend.

Run Meilisearch:

```bash
docker compose up -d meilisearch
python3 manage.py index_flight_search --backend meilisearch
SEARCH_BACKEND=meilisearch python3 manage.py runserver
```

Run OpenSearch instead:

```bash
docker compose --profile opensearch up -d opensearch
python3 manage.py index_flight_search --backend opensearch
SEARCH_BACKEND=opensearch python3 manage.py runserver
```

Selenium 4 uses Selenium Manager to locate/download the matching Chrome driver. Install Chrome or Chromium on the machine before running the scraper.

## Scrape One Route

```bash
python3 manage.py scrape_yatra --origin DEL --destination BOM --days 122
```

Resume without duplicating completed route/date searches:

```bash
python3 manage.py scrape_yatra --origin DEL --destination BOM --days 122 --skip-existing
```

## Scrape Route CSV

Edit `data/routes.csv`, then run:

```bash
python3 manage.py scrape_yatra --routes data/routes.csv --days 122
```

Useful test run:

```bash
python3 manage.py scrape_yatra --origin DEL --destination BOM --limit-days 1 --headful
```

## Background Jobs

Redis is used for Django cache storage and as the Celery broker/result backend.

This repo uses `REDIS_PORT=6380` in `.env` so it does not collide with other local Redis containers on `6379`.

Run a worker:

```bash
.venv/bin/celery -A yatra_scraper worker -l info --pool=solo
```

In another terminal, send a real task through Redis to the Celery worker:

```bash
.venv/bin/python manage.py shell -c "from flights.tasks import warm_route_search_cache; r=warm_route_search_cache.delay('DEL', 'BOM', '2026-05-30'); print(r.id); print(r.get(timeout=20))"
```

Confirm that the task wrote to Redis-backed Django cache:

```bash
.venv/bin/python manage.py shell -c "from django.core.cache import cache; print(cache.get('route-summary:DEL:BOM:2026-05-30'))"
```

## Database Tables

`flights_flightsearch` stores one row per Yatra search request.

`flights_flightoffer` stores each flight/price result found on that rendered page, including normalized fields and raw page text for debugging selector changes.

## Notes

Yatra can change markup, rate-limit, or block automation. Keep the scrape rate conservative with `--delay`, and confirm your usage is allowed by Yatra's current terms before running large jobs.
