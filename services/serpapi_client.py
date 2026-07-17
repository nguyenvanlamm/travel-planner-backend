import os
import time
import re
import unicodedata
import httpx
from dotenv import load_dotenv
from math import radians, sin, cos, sqrt, atan2

load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
BASE_URL = "https://serpapi.com/search.json"
LOCATION_URL = "https://serpapi.com/locations.json"

_cache = {}
CACHE_TTL = 7200


def _cache_key(*args):
    return ":".join(str(a) for a in args)


def _get_cache(key: str):
    item = _cache.get(key)
    if item and item["expires"] > time.time():
        return item["data"]
    return None


def _set_cache(key: str, data, ttl: int = CACHE_TTL):
    _cache[key] = {"data": data, "expires": time.time() + ttl}


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


_CITY_ALIASES = {
    "hà nội": "Hanoi",
    "ha noi": "Hanoi",
    "hanoi": "Hanoi",
    "tp. hồ chí minh": "Ho Chi Minh",
    "tp hồ chí minh": "Ho Chi Minh",
    "tp. ho chi minh": "Ho Chi Minh",
    "tp ho chi minh": "Ho Chi Minh",
    "hồ chí minh": "Ho Chi Minh",
    "ho chi minh": "Ho Chi Minh",
    "saigon": "Ho Chi Minh",
    "sài gòn": "Ho Chi Minh",
    "đà nẵng": "Da Nang",
    "da nang": "Da Nang",
}


def geocode(location: str) -> dict | None:
    key = _cache_key("geo", location.lower().strip())
    cached = _get_cache(key)
    if cached:
        return cached

    normalized = location.strip()
    lower = normalized.lower()
    if lower in _CITY_ALIASES:
        normalized = _CITY_ALIASES[lower]

    queries = [normalized, _strip_accents(normalized)]
    if normalized == location:
        queries.append(_strip_accents(location))
    seen = set()
    try:
        with httpx.Client(timeout=10) as client:
            for q in queries:
                if not q or q in seen:
                    continue
                seen.add(q)
                resp = client.get(LOCATION_URL, params={"q": q, "limit": 1})
                if resp.status_code == 200:
                    data = resp.json()
                    if data and len(data) > 0:
                        gps = data[0].get("gps", [])
                        if isinstance(gps, list) and len(gps) == 2:
                            lng, lat = float(gps[0]), float(gps[1])
                            result = {
                                "lat": lat,
                                "lng": lng,
                                "google_id": str(data[0].get("google_id", "")),
                                "name": data[0].get("canonical_name", data[0].get("name", location)),
                            }
                            _set_cache(key, result, ttl=86400)
                            return result
    except Exception:
        pass
    return None


def search_flights(departure_id: str, arrival_id: str, outbound_date: str, return_date: str, adults: int = 2, children: int = 0) -> list[dict]:
    key = _cache_key("flights", departure_id, arrival_id, outbound_date, return_date, str(adults), str(children))
    cached = _get_cache(key)
    if cached:
        return cached

    params = {
        "api_key": SERPAPI_API_KEY,
        "engine": "google_flights",
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "return_date": return_date,
        "adults": adults,
        "children": children,
        "currency": "VND",
        "hl": "vi",
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(BASE_URL, params=params)
            if resp.status_code == 200:
                data = resp.json()
                results = _parse_flights(data)
                _set_cache(key, results)
                return results
    except Exception:
        pass
    return []


def _parse_flights(data: dict) -> list[dict]:
    items = []
    all_flights = data.get("best_flights", []) + data.get("other_flights", [])
    for flight in all_flights[:6]:
        segments = flight.get("flights", [])
        if not segments:
            continue
        first = segments[0]
        airline = first.get("airline", "Hãng hàng không")
        flight_nums = ", ".join(s.get("flight_number", "") for s in segments if s.get("flight_number"))

        total_min = flight.get("total_duration", 0)
        h, m = divmod(total_min, 60)
        duration_str = f"{h}h" + (f" {m}p" if m else "")

        price = flight.get("price")
        gia_str = f"{price:,.0f} VND/người (khứ hồi)" if isinstance(price, (int, float)) and price > 0 else "Liên hệ"

        booking_link = None
        if flight.get("departure_token"):
            booking_link = f"https://www.google.com/travel/flights?q=WyJDalJJ"  # simplified

        items.append({
            "loai": "Máy bay",
            "hang": airline,
            "thoi_gian": duration_str,
            "gia": gia_str,
            "link": booking_link,
            "_gia_min": price if isinstance(price, (int, float)) and price > 0 else None,
        })
    return items


def search_hotels(destination: str, check_in: str, check_out: str, adults: int = 2) -> list[dict]:
    key = _cache_key("hotels", destination.lower(), check_in, check_out, str(adults))
    cached = _get_cache(key)
    if cached:
        return cached

    params = {
        "api_key": SERPAPI_API_KEY,
        "engine": "google_hotels",
        "q": destination,
        "check_in_date": check_in,
        "check_out_date": check_out,
        "adults": adults,
        "currency": "VND",
        "hl": "vi",
        "gl": "vn",
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(BASE_URL, params=params)
            if resp.status_code == 200:
                data = resp.json()
                results = _parse_hotels(data)
                _set_cache(key, results)
                return results
    except Exception:
        pass
    return []


def _parse_hotels(data: dict) -> list[dict]:
    hotels = []
    for prop in data.get("properties", [])[:9]:
        name = prop.get("name", "")
        if not name:
            continue
        rate = prop.get("rate_per_night", {})
        gia = rate.get("lowest", "Liên hệ")
        rating = prop.get("overall_rating") or 0
        reviews = prop.get("reviews") or 0
        amenities = prop.get("amenities") or []
        hotel_class = prop.get("extracted_hotel_class") or 0
        address = prop.get("address") or ""

        extracted = rate.get("extracted_lowest") or rate.get("extracted_before_taxes_fees") or 0
        hotels.append({
            "ten": name,
            "dia_chi": address,
            "rating": round(float(rating), 1),
            "review_count": int(reviews),
            "tien_nghi": amenities[:8] if isinstance(amenities, list) else [],
            "gia_per_dem": gia,
            "link": prop.get("link") or "",
            "_gia_min": int(extracted) if extracted else None,
        })
    return hotels


def search_places(lat: float, lng: float, query: str, hl: str = "vi") -> list[dict]:
    key = _cache_key("places", f"{lat:.2f}", f"{lng:.2f}", query, hl)
    cached = _get_cache(key)
    if cached:
        return cached

    ll = f"@{lat},{lng},14z"
    queries_to_try = [query]
    if hl == "vi":
        queries_to_try.append(query)

    seen = set()
    try:
        with httpx.Client(timeout=30) as client:
            for q in queries_to_try:
                if q in seen:
                    continue
                seen.add(q)
                params = {
                    "api_key": SERPAPI_API_KEY,
                    "engine": "google_maps",
                    "q": q,
                    "ll": ll,
                    "type": "search",
                    "hl": hl,
                }
                resp = client.get(BASE_URL, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("local_results")
                    if not results:
                        place_results = data.get("place_results")
                        if isinstance(place_results, dict):
                            results = [place_results]
                        elif isinstance(place_results, list):
                            results = place_results
                        else:
                            results = []
                    if results:
                        _set_cache(key, results)
                        return results
    except Exception:
        pass
    return []


def search_places_bilingual(lat: float, lng: float, vi_query: str, en_query: str) -> list[dict]:
    results = search_places(lat, lng, vi_query, hl="vi")
    if not results:
        results = search_places(lat, lng, en_query, hl="en")
    return results


def estimate_flight_cost(dep_lat: float, dep_lng: float, dest_lat: float, dest_lng: float) -> list[dict]:
    dist = _haversine(dep_lat, dep_lng, dest_lat, dest_lng)
    est_price_per_person = int(dist * 1500)
    if est_price_per_person < 500000:
        est_price_per_person = 500000
    hours = max(1, int(dist / 800))
    price_range = f"{est_price_per_person:,.0f} - {est_price_per_person * 2:,.0f} VND/người (khứ hồi)"

    results = [
        {
            "loai": "Máy bay",
            "hang": "VietJet Air",
            "thoi_gian": f"{hours}h",
            "gia": f"{est_price_per_person:,.0f} - {est_price_per_person * 2:,.0f} VND/người (khứ hồi)",
            "link": "https://www.vietjetair.com",
            "_gia_min": est_price_per_person,
        },
        {
            "loai": "Máy bay",
            "hang": "Vietnam Airlines",
            "thoi_gian": f"{hours}h",
            "gia": f"{int(est_price_per_person * 1.3):,.0f} - {int(est_price_per_person * 2.5):,.0f} VND/người (khứ hồi)",
            "link": "https://www.vietnamairlines.com",
            "_gia_min": int(est_price_per_person * 1.3),
        },
    ]
    if dist < 500:
        results.append({
            "loai": "Xe khách",
            "hang": "Phương Trang / Hoàng Long",
            "thoi_gian": f"{int(dist / 60)}h",
            "gia": f"{int(dist * 100):,.0f} - {int(dist * 200):,.0f} VND/người (khứ hồi)",
            "link": "https://vexere.com",
            "_gia_min": int(dist * 100),
        })
    return results
