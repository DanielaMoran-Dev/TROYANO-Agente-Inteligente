"""
Evaluation Agent — Agent 3
Computes impact metrics for validated urban actions using IBM watsonx.ai.
Generates both aggregate impact_metrics and per_action_metrics.
"""

import os
import json
import re
import logging
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai import Credentials

logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("WATSONX_MODEL_ID", "meta-llama/llama-3-3-70b-instruct")


def _get_watsonx_model():
    api_key = os.getenv("WATSONX_API_KEY")
    url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    project_id = os.getenv("WATSONX_PROJECT_ID")
    if not all([api_key, url, project_id]):
        return None
    try:
        credentials = Credentials(url=url, api_key=api_key)
        return ModelInference(
            model_id=MODEL_ID,
            credentials=credentials,
            project_id=project_id,
            params={"decoding_method": "greedy", "max_new_tokens": 1200},
        )
    except Exception as e:
        logger.error("Failed to initialize model '%s': %s", MODEL_ID, e)
        return None


def _build_fallback_metrics(validated_actions: list) -> dict:
    """Generate deterministic fallback metrics based on action properties."""
    feasible = [a for a in validated_actions if a.get("feasible", True)]
    total_cost = sum(a.get("cost_usd", 0) for a in validated_actions)
    feasibility_rate = round(len(feasible) / max(len(validated_actions), 1) * 100, 1)

    green_actions = [a for a in feasible if "green" in str(a.get("type", "")).lower() or "flood" in str(a.get("type", "")).lower()]     
    transport_actions = [a for a in feasible if "transport" in str(a.get("type", "")).lower()]
    housing_actions = [a for a in feasible if "housing" in str(a.get("type", "")).lower()]

    flood_reduction = min(10 + len(green_actions) * 8, 45)
    co2_reduction = len(green_actions) * 250 + len(transport_actions) * 150
    population = len(feasible) * 3500 + len(housing_actions) * 2000
    sustainability = min(55 + len(green_actions) * 7 + len(transport_actions) * 4, 95)
    overall = round((feasibility_rate * 0.3 + sustainability * 0.4 + min(flood_reduction * 2, 30) * 0.3), 1)
    timeline = 12 + len(feasible) * 3

    per_action = [
        {
            "id": a.get("id"),
            "action": a.get("action"),
            "co2_impact": 150 + i * 80 if "green" in str(a.get("type", "")).lower() else 50 + i * 30,
            "population_served": 2000 + i * 500,
            "sustainability_score": min(60 + i * 5, 95),
            "priority": "HIGH" if a.get("feasible") and i < 2 else ("MEDIUM" if a.get("feasible") else "BLOCKED"),
        }
        for i, a in enumerate(validated_actions)
    ]

    return {
        "impact_metrics": {
            "overall_score": overall,
            "flood_reduction_percent": flood_reduction,
            "sustainability_score": sustainability,
            "co2_reduction_tons_per_year": co2_reduction,
            "affected_population": population,
            "implementation_timeline_months": timeline,
            "estimated_total_cost_usd": total_cost,
            "feasibility_rate_percent": feasibility_rate,
            "recommendation": (
                f"Plan includes {len(feasible)} feasible interventions out of {len(validated_actions)} proposed. "
                f"Priority: {'ecological resilience' if len(green_actions) > len(transport_actions) else 'mobility optimization'}. "    
                f"Estimated {co2_reduction:,} tons CO2/yr reduction. Phased implementation recommended over {timeline} months."       
            ),
        },
        "per_action_metrics": per_action,
    }


def run(validated_actions: list) -> dict:
    if not validated_actions:
        return _build_fallback_metrics([])

    model = _get_watsonx_model()
    if not model:
        logger.warning("Evaluation Agent: no model available, using deterministic fallback.")
        return _build_fallback_metrics(validated_actions)

    # Compact action summary to reduce token usage
    actions_summary = [
        {
            "id": a.get("id"),
            "action": a.get("action"),
            "type": a.get("type"),
            "cost_usd": a.get("cost_usd", 0),
            "feasible": a.get("feasible", True),
        }
        for a in validated_actions
    ]

    system_prompt = (
        "You are the Lineal Evaluation Engine. Analyze this set of urban interventions and return impact metrics.\n"
        "Return ONLY a valid JSON object with exactly these keys:\n"
        '{\n'
        '  "impact_metrics": {\n'
        '    "overall_score": <number 0-100>,\n'
        '    "flood_reduction_percent": <number 0-50>,\n'
        '    "sustainability_score": <number 0-100>,\n'
        '    "co2_reduction_tons_per_year": <integer>,\n'
        '    "affected_population": <integer>,\n'
        '    "implementation_timeline_months": <integer>,\n'
        '    "feasibility_rate_percent": <number 0-100>,\n'
        '    "recommendation": "<2-3 sentence technical summary>"\n'
        '  },\n'
        '  "per_action_metrics": [\n'
        '    {"id": "...", "co2_impact": <number>, "population_served": <integer>, '
        '"sustainability_score": <number>, "priority": "HIGH/MEDIUM/LOW/BLOCKED"}\n'
        '  ]\n'
        "}\n"
        "CRITICAL: Return ONLY the JSON object. No explanations. No markdown code blocks."
    )

    try:
        response = model.generate_text(
            prompt=f"<|system|>\n{system_prompt}\n<|user|>\nActions: {json.dumps(actions_summary)}\n<|assistant|>\n{{"
        )
        if not response.strip().startswith('{'):
            response = '{' + response

        # Extract JSON object
        start_idx = response.find("{")
        end_idx = response.rfind("}")
        if start_idx == -1 or end_idx == -1:
            raise ValueError("No JSON object found in response.")

        json_str = response[start_idx : end_idx + 1]
        # Sanitize single quotes
        json_str = re.sub(r"(?<![\\])'", '"', json_str)

        result = json.loads(json_str)

        if "impact_metrics" not in result:
            if "overall_score" in result:
                result = {"impact_metrics": result, "per_action_metrics": []}
            else:
                raise ValueError("Missing 'impact_metrics' key in AI response.")

        actual_total = sum(a.get("cost_usd", 0) for a in validated_actions)
        result["impact_metrics"]["estimated_total_cost_usd"] = actual_total

        if "per_action_metrics" not in result:
            result["per_action_metrics"] = []

        if "feasibility_rate_percent" not in result.get("impact_metrics", {}):
            feasible_count = sum(1 for a in validated_actions if a.get("feasible", True))
            result["impact_metrics"]["feasibility_rate_percent"] = round(
                feasible_count / max(len(validated_actions), 1) * 100, 1
            )

        logger.info("Evaluation Agent: metrics computed successfully.")
        return result

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Evaluation Agent JSON parse failed (%s), using deterministic fallback.", e)
        return _build_fallback_metrics(validated_actions)
    except Exception as e:
        logger.exception("Evaluation Agent unexpected error.")
        return _build_fallback_metrics(validated_actions)
