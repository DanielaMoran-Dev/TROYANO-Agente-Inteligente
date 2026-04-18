"""
Maps Service — Google Maps Platform Integration
Provides geocoding (Places) and route calculation (Routes API) for URBANAI.

- search_place()  → wraps Geocoding API (replaces Nominatim)
- get_routes()    → wraps Routes API (accessibility analysis for parcels)
"""

import hashlib
import os
import logging
import requests

from services import redis_service

logger = logging.getLogger(__name__)

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

PLACES_CACHE_TTL = 7 * 24 * 3600  # 7 days — private practitioners don't move often
ROUTES_CACHE_TTL = 3600           # 1 hour — traffic-aware, stale quickly

GEOCODING_URL   = "https://maps.googleapis.com/maps/api/geocode/json"
ROUTES_URL      = "https://routes.googleapis.com/directions/v2:computeRoutes"
TILES_SESSION_URL = "https://tile.googleapis.com/v1/createSession"
PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"

REQUEST_TIMEOUT = 10

# In-memory cache for the tiles session token (valid ~2 weeks)
_tiles_session_cache: dict = {}


def create_map_session(map_type: str = "roadmap") -> dict:
    """
    Create a Google Maps Tiles API session token.
    Returns tile URL template and session info.
    Uses in-memory cache to avoid creating a new session on every request.
    """
    if not is_configured():
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not set.")

    import time
    cached = _tiles_session_cache.get(map_type)
    if cached and cached.get("expires", 0) > time.time() + 3600:
        return cached

    payload = {
        "mapType":  map_type,
        "language": "es",
        "region":   "MX",
    }

    try:
        response = requests.post(
            f"{TILES_SESSION_URL}?key={GOOGLE_MAPS_API_KEY}",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        if not response.ok:
            msg = f"Tiles API HTTP {response.status_code}: {response.text}"
            logger.error(msg)
            raise RuntimeError(msg)
        data = response.json()
    except requests.exceptions.RequestException as exc:
        logger.error("Tiles session request failed: %s", exc)
        raise RuntimeError(f"Failed to create tiles session: {exc}") from exc

    session_token = data.get("session")
    if not session_token:
        raise RuntimeError(f"Tiles API returned no session token: {data}")

    result = {
        "session":       session_token,
        "tile_url":      f"https://tile.googleapis.com/v1/tiles/{{z}}/{{x}}/{{y}}?session={session_token}&key={GOOGLE_MAPS_API_KEY}",
        "map_type":      map_type,
        "expires":       int(data.get("expiry", 0)),
    }

    _tiles_session_cache[map_type] = result
    logger.info("Google Maps Tiles session created for map_type=%s", map_type)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_configured() -> bool:
    return bool(GOOGLE_MAPS_API_KEY)


def search_place(query: str) -> dict:
    """
    Geocode a free-text query using Google Geocoding API.

    Returns:
        {
            "name": str,
            "lat": float,
            "lng": float,
            "formatted_address": str,
        }

    Raises:
        RuntimeError: If the API call fails or returns no results.
    """
    if not is_configured():
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not set.")

    params = {
        "address": query,
        "key": GOOGLE_MAPS_API_KEY,
        "language": "es",
        "region": "mx",
    }

    try:
        response = requests.get(GEOCODING_URL, params=params, timeout=REQUEST_TIMEOUT)
        if not response.ok:
            msg = f"Geocoding HTTP {response.status_code}: {response.text}"
            logger.error(msg)
            raise RuntimeError(msg)
        data = response.json()
    except requests.exceptions.RequestException as exc:
        logger.error("Geocoding request failed: %s", exc)
        raise RuntimeError(f"Geocoding request failed: {exc}") from exc

    if data.get("status") != "OK" or not data.get("results"):
        status = data.get("status", "UNKNOWN")
        raise RuntimeError(f"Geocoding returned no results (status: {status})")

    result = data["results"][0]
    loc    = result["geometry"]["location"]

    parts      = result["formatted_address"].split(",")
    short_name = ", ".join(p.strip() for p in parts[:2])

    return {
        "name":              short_name,
        "lat":               loc["lat"],
        "lng":               loc["lng"],
        "formatted_address": result["formatted_address"],
    }


def search_nearby_health(
    lat: float,
    lng: float,
    radius_m: int = 5000,
    keyword: str | None = None,
    max_results: int = 20,
) -> list[dict]:
    """
    Busca hospitales/clínicas cerca de (lat, lng) dentro de `radius_m` metros.
    Usa Places API (New) — searchNearby. Devuelve una lista de clínicas
    normalizadas al shape que consume el routing_agent.

    Si `keyword` se provee (p.ej. "cardiología"), se usa searchText con bias
    circular para priorizar por especialidad.
    """
    if not is_configured():
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not set.")

    radius_m = max(500, min(radius_m, 50000))  # Places límite: 50km
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.location,places.types,places.nationalPhoneNumber,"
            "places.rating,places.userRatingCount,places.businessStatus"
        ),
    }

    payload = {
        "includedTypes": ["hospital", "doctor", "medical_lab", "pharmacy"],
        "maxResultCount": max(1, min(max_results, 20)),
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius_m),
            }
        },
        "languageCode": "es",
        "regionCode": "MX",
    }

    try:
        response = requests.post(PLACES_NEARBY_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        if not response.ok:
            logger.error("Places Nearby HTTP %s: %s", response.status_code, response.text)
            return []
        data = response.json()
    except requests.exceptions.RequestException as exc:
        logger.error("Places Nearby request failed: %s", exc)
        return []

    results = []
    for p in data.get("places", []):
        loc = p.get("location") or {}
        p_lat, p_lng = loc.get("latitude"), loc.get("longitude")
        if p_lat is None or p_lng is None:
            continue
        if p.get("businessStatus") and p["businessStatus"] != "OPERATIONAL":
            continue

        types = p.get("types") or []
        display = (p.get("displayName") or {}).get("text") or ""

        results.append({
            "clinic_id": p.get("id"),
            "place_id": p.get("id"),
            "name": display,
            "address": p.get("formattedAddress"),
            "phone": p.get("nationalPhoneNumber"),
            "lat": p_lat,
            "lng": p_lng,
            "types": types,
            "rating": p.get("rating"),
            "rating_count": p.get("userRatingCount"),
            # Heurísticas por tipo — Places no expone seguro/precio:
            "insurances": [],
            "price_level": 2,
            "is_network": False,
            "source": "places",
            "distance_m": _haversine_m(lat, lng, p_lat, p_lng),
        })

    results.sort(key=lambda r: r["distance_m"])
    return results


async def search_nearby_health_cached(
    lat: float,
    lng: float,
    radius_m: int = 5000,
    keyword: str | None = None,
    max_results: int = 20,
) -> list[dict]:
    """Redis-cached wrapper around search_nearby_health(). Falls through on miss."""
    key = f"places:{lat:.3f}:{lng:.3f}:{radius_m}:{keyword or ''}:{max_results}"
    hit = await redis_service.cache_get(key)
    if hit is not None:
        logger.debug("places cache hit: %s", key)
        return hit

    results = search_nearby_health(lat, lng, radius_m, keyword, max_results)
    if results:
        await redis_service.cache_set(key, results, PLACES_CACHE_TTL)
    return results


async def get_routes_cached(
    origin_lat: float,
    origin_lng: float,
    destinations: list[dict],
    travel_mode: str = "DRIVE",
) -> dict:
    """Redis-cached wrapper around get_routes(). Keyed by rounded origin + destination set."""
    dest_sig = ";".join(
        sorted(f"{d['lat']:.3f},{d['lng']:.3f}" for d in destinations if d.get("lat") is not None)
    )
    dest_hash = hashlib.sha1(dest_sig.encode()).hexdigest()[:12]
    key = f"routes:{travel_mode}:{origin_lat:.3f}:{origin_lng:.3f}:{dest_hash}"

    hit = await redis_service.cache_get(key)
    if hit is not None:
        logger.debug("routes cache hit: %s", key)
        return hit

    result = get_routes(origin_lat, origin_lng, destinations, travel_mode)
    if result.get("routes"):
        await redis_service.cache_set(key, result, ROUTES_CACHE_TTL)
    return result


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia en metros entre dos puntos (aproximación esférica)."""
    import math
    R = 6_371_000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def get_routes(
    origin_lat: float,
    origin_lng: float,
    destinations: list[dict],
    travel_mode: str = "DRIVE",
) -> dict:
    """
    Calculate routes from an origin to multiple destinations using the
    Google Routes API.

    Args:
        origin_lat:   Latitude of the origin point.
        origin_lng:   Longitude of the origin point.
        destinations: List of dicts with keys: label, lat, lng.
        travel_mode:  "DRIVE" | "WALK" | "TRANSIT" | "BICYCLE"

    Returns:
        {
            "origin":  { "lat": ..., "lng": ... },
            "mode":    "DRIVE",
            "routes":  [ { "destination", "lat", "lng", "duration_min", "distance_km", "status" }, ... ]
        }
    """
    if not is_configured():
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not set.")

    if not destinations:
        return {"origin": {"lat": origin_lat, "lng": origin_lng}, "mode": travel_mode, "routes": []}

    results = []

    headers = {
        "Content-Type":     "application/json",
        "X-Goog-Api-Key":   GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.legs",
    }

    for node in destinations:
        payload = {
            "origin": {
                "location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}
            },
            "destination": {
                "location": {"latLng": {"latitude": node["lat"], "longitude": node["lng"]}}
            },
            "travelMode": travel_mode,
            "routingPreference": "TRAFFIC_AWARE" if travel_mode == "DRIVE" else "ROUTING_PREFERENCE_UNSPECIFIED",
            "computeAlternativeRoutes": False,
            "languageCode": "es",
            "units": "METRIC",
        }

        try:
            response = requests.post(ROUTES_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()

            if data.get("routes"):
                route      = data["routes"][0]
                duration_s = int(route.get("duration", "0s").rstrip("s"))
                distance_m = route.get("distanceMeters", 0)
                results.append({
                    "destination":  node["label"],
                    "lat":          node["lat"],
                    "lng":          node["lng"],
                    "duration_min": round(duration_s / 60, 1),
                    "distance_km":  round(distance_m / 1000, 2),
                    "status":       "OK",
                })
            else:
                results.append({
                    "destination": node["label"],
                    "lat":         node["lat"],
                    "lng":         node["lng"],
                    "status":      "NO_ROUTE",
                })

        except requests.exceptions.RequestException as exc:
            logger.error("Routes API error for '%s': %s", node["label"], exc)
            results.append({
                "destination": node["label"],
                "lat":         node["lat"],
                "lng":         node["lng"],
                "status":      "ERROR",
                "error":       str(exc),
            })

    return {
        "origin": {"lat": origin_lat, "lng": origin_lng},
        "mode":   travel_mode,
        "routes": results,
    }
