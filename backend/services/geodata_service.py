"""
Geodata Service — SIIMP / ArcGIS Online REST API Integration
Fetches GeoJSON layers from the SIIMP (Sistema Integral de Información Municipal
y Planeación) of Aguascalientes via the public ArcGIS Online REST API.

This service replaces local GeoJSON/OSM files entirely, keeping the architecture
stateless and serverless-ready for IBM Cloud Code Engine.
"""

import os
import json
import logging
import hashlib
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ArcGIS Item IDs — sourced from https://siimp.gob.mx/pduca-visor.html
# Override via environment variables for flexibility without redeployment.
# ---------------------------------------------------------------------------

ARCGIS_BASE_URL = os.getenv(
    "ARCGIS_BASE_URL",
    "https://www.arcgis.com/sharing/rest/content/items",
)

# Layer catalog: maps logical names → ArcGIS Item IDs
LAYER_CATALOG = {
    "vialidades": os.getenv(
        "SIIMP_VIALIDADES_ID", "326852c2fee84bd29309c5f233fc95e1"
    ),
    "contencion_urbana": os.getenv(
        "SIIMP_CONTENCION_ID", "b372b2da8ff5413ab91ec8fd660729e3"
    ),
    "zufos": os.getenv(
        "SIIMP_ZUFOS_ID", "00c831a39c364076a370c66c7e54c48c"
    ),
    "zonas_dinamica_especial": os.getenv(
        "SIIMP_DINAMICA_ID", "f77c54918844465eaab349127455f256"
    ),
    "materiales_petreos": os.getenv(
        "SIIMP_PETREOS_ID", "128350523f3c4ff99eb7515961fb55f4"
    ),
}

# In-memory cache to avoid repeated API calls within the same container lifecycle.
_cache: dict[str, dict] = {}

# Request timeout in seconds
REQUEST_TIMEOUT = int(os.getenv("GEODATA_TIMEOUT", "30"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_layers() -> list[str]:
    """Return all available layer names."""
    return list(LAYER_CATALOG.keys())


def get_layer(layer_name: str, use_cache: bool = True) -> dict:
    """
    Fetch a GeoJSON FeatureCollection from ArcGIS for the given layer name.

    Args:
        layer_name: One of the keys in LAYER_CATALOG (e.g. "vialidades").
        use_cache:  If True, return cached data when available.

    Returns:
        A GeoJSON dict (FeatureCollection).

    Raises:
        ValueError:  If the layer_name is not in the catalog.
        RuntimeError: If the API call fails.
    """
    if layer_name not in LAYER_CATALOG:
        raise ValueError(
            f"Unknown layer '{layer_name}'. Available: {list_layers()}"
        )

    cache_key = layer_name
    if use_cache and cache_key in _cache:
        logger.debug("Cache HIT for layer '%s'", layer_name)
        return _cache[cache_key]

    item_id = LAYER_CATALOG[layer_name]
    url = f"{ARCGIS_BASE_URL}/{item_id}/data?f=json"

    logger.info("Fetching layer '%s' from %s", layer_name, url)
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        geojson = response.json()
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Timeout fetching layer '{layer_name}' after {REQUEST_TIMEOUT}s"
        )
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"Failed to fetch layer '{layer_name}': {exc}"
        ) from exc

    # Validate it looks like GeoJSON
    if geojson.get("type") not in ("FeatureCollection", "Feature"):
        logger.warning(
            "Layer '%s' returned unexpected type: %s",
            layer_name,
            geojson.get("type"),
        )

    _cache[cache_key] = geojson
    logger.info(
        "Layer '%s' fetched — %d features",
        layer_name,
        len(geojson.get("features", [])),
    )
    return geojson


def get_layer_metadata(layer_name: str) -> dict:
    """
    Fetch metadata (title, description, extent, etc.) for a layer item.
    """
    if layer_name not in LAYER_CATALOG:
        raise ValueError(
            f"Unknown layer '{layer_name}'. Available: {list_layers()}"
        )

    item_id = LAYER_CATALOG[layer_name]
    url = f"{ARCGIS_BASE_URL}/{item_id}?f=json"

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"Failed to fetch metadata for '{layer_name}': {exc}"
        ) from exc


def get_multiple_layers(
    layer_names: list[str], use_cache: bool = True
) -> dict[str, dict]:
    """
    Fetch multiple layers and return them as a dict keyed by layer name.
    Failures on individual layers are logged but don't block others.
    """
    results = {}
    for name in layer_names:
        try:
            results[name] = get_layer(name, use_cache=use_cache)
        except Exception as exc:
            logger.error("Failed to fetch layer '%s': %s", name, exc)
            results[name] = {"type": "FeatureCollection", "features": [], "error": str(exc)}
    return results


def clear_cache():
    """Clear the in-memory cache."""
    _cache.clear()
    logger.info("Geodata cache cleared.")
