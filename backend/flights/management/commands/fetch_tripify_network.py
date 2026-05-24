import asyncio
import json
import random
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode, urlparse

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from flights.management.commands.scrape_yatra import INDIAN_AIRPORTS, MAJOR_INDIAN_AIRPORTS, SCHEDULED_INDIAN_AIRPORTS, Route
from flights.models import FlightOffer, FlightSearch


TRIPIFY_BASE_URL = "https://www.tripify.com"
TRIPIFY_SEARCH_URL = f"{TRIPIFY_BASE_URL}/search/flights/"
CITY_NAMES = {
    "DEL": "New Delhi",
    "BOM": "Mumbai",
    "BLR": "Bengaluru",
    "HYD": "Hyderabad",
    "MAA": "Chennai",
    "CCU": "Kolkata",
    "AMD": "Ahmedabad",
    "COK": "Kochi",
    "GOI": "Goa",
    "PNQ": "Pune",
    "JAI": "Jaipur",
    "LKO": "Lucknow",
    "IXC": "Chandigarh",
    "BBI": "Bhubaneswar",
    "GAU": "Guwahati",
    "TRV": "Thiruvananthapuram",
    "PAT": "Patna",
    "IDR": "Indore",
    "NAG": "Nagpur",
    "CJB": "Coimbatore",
}
AIRLINE_PATTERNS = (
    r"air\s?india",
    r"indigo",
    r"vistara",
    r"akasa",
    r"spicejet",
    r"alliance",
    r"star\s?air",
)
NETWORK_KEYWORDS = (
    "flight",
    "fare",
    "price",
    "search",
    "availability",
    "air",
    "journey",
    "trip",
)
PRICE_KEYS = (
    "price",
    "fare",
    "amount",
    "total",
    "totalfare",
    "total_fare",
    "publishedfare",
    "offeredfare",
    "netfare",
    "basefare",
)


@dataclass
class TripifyOffer:
    airline: str = ""
    flight_number: str = ""
    departure_time: str = ""
    arrival_time: str = ""
    duration: str = ""
    stops: str = ""
    price_amount: Decimal | None = None
    currency: str = "INR"
    raw_text: str = ""
    raw_payload: dict | None = None


class Command(BaseCommand):
    help = "Fetch Tripify flight prices from Playwright network logs and store them in PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--origin", help="Single origin IATA code, e.g. DEL.")
        parser.add_argument("--destination", help="Single destination IATA code, e.g. BOM.")
        parser.add_argument("--start-date", default="2026-05-22", help="YYYY-MM-DD.")
        parser.add_argument("--end-date", default="2026-06-22", help="YYYY-MM-DD inclusive.")
        parser.add_argument("--random-routes", action="store_true", default=True)
        parser.add_argument("--all-indian-routes", action="store_true")
        parser.add_argument("--airport-pool", choices=["major", "all"], default="all")
        parser.add_argument("--scheduled-only", action="store_true")
        parser.add_argument("--route-count", type=int, default=10)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--return-after-days", type=int, default=7)
        parser.add_argument("--adults", type=int, default=1)
        parser.add_argument("--children", type=int, default=0)
        parser.add_argument("--infants", type=int, default=0)
        parser.add_argument("--cabin-class", default="Economy")
        parser.add_argument("--headful", action="store_true")
        parser.add_argument("--chrome-path", default="/usr/bin/google-chrome")
        parser.add_argument("--page-timeout", type=int, default=45)
        parser.add_argument("--settle-seconds", type=int, default=20)
        parser.add_argument("--body-limit", type=int, default=300000)
        parser.add_argument("--output", default="logs/tripify_network_random_2026_05_22_to_2026_06_22.jsonl")
        parser.add_argument("--skip-existing", action="store_true")

    def handle(self, *args, **options):
        asyncio.run(self._handle_async(options))

    async def _handle_async(self, options):
        start_date = self._parse_date(options["start_date"])
        end_date = self._parse_date(options["end_date"])
        if end_date < start_date:
            raise CommandError("--end-date must be on or after --start-date.")

        routes = self._build_routes(options)
        departure_dates = [start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)]
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)

        self.stdout.write(
            f"Tripify network scrape: {len(routes)} route(s), {len(departure_dates)} departure date(s), "
            f"round_trip return_after_days={options['return_after_days']}, raw_log={output}"
        )

        total_searches = 0
        total_offers = 0
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=not options["headful"],
                executable_path=options["chrome_path"],
                args=[
                    "--disable-dev-shm-usage",
                    "--disable-notifications",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1440, "height": 1200},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                ),
            )
            await context.route("**/*", lambda route: asyncio.create_task(self._route_request(route)))
            page = await context.new_page()
            page.set_default_timeout(options["page_timeout"] * 1000)

            with output.open("a", encoding="utf-8") as file:
                for route_index, route in enumerate(routes, start=1):
                    for departure_date in departure_dates:
                        return_date = departure_date + timedelta(days=options["return_after_days"])
                        if options["skip_existing"] and await self._has_existing(route, departure_date, return_date):
                            self.stdout.write(f"[{route_index}/{len(routes)}] {route.origin}->{route.destination} {departure_date}: skipped")
                            continue

                        result = await self._capture_search(page, route, departure_date, return_date, options)
                        file.write(json.dumps(result["network_log"], ensure_ascii=False, default=str) + "\n")
                        file.flush()

                        saved = await sync_to_async(self._save_result, thread_sensitive=True)(
                            route,
                            departure_date,
                            return_date,
                            result["search_url"],
                            result["offers"],
                            result["error"],
                        )
                        total_searches += 1
                        total_offers += saved
                        self.stdout.write(
                            f"[{route_index}/{len(routes)}] {route.origin}->{route.destination} "
                            f"{departure_date} return {return_date}: saved_offers={saved}"
                        )

            await context.close()
            await browser.close()

        self.stdout.write(self.style.SUCCESS(f"done searches={total_searches} offers={total_offers} raw_log={output}"))

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
        rng = random.Random(options["seed"])
        rng.shuffle(candidates)
        return candidates[: options["route_count"]]

    async def _has_existing(self, route, departure_date, return_date):
        return await sync_to_async(
            FlightSearch.objects.filter(
                origin=route.origin,
                destination=route.destination,
                departure_date=departure_date,
                return_date=return_date,
                trip_type="round_trip",
                source="tripify",
                status="success",
            ).exists,
            thread_sensitive=True,
        )()

    async def _route_request(self, route):
        if route.request.resource_type in {"image", "font", "media"}:
            await route.abort()
        else:
            await route.continue_()

    async def _capture_search(self, page, route, departure_date, return_date, options):
        search_url = self._build_search_url(route, departure_date, return_date, options)
        captured = []
        offers = []
        error = ""

        async def on_response(response):
            request = response.request
            if request.resource_type not in {"xhr", "fetch", "document"}:
                return
            content_type = response.headers.get("content-type", "")
            record = {
                "origin": route.origin,
                "destination": route.destination,
                "departure_date": departure_date.isoformat(),
                "return_date": return_date.isoformat(),
                "trip_type": "round_trip",
                "search_url": search_url,
                "request_url": request.url,
                "request_method": request.method,
                "request_resource_type": request.resource_type,
                "request_post_data": self._safe_post_data(request),
                "response_status": response.status,
                "response_content_type": content_type,
            }
            if not self._is_candidate_response(request.url, content_type):
                return
            try:
                text = await response.text()
            except Exception as exc:
                record["body_error"] = str(exc)
                captured.append(record)
                return

            record["body_snippet"] = text[: options["body_limit"]]
            parsed = self._parse_json(text)
            if parsed is not None:
                record["json"] = parsed
                offers.extend(self._extract_offers(parsed))
            elif request.resource_type == "document":
                offers.extend(self._extract_offers_from_text(text))
            captured.append(record)

        page.on("response", on_response)
        try:
            await self._submit_search_form(page, route, departure_date, return_date, options)
            await page.wait_for_timeout(options["settle_seconds"] * 1000)
            await page.evaluate("() => { if (document.body) window.scrollTo(0, document.body.scrollHeight); }")
            await page.wait_for_timeout(2000)
            try:
                body_text = await page.locator("body").inner_text(timeout=5000)
                offers.extend(self._extract_offers_from_text(body_text))
            except Exception:
                pass
        except Exception as exc:
            error = str(exc)
        finally:
            page.remove_listener("response", on_response)

        if not error and not offers and not any(record.get("body_snippet") for record in captured):
            error = "No parseable Tripify response body captured from network logs."

        return {
            "search_url": search_url,
            "offers": self._dedupe_offers(offers),
            "error": error,
            "network_log": {
                "origin": route.origin,
                "destination": route.destination,
                "departure_date": departure_date.isoformat(),
                "return_date": return_date.isoformat(),
                "search_url": search_url,
                "response_count": len(captured),
                "responses": captured,
                "error": error,
            },
        }

    def _build_search_url(self, route, departure_date, return_date, options):
        params = {
            "froCity": route.origin,
            "toCity": route.destination,
            "froDate": departure_date.isoformat(),
            "toDate": return_date.isoformat(),
            "returnDate": return_date.isoformat(),
            "adult": str(options["adults"]),
            "child": str(options["children"]),
            "infant": str(options["infants"]),
            "cabinClass": options["cabin_class"],
            "tripType": "rt",
            "utm_source": "online",
            "utm_medium": "network-scrape",
        }
        return f"{TRIPIFY_SEARCH_URL}?{urlencode(params)}"

    async def _submit_search_form(self, page, route, departure_date, return_date, options):
        try:
            await page.goto(TRIPIFY_BASE_URL, wait_until="domcontentloaded", timeout=options["page_timeout"] * 1000)
        except PlaywrightTimeoutError:
            pass

        payload = {
            "tripType": "rt",
            "triptype": "rt",
            "fromCity": f"{CITY_NAMES.get(route.origin, route.origin)}, {route.origin}",
            "toCity": f"{CITY_NAMES.get(route.destination, route.destination)}, {route.destination}",
            "origin": self._city_value(route.origin),
            "destination": self._city_value(route.destination),
            "departDate": departure_date.isoformat(),
            "fromDate": departure_date.isoformat(),
            "returnDate": return_date.isoformat(),
            "toDate": return_date.isoformat(),
            "adult": str(options["adults"]),
            "child": str(options["children"]),
            "infant": str(options["infants"]),
            "cabin": options["cabin_class"],
            "cabinClass": options["cabin_class"],
            "fareType": "Normal",
        }
        try:
            await page.evaluate(
                """(payload) => {
                    const form = document.querySelector("form#searchForm");
                    if (!form) throw new Error("Tripify search form not found");
                    for (const [name, value] of Object.entries(payload)) {
                        const inputs = Array.from(form.querySelectorAll(`[name="${name}"]`));
                        const byId = document.getElementById(name);
                        if (byId && !inputs.includes(byId)) inputs.push(byId);
                        for (const input of inputs) {
                            if (input.type === "radio") {
                                input.checked = input.value === value;
                            } else {
                                input.value = value;
                            }
                        }
                    }
                    const roundTripRadio = form.querySelector('input[name="triptype"][value="rt"]');
                    if (roundTripRadio) roundTripRadio.checked = true;
                    form.submit();
                }""",
                payload,
            )
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=options["page_timeout"] * 1000)
            except PlaywrightTimeoutError:
                pass
        except Exception:
            # Fallback to the public deal-link shape, which is still useful for raw network diagnostics.
            try:
                await page.goto(self._build_search_url(route, departure_date, return_date, options), wait_until="domcontentloaded", timeout=options["page_timeout"] * 1000)
            except PlaywrightTimeoutError:
                pass

    def _city_value(self, code):
        return f"{CITY_NAMES.get(code, code)}({code})"

    def _is_candidate_response(self, url, content_type):
        parsed = urlparse(url)
        if not parsed.netloc.endswith("tripify.com"):
            return False
        lowered = f"{parsed.path} {parsed.query} {content_type}".lower()
        if "json" in lowered:
            return True
        if "html" in lowered and "/search/flights" in parsed.path:
            return True
        if any(keyword in lowered for keyword in NETWORK_KEYWORDS):
            return True
        return False

    def _safe_post_data(self, request):
        try:
            return request.post_data
        except UnicodeDecodeError:
            return "<binary post body>"
        except Exception as exc:
            return f"<post body read failed: {exc}>"

    def _parse_json(self, text):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed
        except Exception:
            return None

    def _extract_offers(self, payload):
        offers = []
        for node in self._walk(payload):
            if not isinstance(node, dict):
                continue
            price = self._extract_price_from_node(node)
            if price is None:
                continue
            text = json.dumps(node, ensure_ascii=False, default=str)
            if not self._looks_like_flight(text, node):
                continue
            offers.append(
                TripifyOffer(
                    airline=self._first_value(node, ("airline", "airlineName", "carrier", "carrierName", "operator", "an")),
                    flight_number=self._flight_number(node, text),
                    departure_time=self._first_value(node, ("departureTime", "departTime", "depTime", "departure", "ddt")),
                    arrival_time=self._first_value(node, ("arrivalTime", "arrTime", "arrival", "adt")),
                    duration=self._first_value(node, ("duration", "journeyDuration", "totalDuration")),
                    stops=self._first_value(node, ("stops", "stop", "stopType", "stopInfo")),
                    price_amount=price,
                    currency=self._first_value(node, ("currency", "currencyCode")) or "INR",
                    raw_text="",
                    raw_payload=node,
                )
            )
        return offers

    def _walk(self, value):
        yield value
        if isinstance(value, dict):
            for child in value.values():
                yield from self._walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from self._walk(child)

    def _looks_like_flight(self, text, node):
        lowered = text.lower()
        has_airport = bool(re.search(r"\b[A-Z]{3}\b", text))
        has_airline = any(re.search(pattern, lowered) for pattern in AIRLINE_PATTERNS)
        has_flight_number = bool(re.search(r"\b[A-Z0-9]{2}\s?-?\s?\d{2,4}\b", text))
        key_blob = " ".join(str(key).lower() for key in node.keys())
        has_flight_keys = any(token in key_blob for token in ("flight", "airline", "carrier", "segment", "journey"))
        return (has_airport or has_airline or has_flight_number) and has_flight_keys

    def _extract_price_from_node(self, node):
        candidates = []
        for key, value in node.items():
            normalized_key = re.sub(r"[^a-z]", "", str(key).lower())
            if any(price_key in normalized_key for price_key in PRICE_KEYS):
                candidates.append(value)
        for value in candidates:
            price = self._decimal_from_value(value)
            if price is not None:
                return price
        return None

    def _decimal_from_value(self, value):
        if isinstance(value, dict):
            for nested in value.values():
                parsed = self._decimal_from_value(nested)
                if parsed is not None:
                    return parsed
            return None
        if isinstance(value, list):
            for nested in value:
                parsed = self._decimal_from_value(nested)
                if parsed is not None:
                    return parsed
            return None
        if value in (None, ""):
            return None
        match = re.search(r"([0-9][0-9,]*(?:\.\d{1,2})?)", str(value))
        if not match:
            return None
        try:
            return Decimal(match.group(1).replace(",", ""))
        except (InvalidOperation, ValueError):
            return None

    def _first_value(self, node, keys):
        lowered = {str(key).lower(): value for key, value in node.items()}
        for key in keys:
            value = lowered.get(key.lower())
            if value not in (None, "", [], {}):
                if isinstance(value, dict):
                    for nested in ("name", "code", "en"):
                        if value.get(nested):
                            return str(value[nested])[:120]
                    return json.dumps(value, ensure_ascii=False, default=str)[:120]
                if isinstance(value, list):
                    return "/".join(str(item) for item in value if item)[:120]
                return str(value)[:120]
        return ""

    def _flight_number(self, node, text):
        value = self._first_value(node, ("flightNumber", "flightNo", "flight", "flight_number", "fl"))
        if value:
            return value[:40]
        match = re.search(r"\b([A-Z0-9]{2}\s?-?\s?\d{2,4})\b", text)
        return match.group(1)[:40] if match else ""

    def _extract_offers_from_text(self, text):
        offers = []
        chunks = re.split(r"\n(?=(?:Air India|IndiGo|Vistara|Akasa|SpiceJet|Alliance|Star Air|[A-Z0-9]{2}\s?-?\s?\d{2,4}))", text)
        for chunk in chunks:
            price = self._extract_price(chunk)
            if price is None:
                continue
            airline = self._first_regex(chunk, AIRLINE_PATTERNS)
            flight_number = self._first_regex(chunk, (r"\b([A-Z0-9]{2}\s?-?\s?\d{2,4})\b",))
            if not airline and not flight_number:
                continue
            if not re.search(r"\b[A-Z]{3}\b", chunk):
                continue
            times = re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", chunk)
            time_values = [f"{hour.zfill(2)}:{minute}" for hour, minute in times]
            offers.append(
                TripifyOffer(
                    airline=airline,
                    flight_number=flight_number,
                    departure_time=time_values[0] if time_values else "",
                    arrival_time=time_values[1] if len(time_values) > 1 else "",
                    duration=self._first_regex(chunk, (r"\b(\d+h\s?\d*m?|\d+\s?hr\s?\d*\s?min)\b",)),
                    stops=self._first_regex(chunk, (r"\b(non[- ]?stop|\d+\s+stop[s]?)\b",)),
                    price_amount=price,
                    raw_text=chunk.strip()[:5000],
                    raw_payload={"fallback": "text"},
                )
            )
        return offers

    def _extract_price(self, text):
        matches = re.findall(r"(?:₹|Rs\.?|INR)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", text, flags=re.IGNORECASE)
        if not matches:
            matches = re.findall(r"\b([0-9]{1,3}(?:,[0-9]{3})+(?:\.\d{1,2})?)\b", text)
        if not matches:
            return None
        try:
            amount = Decimal(matches[-1].replace(",", ""))
        except InvalidOperation:
            return None
        return amount if amount >= Decimal("500") else None

    def _first_regex(self, text, patterns):
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return (match.group(1) if match.groups() else match.group(0)).strip()[:120]
        return ""

    def _dedupe_offers(self, offers):
        seen = set()
        unique = []
        for offer in offers:
            key = (
                offer.airline,
                offer.flight_number,
                offer.departure_time,
                offer.arrival_time,
                offer.duration,
                offer.stops,
                offer.price_amount,
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(offer)
        return unique

    @transaction.atomic
    def _save_result(self, route, departure_date, return_date, search_url, offers, error):
        status = "success" if offers else "no_results"
        if error and not offers:
            status = "failed"
        search = FlightSearch.objects.create(
            origin=route.origin,
            destination=route.destination,
            departure_date=departure_date,
            return_date=return_date,
            trip_type="round_trip",
            source="tripify",
            status=status,
            offers_found=len(offers),
            error_message=error[:2000],
            search_url=search_url,
        )
        FlightOffer.objects.bulk_create(
            [
                FlightOffer(
                    search=search,
                    source="tripify",
                    origin=route.origin,
                    destination=route.destination,
                    departure_date=departure_date,
                    return_date=return_date,
                    trip_type="round_trip",
                    airline=offer.airline,
                    flight_number=offer.flight_number,
                    departure_time=offer.departure_time,
                    arrival_time=offer.arrival_time,
                    duration=offer.duration,
                    stops=offer.stops,
                    price_amount=offer.price_amount,
                    currency=offer.currency or "INR",
                    provider_offer_url="",
                    provider_search_url=search_url,
                    provider_link_status="search_page",
                    provider_offer_key=(
                        f"tripify:{route.origin}:{route.destination}:{departure_date}:{return_date}:"
                        f"{offer.airline}:{offer.flight_number}:{offer.price_amount or ''}"
                    )[:512],
                    raw_text=offer.raw_text,
                    raw_payload=offer.raw_payload or {},
                )
                for offer in offers
            ],
            batch_size=500,
        )
        return len(offers)

    def _parse_date(self, value: str) -> date:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise CommandError("Dates must use YYYY-MM-DD format.") from exc
