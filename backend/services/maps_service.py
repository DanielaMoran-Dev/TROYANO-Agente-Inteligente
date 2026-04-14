"""
Maps Service — Google Maps Platform Integration
Provides geocoding (Places) and route calculation (Routes API) for URBANAI.

- search_place()  → wraps Geocoding API (replaces Nominatim)
- get_routes()    → wraps Routes API (accessibility analysis for parcels)
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

GEOCODING_URL   = "https://maps.googleapis.com/maps/api/geocode/json"
ROUTES_URL      = "https://routes.googleapis.com/directions/v2:computeRoutes"
TILES_SESSION_URL = "https://tile.googleapis.com/v1/createSession"

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
