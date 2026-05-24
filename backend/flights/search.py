import hashlib
import json

from django.conf import settings
from django.core.cache import cache

from .models import FlightOffer


SORT_FIELDS = {
    "price": ("price_amount", "departure_time"),
    "departure": ("departure_time", "price_amount"),
    "arrival": ("arrival_time", "price_amount"),
    "airline": ("airline", "price_amount"),
}

FLIGHT_OFFER_IDS_CACHE_TIMEOUT = 60 * 10


def normalized_search_filters(**filters):
    limit = max(1, min(filters.get("limit") or 100, 5000))
    return {
        "origin": filters.get("origin").upper() if filters.get("origin") else "",
        "destination": filters.get("destination").upper() if filters.get("destination") else "",
        "date": str(filters.get("date") or ""),
        "return_date": str(filters.get("return_date") or ""),
        "provider": filters.get("provider") or "",
        "airline": filters.get("airline") or "",
        "stops": filters.get("stops") or "",
        "sort": filters.get("sort") or "price",
        "limit": limit,
    }


def flight_offer_ids_cache_key(**filters):
    normalized = normalized_search_filters(**filters)
    digest = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()[:24]
    return f"flight-offer-ids:{digest}"


def get_cached_flight_offer_ids(**filters):
    return cache.get(flight_offer_ids_cache_key(**filters))


def set_cached_flight_offer_ids(offer_ids, **filters):
    cache.set(flight_offer_ids_cache_key(**filters), list(offer_ids), timeout=FLIGHT_OFFER_IDS_CACHE_TIMEOUT)


def serialize_offer(offer):
    return {
        "id": offer.id,
        "provider": offer.source,
        "origin": offer.origin,
        "destination": offer.destination,
        "departure_date": offer.departure_date.isoformat(),
        "return_date": offer.return_date.isoformat() if offer.return_date else None,
        "trip_type": offer.trip_type,
        "airline": offer.airline,
        "flight_number": offer.flight_number,
        "departure_time": offer.departure_time,
        "arrival_time": offer.arrival_time,
        "duration": offer.duration,
        "stops": offer.stops,
        "price_amount": float(offer.price_amount) if offer.price_amount is not None else None,
        "currency": offer.currency,
        "provider_url": offer.provider_offer_url or offer.provider_search_url,
        "provider_offer_url": offer.provider_offer_url,
        "provider_search_url": offer.provider_search_url,
        "provider_link_status": offer.provider_link_status,
        "provider_offer_key": offer.provider_offer_key,
        "search_text": " ".join(
            item
            for item in [
                offer.airline,
                offer.flight_number,
                offer.source,
                offer.origin,
                offer.destination,
                offer.stops,
            ]
            if item
        ),
    }


def filter_postgres_offers(
    origin=None,
    destination=None,
    date=None,
    return_date=None,
    provider=None,
    airline=None,
    stops=None,
    sort="price",
    limit=100,
):
    queryset = FlightOffer.objects.select_related("search")
    if origin:
        queryset = queryset.filter(origin=origin.upper())
    if destination:
        queryset = queryset.filter(destination=destination.upper())
    if date:
        queryset = queryset.filter(departure_date=date)
    if return_date:
        queryset = queryset.filter(return_date=return_date)
    if provider:
        queryset = queryset.filter(source__iexact=provider)
    if airline:
        queryset = queryset.filter(airline__icontains=airline)
    if stops:
        queryset = queryset.filter(stops__icontains=stops)

    limit = max(1, min(limit or 100, 5000))
    return queryset.order_by(*SORT_FIELDS.get(sort, SORT_FIELDS["price"]))[:limit]


def search_offer_ids(**filters):
    backend = settings.SEARCH_BACKEND
    if backend == "meilisearch":
        return search_meilisearch_offer_ids(**filters)
    if backend == "opensearch":
        return search_opensearch_offer_ids(**filters)
    return None


def get_meilisearch_index():
    import meilisearch

    client = meilisearch.Client(settings.MEILISEARCH_URL, settings.MEILISEARCH_MASTER_KEY)
    return client.index(settings.MEILISEARCH_FLIGHT_INDEX)


def configure_meilisearch_index():
    index = get_meilisearch_index()
    index.update_filterable_attributes(
        [
            "origin",
            "destination",
            "departure_date",
            "return_date",
            "provider",
            "airline",
            "stops",
        ]
    )
    index.update_sortable_attributes(["price_amount", "departure_time", "arrival_time", "airline"])


def index_meilisearch_offers(offers):
    documents = [serialize_offer(offer) for offer in offers]
    if not documents:
        return {"indexed": 0}
    configure_meilisearch_index()
    get_meilisearch_index().add_documents(documents, primary_key="id")
    return {"indexed": len(documents)}


def search_meilisearch_offer_ids(
    origin=None,
    destination=None,
    date=None,
    return_date=None,
    provider=None,
    airline=None,
    stops=None,
    sort="price",
    limit=100,
):
    filters = []
    for field, value in [
        ("origin", origin.upper() if origin else None),
        ("destination", destination.upper() if destination else None),
        ("departure_date", date),
        ("return_date", return_date),
        ("provider", provider),
        ("airline", airline),
        ("stops", stops),
    ]:
        if value:
            filters.append(f'{field} = "{value}"')

    sort_map = {
        "price": ["price_amount:asc", "departure_time:asc"],
        "departure": ["departure_time:asc", "price_amount:asc"],
        "arrival": ["arrival_time:asc", "price_amount:asc"],
        "airline": ["airline:asc", "price_amount:asc"],
    }
    result = get_meilisearch_index().search(
        "",
        {
            "filter": filters,
            "sort": sort_map.get(sort, sort_map["price"]),
            "limit": max(1, min(limit or 100, 5000)),
        },
    )
    return [hit["id"] for hit in result.get("hits", [])]


def get_opensearch_client():
    from opensearchpy import OpenSearch

    return OpenSearch(
        hosts=[settings.OPENSEARCH_URL],
        http_auth=(settings.OPENSEARCH_USERNAME, settings.OPENSEARCH_PASSWORD),
        use_ssl=settings.OPENSEARCH_URL.startswith("https://"),
        verify_certs=False,
    )


def configure_opensearch_index():
    client = get_opensearch_client()
    index = settings.OPENSEARCH_FLIGHT_INDEX
    if client.indices.exists(index=index):
        return
    client.indices.create(
        index=index,
        body={
            "mappings": {
                "properties": {
                    "origin": {"type": "keyword"},
                    "destination": {"type": "keyword"},
                    "departure_date": {"type": "date"},
                    "return_date": {"type": "date"},
                    "provider": {"type": "keyword"},
                    "airline": {"type": "keyword"},
                    "stops": {"type": "keyword"},
                    "price_amount": {"type": "float"},
                    "departure_time": {"type": "keyword"},
                    "arrival_time": {"type": "keyword"},
                    "search_text": {"type": "text"},
                }
            }
        },
    )


def index_opensearch_offers(offers):
    from opensearchpy.helpers import bulk

    documents = [serialize_offer(offer) for offer in offers]
    if not documents:
        return {"indexed": 0}
    configure_opensearch_index()
    actions = [
        {
            "_op_type": "index",
            "_index": settings.OPENSEARCH_FLIGHT_INDEX,
            "_id": document["id"],
            "_source": document,
        }
        for document in documents
    ]
    indexed, _ = bulk(get_opensearch_client(), actions)
    return {"indexed": indexed}


def search_opensearch_offer_ids(
    origin=None,
    destination=None,
    date=None,
    return_date=None,
    provider=None,
    airline=None,
    stops=None,
    sort="price",
    limit=100,
):
    filters = []
    for field, value in [
        ("origin", origin.upper() if origin else None),
        ("destination", destination.upper() if destination else None),
        ("departure_date", date),
        ("return_date", return_date),
        ("provider", provider),
        ("airline", airline),
        ("stops", stops),
    ]:
        if value:
            filters.append({"term": {field: value}})

    sort_map = {
        "price": [{"price_amount": "asc"}, {"departure_time": "asc"}],
        "departure": [{"departure_time": "asc"}, {"price_amount": "asc"}],
        "arrival": [{"arrival_time": "asc"}, {"price_amount": "asc"}],
        "airline": [{"airline": "asc"}, {"price_amount": "asc"}],
    }
    result = get_opensearch_client().search(
        index=settings.OPENSEARCH_FLIGHT_INDEX,
        body={
            "query": {"bool": {"filter": filters}} if filters else {"match_all": {}},
            "sort": sort_map.get(sort, sort_map["price"]),
            "size": max(1, min(limit or 100, 5000)),
        },
    )
    return [hit["_id"] for hit in result["hits"]["hits"]]
