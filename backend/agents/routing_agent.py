"""
Routing Agent — encuentra y rankea clínicas vía MongoDB Vector Search
+ Google Maps travel times.

Usa el schema real de la colección `clinics`:
  - insurances: array[str]
  - price_level: int (1=público, 2=bajo, 3=premium)
  - lat, lng en raíz del documento
  - doctor_id: ObjectId|null
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
) -> list[dict]:
    """
    Args:
        triage:       Output del triage_agent.run()
        insurance:    "imss" | "issste" | "seguro_popular" | "ninguno"
        budget_level: "$" | "$$" | "$$$"
        coords:       {"lat": float, "lng": float}
        limit:        Máximo de resultados.

    Returns:
        Lista rankeada de clínicas enriquecidas con travel_time_min.
    """
    specialty = triage.get("specialty", "")
    unit_type = triage.get("unit_type", "")
    urgency = triage.get("urgency_level", "medium")
    red_flags = triage.get("red_flags") or []

    # 1. Embedding de la consulta
    embed_text = " ".join(filter(None, [specialty, unit_type, *red_flags]))
    embedding = gemini_service.embed(embed_text)

    # 2. Vector search (pide más candidatos para compensar filtros hard)
    candidates = await mongo_service.vector_search_clinics(embedding, limit=limit * 3)

    # 3. Filtros hard por seguro y budget
    allowed_prices = BUDGET_MAP.get(budget_level, [1, 2, 3])
    filtered = [
        c for c in candidates
        if (insurance == "ninguno" or insurance in (c.get("insurances") or []))
        and c.get("price_level", 1) in allowed_prices
    ]

    if not filtered:
        # Fallback: si los filtros dejan vacío, regresar los top candidatos
        filtered = candidates[:limit]

    # 4. Travel times vía Google Maps (en paralelo dentro del service)
    destinations = [
        {
            "label": c.get("clinic_id") or c.get("clues_id") or c.get("name"),
            "lat": c.get("lat"),
            "lng": c.get("lng"),
        }
        for c in filtered[:limit]
        if c.get("lat") is not None and c.get("lng") is not None
    ]

    travel_map: dict[str, float] = {}
    if destinations and maps_service.is_configured():
        try:
            routes_result = maps_service.get_routes(
                origin_lat=coords["lat"],
                origin_lng=coords["lng"],
                destinations=destinations,
                travel_mode="DRIVE",
            )
            for r in routes_result.get("routes", []):
                if r.get("status") == "OK":
                    travel_map[r["destination"]] = r["duration_min"]
        except Exception as e:
            logger.warning("Maps API unavailable: %s", e)

    # 5. Enriquecer con travel_time_min
    for c in filtered[:limit]:
        label = c.get("clinic_id") or c.get("clues_id") or c.get("name")
        c["travel_time_min"] = travel_map.get(label)

    # 6. Ranking: score combina travel_time + relevancia semántica
    urgency_weight = {"critical": 0.5, "medium": 0.3, "low": 0.1}.get(urgency, 0.3)

    def rank_score(c: dict) -> float:
        travel = c.get("travel_time_min") or 60
        semantic = 1 - float(c.get("score") or 0)
        return travel * (1 - urgency_weight) + semantic * urgency_weight * 100

    ranked = sorted(filtered[:limit], key=rank_score)
    return ranked
