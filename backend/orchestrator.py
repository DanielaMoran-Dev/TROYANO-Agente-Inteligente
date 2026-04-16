"""
Orchestrator — Smart Routing Pipeline

Flow:
  1. Zone Analyzer   → what is spatially allowed/blocked in the drawn polygon
  2. Intent Router   → which agent types the user actually wants
  3. Construction    → generate interventions of the requested types only,
                       placed inside the zone, respecting zone constraints
  4. Feasibility     → validate each intervention against regulations + zone constraints
  5. Evaluation      → compute impact metrics
  6. Analyzer        → write final synthesis
  7. Gemini Ranker   → optional ranking (skipped if unconfigured or < 2 feasible)

Every agent receives:
  • The user's full prompt / brief
  • The zone polygon (GeoJSON)
  • The map centre coordinates
  • The ZoneConstraints object (SIIMP spatial analysis)
  • The intent type list
"""

from typing import List, Optional

from agents import construction_agent, feasibility_agent, evaluation_agent, analyzer_agent
from agents import gemini_ranker
from services import zone_analyzer, intent_router


def run_pipeline(
    prompt: str,
    zone: Optional[dict] = None,
    center: Optional[dict] = None,
    brief: Optional[dict] = None,
) -> dict:
    """
    Execute the full routed multi-agent urban planning pipeline.

    Parameters
    ----------
    prompt  : The project description from the orchestrator chat interview.
    zone    : GeoJSON Polygon drawn by the user on the map (optional).
    center  : {"lat": float, "lng": float} — current map centre.
    brief   : Full orchestrator_brief dict from the chat interview (optional).
              Used by the intent router for high-confidence type detection.
    """

    # ── 1. ZONE ANALYSIS — what can be built here? ──────────────────────────
    print("--- [NODE] ZONE ANALYSIS ---")
    constraints = zone_analyzer.analyze(zone)

    # If zone polygon is absent/unclassified, use brief.land_status as fallback signal
    if constraints.land_use_status == "unknown" and brief and isinstance(brief, dict):
        brief_land = str(brief.get("land_status", "")).lower()
        if brief_land in ("extension", "infill"):
            constraints.land_use_status = brief_land
            print(f"    land_use_status overridden by brief: {brief_land}")

    print(f"    Zone area: {constraints.estimated_area_m2:,.0f} m²")
    print(f"    Allowed types: {constraints.allowed_types}")
    print(f"    Restricted: {constraints.restricted_types}")

    # ── 2. INTENT ROUTING — what did the user ask for? ──────────────────────
    print("--- [NODE] INTENT ROUTING ---")
    intent_types = intent_router.route(prompt, brief)
    print(f"    Intent types: {intent_types}")

    # Intersect user intent with zone-allowed types (hard restrictions win)
    if constraints.restricted_types:
        effective_types = [t for t in intent_types if t in constraints.allowed_types]
        if not effective_types:
            # All requested types are blocked — still try green/flood as fallback
            effective_types = [t for t in ["green_space", "flood_management"]
                               if t in constraints.allowed_types] or constraints.allowed_types
            print(f"    WARNING: All requested types restricted — routing to fallback: {effective_types}")
    else:
        effective_types = intent_types

    print(f"    Effective types after zone filter: {effective_types}")

    # Build a rich context string that every agent will receive
    zone_context = constraints.to_prompt_text()

    # ── 3. CONSTRUCTION — generate interventions ────────────────────────────
    print("--- [NODE] CONSTRUCTION ---")
    construction_res = construction_agent.run(
        prompt=prompt,
        zone=zone,
        center=center,
        types_filter=effective_types,
        zone_constraints_text=zone_context,
        brief=brief,
    )
    proposed_actions = construction_res.get("proposed_actions", [])
    if construction_res.get("error"):
        return {"error": construction_res["error"]}
    print(f"    Generated {len(proposed_actions)} interventions of types: "
          f"{list({a.get('type') for a in proposed_actions})}")

    # ── 4. FEASIBILITY — validate against rules + zone constraints ───────────
    print("--- [NODE] FEASIBILITY ---")
    feasibility_res = feasibility_agent.run(
        proposed_actions=proposed_actions,
        prompt=prompt,
        zone_constraints_text=zone_context,
        land_use_status=constraints.land_use_status,
    )
    validated_actions = feasibility_res.get("validated_actions", [])
    feasible_n = sum(1 for a in validated_actions if a.get("feasible"))
    print(f"    {feasible_n}/{len(validated_actions)} actions feasible")

    # ── 5. EVALUATION — impact metrics ──────────────────────────────────────
    print("--- [NODE] EVALUATION ---")
    evaluation_res = evaluation_agent.run(validated_actions, brief=brief)
    impact_metrics = evaluation_res.get("impact_metrics", {})

    # ── 6. ANALYZER — final synthesis ───────────────────────────────────────
    print("--- [NODE] ANALYZER ---")
    analyzer_res = analyzer_agent.run(
        validated_actions=validated_actions,
        impact_metrics=impact_metrics,
        zone_context=zone_context,
        intent_types=effective_types,
        prompt=prompt,
        brief=brief,
    )
    final_analysis = analyzer_res.get("final_analysis", "")

    # ── 7. GEMINI RANKER — optional ─────────────────────────────────────────
    print("--- [NODE] GEMINI RANKER ---")
    per_action_metrics = evaluation_res.get("per_action_metrics", [])
    metrics_with_per = {**impact_metrics, "per_action_metrics": per_action_metrics}
    gemini_result = gemini_ranker.run(proposed_actions, validated_actions, metrics_with_per)

    # ── Build result ────────────────────────────────────────────────────────
    result = {
        "prompt": prompt,
        "intent_types": effective_types,
        "zone_constraints": {
            "allowed": constraints.allowed_types,
            "restricted": constraints.restricted_types,
            "notes": constraints.regulatory_notes,
            "area_m2": round(constraints.estimated_area_m2),
            "land_use_status": constraints.land_use_status,
        },
        "proposed_actions":  proposed_actions,
        "validated_actions": validated_actions,
        "impact_metrics":    impact_metrics,
        "per_action_metrics": per_action_metrics,
        "final_analysis":    final_analysis,
        "geojson_current": (
            {"type": "FeatureCollection",
             "features": [{"type": "Feature", "geometry": zone, "properties": {}}]}
            if zone else {}
        ),
    }
    if gemini_result is not None:
        result["gemini_ranking"] = gemini_result
    return result
