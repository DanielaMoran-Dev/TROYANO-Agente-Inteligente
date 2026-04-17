"""
FastAPI backend for Lineal — Smart City Planner.
"""

import os
import sys
import logging
import traceback

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Ensure the backend directory is on the path so agents are importable
sys.path.insert(0, os.path.dirname(__file__))

from agents import orchestrator_agent
# import orchestrator  # Agentes comentados temporalmente

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Lineal — Smart City Planner API",
    description=(
        "Multi-agent AI system for urban planning powered by IBM watsonx."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_csp_header(request, call_next):
    response = await call_next(request)
    csp = (
        "default-src * 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; "
        "script-src * 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; "
        "connect-src * 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; "
        "img-src * 'self' 'unsafe-inline' data: blob:; "
        "style-src * 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src * 'self' 'unsafe-inline' data: https://fonts.gstatic.com; "
        "worker-src * 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; "
        "frame-src * 'self' 'unsafe-inline' 'unsafe-eval' data: blob:;"
    )
    response.headers["Content-Security-Policy"] = csp
    return response

# Mount frontend static files
from fastapi.staticfiles import StaticFiles
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/ui", StaticFiles(directory=frontend_path, html=True), name="frontend")

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class PlanRequest(BaseModel):
    prompt: str = Field(..., min_length=5, max_length=3000)
    zone: Optional[dict] = None
    center: Optional[dict] = None
    brief: Optional[dict] = None   # full orchestrator_brief from chat interview


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "TROYANO",
        "version": "1.0.0",
        "mode": "gemini",
    }


# @app.post("/generate-plan", tags=["planning"])
# async def generate_plan(body: PlanRequest):
#     """Run the full multi-agent urban planning pipeline."""
#     try:
#         result = orchestrator.run_pipeline(
#             body.prompt, zone=body.zone, center=body.center, brief=body.brief,
#         )
#         return result
#     except Exception as exc:
#         traceback.print_exc()
#         raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}") from exc


# ---------------------------------------------------------------------------
# Geodata endpoints — SIIMP / ArcGIS API-First Strategy
# ---------------------------------------------------------------------------

from services import geodata_service


@app.get("/geo/layers", tags=["geodata"])
async def list_geo_layers():
    """List all available SIIMP/ArcGIS layers."""
    return {"layers": geodata_service.list_layers()}


@app.get("/geo/layer/{layer_name}", tags=["geodata"])
async def get_geo_layer(layer_name: str):
    """
    Fetch a single GeoJSON layer from SIIMP by name.
    Available layers: vialidades, contencion_urbana, zufos,
    zonas_dinamica_especial, materiales_petreos.
    """
    try:
        geojson = geodata_service.get_layer(layer_name)
        return geojson
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class MultiLayerRequest(BaseModel):
    layers: list[str] = Field(..., min_length=1)


@app.post("/geo/multi", tags=["geodata"])
async def get_multiple_geo_layers(body: MultiLayerRequest):
    """Fetch multiple GeoJSON layers in a single request."""
    results = geodata_service.get_multiple_layers(body.layers)
    return results


@app.get("/geo/layer/{layer_name}/metadata", tags=["geodata"])
async def get_geo_layer_metadata(layer_name: str):
    """Fetch metadata (title, extent, description) for a SIIMP layer."""
    try:
        metadata = geodata_service.get_layer_metadata(layer_name)
        return metadata
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Watson Discovery — RAG Knowledge Base
# ---------------------------------------------------------------------------

from services import discovery_service


class DiscoveryQuery(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    topics: Optional[list[str]] = None
    max_results: Optional[int] = 3


@app.post("/discovery/query", tags=["discovery"])
async def query_discovery(body: DiscoveryQuery):
    """Query regulatory documents via Watson Discovery RAG."""
    result = discovery_service.query(
        body.question, topics=body.topics, max_results=body.max_results
    )
    return result


@app.get("/discovery/documents", tags=["discovery"])
async def list_discovery_documents():
    """List all documents in the knowledge base."""
    return {"documents": discovery_service.list_documents()}


@app.get("/discovery/status", tags=["discovery"])
async def discovery_status():
    """Check Watson Discovery configuration status."""
    return {
        "configured": discovery_service.is_configured(),
        "mode": "watson_discovery" if discovery_service.is_configured() else "local_catalog",
        "document_count": len(discovery_service.PDF_CATALOG),
    }


# ---------------------------------------------------------------------------
# Google Maps — Places (Geocoding) + Routes API
# ---------------------------------------------------------------------------

from services import maps_service


class RoutesRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    destinations: list[dict]
    travel_mode: Optional[str] = "DRIVE"


@app.get("/maps/search", tags=["maps"])
async def maps_search(q: str):
    """
    Geocode a free-text query using Google Geocoding API.
    Returns: { name, lat, lng, formatted_address }
    """
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required.")
    try:
        result = maps_service.search_place(q.strip())
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/maps/routes", tags=["maps"])
async def maps_routes(body: RoutesRequest):
    """
    Calculate travel times and distances from an origin to city reference nodes.
    travel_mode: DRIVE | WALK | TRANSIT | BICYCLE
    """
    try:
        result = maps_service.get_routes(
            origin_lat=body.origin_lat,
            origin_lng=body.origin_lng,
            destinations=body.destinations,
            travel_mode=body.travel_mode or "DRIVE",
        )
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/maps/tile/{z}/{x}/{y}", tags=["maps"])
async def proxy_map_tile(z: int, x: int, y: int, map_type: str = "roadmap"):
    """
    Proxy Google Maps tiles through the backend to avoid browser CORS restrictions.
    On session/tile failure, retries once with a fresh session.
    Returns a transparent 1x1 PNG if tile is unavailable (prevents MapLibre errors).
    """
    import requests as req

    # 1x1 transparent PNG — returned when Google has no tile for these coords
    TRANSPARENT_PNG = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def fetch_tile(session: str) -> req.Response:
        key = maps_service.GOOGLE_MAPS_API_KEY
        url = f"https://tile.googleapis.com/v1/tiles/{z}/{x}/{y}?session={session}&key={key}"
        return req.get(url, timeout=10)

    try:
        session_data = maps_service.create_map_session(map_type)
        r = fetch_tile(session_data["session"])

        # Session expired or invalid → clear cache and retry once
        if r.status_code in (401, 403, 404):
            logger.warning("Tile %s/%s/%s returned %s — refreshing session", z, x, y, r.status_code)
            maps_service._tiles_session_cache.pop(map_type, None)
            session_data = maps_service.create_map_session(map_type)
            r = fetch_tile(session_data["session"])

        if not r.ok:
            logger.warning("Tile %s/%s/%s unavailable (%s) — returning transparent", z, x, y, r.status_code)
            return Response(content=TRANSPARENT_PNG, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=60"})

        return Response(
            content=r.content,
            media_type=r.headers.get("content-type", "image/png"),
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as exc:
        logger.error("Tile proxy error %s/%s/%s: %s", z, x, y, exc)
        return Response(content=TRANSPARENT_PNG, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=60"})


@app.get("/maps/session", tags=["maps"])
async def maps_session(map_type: str = "roadmap"):
    """
    Create (or return cached) a Google Maps Tiles API session.
    Returns the tile URL template ready to use in MapLibre.
    map_type: roadmap | satellite | terrain
    """
    try:
        result = maps_service.create_map_session(map_type)
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/maps/key", tags=["maps"])
async def maps_key():
    """Return the Google Maps API key for frontend use."""
    if not maps_service.is_configured():
        raise HTTPException(status_code=503, detail="Google Maps API key not configured.")
    return {"key": maps_service.GOOGLE_MAPS_API_KEY}


@app.get("/maps/status", tags=["maps"])
async def maps_status():
    """Check Google Maps API configuration status."""
    return {"configured": maps_service.is_configured()}


# ---------------------------------------------------------------------------
# Watson Orchestrate — Skill Manifest
# ---------------------------------------------------------------------------

import json as _json


@app.get("/orchestrate/manifest", tags=["orchestrate"])
async def get_orchestrate_manifest():
    """
    Serve the OpenAPI manifest for Watson Orchestrate skill registration.
    Import this URL into Orchestrate to discover Lineal's capabilities.
    """
    manifest_path = os.path.join(os.path.dirname(__file__), "orchestrate_manifest.json")
    try:
        with open(manifest_path, "r") as f:
            return _json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Orchestrate manifest not found.")


# ---------------------------------------------------------------------------
# Orchestrator Chat — Agent 0 (multi-turn interview)
# ---------------------------------------------------------------------------


class OrchestratorChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=2000)


class OrchestratorResetRequest(BaseModel):
    session_id: str


@app.post("/orchestrator/start", tags=["orchestrator"])
async def orchestrator_start():
    """Create a new interview session and return the opening message."""
    session_id = orchestrator_agent.start_session()
    return {
        "session_id": session_id,
        "reply": orchestrator_agent.get_opening_message(),
        "done": False,
        "brief": None,
    }


@app.post("/orchestrator/chat", tags=["orchestrator"])
async def orchestrator_chat(body: OrchestratorChatRequest):
    """
    Send one message in the interview.
    If session_id is omitted a new session is auto-created.
    Returns: { session_id, reply, done, brief? }
    """
    session_id = body.session_id or orchestrator_agent.start_session()
    try:
        result = orchestrator_agent.chat(session_id, body.message)
        return {"session_id": session_id, **result}
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Orchestrator error: {exc}") from exc


@app.post("/orchestrator/reset", tags=["orchestrator"])
async def orchestrator_reset(body: OrchestratorResetRequest):
    """Clear an interview session."""
    orchestrator_agent.reset_session(body.session_id)
    return {"ok": True}
