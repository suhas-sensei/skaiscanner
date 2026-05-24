import json
import random
import signal
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from flights.management.commands.scrape_yatra import (
    INDIAN_AIRPORTS,
    MAJOR_INDIAN_AIRPORTS,
    SCHEDULED_INDIAN_AIRPORTS,
    Route,
)
from flights.models import FlightOffer, FlightSearch


BOOKING_API_URL = "https://flights.booking.com/api/flights/"
BOOKING_RESULTS_URL = "https://flights.booking.com/flights/{origin}.AIRPORT-{destination}.AIRPORT/"


class ProviderTimeout(RuntimeError):
    pass


def _raise_timeout(signum, frame):
    raise ProviderTimeout("Booking.com API call exceeded hard timeout")


class BookingClient:
    def __init__(self, timeout=20):
        self.timeout = timeout
        self.opener = urllib.request.build_opener()

    def search(self, origin, destination, departure_date, return_date):
        params = self._params(origin, destination, departure_date, return_date)
        url = f"{BOOKING_API_URL}?{urllib.parse.urlencode(params)}"
        command = [
            "curl",
            "--silent",
            "--show-error",
            "--fail",
            "--max-time",
            str(int(self.timeout)),
            url,
            "-H",
            "accept: application/json",
            "-H",
            "referer: https://flights.booking.com/",
            "-H",
            (
                "user-agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
            ),
        ]
        try:
            result = subprocess.run(command, capture_output=True, timeout=self.timeout + 3)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"curl timed out after {exc.timeout}s") from exc
        output = result.stdout.decode("utf-8", "replace")
        if output.strip().startswith("{"):
            return url, json.loads(output)
        if result.returncode:
            detail = (result.stderr + result.stdout).decode("utf-8", "replace")
            raise RuntimeError(detail[:1000])
        return url, json.loads(output)

    def results_url(self, origin, destination, departure_date, return_date):
        params = self._params(origin, destination, departure_date, return_date)
        return BOOKING_RESULTS_URL.format(origin=origin, destination=destination) + "?" + urllib.parse.urlencode(params)

    def _params(self, origin, destination, departure_date, return_date):
        return {
            "type": "ROUNDTRIP",
            "adults": "1",
            "cabinClass": "ECONOMY",
            "children": "",
            "from": f"{origin}.AIRPORT",
            "to": f"{destination}.AIRPORT",
            "fromCountry": "IN",
            "toCountry": "IN",
            "fromLocationName": origin,
            "toLocationName": destination,
            "depart": departure_date.isoformat(),
            "return": return_date.isoformat(),
            "sort": "BEST",
            "travelPurpose": "leisure",
            "ca_source": "flights_index_sb",
            "aid": "304142",
        }


class Command(BaseCommand):
    help = "Fetch Booking.com round-trip flight offers via the public flights API."

    def add_arguments(self, parser):
        parser.add_argument("--origin")
        parser.add_argument("--destination")
        parser.add_argument("--start-date", required=True)
        parser.add_argument("--end-date", required=True)
        parser.add_argument("--return-offset", type=int, default=7)
        parser.add_argument("--random-routes", action="store_true")
        parser.add_argument("--all-indian-routes", action="store_true")
        parser.add_argument("--airport-pool", choices=["major", "all"], default="all")
        parser.add_argument("--scheduled-only", action="store_true")
        parser.add_argument("--route-count", type=int, default=10)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--api-timeout", type=float, default=20)
        parser.add_argument("--sleep", type=float, default=0)
        parser.add_argument("--skip-existing", action="store_true")

    def handle(self, *args, **options):
        start_date = datetime.strptime(options["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(options["end_date"], "%Y-%m-%d").date()
        if start_date > end_date:
            raise CommandError("--start-date must be <= --end-date")

        routes = self._build_routes(options)
        client = BookingClient(timeout=options["api_timeout"])
        total_searches = 0
        total_offers = 0

        for route_index, route in enumerate(routes, start=1):
            current = start_date
            while current <= end_date:
                return_date = min(current + timedelta(days=options["return_offset"]), end_date)
                if return_date <= current:
                    current += timedelta(days=1)
                    continue
                if options["skip_existing"] and self._has_existing(route, current, return_date):
                    current += timedelta(days=1)
                    continue

                total_searches += 1
                total_offers += self._fetch_and_save(client, route, current, return_date, route_index, len(routes))
                current += timedelta(days=1)

        self.stdout.write(self.style.SUCCESS(f"done searches={total_searches} offers={total_offers}"))

    def _build_routes(self, options):
        if options["origin"] or options["destination"]:
            if not options["origin"] or not options["destination"]:
                raise CommandError("--origin and --destination must be provided together.")
            return [Route(options["origin"].upper(), options["destination"].upper())]

        airport_pool = MAJOR_INDIAN_AIRPORTS if options["airport_pool"] == "major" else (
            SCHEDULED_INDIAN_AIRPORTS if options["scheduled_only"] else INDIAN_AIRPORTS
        )
        candidates = [Route(origin, destination) for origin in airport_pool for destination in airport_pool if origin != destination]
        if options["all_indian_routes"]:
            return candidates
        if not options["random_routes"]:
            raise CommandError("Provide --origin/--destination, --random-routes, or --all-indian-routes.")
        rng = random.Random(options["seed"])
        rng.shuffle(candidates)
        return candidates[: options["route_count"]]

    def _has_existing(self, route, departure_date, return_date):
        return FlightSearch.objects.filter(
            origin=route.origin,
            destination=route.destination,
            departure_date=departure_date,
            return_date=return_date,
            trip_type="round_trip",
            source="booking",
            status="success",
        ).exists()

    def _fetch_and_save(self, client, route, departure_date, return_date, route_index, route_count):
        results_url = client.results_url(route.origin, route.destination, departure_date, return_date)
        search = FlightSearch.objects.create(
            origin=route.origin,
            destination=route.destination,
            departure_date=departure_date,
            return_date=return_date,
            trip_type="round_trip",
            source="booking",
            status="failed",
            search_url=results_url,
        )
        try:
            signal.signal(signal.SIGALRM, _raise_timeout)
            signal.alarm(max(1, int(client.timeout) + 2))
            request_url, payload = client.search(route.origin, route.destination, departure_date, return_date)
            signal.alarm(0)
            offers = [
                self._make_offer(search, route, departure_date, return_date, results_url, offer)
                for offer in payload.get("flightOffers") or []
            ]
            FlightOffer.objects.bulk_create(offers, batch_size=100)
            search.status = "success" if offers else "no_results"
            search.offers_found = len(offers)
            search.error_message = "" if offers else "no flightOffers in Booking response"
            search.search_url = request_url
            search.save(update_fields=["status", "offers_found", "error_message", "search_url"])
            self.stdout.write(
                f"[{route_index}/{route_count}] {route.origin}-{route.destination} "
                f"{departure_date} return {return_date}: {len(offers)} offers"
            )
            return len(offers)
        except Exception as exc:
            signal.alarm(0)
            search.error_message = str(exc)[:2000]
            search.save(update_fields=["error_message"])
            self.stdout.write(self.style.WARNING(f"[{route_index}/{route_count}] {route.origin}-{route.destination} {departure_date}: failed: {exc}"))
            return 0

    def _make_offer(self, search, route, departure_date, return_date, results_url, offer):
        segments = offer.get("segments") or []
        first_segment = segments[0] if segments else {}
        last_segment = segments[-1] if segments else {}
        legs = [leg for segment in segments for leg in segment.get("legs", [])]
        first_leg = legs[0] if legs else {}
        carrier = ((first_leg.get("carriersData") or [{}])[0] or {}).get("name", "")
        flight_numbers = "/".join(
            filter(
                None,
                [
                    f"{((leg.get('flightInfo') or {}).get('carrierInfo') or {}).get('marketingCarrier', '')}{(leg.get('flightInfo') or {}).get('flightNumber', '')}"
                    for leg in legs
                ],
            )
        )
        price = (offer.get("priceBreakdown") or {}).get("totalRounded") or (offer.get("priceBreakdown") or {}).get("total") or {}
        amount = Decimal(str(price.get("units") or 0)) + (Decimal(str(price.get("nanos") or 0)) / Decimal("1000000000"))
        stops = sum(max(len(segment.get("legs") or []) - 1, 0) for segment in segments)
        total_seconds = sum(int(segment.get("totalTime") or 0) for segment in segments)
        return FlightOffer(
            search=search,
            source="booking",
            origin=route.origin,
            destination=route.destination,
            departure_date=departure_date,
            return_date=return_date,
            trip_type="round_trip",
            airline=carrier,
            flight_number=flight_numbers[:40],
            departure_time=(first_segment.get("departureTime") or "")[11:16],
            arrival_time=(last_segment.get("arrivalTime") or "")[11:16],
            duration=f"{round(total_seconds / 60)}m" if total_seconds else "",
            stops=str(stops),
            price_amount=amount if amount else None,
            currency=price.get("currencyCode") or "INR",
            provider_offer_url="",
            provider_search_url=results_url,
            provider_link_status="search_page",
            provider_offer_key=(offer.get("flightKey") or offer.get("token") or "")[:512],
            raw_text=offer.get("flightKey") or "",
            raw_payload=offer,
        )
