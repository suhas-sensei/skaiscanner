import asyncio
import json
from datetime import timedelta
from pathlib import Path

from django.core.management.base import CommandError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from flights.management.commands.scrape_yatra import Command as ScrapeCommand
from flights.management.commands.scrape_yatra import Route


KEYWORDS = (
    "flight",
    "fare",
    "price",
    "itinerary",
    "itineraries",
    "segment",
    "airline",
    "search",
    "availability",
)


class Command(ScrapeCommand):
    help = "Capture Yatra network requests/responses for reverse-engineering flight data APIs."

    def add_arguments(self, parser):
        parser.add_argument("--origin", required=True, help="Origin IATA code, e.g. BLR.")
        parser.add_argument("--destination", required=True, help="Destination IATA code, e.g. CCU.")
        parser.add_argument("--start-date", required=True, help="YYYY-MM-DD.")
        parser.add_argument("--end-date", required=True, help="YYYY-MM-DD inclusive.")
        parser.add_argument(
            "--trip-types",
            nargs="+",
            choices=["one_way", "round_trip"],
            default=["one_way", "round_trip"],
        )
        parser.add_argument("--return-after-days", type=int, default=7)
        parser.add_argument("--adults", type=int, default=1)
        parser.add_argument("--children", type=int, default=0)
        parser.add_argument("--infants", type=int, default=0)
        parser.add_argument("--cabin-class", default="Economy")
        parser.add_argument("--headful", action="store_true")
        parser.add_argument("--page-timeout", type=int, default=25)
        parser.add_argument("--settle-seconds", type=int, default=25)
        parser.add_argument("--output", default="logs/yatra_network_blr_ccu_2026_05_22_to_2026_06_22.jsonl")
        parser.add_argument("--body-limit", type=int, default=20000)

    def handle(self, *args, **options):
        asyncio.run(self._handle_async(options))

    async def _handle_async(self, options):
        route = Route(options["origin"].upper(), options["destination"].upper())
        start_date = self._parse_start_date(options["start_date"])
        dates = self._build_departure_dates(start_date, options)
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)

        jobs = []
        for departure_date in dates:
            for trip_type in options["trip_types"]:
                return_date = departure_date + timedelta(days=options["return_after_days"]) if trip_type == "round_trip" else None
                jobs.append((route, departure_date, return_date, trip_type))
                if trip_type == "round_trip":
                    jobs.append((Route(route.destination, route.origin), return_date, None, "return_leg"))

        self.stdout.write(f"Capturing {len(jobs)} network page loads into {output}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=not options["headful"],
                executable_path="/usr/bin/google-chrome",
                args=[
                    "--disable-dev-shm-usage",
                    "--disable-notifications",
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
            await context.route("**/*", lambda r: asyncio.create_task(self._route_request(r)))
            page = await context.new_page()
            page.set_default_timeout(options["page_timeout"] * 1000)

            with output.open("a", encoding="utf-8") as file:
                for index, (job_route, departure_date, return_date, trip_type) in enumerate(jobs, start=1):
                    url_trip_type = "one_way" if trip_type == "return_leg" else trip_type
                    search_url = self._build_search_url(job_route, departure_date, return_date, url_trip_type, options)
                    self.stdout.write(f"[{index}/{len(jobs)}] {job_route.origin}->{job_route.destination} {departure_date} {trip_type}")
                    await self._capture_page(page, file, job_route, departure_date, return_date, trip_type, search_url, options)

            await context.close()
            await browser.close()

    async def _route_request(self, route):
        if route.request.resource_type in {"image", "font", "media"}:
            await route.abort()
        else:
            await route.continue_()

    async def _capture_page(self, page, file, route, departure_date, return_date, trip_type, search_url, options):
        responses = []

        async def on_response(response):
            request = response.request
            if request.resource_type not in {"xhr", "fetch", "document"}:
                return
            content_type = response.headers.get("content-type", "")
            record = {
                "origin": route.origin,
                "destination": route.destination,
                "departure_date": departure_date.isoformat(),
                "return_date": return_date.isoformat() if return_date else None,
                "trip_type": trip_type,
                "request_method": request.method,
                "request_url": request.url,
                "request_resource_type": request.resource_type,
                "request_post_data": self._safe_post_data(request),
                "response_status": response.status,
                "response_content_type": content_type,
                "response_headers": dict(response.headers),
                "source_search_url": search_url,
            }
            if self._is_interesting_url(request.url) or self._is_interesting_content_type(content_type):
                try:
                    body = await response.text()
                except Exception as exc:
                    body = f"<body read failed: {exc}>"
                record["body_snippet"] = body[: options["body_limit"]]
                record["candidate"] = self._is_candidate(request.url, body, content_type)
            else:
                record["candidate"] = self._is_interesting_url(request.url)
            responses.append(record)

        page.on("response", on_response)
        try:
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=options["page_timeout"] * 1000)
            except PlaywrightTimeoutError:
                pass
            await self._wait_for_result_or_challenge(page, options["settle_seconds"])
            await page.wait_for_timeout(options["settle_seconds"] * 1000)
            await page.evaluate("() => { if (document.body) window.scrollTo(0, document.body.scrollHeight); }")
            await page.wait_for_timeout(2000)
        finally:
            page.remove_listener("response", on_response)

        for record in responses:
            file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        file.flush()

    def _is_interesting_url(self, url):
        lowered = url.lower()
        return any(keyword in lowered for keyword in KEYWORDS)

    def _is_interesting_content_type(self, content_type):
        lowered = content_type.lower()
        return "json" in lowered or "text" in lowered or "javascript" in lowered

    def _is_candidate(self, url, body, content_type):
        lowered = f"{url}\n{content_type}\n{body[:5000]}".lower()
        return any(keyword in lowered for keyword in KEYWORDS) and any(token in lowered for token in ("₹", "rs.", "price", "fare", "flight", "airline"))

    def _safe_post_data(self, request):
        try:
            return request.post_data
        except UnicodeDecodeError:
            return "<binary post body>"
        except Exception as exc:
            return f"<post body read failed: {exc}>"

    async def _wait_for_result_or_challenge(self, page, timeout):
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            try:
                body = (await page.locator("body").inner_text(timeout=3000)).lower()
            except Exception:
                body = ""
            if "view fares" in body or "no flight" in body or "no result" in body:
                return
            await page.wait_for_timeout(1000)

    def _build_departure_dates(self, start_date, options):
        if not options["end_date"]:
            raise CommandError("--end-date is required")
        options.setdefault("limit_days", None)
        return super()._build_departure_dates(start_date, options)
