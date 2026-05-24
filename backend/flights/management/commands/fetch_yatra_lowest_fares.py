import asyncio
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from django.core.management.base import BaseCommand
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


class Command(BaseCommand):
    help = "Bootstrap one Yatra browser session, then fetch lowest-fare network endpoint for a date range."

    def add_arguments(self, parser):
        parser.add_argument("--origin", required=True)
        parser.add_argument("--destination", required=True)
        parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
        parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
        parser.add_argument("--include-return", action="store_true")
        parser.add_argument("--headful", action="store_true")
        parser.add_argument("--output", default="logs/yatra_lowest_fares_blr_ccu_month.json")
        parser.add_argument("--page-timeout", type=int, default=35)

    def handle(self, *args, **options):
        asyncio.run(self._handle_async(options))

    async def _handle_async(self, options):
        origin = options["origin"].upper()
        destination = options["destination"].upper()
        start_date = self._parse_date(options["start_date"])
        end_date = self._parse_date(options["end_date"])

        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)

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

            await self._bootstrap_session(page, origin, destination, start_date, options)

            results = {
                "origin": origin,
                "destination": destination,
                "start_date": options["start_date"],
                "end_date": options["end_date"],
                "requests": [],
            }
            results["requests"].append(await self._fetch_lowest_fares(page, origin, destination, start_date, end_date))
            if options["include_return"]:
                results["requests"].append(await self._fetch_lowest_fares(page, destination, origin, start_date, end_date))

            output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
            self.stdout.write(f"Wrote {output}")
            for item in results["requests"]:
                days = len((item.get("json") or {}).get("day", {}))
                self.stdout.write(f"{item['origin']}->{item['destination']}: status={item['status']} days={days} url={item['url']}")

            await context.close()
            await browser.close()

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
            "text_snippet": payload["text"][:5000],
        }

    def _parse_date(self, value):
        return datetime.strptime(value, "%Y-%m-%d").date()
