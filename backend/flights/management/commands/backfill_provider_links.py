from urllib.parse import urlencode

from django.core.management.base import BaseCommand

from flights.models import FlightOffer


def yatra_search_url(offer):
    params = {
        "type": "O",
        "viewName": "normal",
        "flexi": "0",
        "noOfSegments": "1",
        "origin": offer.origin,
        "originCountry": "IN",
        "destination": offer.destination,
        "destinationCountry": "IN",
        "flight_depart_date": offer.departure_date.strftime("%d/%m/%Y"),
        "ADT": "1",
        "CHD": "0",
        "INF": "0",
        "class": "Economy",
        "source": "fresco-home",
    }
    return "https://flight.yatra.com/air-search-ui/dom2/trigger?" + urlencode(params)


def tripify_search_url(offer):
    params = {
        "froCity": offer.origin,
        "toCity": offer.destination,
        "froDate": offer.departure_date.isoformat(),
        "toDate": offer.return_date.isoformat() if offer.return_date else "",
        "returnDate": offer.return_date.isoformat() if offer.return_date else "",
        "adult": "1",
        "child": "0",
        "infant": "0",
        "cabinClass": "Economy",
        "tripType": "rt" if offer.return_date else "ow",
    }
    return "https://www.tripify.com/search/flights/?" + urlencode(params)


class Command(BaseCommand):
    help = "Backfill provider search/deeplink metadata for existing offers."

    def handle(self, *args, **options):
        updated = 0
        for offer in FlightOffer.objects.filter(provider_link_status="unavailable").iterator(chunk_size=1000):
            source = (offer.source or "").lower()
            if source.startswith("yatra"):
                offer.provider_search_url = yatra_search_url(offer)
                offer.provider_link_status = "search_page"
                offer.provider_offer_key = (
                    f"yatra:{offer.origin}:{offer.destination}:{offer.departure_date}:"
                    f"{offer.airline}:{offer.flight_number}:{offer.price_amount or ''}"
                )[:512]
            elif source == "vakatrip":
                offer.provider_search_url = "https://www.vakatrip.com/flight"
                offer.provider_link_status = "session_required"
                offer.provider_offer_key = (
                    offer.raw_text
                    or (offer.raw_payload or {}).get("routing_key")
                    or f"vakatrip:{offer.origin}:{offer.destination}:{offer.departure_date}:{offer.return_date}:"
                    f"{offer.flight_number}:{offer.price_amount or ''}"
                )[:512]
            elif source == "tripify":
                offer.provider_search_url = tripify_search_url(offer)
                offer.provider_link_status = "search_page"
                offer.provider_offer_key = (
                    f"tripify:{offer.origin}:{offer.destination}:{offer.departure_date}:{offer.return_date}:"
                    f"{offer.airline}:{offer.flight_number}:{offer.price_amount or ''}"
                )[:512]
            else:
                continue
            offer.save(
                update_fields=[
                    "provider_search_url",
                    "provider_link_status",
                    "provider_offer_key",
                ]
            )
            updated += 1
        self.stdout.write(self.style.SUCCESS(f"updated={updated}"))
