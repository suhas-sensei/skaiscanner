import json
import os
import random
import subprocess
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from flights.management.commands.scrape_yatra import (
    INDIAN_AIRPORTS,
    MAJOR_INDIAN_AIRPORTS,
    SCHEDULED_INDIAN_AIRPORTS,
    Route,
)
from flights.models import FlightOffer, FlightSearch


PROVIDER_NAMES = {"Aertrip", "Agoda", "Air India", "Air India Express", "Akasa Air"}
SOURCE_NAMES = {
    "Aertrip": "aertrip",
    "Agoda": "agoda",
    "Air India": "air_india",
    "Air India Express": "air_india_express",
    "Akasa Air": "akasa_air",
}


class Command(BaseCommand):
    help = "Fetch Aertrip/Agoda/Air India/Air India Express/Akasa offers through skyclone adapters and store them."

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
        parser.add_argument("--passengers", type=int, default=1)
        parser.add_argument("--node-timeout", type=int, default=240)
        parser.add_argument("--skip-existing", action="store_true")
        parser.add_argument(
            "--providers",
            nargs="+",
            default=sorted(PROVIDER_NAMES),
            help="Subset of providers to persist. Defaults to all five requested providers.",
        )

    def handle(self, *args, **options):
        start_date = datetime.strptime(options["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(options["end_date"], "%Y-%m-%d").date()
        if start_date > end_date:
            raise CommandError("--start-date must be <= --end-date")

        selected_providers = set(options["providers"])
        unknown = selected_providers - PROVIDER_NAMES
        if unknown:
            raise CommandError(f"Unknown provider(s): {', '.join(sorted(unknown))}")

        routes = self._build_routes(options)
        dates = [start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)]
        total_searches = 0
        total_offers = 0
        for route_index, route in enumerate(routes, start=1):
            for departure_date in dates:
                return_date = min(departure_date + timedelta(days=options["return_offset"]), end_date)
                if return_date <= departure_date:
                    continue
                if options["skip_existing"] and self._all_selected_providers_done(selected_providers, route, departure_date, return_date):
                    continue
                saved = self._fetch_and_save(selected_providers, route, departure_date, return_date, options, route_index, len(routes))
                total_searches += len(selected_providers)
                total_offers += saved

        self.stdout.write(self.style.SUCCESS(f"done provider_searches={total_searches} offers={total_offers}"))

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

    def _all_selected_providers_done(self, selected_providers, route, departure_date, return_date):
        source_names = [SOURCE_NAMES[name] for name in selected_providers]
        found = set(
            FlightSearch.objects.filter(
                source__in=source_names,
                origin=route.origin,
                destination=route.destination,
                departure_date=departure_date,
                return_date=return_date,
                trip_type="round_trip",
            ).values_list("source", flat=True)
        )
        return set(source_names).issubset(found)

    def _fetch_and_save(self, selected_providers, route, departure_date, return_date, options, route_index, route_count):
        search_rows = {
            provider: FlightSearch.objects.create(
                origin=route.origin,
                destination=route.destination,
                departure_date=departure_date,
                return_date=return_date,
                trip_type="round_trip",
                source=SOURCE_NAMES[provider],
                status="failed",
                search_url=self._provider_search_url(provider, route, departure_date, return_date),
            )
            for provider in selected_providers
        }
        try:
            payload = self._run_skyclone(route, departure_date, return_date, options)
        except Exception as exc:
            message = str(exc)[:2000]
            for search in search_rows.values():
                search.error_message = message
                search.save(update_fields=["error_message"])
            self.stdout.write(self.style.WARNING(f"[{route_index}/{route_count}] {route.origin}-{route.destination} {departure_date}: failed: {message}"))
            return 0

        stats_by_provider = {stat.get("name"): stat for stat in payload.get("providerStats") or []}
        provider_offers = {provider: [] for provider in selected_providers}
        for flight in payload.get("flights") or []:
            for provider in flight.get("providers") or []:
                name = provider.get("name")
                if name not in selected_providers:
                    continue
                for provider_offer in provider.get("offers") or [provider]:
                    provider_offers[name].append(
                        self._make_offer(search_rows[name], route, departure_date, return_date, flight, {**provider, **provider_offer})
                    )

        saved_total = 0
        for provider_name, search in search_rows.items():
            offers = provider_offers[provider_name]
            if offers:
                FlightOffer.objects.bulk_create(offers, batch_size=100)
                search.status = "success"
                search.offers_found = len(offers)
                search.error_message = ""
                saved_total += len(offers)
            else:
                stat = stats_by_provider.get(provider_name) or {}
                search.status = "no_results" if stat.get("status") == "ok" else "failed"
                search.offers_found = 0
                search.error_message = stat.get("error") or "no offers returned"
            search.save(update_fields=["status", "offers_found", "error_message"])

        self.stdout.write(
            f"[{route_index}/{route_count}] {route.origin}-{route.destination} {departure_date} return {return_date}: "
            + ", ".join(f"{provider}={len(provider_offers[provider])}" for provider in sorted(selected_providers))
        )
        return saved_total

    def _run_skyclone(self, route, departure_date, return_date, options):
        repo_root = Path(__file__).resolve().parents[4]
        command = [
            "node",
            "scripts/export-search.js",
            "--origin",
            route.origin,
            "--destination",
            route.destination,
            "--date",
            departure_date.isoformat(),
            "--returnDate",
            return_date.isoformat(),
            "--passengers",
            str(options["passengers"]),
        ]
        env = os.environ.copy()
        env.setdefault("AIR_INDIA_USE_AGODA_FALLBACK", "1")
        env.setdefault("AIR_INDIA_EXPRESS_USE_AGODA_FALLBACK", "1")
        env.setdefault("AKASA_AIR_USE_AGODA_FALLBACK", "1")
        env.setdefault("APIFY_AGODA_FLIGHT_RESULT_COUNT", "30")
        env["SKYCLONE_PROVIDERS"] = ",".join(sorted(PROVIDER_NAMES))
        result = subprocess.run(
            command,
            cwd=repo_root / "skyclone",
            env=env,
            capture_output=True,
            text=True,
            timeout=options["node_timeout"],
        )
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip())
        return json.loads(result.stdout)

    def _make_offer(self, search, route, departure_date, return_date, flight, provider):
        price = self._decimal(provider.get("price"))
        departure_time = self._time_part(flight.get("departureTime"))
        arrival_time = self._time_part(flight.get("arrivalTime"))
        duration = flight.get("durationMinutes")
        return FlightOffer(
            search=search,
            source=search.source,
            origin=route.origin,
            destination=route.destination,
            departure_date=departure_date,
            return_date=return_date,
            trip_type="round_trip",
            airline=(flight.get("airline") or "")[:120],
            flight_number=(flight.get("flightNumber") or "")[:40],
            departure_time=departure_time,
            arrival_time=arrival_time,
            duration=f"{duration}m" if duration is not None else "",
            stops=str(flight.get("stops") if flight.get("stops") is not None else ""),
            price_amount=price,
            currency=(provider.get("currency") or "INR")[:8],
            provider_offer_url=provider.get("bookingUrl") or "",
            provider_search_url=self._provider_search_url(provider.get("name"), route, departure_date, return_date),
            provider_link_status="exact" if provider.get("bookingUrl") else "search_page",
            provider_offer_key=f"{provider.get('name')}:{flight.get('flightKey')}:{provider.get('price')}"[:512],
            raw_text=flight.get("flightKey") or "",
            raw_payload={"flight": flight, "provider": provider},
        )

    def _provider_search_url(self, provider, route, departure_date, return_date):
        if provider == "Aertrip":
            return (
                "https://www.aertrip.com/v2/flights?"
                f"origin={route.origin}&destination={route.destination}&depart={departure_date.strftime('%d-%m-%Y')}"
                f"&return={return_date.strftime('%d-%m-%Y')}&adult=1&child=0&infant=0&trip_type=return&cabinclass=Economy&pType=flight"
            )
        if provider == "Agoda":
            return (
                "https://www.agoda.com/flights/results?"
                f"origin={route.origin}&destination={route.destination}&departureDate={departure_date.isoformat()}"
                f"&returnDate={return_date.isoformat()}&adults=1"
            )
        if provider == "Air India":
            return (
                "https://www.airindia.com/in/en/book-flights.html?"
                f"origin={route.origin}&destination={route.destination}&departureDate={departure_date.isoformat()}"
                f"&returnDate={return_date.isoformat()}&adults=1"
            )
        if provider == "Air India Express":
            return (
                "https://www.airindiaexpress.com/booking?"
                f"origin={route.origin}&destination={route.destination}&departureDate={departure_date.isoformat()}"
                f"&returnDate={return_date.isoformat()}&adults=1"
            )
        if provider == "Akasa Air":
            return (
                "https://www.akasaair.com?"
                f"origin={route.origin}&destination={route.destination}&departureDate={departure_date.isoformat()}"
                f"&returnDate={return_date.isoformat()}&adults=1"
            )
        return ""

    def _decimal(self, value):
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    def _time_part(self, value):
        if not value:
            return ""
        text = str(value)
        if "T" in text:
            return text.split("T", 1)[1][:5]
        return text[:5]
