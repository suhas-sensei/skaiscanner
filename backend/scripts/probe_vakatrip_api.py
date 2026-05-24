import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import date, timedelta


API_BASE = "https://pro.vakatrip.com/api"
SIGNING_SALT = "signature.vakatrip.com.cn.org"


def js_stringify(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def sign_payload(payload):
    parts = []
    for key in sorted(payload):
        value = payload[key]
        if isinstance(value, (dict, list)):
            rendered = js_stringify(value) if value else ""
        else:
            rendered = "" if value is None else str(value)
        parts.append(f"{key}={rendered}")
    base = "&".join(parts) + SIGNING_SALT
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def with_common_fields(payload, endpoint):
    data = dict(payload)
    data["timestamp"] = int(time.time() * 1000)
    data["channel_key"] = "365|letsflyhk-vakatrip_cnl-all"
    data["meta_click_id"] = ""
    data["language"] = data.get("language") or "en"
    data["referer"] = ""
    data["quote_id"] = ""
    data["device_type"] = 1
    data["qs"] = 0
    data["ref"] = ""
    if "MetaSearchBooking" not in endpoint and "LowFareSearch" not in endpoint:
        data["abTest"] = 0
    if not data.get("globalSearchId") and not data.get("product_origin"):
        data["globalSearchId"] = ""
        data["product_origin"] = 3
    data["signature"] = sign_payload(data)
    return data


def post(endpoint, payload):
    data = with_common_fields(payload, endpoint)
    body = js_stringify(data).encode("utf-8")
    request = urllib.request.Request(
        API_BASE + endpoint,
        data=body,
        method="POST",
        headers={
            "content-type": "application/json;charset=UTF-8",
            "origin": "https://www.vakatrip.com",
            "referer": "https://www.vakatrip.com/",
            "user-agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124 Safari/537.36"
            ),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def city_search(code):
    return post(
        "/v1/CitySearch",
        {
            "lang": "en",
            "country_code": "IN",
            "word": code,
            "product_origin": 6,
        },
    )


def low_fare_search(origin, destination, depart, return_date=None):
    payload = {
        "searchId": "",
        "timeout": 5,
        "departuretime": depart.strftime("%Y%m%d"),
        "departuretime_format": None,
        "returntime": return_date.strftime("%Y%m%d") if return_date else None,
        "returntime_format": None,
        "adults": 1,
        "children": 0,
        "cabinClass": "Y",
        "onewayName": f"{origin}({origin})",
        "returnName": f"{destination}({destination})",
        "fromCityName": origin,
        "fromAirportName": origin,
        "returnCityName": destination,
        "returnAirportName": destination,
        "fromCityCode": origin,
        "returnCityCode": destination,
        "fromAirportCode": origin,
        "returnAirportCode": destination,
        "oneway": origin,
        "return": destination,
        "onewaytype": "airport",
        "returntype": "airport",
        "product_origin": 6,
        "currency": "INR",
    }
    return post("/v1/LowFareSearch", payload)


def main():
    for code in ("BLR", "CCU", "KOL"):
        status, raw = city_search(code)
        print(f"CITY {code} HTTP {status}")
        print(raw[:2000])
    depart = date(2026, 5, 23)
    ret = depart + timedelta(days=7)
    status, raw = low_fare_search("BLR", "CCU", depart, ret)
    print(f"LOWFARE BLR-CCU {depart} return {ret} HTTP {status}")
    print(raw[:8000])


if __name__ == "__main__":
    main()
