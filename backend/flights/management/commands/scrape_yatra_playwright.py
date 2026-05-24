import asyncio
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.core.management.base import CommandError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from flights.management.commands.scrape_yatra import Command as SeleniumScrapeCommand
from flights.management.commands.scrape_yatra import Route
from flights.models import FlightSearch


class Command(SeleniumScrapeCommand):
    help = "Scrape Yatra flight prices into PostgreSQL with parallel Playwright browsers."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--concurrency", type=int, default=10, help="Number of parallel browser instances.")
        parser.add_argument("--chrome-path", default="/usr/bin/google-chrome", help="Chrome/Chromium executable path.")
        parser.add_argument("--progress-every", type=int, default=25, help="Print progress every N completed jobs.")
        parser.add_argument("--retries", type=int, default=2, help="Retries per route/date/trip job after transient browser failures.")

    def handle(self, *args, **options):
        if options["concurrency"] < 1:
            raise CommandError("--concurrency must be >= 1")
        asyncio.run(self._handle_async(options))

    async def _handle_async(self, options):
        routes = self._load_routes(options)
        if options["limit_routes"]:
            routes = routes[: options["limit_routes"]]

        start_date = self._parse_start_date(options["start_date"])
        departure_dates = self._build_departure_dates(start_date, options)
        jobs = self._build_jobs(routes, departure_dates, options)

        self.stdout.write(
            f"Playwright scrape: {len(routes)} route(s), {len(departure_dates)} date(s), "
            f"{len(jobs)} route/date/trip job(s), concurrency={options['concurrency']}."
        )

        queue = asyncio.Queue()
        for job in jobs:
            await queue.put(job)

        stats = {"done": 0, "saved_offers": 0, "failed": 0, "skipped": 0}
        lock = asyncio.Lock()

        async with async_playwright() as p:
            workers = [
                asyncio.create_task(self._worker(worker_id, p, queue, options, stats, lock))
                for worker_id in range(options["concurrency"])
            ]
            await queue.join()
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        self.stdout.write(
            f"Done. jobs={stats['done']} skipped={stats['skipped']} "
            f"failed={stats['failed']} saved_offers={stats['saved_offers']}"
        )

    def _build_jobs(self, routes, departure_dates, options):
        jobs = []
        for route in routes:
            for departure_date in departure_dates:
                for trip_type in options["trip_types"]:
                    return_date = departure_date + timedelta(days=options["return_after_days"]) if trip_type == "round_trip" else None
                    jobs.append((route, departure_date, return_date, trip_type))
        return jobs

    async def _worker(self, worker_id, playwright, queue, options, stats, lock):
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
        await context.route(
            "**/*",
            lambda route: asyncio.create_task(self._route_request(route)),
        )
        page = await context.new_page()
        page.set_default_timeout(options["page_timeout"] * 1000)

        try:
            while True:
                route, departure_date, return_date, trip_type = await queue.get()
                try:
                    skipped = await self._maybe_skip_existing(route, departure_date, return_date, trip_type, options)
                    if skipped:
                        await self._mark_progress(stats, lock, options, skipped=True)
                        continue

                    offers = await self._scrape_job_with_retries(page, route, departure_date, return_date, trip_type, options)
                    offers = self._dedupe_offers(offers)
                    search_url = self._build_search_url(route, departure_date, return_date, trip_type, options)
                    status = "success" if offers else "no_results"
                    await sync_to_async(self._save_search, thread_sensitive=True)(
                        route, departure_date, return_date, trip_type, search_url, status, offers, ""
                    )
                    await self._mark_progress(stats, lock, options, saved_offers=len(offers))
                    self.stdout.write(
                        f"[w{worker_id}] {route.origin}->{route.destination} {departure_date} "
                        f"{trip_type}: saved {len(offers)}"
                    )
                except Exception as exc:
                    search_url = self._build_search_url(route, departure_date, return_date, trip_type, options)
                    await sync_to_async(self._save_search, thread_sensitive=True)(
                        route, departure_date, return_date, trip_type, search_url, "failed", [], str(exc)
                    )
                    await self._mark_progress(stats, lock, options, failed=True)
                    self.stderr.write(
                        f"[w{worker_id}] {route.origin}->{route.destination} {departure_date} {trip_type}: failed: {exc}"
                    )
                finally:
                    queue.task_done()
        finally:
            await context.close()
            await browser.close()

    async def _route_request(self, route):
        if route.request.resource_type in {"image", "font", "media"}:
            await route.abort()
        else:
            await route.continue_()

    async def _maybe_skip_existing(self, route, departure_date, return_date, trip_type, options):
        if not options["skip_existing"]:
            return False
        return await sync_to_async(
            FlightSearch.objects.filter(
                origin=route.origin,
                destination=route.destination,
                departure_date=departure_date,
                return_date=return_date,
                trip_type=trip_type,
                status="success",
            ).exists,
            thread_sensitive=True,
        )()

    async def _scrape_job(self, page, route: Route, departure_date, return_date, trip_type, options):
        search_url = self._build_search_url(route, departure_date, return_date, trip_type, options)
        offers = await self._scrape_search_playwright(page, search_url, options["page_timeout"])
        if trip_type == "round_trip" and not offers and return_date:
            outbound_url = self._build_search_url(route, departure_date, None, "one_way", options)
            inbound_route = Route(route.destination, route.origin)
            inbound_url = self._build_search_url(inbound_route, return_date, None, "one_way", options)

            outbound = await self._scrape_search_playwright(page, outbound_url, options["page_timeout"])
            for offer in outbound:
                offer.origin = route.origin
                offer.destination = route.destination
                offer.departure_date = departure_date
                offer.raw_payload = {**(offer.raw_payload or {}), "round_trip_leg": "outbound", "leg_search_url": outbound_url}

            inbound = await self._scrape_search_playwright(page, inbound_url, options["page_timeout"])
            for offer in inbound:
                offer.origin = route.destination
                offer.destination = route.origin
                offer.departure_date = return_date
                offer.raw_payload = {**(offer.raw_payload or {}), "round_trip_leg": "return", "leg_search_url": inbound_url}

            return outbound + inbound
        return offers

    async def _scrape_job_with_retries(self, page, route, departure_date, return_date, trip_type, options):
        last_error = None
        for attempt in range(options["retries"] + 1):
            try:
                return await self._scrape_job(page, route, departure_date, return_date, trip_type, options)
            except Exception as exc:
                last_error = exc
                if attempt >= options["retries"]:
                    break
                await page.wait_for_timeout(1000 * (attempt + 1))
        raise last_error

    async def _scrape_search_playwright(self, page, search_url, timeout):
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=timeout * 1000)
        except PlaywrightTimeoutError:
            pass

        await self._wait_for_results_playwright(page, timeout)
        await self._scroll_playwright(page)

        texts = await self._candidate_texts(page)
        offers = []
        for text in texts:
            offer = self._extract_offer_from_text(text)
            if offer:
                offers.append(offer)

        if offers:
            return offers

        body_text = await page.locator("body").inner_text(timeout=5000)
        return self._extract_offers_from_page_text(body_text)

    async def _wait_for_results_playwright(self, page, timeout):
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            try:
                body_text = (await page.locator("body").inner_text(timeout=3000)).lower()
            except PlaywrightTimeoutError:
                body_text = ""
            if "no flight" in body_text or "no result" in body_text:
                return
            if "view fares" in body_text and self._contains_airline(body_text):
                return
            await asyncio.sleep(1)

    async def _scroll_playwright(self, page):
        last_height = 0
        for _ in range(6):
            await page.evaluate("() => { if (document.body) window.scrollTo(0, document.body.scrollHeight); }")
            await page.wait_for_timeout(500)
            height = await page.evaluate("() => document.body ? document.body.scrollHeight : 0")
            if height == last_height:
                break
            last_height = height

    async def _candidate_texts(self, page):
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
        texts = []
        for selector in selectors:
            locator = page.locator(selector)
            count = await locator.count()
            for index in range(min(count, 250)):
                try:
                    text = (await locator.nth(index).inner_text(timeout=1000)).strip()
                except PlaywrightTimeoutError:
                    continue
                if len(text) < 20 or text in seen:
                    continue
                if self._extract_price_from_lines(text.splitlines()) is None:
                    continue
                seen.add(text)
                texts.append(text)
        return texts

    def _contains_airline(self, text):
        return bool(self._first_matching_line([text], [r"air\s?india", r"indigo", r"vistara", r"akasa", r"spicejet", r"alliance"]))

    async def _mark_progress(self, stats, lock, options, saved_offers=0, failed=False, skipped=False):
        async with lock:
            stats["done"] += 1
            stats["saved_offers"] += saved_offers
            if failed:
                stats["failed"] += 1
            if skipped:
                stats["skipped"] += 1
            if stats["done"] % options["progress_every"] == 0:
                self.stdout.write(
                    f"progress jobs={stats['done']} skipped={stats['skipped']} "
                    f"failed={stats['failed']} saved_offers={stats['saved_offers']}"
                )
