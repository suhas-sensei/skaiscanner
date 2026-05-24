import graphene
from graphene_django import DjangoObjectType
import re
from django.core.cache import cache

from .models import FlightOffer
from .search import filter_postgres_offers, get_cached_flight_offer_ids, search_offer_ids, set_cached_flight_offer_ids
from .tasks import warm_route_search_cache


SEGMENT_KEYS = ("ow", "legs", "segments", "lineSegments")
DEPARTURE_KEYS = ("dac", "origin", "from", "departure", "departureAirport", "originAirport", "depAirport", "depCity")
ARRIVAL_KEYS = ("aac", "destination", "to", "arrival", "arrivalAirport", "destinationAirport", "arrAirport", "arrCity")
CODE_KEYS = ("code", "iata", "iataCode", "airportCode", "airportCityCode", "id")
VIA_RE = re.compile(r"\bvia\s+([A-Za-z .'-]+)", re.IGNORECASE)
AIRPORT_NAME_CODES = {
    "agartala": "IXA",
    "ahmedabad": "AMD",
    "aurangabad": "IXU",
    "bagdogra": "IXB",
    "belagavi": "IXG",
    "bengaluru": "BLR",
    "bhubaneswar": "BBI",
    "chandigarh": "IXC",
    "chennai": "MAA",
    "delhi": "DEL",
    "goa": "GOI",
    "hyderabad": "HYD",
    "jaipur": "JAI",
    "jammu": "IXJ",
    "kandla": "IXY",
    "kochi": "COK",
    "kolkata": "CCU",
    "leh": "IXL",
    "lilabari": "IXI",
    "lucknow": "LKO",
    "madurai": "IXM",
    "mangaluru": "IXE",
    "mangalore": "IXE",
    "mumbai": "BOM",
    "new delhi": "DEL",
    "patna": "PAT",
    "port blair": "IXZ",
    "prayagraj": "IXD",
    "ranchi": "IXR",
    "silchar": "IXS",
    "srinagar": "SXR",
    "varanasi": "VNS",
}


def airport_code(value):
    if isinstance(value, str):
        token = value.strip().upper()
        return token if len(token) == 3 and token.isalpha() else ""
    if isinstance(value, dict):
        for key in CODE_KEYS:
            code = airport_code(value.get(key))
            if code:
                return code
    return ""


def endpoint_code(segment, keys):
    if not isinstance(segment, dict):
        return ""
    for key in keys:
        code = airport_code(segment.get(key))
        if code:
            return code
    return ""


def dedupe_codes(codes):
    return list(dict.fromkeys(code for code in codes if code))


def route_stops_from_segments(segments, origin=None, destination=None):
    if not isinstance(segments, list) or len(segments) <= 1:
        return []

    airports = []
    for segment in segments:
        dep = endpoint_code(segment, DEPARTURE_KEYS)
        arr = endpoint_code(segment, ARRIVAL_KEYS)
        if not dep or not arr:
            return []
        if not airports:
            airports.append(dep)
        airports.append(arr)

    if origin and airports[0] != origin:
        return []
    if destination and airports[-1] != destination:
        return []
    return dedupe_codes(airports[1:-1])


def routing_key_stop_airports(value, origin=None, destination=None):
    if not isinstance(value, str):
        return []

    candidates = [value]
    candidates.extend(value.split("_"))
    for candidate in candidates:
        pairs = re.findall(r"\b([A-Z]{3})-([A-Z]{3})\b", candidate.upper())
        if len(pairs) <= 1:
            continue
        airports = [pairs[0][0], *[arrival for _, arrival in pairs]]
        if origin and airports[0] != origin:
            continue
        if destination and airports[-1] != destination:
            continue
        return dedupe_codes(airports[1:-1])
    return []


def segment_stop_airports(payload, origin=None, destination=None):
    if isinstance(payload, dict):
        for key in ("routing_key", "routingKey", "flightKey"):
            stops = routing_key_stop_airports(payload.get(key), origin, destination)
            if stops:
                return stops

        for key in SEGMENT_KEYS:
            value = payload.get(key)
            stops = route_stops_from_segments(value, origin, destination)
            if stops:
                return stops
            stops = route_stops_from_segments(value)
            if stops:
                return stops

        for value in payload.values():
            stops = segment_stop_airports(value, origin, destination)
            if stops:
                return stops
    if isinstance(payload, list):
        for value in payload:
            stops = segment_stop_airports(value, origin, destination)
            if stops:
                return stops
    return []


def via_stop_airports(payload):
    lines = []
    if isinstance(payload, dict):
        raw_lines = payload.get("lines")
        if isinstance(raw_lines, list):
            lines.extend(str(line) for line in raw_lines)
        for key in ("stops", "stop", "stopover", "layover"):
            if payload.get(key):
                lines.append(str(payload.get(key)))
    elif isinstance(payload, list):
        lines.extend(str(line) for line in payload)
    elif isinstance(payload, str):
        lines.append(payload)

    stops = []
    for line in lines:
        for match in VIA_RE.finditer(line):
            value = match.group(1).strip().lower()
            value = re.split(r"\s{2,}|\(|,|₹|\d", value, maxsplit=1)[0].strip()
            code = AIRPORT_NAME_CODES.get(value)
            if code:
                stops.append(code)
    return list(dict.fromkeys(stops))


class FlightOfferType(DjangoObjectType):
    provider = graphene.String()
    provider_url = graphene.String()
    stop_airports = graphene.List(graphene.String)

    class Meta:
        model = FlightOffer
        fields = (
            "id",
            "origin",
            "destination",
            "departure_date",
            "return_date",
            "trip_type",
            "airline",
            "flight_number",
            "departure_time",
            "arrival_time",
            "duration",
            "stops",
            "price_amount",
            "currency",
            "provider_offer_url",
            "provider_search_url",
            "provider_link_status",
            "provider_offer_key",
        )

    def resolve_provider(self, info):
        return self.source

    def resolve_provider_url(self, info):
        return self.provider_offer_url or self.provider_search_url

    def resolve_stop_airports(self, info):
        return segment_stop_airports(self.raw_payload, self.origin, self.destination) or via_stop_airports(self.raw_payload or self.raw_text)


class StopFareType(graphene.ObjectType):
    key = graphene.String()
    count = graphene.Int()
    price_amount = graphene.Decimal()
    currency = graphene.String()


class StopFareSummaryType(graphene.ObjectType):
    direct = graphene.Field(StopFareType)
    one = graphene.Field(StopFareType)
    multi = graphene.Field(StopFareType)


def stops_count(value):
    normalized = (value or "").strip().lower()
    if not normalized or "non" in normalized or normalized == "direct":
        return 0
    match = re.search(r"\d+", normalized)
    return int(match.group(0)) if match else 0


def empty_stop_fare(key):
    return StopFareType(key=key, count=0, price_amount=None, currency="INR")


def route_summary_cache_key(origin, destination, date):
    return f"route-summary:{origin.upper()}:{destination.upper()}:{date}"


def route_summary_warm_lock_key(origin, destination, date):
    return f"route-summary-warm-lock:{origin.upper()}:{destination.upper()}:{date}"


def enqueue_route_search_cache_warm(origin, destination, date):
    if not origin or not destination or not date:
        return
    lock_key = route_summary_warm_lock_key(origin, destination, date)
    if not cache.add(lock_key, True, timeout=60):
        return
    try:
        warm_route_search_cache.delay(origin.upper(), destination.upper(), date)
    except Exception:
        cache.delete(lock_key)


def cached_route_summary(origin, destination, date):
    if not origin or not destination or not date:
        return None
    return cache.get(route_summary_cache_key(origin, destination, date))


def stop_fare_from_payload(payload, key):
    fare = (payload.get("stop_fares") or {}).get(key) or {}
    return StopFareType(
        key=fare.get("key") or key,
        count=fare.get("count") or 0,
        price_amount=fare.get("price_amount"),
        currency=fare.get("currency") or "INR",
    )


class Query(graphene.ObjectType):
    flight_offer = graphene.Field(FlightOfferType, id=graphene.ID(required=True))
    flight_offers = graphene.List(
        FlightOfferType,
        origin=graphene.String(),
        destination=graphene.String(),
        date=graphene.String(),
        return_date=graphene.String(),
        provider=graphene.String(),
        airline=graphene.String(),
        stops=graphene.String(),
        sort=graphene.String(default_value="price"),
        limit=graphene.Int(default_value=100),
    )
    airports = graphene.List(graphene.String)
    airlines = graphene.List(graphene.String)
    providers = graphene.List(graphene.String)
    route_providers = graphene.List(
        graphene.String,
        origin=graphene.String(required=True),
        destination=graphene.String(required=True),
        date=graphene.String(required=True),
    )
    stop_fare_summary = graphene.Field(
        StopFareSummaryType,
        origin=graphene.String(required=True),
        destination=graphene.String(required=True),
        date=graphene.String(required=True),
    )

    def resolve_flight_offer(self, info, id):
        return FlightOffer.objects.filter(id=id).first()

    def resolve_flight_offers(
        self,
        info,
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
        limit = max(1, min(limit or 100, 5000))
        filters = {
            "origin": origin,
            "destination": destination,
            "date": date,
            "return_date": return_date,
            "provider": provider,
            "airline": airline,
            "stops": stops,
            "sort": sort,
            "limit": limit,
        }
        enqueue_route_search_cache_warm(origin, destination, date)
        cached_offer_ids = get_cached_flight_offer_ids(**filters)
        if cached_offer_ids is not None:
            offers_by_id = FlightOffer.objects.in_bulk(cached_offer_ids)
            return [offers_by_id[int(offer_id)] for offer_id in cached_offer_ids if int(offer_id) in offers_by_id]

        offer_ids = search_offer_ids(**filters)
        if offer_ids is None:
            offers = list(filter_postgres_offers(**filters))
            set_cached_flight_offer_ids([offer.id for offer in offers], **filters)
            return offers
        set_cached_flight_offer_ids(offer_ids, **filters)
        offers_by_id = FlightOffer.objects.in_bulk(offer_ids)
        return [offers_by_id[int(offer_id)] for offer_id in offer_ids if int(offer_id) in offers_by_id]

    def resolve_airports(self, info):
        origins = FlightOffer.objects.values_list("origin", flat=True)
        destinations = FlightOffer.objects.values_list("destination", flat=True)
        return sorted({code for code in origins.union(destinations) if code})

    def resolve_airlines(self, info):
        return list(
            FlightOffer.objects.exclude(airline="")
            .order_by("airline")
            .values_list("airline", flat=True)
            .distinct()
        )

    def resolve_providers(self, info):
        return list(
            FlightOffer.objects.exclude(source="")
            .order_by("source")
            .values_list("source", flat=True)
            .distinct()
        )

    def resolve_route_providers(self, info, origin, destination, date):
        enqueue_route_search_cache_warm(origin, destination, date)
        summary = cached_route_summary(origin, destination, date)
        if summary is not None:
            return summary.get("providers", [])
        return list(
            FlightOffer.objects.filter(
                origin=origin.upper(),
                destination=destination.upper(),
                departure_date=date,
            )
            .exclude(source="")
            .order_by("source")
            .values_list("source", flat=True)
            .distinct()
        )

    def resolve_stop_fare_summary(self, info, origin, destination, date):
        enqueue_route_search_cache_warm(origin, destination, date)
        summary_payload = cached_route_summary(origin, destination, date)
        if summary_payload is not None:
            return StopFareSummaryType(
                direct=stop_fare_from_payload(summary_payload, "direct"),
                one=stop_fare_from_payload(summary_payload, "one"),
                multi=stop_fare_from_payload(summary_payload, "multi"),
            )
        summary = {
            "direct": empty_stop_fare("direct"),
            "one": empty_stop_fare("one"),
            "multi": empty_stop_fare("multi"),
        }
        offers = (
            FlightOffer.objects.filter(
                origin=origin.upper(),
                destination=destination.upper(),
                departure_date=date,
                price_amount__isnull=False,
                price_amount__gt=0,
            )
            .order_by("price_amount")
            .values("stops", "price_amount", "currency")
        )
        for offer in offers:
            count = stops_count(offer["stops"])
            key = "direct" if count == 0 else "one" if count == 1 else "multi"
            fare = summary[key]
            fare.count += 1
            if fare.price_amount is None or offer["price_amount"] < fare.price_amount:
                fare.price_amount = offer["price_amount"]
                fare.currency = offer["currency"] or "INR"
        return StopFareSummaryType(**summary)
