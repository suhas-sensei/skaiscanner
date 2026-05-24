import asyncio
import json
import random
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from flights.management.commands.scrape_yatra import INDIAN_AIRPORTS, MAJOR_INDIAN_AIRPORTS, SCHEDULED_INDIAN_AIRPORTS, Route
from flights.models import FlightOffer, FlightSearch


def yatra_search_page_url(origin, destination, departure_date):
    params = {
        "type": "O",
        "viewName": "normal",
        "flexi": "0",
        "noOfSegments": "1",
        "origin": origin,
        "originCountry": "IN",
        "destination": destination,
        "destinationCountry": "IN",
        "flight_depart_date": departure_date.strftime("%d/%m/%Y"),
        "ADT": "1",
        "CHD": "0",
        "INF": "0",
        "class": "Economy",
        "source": "fresco-home",
    }
    return "https://flight.yatra.com/air-search-ui/dom2/trigger?" + urlencode(params)


class Command(BaseCommand):
    help = "Fetch Yatra lowest-fare network endpoint in bulk and store normalized rows in PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--start-date", default="2026-05-22")
        parser.add_argument("--end-date", default="2026-06-22")
        parser.add_argument("--random-routes", action="store_true")
        parser.add_argument("--all-indian-routes", action="store_true")
        parser.add_argument("--airport-pool", choices=["major", "all"], default="all")
        parser.add_argument("--scheduled-only", action="store_true")
        parser.add_argument("--route-count", type=int, default=25)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--include-return", action="store_true", default=True)
        parser.add_argument("--headful", action="store_true")
        parser.add_argument("--page-timeout", type=int, default=35)
        parser.add_argument("--output", default="logs/yatra_lowest_fares_bulk.jsonl")
        parser.add_argument("--skip-existing", action="store_true")

    def handle(self, *args, **options):
        asyncio.run(self._handle_async(options))

    async def _handle_async(self, options):
        routes = self._build_routes(options)
        start_date = self._parse_date(options["start_date"])
        end_date = self._parse_date(options["end_date"])
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)

        self.stdout.write(
            f"Fetching lowest fares for {len(routes)} route pair(s), "
            f"{options['start_date']}..{options['end_date']}, include_return={options['include_return']}"
        )

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=not options["headful"],
                executable_path="/usr/bin/google-chrome",
                args=["--disable-dev-shm-usage", "--disable-notifications", "--no-sandbox"],
            )
            context = await browser.new_context(
                viewport={"width": 1440, "height": 1200},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            page.set_default_timeout(options["page_timeout"] * 1000)

            first = routes[0]
            await self._bootstrap_session(page, first.origin, first.destination, start_date, options)

            total_searches = 0
            total_offers = 0
            with output.open("a", encoding="utf-8") as file:
                for index, route in enumerate(routes, start=1):
                    directions = [route]
                    if options["include_return"]:
                        directions.append(Route(route.destination, route.origin))

                    for direction in directions:
                        if options["skip_existing"]:
                            exists = await sync_to_async(
                                FlightSearch.objects.filter(
                                    origin=direction.origin,
                                    destination=direction.destination,
                                    departure_date=start_date,
                                    return_date=end_date,
                                    trip_type="lowest_fare",
                                    status="success",
                                ).exists,
                                thread_sensitive=True,
                            )()
                            if exists:
                                self.stdout.write(f"[{index}/{len(routes)}] {direction.origin}->{direction.destination}: skipped")
                                continue

                        result = await self._fetch_lowest_fares(page, direction.origin, direction.destination, start_date, end_date)
                        file.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
                        file.flush()

                        saved = await sync_to_async(self._save_result, thread_sensitive=True)(direction, start_date, end_date, result)
                        total_searches += 1
                        total_offers += saved
                        days = len((result.get("json") or {}).get("day", {}))
                        self.stdout.write(
                            f"[{index}/{len(routes)}] {direction.origin}->{direction.destination}: "
                            f"status={result['status']} days={days} saved_offers={saved}"
                        )

            await context.close()
            await browser.close()

        self.stdout.write(f"Done. searches={total_searches} offers={total_offers} raw_log={output}")

    def _build_routes(self, options):
        if options["airport_pool"] == "major":
            airport_pool = MAJOR_INDIAN_AIRPORTS
        else:
            airport_pool = SCHEDULED_INDIAN_AIRPORTS if options["scheduled_only"] else INDIAN_AIRPORTS
        candidates = [Route(origin, destination) for origin in airport_pool for destination in airport_pool if origin != destination]
        if options["all_indian_routes"]:
            return candidates
        if not options["random_routes"]:
            raise CommandError("Use --random-routes or --all-indian-routes.")
        rng = random.Random(options["seed"])
        rng.shuffle(candidates)
        return candidates[: options["route_count"]]

    async def _bootstrap_session(self, page, origin, destination, start_date, options):
        params = {
            "type": "O",
            "viewName": "normal",
            "flexi": "0",
            "noOfSegments": "1",
            "origin": origin,
            "originCountry": "IN",
            "destination": destination,
            "destinationCountry": "IN",
            "flight_depart_date": start_date.strftime("%d/%m/%Y"),
            "ADT": "1",
            "CHD": "0",
            "INF": "0",
            "class": "Economy",
            "source": "fresco-home",
        }
        url = "https://flight.yatra.com/air-search-ui/dom2/trigger?" + urlencode(params)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=options["page_timeout"] * 1000)
        except PlaywrightTimeoutError:
            pass

        deadline = asyncio.get_running_loop().time() + options["page_timeout"]
        while asyncio.get_running_loop().time() < deadline:
            try:
                text = (await page.locator("body").inner_text(timeout=3000)).lower()
            except Exception:
                text = ""
            if "view fares" in text or "no flight" in text or "no result" in text:
                return
            await page.wait_for_timeout(1000)

    async def _fetch_lowest_fares(self, page, origin, destination, start_date, end_date):
        params = {
            "origin": origin,
            "destination": destination,
            "from": start_date.strftime("%d-%m-%Y"),
            "to": end_date.strftime("%d-%m-%Y"),
            "tripType": "O",
            "airlines": "all",
            "_i": str(int(datetime.now().timestamp() * 1000)),
            "src": "srp",
        }
        url = "https://flight.yatra.com/lowest-fare-service/dom2/get-fare?" + urlencode(params)
        payload = await page.evaluate(
            """async (url) => {
                const response = await fetch(url, { credentials: 'include' });
                const text = await response.text();
                return { status: response.status, contentType: response.headers.get('content-type'), text };
            }""",
            url,
        )
        parsed = None
        try:
            parsed = json.loads(payload["text"])
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
        except Exception:
            parsed = None
        return {
            "origin": origin,
            "destination": destination,
            "url": url,
            "status": payload["status"],
            "content_type": payload["contentType"],
            "json": parsed,
            "text_snippet": payload["text"][:2000],
        }

    @transaction.atomic
    def _save_result(self, route, start_date, end_date, result):
        payload = result.get("json") or {}
        days = payload.get("day") or {}
        status = "success" if result["status"] == 200 and days else "no_results"
        search = FlightSearch.objects.create(
            origin=route.origin,
            destination=route.destination,
            departure_date=start_date,
            return_date=end_date,
            trip_type="lowest_fare",
            status=status,
            offers_found=0,
            search_url=result["url"],
            error_message="" if status == "success" else result.get("text_snippet", "")[:2000],
        )

        offers = []
        for day, day_payload in sorted(days.items()):
            date_value = self._parse_date(day)
            for airline_code, fare in (day_payload.get("af") or {}).items():
                legs = fare.get("ow") or []
                first_leg = legs[0] if legs else {}
                last_leg = legs[-1] if legs else {}
                price = self._decimal(fare.get("tf") or fare.get("lf") or fare.get("bf"))
                offers.append(
                    FlightOffer(
                        search=search,
                        source="yatra_lowest_fare",
                        origin=route.origin,
                        destination=route.destination,
                        departure_date=date_value,
                        return_date=end_date,
                        trip_type="lowest_fare",
                        airline=first_leg.get("an") or airline_code,
                        flight_number="/".join(str(leg.get("ac", "")) + "-" + str(leg.get("fl", "")) for leg in legs).strip("/"),
                        departure_time=(first_leg.get("ddt") or "")[-5:],
                        arrival_time=(last_leg.get("adt") or "")[-5:],
                        duration="",
                        stops="Non Stop" if len(legs) == 1 else f"{max(len(legs) - 1, 0)} Stop",
                        price_amount=price,
                        currency="INR",
                        provider_offer_url="",
                        provider_search_url=yatra_search_page_url(route.origin, route.destination, date_value),
                        provider_link_status="search_page",
                        provider_offer_key=f"yatra:{route.origin}:{route.destination}:{date_value}:{airline_code}:{price or ''}",
                        raw_text="",
                        raw_payload={"date": day, "airline_code": airline_code, "fare": fare, "lowest_fare": day_payload.get("lf")},
                    )
                )

        FlightOffer.objects.bulk_create(offers, batch_size=500)
        search.offers_found = len(offers)
        search.save(update_fields=["offers_found"])
        return len(offers)

    def _parse_date(self, value):
        return datetime.strptime(value, "%Y-%m-%d").date()

    def _decimal(self, value):
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
