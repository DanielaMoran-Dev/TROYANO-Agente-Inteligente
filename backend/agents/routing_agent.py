"""
Routing Agent — finds and ranks clinics via MongoDB Vector Search + Google Maps travel times.
"""

import asyncio
import logging

from services import gemini_service, mongo_service, maps_service

logger = logging.getLogger(__name__)

BUDGET_MAP = {
    "$": ["$"],
    "$$": ["$", "$$"],
    "$$$": ["$", "$$", "$$$"],
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
        triage:       Output from triage_agent.run()
        insurance:    "imss" | "issste" | "seguro_popular" | "ninguno"
        budget_level: "$" | "$$" | "$$$"
        coords:       {"lat": float, "lng": float}
        limit:        max results to return

    Returns:
        Ranked list of clinic dicts enriched with travel_time_min.
    """
    specialty = triage.get("specialty", "")
    unit_type = triage.get("unit_type", "")
    urgency = triage.get("urgency_level", "medium")

    # 1. Embed specialty + unit_type
    embed_text = f"{specialty} {unit_type}"
    embedding = gemini_service.embed(embed_text)

    # 2. Vector search
    candidates = await mongo_service.vector_search_clinics(embedding, limit=limit * 3)

    # 3. Filter by insurance and budget
    allowed_budgets = BUDGET_MAP.get(budget_level, ["$"])
    filtered = [
        c for c in candidates
        if (insurance == "ninguno" or insurance in (c.get("insurance") or []))
        and c.get("budget_level", "$") in allowed_budgets
    ]

    if not filtered:
        filtered = candidates  # fallback: return all if filters leave nothing

    # 4. Get travel times
    destinations = [
        {"label": c["name"], "lat": c["coords"]["lat"], "lng": c["coords"]["lng"]}
        for c in filtered[:limit]
        if c.get("coords")
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

    # 5. Enrich and rank
    for c in filtered[:limit]:
        c["travel_time_min"] = travel_map.get(c.get("name"), None)

    urgency_weight = {"critical": 0.5, "medium": 0.3, "low": 0.1}.get(urgency, 0.3)

    def rank_score(c):
        travel = c.get("travel_time_min") or 60
        return travel * (1 - urgency_weight) + (1 - c.get("score", 0)) * urgency_weight * 100

    ranked = sorted(filtered[:limit], key=rank_score)
    return ranked
