import json
from pathlib import Path

from playwright.sync_api import sync_playwright


LOG_PATH = Path("logs/vakatrip_network_capture_blr_ccu.jsonl")


def main():
    LOG_PATH.parent.mkdir(exist_ok=True)
    captured = []

    def keep_request(request):
        url = request.url
        return "pro.vakatrip.com/api" in url

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1000},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124 Safari/537.36"
            ),
        )

        def on_response(response):
            request = response.request
            if not keep_request(request):
                return
            try:
                body = response.text()
            except Exception as exc:
                body = f"<body read failed: {exc}>"
            captured.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "post_data": request.post_data,
                    "status": response.status,
                    "response": body[:20000],
                }
            )

        page.on("response", on_response)
        page.goto("https://www.vakatrip.com", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)

        from_input = page.locator('input[placeholder="From"]').first
        to_input = page.locator('input[placeholder="To"]').first
        from_input.click()
        from_input.fill("BLR")
        page.wait_for_timeout(1500)
        page.locator(".el-autocomplete-suggestion li").first.click(timeout=10000)

        to_input.click()
        to_input.fill("CCU")
        page.wait_for_timeout(1500)
        page.locator(".el-autocomplete-suggestion li").first.click(timeout=10000)

        # Keep the site defaults for dates: 2026-05-23 outbound and 2026-05-29 return.
        page.get_by_text("Search", exact=True).click(timeout=10000)
        page.wait_for_timeout(25000)

        browser.close()

    with LOG_PATH.open("w", encoding="utf-8") as fh:
        for item in captured:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"captured={len(captured)} log={LOG_PATH}")
    for item in captured:
        print(json.dumps({k: item[k] for k in ("method", "url", "status", "post_data")}, ensure_ascii=False)[:4000])
        print((item.get("response") or "")[:2000])


if __name__ == "__main__":
    main()
