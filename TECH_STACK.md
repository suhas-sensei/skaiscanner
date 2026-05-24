# Skaiscanner Tech Stack

| Area | Use |
| --- | --- |
| Frontend | **React + TypeScript + Vite or Next.js** |
| Backend API | **Django + GraphQL** |
| Database | **Postgres**, keep it |
| Background jobs | **Celery + Redis** |
| Cache | **Redis** |
| Search/filtering | Start with **Postgres indexes**, add **Meilisearch/OpenSearch** only if needed |
| Auth | Django auth with basic email OTP sign-in and session auth |
| Admin/data ops | Django Admin |
| API docs | **GraphQL schema / GraphiQL** |
| Deployment | **Docker Compose** first; later AWS ECS/Fargate or Render/Fly/Railway |
| Observability | Sentry + structured logs; Prometheus/Grafana later |
| CI/CD | GitHub Actions |

## What I would remove from the image for your case

- **Java microservices**: not needed. Django can serve this well.
- **gRPC / Protobuf**: unnecessary unless you split into many services.
- **Kubernetes / Istio / Argo CD**: too much for an MVP.
- **Cassandra / Memcached**: Postgres + Redis is enough.
- **Databricks / Spark / lakehouse layers**: only useful for large-scale analytics pipelines.
- **Redshift / Aurora / Lambda / ELB**: optional later, not needed locally or early.
- **Logstash/Kibana**: use simple logs + Sentry first.
- **Swift/Kotlin mobile apps**: build responsive web first.

## What I would add to your current setup

1. **GraphQL for Django**
   Use Django as the real API layer with typed GraphQL queries instead of REST endpoints.

2. **Better flight search API**
   Queries like:

   ```text
   flightOffers(origin: "DEL", destination: "BOM", date: "2026-05-29")
   airports
   airlines
   providers
   flightOffer(id: 1)
   ```

3. **Indexes/materialized views**
   Your important query path is:

   ```text
   origin + destination + departure_date + passengers/sort/filter
   ```

   You already have some indexes. Add more only around actual slow queries.

4. **Redis caching**
   Cache common searches like `DEL-BOM-2026-05-29` for a few minutes or hours.

5. **Celery**
   Use it for scraping/import jobs, provider-link refreshes, stale data cleanup, and scheduled updates.

6. **Frontend search experience**
   Build the Skyscanner-like parts:

   - airport autocomplete
   - date picker
   - results list
   - filters by airline/stops/time/price/provider
   - sorting by best/cheapest/fastest
   - provider deep links
   - loading and empty states

## Recommended architecture

```text
React / Next.js frontend
        |
Django GraphQL API
        |
Postgres flight database
        |
Redis cache
        |
Celery workers for scraping/import/update jobs
```

Given your repo already has `yatra_django_scraper` with Django models and a `skyclone` Node UI/API, I’d consolidate toward:

- **Django owns database + API**
- **React/TypeScript owns UI**
- **Node only if you specifically need it for provider adapters or frontend tooling**

That keeps the project much simpler while still looking and behaving like a Skyscanner clone.
