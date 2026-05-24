import json
import os
import subprocess
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from flights.models import FlightOffer, FlightSearch


REPO_ROOT = settings.BASE_DIR.parent
SKYCLONE_DIR = REPO_ROOT / "skyclone"


def parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value)
    return date.fromisoformat(text[:10])


def parse_time(value):
    if not value:
        return ""
    text = str(value)
    if "T" in text:
        return text.split("T", 1)[1][:5]
    if " " in text:
        return text.split(" ", 1)[1][:5]
    return text[:5]


def duration_label(minutes):
    if minutes is None:
        return ""
    try:
        total = int(minutes)
    except (TypeError, ValueError):
        return ""
    hours, mins = divmod(total, 60)
    return f"{hours}h {mins:02d}m"


def stops_label(stops):
    try:
        count = int(stops)
    except (TypeError, ValueError):
        return str(stops or "")
    if count == 0:
        return "Non Stop"
    if count == 1:
        return "1 Stop"
    return f"{count} Stops"


def decimal_price(value):
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def provider_key(offer):
    return "|".join(
        str(offer.get(field) or "")
        for field in [
            "provider",
            "airline",
            "flightNumber",
            "origin",
            "destination",
            "departureTime",
            "arrivalTime",
            "price",
            "bookingUrl",
        ]
    )


class Command(BaseCommand):
    help = "Import normalized offers from the skyclone provider adapters into Postgres."

    def add_arguments(self, parser):
        parser.add_argument("--origin")
        parser.add_argument("--destination")
        parser.add_argument("--date")
        parser.add_argument("--passengers", type=int, default=1)
        parser.add_argument("--providers", help="Comma-separated provider names for SKYCLONE_PROVIDERS")
        parser.add_argument("--all-existing", action="store_true", help="Import every distinct route/date already in FlightOffer")
        parser.add_argument("--limit-routes", type=int, default=0)
        parser.add_argument("--timeout", type=int, default=180)

    def handle(self, *args, **options):
        routes = self.get_routes(options)
        if not routes:
            raise CommandError("Provide --origin --destination --date, or use --all-existing.")

        total_created = 0
        total_updated = 0
        total_offers = 0
        for route in routes:
            result = self.run_skyclone(route, options)
            created, updated, offer_count = self.import_result(route, result)
            total_created += created
            total_updated += updated
            total_offers += offer_count
            self.stdout.write(
                f"{route['origin']}-{route['destination']} {route['date']}: "
                f"{offer_count} provider offers, {created} created, {updated} updated"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {total_offers} offers: {total_created} created, {total_updated} updated"
            )
        )

    def get_routes(self, options):
        if options["all_existing"]:
            queryset = (
                FlightOffer.objects.values("origin", "destination", "departure_date")
                .distinct()
                .order_by("origin", "destination", "departure_date")
            )
            if options["limit_routes"]:
                queryset = queryset[: options["limit_routes"]]
            return [
                {
                    "origin": item["origin"],
                    "destination": item["destination"],
                    "date": item["departure_date"].isoformat(),
                    "passengers": options["passengers"],
                }
                for item in queryset
            ]

        if not options["origin"] or not options["destination"] or not options["date"]:
            return []
        return [
            {
                "origin": options["origin"].upper(),
                "destination": options["destination"].upper(),
                "date": options["date"],
                "passengers": options["passengers"],
            }
        ]

    def run_skyclone(self, route, options):
        env = os.environ.copy()
        if options["providers"]:
            env["SKYCLONE_PROVIDERS"] = options["providers"]

        command = [
            "node",
            "scripts/export-search.js",
            "--origin",
            route["origin"],
            "--destination",
            route["destination"],
            "--date",
            route["date"],
            "--passengers",
            str(route["passengers"]),
        ]
        completed = subprocess.run(
            command,
            cwd=SKYCLONE_DIR,
            env=env,
            text=True,
            capture_output=True,
            timeout=options["timeout"],
            check=False,
        )
        if completed.returncode != 0:
            raise CommandError(completed.stderr.strip() or completed.stdout.strip())
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise CommandError(f"Could not parse skyclone JSON: {error}") from error

    @transaction.atomic
    def import_result(self, route, result):
        provider_stats = {item["name"]: item for item in result.get("providerStats", [])}
        searches = {}
        for name, stats in provider_stats.items():
            search = FlightSearch.objects.create(
                origin=route["origin"],
                destination=route["destination"],
                departure_date=route["date"],
                source=name,
                status="success" if stats.get("status") == "ok" else "failed",
                offers_found=stats.get("offerCount") or 0,
                error_message=stats.get("error") or "",
            )
            searches[name] = search

        created = 0
        updated = 0
        offer_count = 0
        for flight in result.get("flights", []):
            for provider in flight.get("providers", []):
                for raw_offer in provider.get("offers") or [provider]:
                    offer = {
                        "provider": provider.get("name") or raw_offer.get("name"),
                        "airline": flight.get("airline"),
                        "flightNumber": flight.get("flightNumber"),
                        "origin": flight.get("origin") or route["origin"],
                        "destination": flight.get("destination") or route["destination"],
                        "departureTime": flight.get("departureTime"),
                        "arrivalTime": flight.get("arrivalTime"),
                        "durationMinutes": flight.get("durationMinutes"),
                        "stops": flight.get("stops"),
                        "price": raw_offer.get("price") or provider.get("price"),
                        "currency": raw_offer.get("currency") or provider.get("currency") or flight.get("currency") or "INR",
                        "bookingUrl": raw_offer.get("bookingUrl") or provider.get("bookingUrl"),
                        "scrapedAt": raw_offer.get("scrapedAt") or provider.get("scrapedAt"),
                    }
                    source = offer["provider"] or "unknown"
                    search = searches.get(source) or FlightSearch.objects.create(
                        origin=route["origin"],
                        destination=route["destination"],
                        departure_date=route["date"],
                        source=source,
                        status="success",
                        offers_found=0,
                    )
                    payload = {
                        "search": search,
                        "source": source,
                        "origin": offer["origin"],
                        "destination": offer["destination"],
                        "departure_date": parse_date(route["date"]),
                        "trip_type": "one_way",
                        "airline": offer["airline"] or "",
                        "flight_number": offer["flightNumber"] or "",
                        "departure_time": parse_time(offer["departureTime"]),
                        "arrival_time": parse_time(offer["arrivalTime"]),
                        "duration": duration_label(offer["durationMinutes"]),
                        "stops": stops_label(offer["stops"]),
                        "price_amount": decimal_price(offer["price"]),
                        "currency": offer["currency"],
                        "provider_offer_url": offer["bookingUrl"] or "",
                        "provider_search_url": offer["bookingUrl"] or "",
                        "provider_link_status": "search_page" if offer["bookingUrl"] else "unavailable",
                        "provider_offer_key": provider_key(offer),
                        "raw_payload": offer,
                    }
                    existing = FlightOffer.objects.filter(
                        source=payload["source"],
                        origin=payload["origin"],
                        destination=payload["destination"],
                        departure_date=payload["departure_date"],
                        provider_offer_key=payload["provider_offer_key"],
                    ).first()
                    if existing:
                        for field, value in payload.items():
                            setattr(existing, field, value)
                        existing.scraped_at = timezone.now()
                        existing.save()
                        updated += 1
                    else:
                        FlightOffer.objects.create(**payload)
                        created += 1
                    offer_count += 1

        return created, updated, offer_count
