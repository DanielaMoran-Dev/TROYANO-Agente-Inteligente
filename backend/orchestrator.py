"""
Orchestrator — Advanced Version
Coordination logic for multi-agent urban simulation.
"""

from typing import List, Optional
from agents import construction_agent, feasibility_agent, evaluation_agent, analyzer_agent

def run_pipeline(prompt: str, zone: dict = None, center: dict = None) -> dict:
    """
    Execute the full multi-agent urban planning pipeline.
    """
    # 1. CONSTRUCTION
    print("--- [NODE] CONSTRUCTION ---")
    construction_res = construction_agent.run(prompt, zone, center)
    proposed_actions = construction_res.get("proposed_actions", [])
    if construction_res.get("error"):
        return {"error": construction_res["error"]}

    # 2. FEASIBILITY
    print("--- [NODE] FEASIBILITY ---")
    feasibility_res = feasibility_agent.run(proposed_actions, prompt)
    validated_actions = feasibility_res.get("validated_actions", [])

    # 3. EVALUATION
    print("--- [NODE] EVALUATION ---")
    evaluation_res = evaluation_agent.run(validated_actions)
    impact_metrics = evaluation_res.get("impact_metrics", {})

    # 4. ANALYZER
    print("--- [NODE] ANALYZER ---")
    analyzer_res = analyzer_agent.run(validated_actions, impact_metrics)
    final_analysis = analyzer_res.get("final_analysis", "")

    return {
        "prompt": prompt,
        "proposed_actions": proposed_actions,
        "validated_actions": validated_actions,
        "impact_metrics": impact_metrics,
        "final_analysis": final_analysis,
        "geojson_current": {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": zone}]} if zone else {}
    }
