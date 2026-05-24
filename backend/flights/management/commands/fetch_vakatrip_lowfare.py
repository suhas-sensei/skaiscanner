import hashlib
import json
import random
import signal
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from flights.management.commands.scrape_yatra import INDIAN_AIRPORTS, MAJOR_INDIAN_AIRPORTS, SCHEDULED_INDIAN_AIRPORTS, Route
from flights.models import FlightOffer, FlightSearch


API_BASE = "https://pro.vakatrip.com/api"
SIGNING_SALT = "signature.vakatrip.com.cn.org"
VAKATRIP_FLIGHT_URL = "https://www.vakatrip.com/flight"


class ProviderTimeout(RuntimeError):
    pass


def _raise_timeout(signum, frame):
    raise ProviderTimeout("Vakatrip API call exceeded hard timeout")


def js_stringify(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def sign_payload(payload):
    parts = []
    for key in sorted(payload):
        if key == "signature":
            continue
        value = payload[key]
        if isinstance(value, (dict, list)):
            rendered = js_stringify(value) if value else ""
        else:
            rendered = "" if value is None else str(value)
        parts.append(f"{key}={rendered}")
    return hashlib.md5(("&".join(parts) + SIGNING_SALT).encode("utf-8")).hexdigest()


class VakatripClient:
    def __init__(self, timeout=20):
        self.opener = urllib.request.build_opener()
        self.timeout = timeout

    def _with_common_fields(self, payload, endpoint):
        data = dict(payload)
        data["timestamp"] = int(time.time() * 1000)
        data["channel_key"] = "365|letsflyhk-vakatrip_cnl-all"
        data["meta_click_id"] = ""
        data["language"] = data.get("language") or "en"
        data["referer"] = ""
        data["quote_id"] = ""
        data["device_type"] = 1
        data["qs"] = 0
        data["ref"] = ""
        if "MetaSearchBooking" not in endpoint and "LowFareSearch" not in endpoint:
            data["abTest"] = 0
        if not data.get("globalSearchId") and not data.get("product_origin"):
            data["globalSearchId"] = ""
            data["product_origin"] = 3
        data["signature"] = sign_payload(data)
        return data

    def request(self, endpoint, payload=None, method="POST"):
        url = API_BASE + endpoint
        body = None
        if method == "POST":
            body = js_stringify(self._with_common_fields(payload or {}, endpoint)).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "content-type": "application/json;charset=UTF-8",
                "origin": "https://www.vakatrip.com",
                "referer": "https://www.vakatrip.com/",
                "user-agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124 Safari/537.36"
                ),
            },
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(exc.read().decode("utf-8", "replace")) from exc

    def city(self, code):
        data = self.request(
            "/v1/CitySearch",
            {"lang": "en", "country_code": "IN", "word": code, "product_origin": 6},
        )
        if not data:
            raise RuntimeError(f"CitySearch returned no result for {code}")
        city = data[0]
        return {
            "code": city["city_code"],
            "name": city["city_name"],
            "type": city.get("type") or "city",
        }

    def captcha(self):
        data = self.request("/v1/CodeUuid", method="GET")
        payload = data.get("data") or {}
        if not payload.get("captcha_code") or not payload.get("gvcode_uuid"):
            raise RuntimeError("CodeUuid response did not include captcha_code/gvcode_uuid")
        return payload["captcha_code"], payload["gvcode_uuid"]

    def low_fare(self, origin, destination, depart_date, return_date):
        captcha_code, captcha_uuid = self.captcha()
        payload = {
            "searchId": "",
            "timeout": 5,
            "departuretime": depart_date.strftime("%Y%m%d"),
            "returntime": return_date.strftime("%Y%m%d") if return_date else None,
            "adults": 1,
            "children": 0,
            "cabinClass": "Y",
            "onewayName": f"{origin['name']}({origin['code']})",
            "returnName": f"{destination['name']}({destination['code']})",
            "fromCityName": "",
            "fromAirportName": "",
            "returnCityName": "",
            "returnAirportName": "",
            "fromCityCode": "",
            "returnCityCode": "",
            "fromAirportCode": "",
            "returnAirportCode": "",
            "oneway": origin["code"],
            "onewaytype": "city",
            "return": destination["code"],
            "returntype": "city",
            "currency": "INR",
            "offset": 20,
            "gvcode_b64str": captcha_code,
            "gvcode_uuid": captcha_uuid,
            "globalSearchId": "",
            "product_origin": 6,
        }
        return self.request("/v1/LowFareSearch", payload)


def parse_yyyymmdd(value):
    return datetime.strptime(value[:8], "%Y%m%d").date() if value else None


def flatten_segments(card):
    result = []
    for segment in card.get("segments") or []:
        result.extend(segment.get("lineSegments") or [])
    if result:
        return result
    routing = card.get("routing") or {}
    return (routing.get("fromSegments") or []) + (routing.get("retSegments") or [])


def make_offer(search, origin, destination, depart_date, return_date, card):
    segments = flatten_segments(card)
    first = segments[0] if segments else {}
    last = segments[-1] if segments else {}
    price = card.get("price") or {}
    amount = (price.get("showAdultFare") or price.get("adultFare") or 0) + (
        price.get("showAdultTax") or price.get("adultTax") or 0
    )
    airline = ((first.get("airway") or {}).get("en") or first.get("carrier") or "").strip()
    flight_numbers = "/".join(filter(None, [segment.get("flightNumber") for segment in segments]))
    duration = sum(int(segment.get("duration") or 0) for segment in segments)
    stops = sum(max(len((segment_group.get("lineSegments") or [])) - 1, 0) for segment_group in card.get("segments") or [])
    return FlightOffer(
        search=search,
        source="vakatrip",
        origin=origin,
        destination=destination,
        departure_date=depart_date,
        return_date=return_date,
        trip_type="round_trip" if return_date else "one_way",
        airline=airline,
        flight_number=flight_numbers[:40],
        departure_time=first.get("depTime") or first.get("depTimeStamp") or "",
        arrival_time=last.get("arrTime") or "",
        duration=f"{duration}m" if duration else "",
        stops=str(stops),
        price_amount=Decimal(str(amount)) if amount else None,
        currency=price.get("showCurrency") or price.get("currency") or "INR",
        provider_offer_url="",
        provider_search_url=VAKATRIP_FLIGHT_URL,
        provider_link_status="session_required",
        provider_offer_key=(
            card.get("routing_key")
            or (card.get("routing") or {}).get("routing_key")
            or f"vakatrip:{origin}:{destination}:{depart_date}:{return_date}:{flight_numbers}:{amount}"
        )[:512],
        raw_text=card.get("routing_key", ""),
        raw_payload=card,
    )


class Command(BaseCommand):
    help = "Fetch Vakatrip round-trip low fare search results via signed network API."

    def add_arguments(self, parser):
        parser.add_argument("--origin")
        parser.add_argument("--destination")
        parser.add_argument("--random-routes", action="store_true")
        parser.add_argument("--all-indian-routes", action="store_true")
        parser.add_argument("--airport-pool", choices=["major", "all"], default="all")
        parser.add_argument("--scheduled-only", action="store_true")
        parser.add_argument("--route-count", type=int, default=25)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--start-date", required=True)
        parser.add_argument("--end-date", required=True)
        parser.add_argument("--return-offset", type=int, default=7)
        parser.add_argument("--sleep", type=float, default=0.25)
        parser.add_argument("--api-timeout", type=float, default=12)
        parser.add_argument("--skip-existing", action="store_true")

    def handle(self, *args, **options):
        start_date = datetime.strptime(options["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(options["end_date"], "%Y-%m-%d").date()
        if start_date > end_date:
            raise CommandError("--start-date must be <= --end-date")

        routes = self._build_routes(options)
        client = VakatripClient(timeout=options["api_timeout"])

        total_searches = 0
        total_offers = 0
        city_cache = {}
        for route_index, route in enumerate(routes, start=1):
            origin_code = route.origin
            destination_code = route.destination
            try:
                if origin_code not in city_cache:
                    city_cache[origin_code] = client.city(origin_code)
                if destination_code not in city_cache:
                    city_cache[destination_code] = client.city(destination_code)
                origin = city_cache[origin_code]
                destination = city_cache[destination_code]
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f"[{route_index}/{len(routes)}] {origin_code}-{destination_code}: unsupported by Vakatrip CitySearch: {exc}"
                    )
                )
                continue

            current = start_date
            while current <= end_date:
                return_date = current + timedelta(days=options["return_offset"])
                if return_date > end_date:
                    return_date = end_date
                if return_date <= current:
                    current += timedelta(days=1)
                    continue
                if options["skip_existing"] and FlightSearch.objects.filter(
                    origin=origin_code,
                    destination=destination_code,
                    departure_date=current,
                    return_date=return_date,
                    trip_type="round_trip",
                    source="vakatrip",
                    status__in=["success", "no_results"],
                ).exists():
                    current += timedelta(days=1)
                    continue
                total_searches += 1
                total_offers += self._fetch_and_save(
                    client,
                    origin,
                    destination,
                    origin_code,
                    destination_code,
                    current,
                    return_date,
                    route_index,
                    len(routes),
                )
                current += timedelta(days=1)
                if options["sleep"]:
                    time.sleep(options["sleep"])

        self.stdout.write(self.style.SUCCESS(f"done searches={total_searches} offers={total_offers}"))

    def _build_routes(self, options):
        if options["origin"] or options["destination"]:
            if not options["origin"] or not options["destination"]:
                raise CommandError("--origin and --destination must be provided together.")
            return [Route(options["origin"].upper(), options["destination"].upper())]
        if options["airport_pool"] == "major":
            airport_pool = MAJOR_INDIAN_AIRPORTS
        else:
            airport_pool = SCHEDULED_INDIAN_AIRPORTS if options["scheduled_only"] else INDIAN_AIRPORTS
        candidates = [Route(origin, destination) for origin in airport_pool for destination in airport_pool if origin != destination]
        if options["all_indian_routes"]:
            return candidates
        if not options["random_routes"]:
            raise CommandError("Provide --origin/--destination, --random-routes, or --all-indian-routes.")
        rng = random.Random(options["seed"])
        rng.shuffle(candidates)
        return candidates[: options["route_count"]]

    def _fetch_and_save(self, client, origin, destination, origin_code, destination_code, current, return_date, route_index, route_count):
        search = FlightSearch.objects.create(
            origin=origin_code,
            destination=destination_code,
            departure_date=current,
            return_date=return_date,
            trip_type="round_trip",
            source="vakatrip",
            status="failed",
            search_url=f"{API_BASE}/v1/LowFareSearch",
        )
        try:
            signal.signal(signal.SIGALRM, _raise_timeout)
            signal.alarm(max(1, int(client.timeout) + 2))
            response = client.low_fare(origin, destination, current, return_date)
            signal.alarm(0)
            cards = response.get("tripCard") or []
            offers = [
                make_offer(search, origin_code, destination_code, current, return_date, card)
                for card in cards
            ]
            FlightOffer.objects.bulk_create(offers, batch_size=100)
            search.status = "success" if offers else "no_results"
            search.offers_found = len(offers)
            search.error_message = "" if offers else response.get("msg", "no results")
            search.save(update_fields=["status", "offers_found", "error_message"])
            self.stdout.write(
                f"[{route_index}/{route_count}] {origin_code}-{destination_code} {current} return {return_date}: {len(offers)} offers"
            )
            return len(offers)
        except Exception as exc:
            signal.alarm(0)
            search.error_message = str(exc)[:2000]
            search.save(update_fields=["error_message"])
            self.stdout.write(
                self.style.WARNING(f"[{route_index}/{route_count}] {origin_code}-{destination_code} {current}: failed: {exc}")
            )
            return 0
