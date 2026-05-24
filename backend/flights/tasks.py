from datetime import timedelta

from celery import shared_task
from django.core.cache import cache
from django.db.models import Count, Min
from django.utils import timezone

from .models import FlightOffer
from .search import filter_postgres_offers, index_meilisearch_offers, index_opensearch_offers, set_cached_flight_offer_ids


def _stops_count(value):
    normalized = (value or "").strip().lower()
    if not normalized or "non" in normalized or normalized == "direct":
        return 0
    digits = "".join(character for character in normalized if character.isdigit())
    return int(digits) if digits else 0


def _empty_stop_fare(key):
    return {"key": key, "count": 0, "price_amount": None, "currency": "INR"}


@shared_task
def warm_route_search_cache(origin, destination, departure_date):
    queryset = FlightOffer.objects.filter(
        origin=origin.upper(),
        destination=destination.upper(),
        departure_date=departure_date,
    )
    offers = (
        queryset
        .values("origin", "destination", "departure_date")
        .annotate(offer_count=Count("id"), cheapest_price=Min("price_amount"), currency=Min("currency"))
        .order_by("origin", "destination", "departure_date")
        .first()
    )
    payload = offers or {
        "origin": origin.upper(),
        "destination": destination.upper(),
        "departure_date": departure_date,
        "offer_count": 0,
        "cheapest_price": None,
        "currency": "INR",
    }
    payload["providers"] = list(
        queryset.exclude(source="")
        .order_by("source")
        .values_list("source", flat=True)
        .distinct()
    )
    stop_fares = {
        "direct": _empty_stop_fare("direct"),
        "one": _empty_stop_fare("one"),
        "multi": _empty_stop_fare("multi"),
    }
    for offer in (
        queryset.filter(price_amount__isnull=False, price_amount__gt=0)
        .order_by("price_amount")
        .values("stops", "price_amount", "currency")
    ):
        count = _stops_count(offer["stops"])
        key = "direct" if count == 0 else "one" if count == 1 else "multi"
        fare = stop_fares[key]
        fare["count"] += 1
        if fare["price_amount"] is None or offer["price_amount"] < fare["price_amount"]:
            fare["price_amount"] = offer["price_amount"]
            fare["currency"] = offer["currency"] or "INR"
    payload["stop_fares"] = stop_fares
    default_filters = {
        "origin": origin.upper(),
        "destination": destination.upper(),
        "date": departure_date,
        "sort": "price",
        "limit": 5000,
    }
    set_cached_flight_offer_ids(
        [offer.id for offer in filter_postgres_offers(**default_filters)],
        **default_filters,
    )
    cache_key = f"route-summary:{origin.upper()}:{destination.upper()}:{departure_date}"
    cache.set(cache_key, payload, timeout=60 * 30)
    return payload


@shared_task
def count_stale_offers(days=2):
    cutoff = timezone.now() - timedelta(days=days)
    return FlightOffer.objects.filter(scraped_at__lt=cutoff).count()


@shared_task
def index_flight_offers_for_search(backend="meilisearch", batch_size=1000):
    indexed = 0
    queryset = FlightOffer.objects.order_by("id")
    for start in range(0, queryset.count(), batch_size):
        batch = list(queryset[start : start + batch_size])
        if backend == "opensearch":
            result = index_opensearch_offers(batch)
        else:
            result = index_meilisearch_offers(batch)
        indexed += result["indexed"]
    return {"backend": backend, "indexed": indexed}
