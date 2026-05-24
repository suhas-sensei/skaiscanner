import csv
import random
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from flights.models import FlightOffer, FlightSearch


YATRA_TRIGGER_URL = "https://flight.yatra.com/air-search-ui/dom2/trigger"
DEFAULT_ROUTES_FILE = Path(__file__).resolve().parents[3] / "data" / "routes.csv"
DEFAULT_AIRPORTS_FILE = Path(__file__).resolve().parents[3] / "data" / "indian_airports.csv"
MAJOR_INDIAN_AIRPORTS = [
    "DEL", "BOM", "BLR", "HYD", "MAA", "CCU", "AMD", "COK", "GOI", "PNQ",
    "JAI", "LKO", "IXC", "BBI", "GAU", "TRV", "PAT", "IDR", "NAG", "CJB",
]


@dataclass(frozen=True)
class Route:
    origin: str
    destination: str


@dataclass
class ExtractedOffer:
    origin: str = ""
    destination: str = ""
    departure_date: date | None = None
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


def load_indian_airports(scheduled_only=False):
    if not DEFAULT_AIRPORTS_FILE.exists():
        return MAJOR_INDIAN_AIRPORTS
    airports = []
    with DEFAULT_AIRPORTS_FILE.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            code = (row.get("iata_code") or "").strip().upper()
            if not code:
                continue
            if scheduled_only and row.get("scheduled_service") != "yes":
                continue
            airports.append(code)
    return sorted(set(airports))


INDIAN_AIRPORTS = load_indian_airports(scheduled_only=False)
SCHEDULED_INDIAN_AIRPORTS = load_indian_airports(scheduled_only=True)


class Command(BaseCommand):
    help = "Scrape Yatra flight prices for configured routes and dates into PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--origin", help="Single origin IATA code, e.g. DEL.")
        parser.add_argument("--destination", help="Single destination IATA code, e.g. BOM.")
        parser.add_argument("--routes", default=str(DEFAULT_ROUTES_FILE), help="CSV with origin,destination columns.")
        parser.add_argument("--random-routes", action="store_true", help="Generate random Indian airport route pairs.")
        parser.add_argument("--all-major-routes", action="store_true", help="Use every directed pair in the major Indian airport pool.")
        parser.add_argument("--all-indian-routes", action="store_true", help="Use every directed pair in the full configured Indian airport pool.")
        parser.add_argument(
            "--airport-pool",
            choices=["major", "all"],
            default="all",
            help="Airport pool used by --random-routes. Defaults to all configured Indian airports.",
        )
        parser.add_argument("--scheduled-only", action="store_true", help="Limit --airport-pool all to airports with scheduled service.")
        parser.add_argument("--route-count", type=int, default=100, help="Number of random route pairs to generate.")
        parser.add_argument("--seed", type=int, default=42, help="Seed for reproducible random routes.")
        parser.add_argument("--start-date", help="YYYY-MM-DD. Defaults to today.")
        parser.add_argument("--end-date", help="YYYY-MM-DD inclusive. Overrides --days when provided.")
        parser.add_argument("--days", type=int, default=122, help="Number of departure dates to scrape. Defaults to ~4 months.")
        parser.add_argument(
            "--trip-types",
            nargs="+",
            choices=["one_way", "round_trip"],
            default=["one_way"],
            help="Trip types to scrape.",
        )
        parser.add_argument("--return-after-days", type=int, default=7, help="Return date offset for round trips.")
        parser.add_argument("--adults", type=int, default=1)
        parser.add_argument("--children", type=int, default=0)
        parser.add_argument("--infants", type=int, default=0)
        parser.add_argument("--cabin-class", default="Economy")
        parser.add_argument("--headful", action="store_true", help="Run Chrome with a visible browser window.")
        parser.add_argument("--delay", type=float, default=2.0, help="Seconds to wait between searches.")
        parser.add_argument("--page-timeout", type=int, default=35)
        parser.add_argument("--limit-routes", type=int, help="Scrape only the first N routes from the route list.")
        parser.add_argument("--limit-days", type=int, help="Scrape only the first N generated dates.")
        parser.add_argument("--skip-existing", action="store_true", help="Skip searches already stored for the route/date.")

    def handle(self, *args, **options):
        routes = self._load_routes(options)
        if options["limit_routes"]:
            routes = routes[: options["limit_routes"]]

        start_date = self._parse_start_date(options["start_date"])
        departure_dates = self._build_departure_dates(start_date, options)

        trip_types = options["trip_types"]
        self.stdout.write(
            f"Scraping {len(routes)} route(s) across {len(departure_dates)} date(s), "
            f"trip types: {', '.join(trip_types)}."
        )

        driver = self._build_driver(headless=not options["headful"], timeout=options["page_timeout"])
        try:
            for route in routes:
                for departure_date in departure_dates:
                    for trip_type in trip_types:
                        return_date = None
                        if trip_type == "round_trip":
                            return_date = departure_date + timedelta(days=options["return_after_days"])
                        if options["skip_existing"] and FlightSearch.objects.filter(
                            origin=route.origin,
                            destination=route.destination,
                            departure_date=departure_date,
                            return_date=return_date,
                            trip_type=trip_type,
                            status="success",
                        ).exists():
                            self.stdout.write(
                                f"{route.origin}->{route.destination} {departure_date} {trip_type}: skipped existing"
                            )
                            continue
                        self._scrape_and_store(driver, route, departure_date, return_date, trip_type, options)
                        time.sleep(options["delay"])
        finally:
            driver.quit()

    def _load_routes(self, options) -> list[Route]:
        if options["origin"] or options["destination"]:
            if not options["origin"] or not options["destination"]:
                raise CommandError("--origin and --destination must be provided together.")
            return [Route(options["origin"].upper(), options["destination"].upper())]

        if options["random_routes"]:
            rng = random.Random(options["seed"])
            if options["airport_pool"] == "major":
                airport_pool = MAJOR_INDIAN_AIRPORTS
            else:
                airport_pool = SCHEDULED_INDIAN_AIRPORTS if options["scheduled_only"] else INDIAN_AIRPORTS
            candidates = [(origin, destination) for origin in airport_pool for destination in airport_pool if origin != destination]
            rng.shuffle(candidates)
            return [Route(origin, destination) for origin, destination in candidates[: options["route_count"]]]

        if options["all_major_routes"] or options["all_indian_routes"]:
            airport_pool = SCHEDULED_INDIAN_AIRPORTS if options["all_indian_routes"] and options["scheduled_only"] else INDIAN_AIRPORTS if options["all_indian_routes"] else MAJOR_INDIAN_AIRPORTS
            return [Route(origin, destination) for origin in airport_pool for destination in airport_pool if origin != destination]

        path = Path(options["routes"])
        if not path.exists():
            raise CommandError(f"Routes CSV not found: {path}")

        routes: list[Route] = []
        with path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                origin = (row.get("origin") or "").strip().upper()
                destination = (row.get("destination") or "").strip().upper()
                if origin and destination and origin != destination:
                    routes.append(Route(origin, destination))

        if not routes:
            raise CommandError(f"No valid routes found in {path}")
        return routes

    def _parse_start_date(self, raw_value: str | None) -> date:
        if not raw_value:
            return date.today()
        try:
            return datetime.strptime(raw_value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise CommandError("--start-date must use YYYY-MM-DD format.") from exc

    def _build_departure_dates(self, start_date: date, options) -> list[date]:
        if options["end_date"]:
            try:
                end_date = datetime.strptime(options["end_date"], "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("--end-date must use YYYY-MM-DD format.") from exc
            if end_date < start_date:
                raise CommandError("--end-date must be on or after --start-date.")
            dates = [start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)]
        else:
            dates = [start_date + timedelta(days=offset) for offset in range(options["days"])]

        if options["limit_days"]:
            return dates[: options["limit_days"]]
        return dates

    def _build_driver(self, headless: bool, timeout: int):
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.page_load_strategy = "eager"
        chrome_options.add_argument("--window-size=1440,1200")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )

        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(timeout)
        return driver

    def _scrape_and_store(self, driver, route: Route, departure_date: date, return_date: date | None, trip_type: str, options):
        search_url = self._build_search_url(route, departure_date, return_date, trip_type, options)
        suffix = f" return {return_date}" if return_date else ""
        self.stdout.write(f"{route.origin}->{route.destination} {departure_date}{suffix} {trip_type}: loading")

        try:
            offers = self._scrape_search(driver, search_url, options["page_timeout"])
            if trip_type == "round_trip" and not offers and return_date:
                offers = self._scrape_round_trip_as_two_one_way_legs(driver, route, departure_date, return_date, options)
        except Exception as exc:
            self._save_search(route, departure_date, return_date, trip_type, search_url, "failed", [], str(exc))
            self.stderr.write(f"{route.origin}->{route.destination} {departure_date} {trip_type}: failed: {exc}")
            return

        offers = self._dedupe_offers(offers)
        status = "success" if offers else "no_results"
        self._save_search(route, departure_date, return_date, trip_type, search_url, status, offers, "")
        self.stdout.write(f"{route.origin}->{route.destination} {departure_date} {trip_type}: saved {len(offers)} offer(s)")

    def _build_search_url(self, route: Route, departure_date: date, return_date: date | None, trip_type: str, options) -> str:
        params = {
            "type": "R" if trip_type == "round_trip" else "O",
            "viewName": "normal",
            "flexi": "0",
            "noOfSegments": "2" if trip_type == "round_trip" else "1",
            "origin": route.origin,
            "originCountry": "IN",
            "destination": route.destination,
            "destinationCountry": "IN",
            "flight_depart_date": departure_date.strftime("%d/%m/%Y"),
            "ADT": str(options["adults"]),
            "CHD": str(options["children"]),
            "INF": str(options["infants"]),
            "class": options["cabin_class"],
            "source": "fresco-home",
        }
        if return_date:
            params["flight_return_date"] = return_date.strftime("%d/%m/%Y")
        return f"{YATRA_TRIGGER_URL}?{urlencode(params)}"

    def _scrape_round_trip_as_two_one_way_legs(self, driver, route: Route, departure_date: date, return_date: date, options):
        outbound_url = self._build_search_url(route, departure_date, None, "one_way", options)
        return_route = Route(route.destination, route.origin)
        inbound_url = self._build_search_url(return_route, return_date, None, "one_way", options)

        self.stdout.write(
            f"{route.origin}->{route.destination} {departure_date} round_trip: "
            "direct page empty, scraping outbound/inbound one-way legs"
        )
        outbound = self._scrape_search(driver, outbound_url, options["page_timeout"])
        for offer in outbound:
            offer.origin = route.origin
            offer.destination = route.destination
            offer.departure_date = departure_date
            offer.raw_payload = {**(offer.raw_payload or {}), "round_trip_leg": "outbound", "leg_search_url": outbound_url}

        inbound = self._scrape_search(driver, inbound_url, options["page_timeout"])
        for offer in inbound:
            offer.origin = route.destination
            offer.destination = route.origin
            offer.departure_date = return_date
            offer.raw_payload = {**(offer.raw_payload or {}), "round_trip_leg": "return", "leg_search_url": inbound_url}

        return outbound + inbound

    def _scrape_search(self, driver, search_url: str, timeout: int) -> list[ExtractedOffer]:
        try:
            driver.get(search_url)
        except TimeoutException:
            driver.execute_script("window.stop();")

        wait = WebDriverWait(driver, timeout)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        self._close_overlays(driver)
        self._wait_for_results_or_empty_state(driver, timeout)
        self._scroll_results(driver)

        cards = self._find_result_cards(driver)
        if cards:
            return [offer for card in cards if (offer := self._extract_offer_from_card(card))]

        return self._extract_offers_from_page_text(driver.find_element(By.TAG_NAME, "body").text)

    def _close_overlays(self, driver):
        selectors = [
            "button[aria-label='Close']",
            ".close",
            ".closeIcon",
            ".ytfi-close",
            "[class*='close']",
        ]
        for selector in selectors:
            for element in driver.find_elements(By.CSS_SELECTOR, selector)[:3]:
                try:
                    if element.is_displayed():
                        element.click()
                        time.sleep(0.3)
                except WebDriverException:
                    continue

    def _wait_for_results_or_empty_state(self, driver, timeout: int):
        markers = [
            ".flightItem",
            ".flight-det",
            ".result-set",
            "[class*='flight']",
            "[class*='Flight']",
            "text/No flights",
        ]
        end = time.time() + timeout
        while time.time() < end:
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if "no flight" in body_text or "no result" in body_text:
                return
            if "view fares" in body_text and re.search(r"\b(indigo|air india|vistara|spicejet|akasa)\b", body_text):
                return
            for selector in markers[:-1]:
                if driver.find_elements(By.CSS_SELECTOR, selector):
                    return
            time.sleep(1)

    def _scroll_results(self, driver):
        last_height = 0
        for _ in range(8):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.8)
            height = driver.execute_script("return document.body.scrollHeight")
            if height == last_height:
                break
            last_height = height

    def _find_result_cards(self, driver):
        selectors = [
            ".flightItem",
            ".flight-det",
            ".result-set",
            ".flight-card",
            "[class*='flightItem']",
            "[class*='FlightCard']",
            "[class*='flight-card']",
            "[class*='result'] [class*='flight']",
        ]
        seen = set()
        cards = []
        for selector in selectors:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                try:
                    element_id = element.id
                    text = element.text.strip()
                    if element_id in seen or len(text) < 20:
                        continue
                    if self._extract_price_from_lines(text.splitlines()) is None:
                        continue
                except StaleElementReferenceException:
                    continue
                seen.add(element_id)
                cards.append(element)
        return cards

    def _extract_offer_from_card(self, card) -> ExtractedOffer | None:
        try:
            text = card.text.strip()
        except StaleElementReferenceException:
            return None
        return self._extract_offer_from_text(text)

    def _extract_offer_from_text(self, text: str) -> ExtractedOffer | None:
        price = self._extract_price(text)
        if price is None:
            return None
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        price = self._extract_price_from_lines(lines)
        if price is None:
            return None

        airline = self._first_matching_line(lines, [r"air\s?india", r"indigo", r"vistara", r"akasa", r"spicejet", r"alliance"])
        flight_number = self._first_regex(text, r"\b([A-Z0-9]{2}\s?-?\s?\d{2,4})\b")
        times = re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
        time_values = [f"{hour.zfill(2)}:{minute}" for hour, minute in times]

        return ExtractedOffer(
            airline=airline,
            flight_number=flight_number,
            departure_time=time_values[0] if time_values else "",
            arrival_time=time_values[1] if len(time_values) > 1 else "",
            duration=self._first_regex(text, r"\b(\d+h\s?\d*m?|\d+\s?hr\s?\d*\s?min)\b", flags=re.IGNORECASE),
            stops=self._first_regex(text, r"\b(non[- ]?stop|\d+\s+stop[s]?)\b", flags=re.IGNORECASE),
            price_amount=price,
            currency="INR",
            raw_text=text,
            raw_payload={"lines": lines},
        )

    def _extract_offers_from_page_text(self, text: str) -> list[ExtractedOffer]:
        offers = []
        chunks = re.split(r"\n(?=(?:Air India|IndiGo|Vistara|Akasa|SpiceJet|Alliance|[A-Z0-9]{2}\s?-?\s?\d{2,4}))", text)
        for chunk in chunks:
            price = self._extract_price_from_lines(chunk.splitlines())
            if price is None:
                continue
            offer = ExtractedOffer(
                airline=self._first_matching_line(chunk.splitlines(), [r"air\s?india", r"indigo", r"vistara", r"akasa", r"spicejet", r"alliance"]),
                flight_number=self._first_regex(chunk, r"\b([A-Z0-9]{2}\s?-?\s?\d{2,4})\b"),
                price_amount=price,
                raw_text=chunk.strip(),
                raw_payload={"fallback": "page_text"},
            )
            if offer.raw_text:
                offers.append(offer)
        return offers

    def _extract_price(self, text: str) -> Decimal | None:
        matches = re.findall(r"(?:₹|Rs\.?|INR)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", text, flags=re.IGNORECASE)
        if not matches:
            matches = re.findall(r"\b([0-9]{1,3}(?:,[0-9]{3})+(?:\.\d{1,2})?)\b", text)
        if not matches:
            return None
        try:
            return Decimal(matches[-1].replace(",", ""))
        except InvalidOperation:
            return None

    def _extract_price_from_lines(self, lines) -> Decimal | None:
        clean_lines = [line.strip() for line in lines if line and line.strip()]

        for index, line in enumerate(clean_lines):
            if "view fares" not in line.lower():
                continue
            for candidate in reversed(clean_lines[max(0, index - 5):index]):
                price = self._extract_fare_candidate(candidate)
                if price is not None:
                    return price

        for line in reversed(clean_lines):
            price = self._extract_fare_candidate(line)
            if price is not None:
                return price

        return self._extract_price("\n".join(clean_lines))

    def _extract_fare_candidate(self, text: str) -> Decimal | None:
        lowered = text.lower()
        blocked_terms = [" off", "code", "rbl", "freefly", "ecash", "co2", "emissions", "cashback"]
        if any(term in lowered for term in blocked_terms):
            return None

        matches = re.findall(r"(?:₹|rs\.?|inr)?\s*(?:[a-z ]*?at)?\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.\d{1,2})?)", text, flags=re.IGNORECASE)
        if not matches:
            return None
        try:
            return Decimal(matches[-1].replace(",", ""))
        except InvalidOperation:
            return None

    def _first_matching_line(self, lines, patterns) -> str:
        for line in lines:
            for pattern in patterns:
                if re.search(pattern, line, flags=re.IGNORECASE):
                    return line[:120]
        return ""

    def _first_regex(self, text: str, pattern: str, flags=0) -> str:
        match = re.search(pattern, text, flags=flags)
        return match.group(1).strip() if match else ""

    @transaction.atomic
    def _save_search(
        self,
        route: Route,
        departure_date: date,
        return_date: date | None,
        trip_type: str,
        search_url: str,
        status: str,
        offers: list[ExtractedOffer],
        error: str,
    ):
        search = FlightSearch.objects.create(
            origin=route.origin,
            destination=route.destination,
            departure_date=departure_date,
            return_date=return_date,
            trip_type=trip_type,
            status=status,
            offers_found=len(offers),
            error_message=error[:2000],
            search_url=search_url,
        )
        FlightOffer.objects.bulk_create(
            [
                FlightOffer(
                    search=search,
                    origin=offer.origin or route.origin,
                    destination=offer.destination or route.destination,
                    departure_date=offer.departure_date or departure_date,
                    return_date=return_date,
                    trip_type=trip_type,
                    airline=offer.airline,
                    flight_number=offer.flight_number,
                    departure_time=offer.departure_time,
                    arrival_time=offer.arrival_time,
                    duration=offer.duration,
                    stops=offer.stops,
                    price_amount=offer.price_amount,
                    currency=offer.currency,
                    raw_text=offer.raw_text,
                    raw_payload=offer.raw_payload or {},
                )
                for offer in offers
            ],
            batch_size=500,
        )

    def _dedupe_offers(self, offers: list[ExtractedOffer]) -> list[ExtractedOffer]:
        seen = set()
        unique_offers = []
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
            unique_offers.append(offer)
        return unique_offers
