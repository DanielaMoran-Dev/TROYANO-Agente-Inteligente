"""
Routing Agent — encuentra y rankea clínicas cercanas al paciente.

Fuentes de candidatos:
  1. Google Places Nearby (real-world, radio geográfico) — PRIMARIA
  2. MongoDB Vector Search sobre `clinics` (semántica + network) — SECUNDARIA

Se combinan, se deduplican por (lat,lng) o place_id, se filtran por radio,
seguro y presupuesto, y se rankean por travel_time + relevancia.
"""

import logging

from services import gemini_service, mongo_service, maps_service

logger = logging.getLogger(__name__)


# $ → price_level 1, $$ → 1-2, $$$ → 1-3
BUDGET_MAP: dict[str, list[int]] = {
    "$": [1],
    "$$": [1, 2],
    "$$$": [1, 2, 3],
}


async def run(
    triage: dict,
    insurance: str,
    budget_level: str,
    coords: dict,
    limit: int = 10,
    radius_m: int = 5000,
) -> list[dict]:
    """
    Args:
        triage:       Output del triage_agent.run()
        insurance:    "imss" | "issste" | "seguro_popular" | "ninguno"
        budget_level: "$" | "$$" | "$$$"
        coords:       {"lat": float, "lng": float}
        limit:        Máximo de resultados.
        radius_m:     Perímetro de búsqueda en metros (default 5 km).

    Returns:
        Lista rankeada de clínicas enriquecidas con travel_time_min y distance_m.
    """
    specialty = triage.get("specialty", "")
    unit_type = triage.get("unit_type", "")
    urgency = triage.get("urgency_level", "medium")
    red_flags = triage.get("red_flags") or []

    origin_lat, origin_lng = coords["lat"], coords["lng"]

    # ── 1. Candidatos desde Google Places (reales, cercanos) ──
    places_candidates: list[dict] = []
    if maps_service.is_configured():
        try:
            places_candidates = maps_service.search_nearby_health(
                lat=origin_lat,
                lng=origin_lng,
                radius_m=radius_m,
                max_results=20,
            )
            logger.info("Places: %d lugares en %dm", len(places_candidates), radius_m)
        except Exception as exc:
            logger.warning("Places nearby unavailable: %s", exc)

    # ── 2. Candidatos desde DB (vector search) filtrados por radio ──
    db_candidates: list[dict] = []
    try:
        embed_text = " ".join(filter(None, [specialty, unit_type, *red_flags]))
        if embed_text:
            embedding = gemini_service.embed(embed_text)
            raw = await mongo_service.vector_search_clinics(embedding, limit=limit * 3)
            for c in raw:
                if c.get("lat") is None or c.get("lng") is None:
                    continue
                d = maps_service._haversine_m(origin_lat, origin_lng, c["lat"], c["lng"])
                if d <= radius_m:
                    c["distance_m"] = d
                    c["source"] = "db"
                    db_candidates.append(c)
            logger.info("DB: %d clínicas dentro de %dm", len(db_candidates), radius_m)
    except Exception as exc:
        logger.warning("DB vector search unavailable: %s", exc)

    # ── 3. Merge con deduplicación (DB gana si hay match por proximidad <100m) ──
    merged = _merge_candidates(db_candidates, places_candidates)

    # ── 4. Filtros hard por seguro y budget ──
    allowed_prices = BUDGET_MAP.get(budget_level, [1, 2, 3])

    def passes_filters(c: dict) -> bool:
        # Seguro: DB respeta lista; Places no la conoce, así que pasa si insurance=ninguno o es Places.
        if insurance != "ninguno":
            ins_list = c.get("insurances") or []
            if c.get("source") == "db" and insurance not in ins_list:
                return False
        return c.get("price_level", 2) in allowed_prices

    filtered = [c for c in merged if passes_filters(c)]
    if not filtered:
        filtered = merged

    filtered = filtered[:limit]

    # ── 5. Travel times vía Routes API ──
    destinations = [
        {
            "label": c.get("clinic_id") or c.get("place_id") or c.get("name"),
            "lat": c["lat"],
            "lng": c["lng"],
        }
        for c in filtered
    ]

    travel_map: dict[str, float] = {}
    if destinations and maps_service.is_configured():
        try:
            routes_result = maps_service.get_routes(
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                destinations=destinations,
                travel_mode="DRIVE",
            )
            for r in routes_result.get("routes", []):
                if r.get("status") == "OK":
                    travel_map[r["destination"]] = r["duration_min"]
        except Exception as exc:
            logger.warning("Routes API unavailable: %s", exc)

    for c in filtered:
        label = c.get("clinic_id") or c.get("place_id") or c.get("name")
        c["travel_time_min"] = travel_map.get(label)

    # ── 6. Ranking ──
    urgency_weight = {"critical": 0.5, "medium": 0.3, "low": 0.1}.get(urgency, 0.3)

    def rank_score(c: dict) -> float:
        # Travel time primario; si falta, usa distancia lineal como proxy (min ≈ km).
        travel = c.get("travel_time_min")
        if travel is None:
            travel = (c.get("distance_m") or 60_000) / 1000.0
        semantic = 1 - float(c.get("score") or 0)
        network_bonus = -5 if c.get("is_network") else 0
        return travel * (1 - urgency_weight) + semantic * urgency_weight * 100 + network_bonus

    return sorted(filtered, key=rank_score)


def _merge_candidates(db_list: list[dict], places_list: list[dict]) -> list[dict]:
    """Combina DB + Places; si hay duplicados geográficos (<100m) prioriza DB (tiene network/seguro)."""
    merged: list[dict] = list(db_list)
    for p in places_list:
        dup = False
        for d in db_list:
            if d.get("lat") is None or d.get("lng") is None:
                continue
            if maps_service._haversine_m(p["lat"], p["lng"], d["lat"], d["lng"]) < 100:
                dup = True
                break
        if not dup:
            merged.append(p)
    return merged
