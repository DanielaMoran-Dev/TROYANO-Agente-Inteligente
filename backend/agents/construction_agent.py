"""
Construction Agent — Agent 1
Generates urban planning actions from a user prompt using IBM watsonx.ai.
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
            params={"decoding_method": "greedy", "max_new_tokens": 1500},
        )
    except Exception as e:
        logger.error("Failed to initialize model '%s': %s", MODEL_ID, e)
        return None

def run(prompt: str, zone: dict = None, center: dict = None) -> dict:
    model = _get_watsonx_model()
    
    lat = center.get('lat', 21.88) if center else 21.88
    lng = center.get('lng', -102.29) if center else -102.29

    if not model:
        logger.warning("Construction Agent: Model credentials not found. Using fallback simulation data (Demo Mode).")
        return {"proposed_actions": _build_fallback_actions(lat, lng, prompt)}
    zone_str = json.dumps(zone) if zone else "Not provided"
    
    system_prompt = (
        "You are the Lineal Generative Engine. Design a realistic urban simulation.\n"
        f"CONTEXT: Center at {lat}, {lng}. Zone: {zone_str}.\n"
        "Task: Create 4-8 interventions spread across the zone.\n"
        "Categories: 'housing', 'transport', 'green_space', 'flood_management', 'infrastructure'.\n"
        "Return ONLY a valid JSON array. No markdown, no explanation, no extra text.\n"
        'Example format: [{"action":"...","type":"...","description":"...","cost_usd":1000000,"latitude":0.0,"longitude":0.0,"visual_params":{"building_count":1,"height_floors":5,"area_m2":5000}}]'
    )

    try:
        response = model.generate_text(
            prompt=f"<|system|>\n{system_prompt}\n<|user|>\n{prompt}\n<|assistant|>\n["
        )
        # Model may omit the opening bracket since we seeded it
        if not response.strip().startswith('['):
            response = '[' + response
        logger.info("Construction Agent raw response: %s", response[:500])

        start_idx = response.find('[')
        end_idx = response.rfind(']')
        if start_idx == -1 or end_idx == -1:
            raise ValueError("No JSON array found.")

        actions = json.loads(response[start_idx:end_idx+1])
        for idx, a in enumerate(actions):
            a["id"] = f"action_{idx+1:03d}"
            if "cost_usd" not in a: a["cost_usd"] = 1000000

        return {"proposed_actions": actions}
    except Exception as e:
        logger.warning("Construction Agent failed (%s), using fallback actions.", e)
        return {"proposed_actions": _build_fallback_actions(lat, lng, prompt)}


def _build_fallback_actions(lat: float, lng: float, prompt: str) -> list:
    offsets = [
        (0.005,  0.003), (-0.004,  0.006), (0.002, -0.007),
        (-0.006, -0.002), (0.008,  0.001), (-0.001,  0.009),
    ]
    templates = [
        {"action": "Green Corridor", "type": "green_space",
         "description": "Linear park with native vegetation for flood drainage and CO2 capture.",
         "cost_usd": 2500000,
         "visual_params": {"building_count": 0, "height_floors": 0, "area_m2": 18000}},
        {"action": "BRT Transit Corridor", "type": "transport",
         "description": "Bus rapid transit lane with dedicated infrastructure and smart signals.",
         "cost_usd": 8000000,
         "visual_params": {"building_count": 3, "height_floors": 2, "area_m2": 5000}},
        {"action": "Flood Retention Basin", "type": "flood_management",
         "description": "Underground retention basin to mitigate peak stormwater runoff.",
         "cost_usd": 4500000,
         "visual_params": {"building_count": 0, "height_floors": 0, "area_m2": 12000}},
        {"action": "Mixed-Use Housing Tower", "type": "housing",
         "description": "High-density residential tower with ground-level commercial use.",
         "cost_usd": 15000000,
         "visual_params": {"building_count": 1, "height_floors": 20, "area_m2": 3000}},
        {"action": "Solar Microgrid Hub", "type": "infrastructure",
         "description": "Distributed solar energy generation with battery storage for resilience.",
         "cost_usd": 3200000,
         "visual_params": {"building_count": 2, "height_floors": 1, "area_m2": 4000}},
        {"action": "Permeable Pavement District", "type": "flood_management",
         "description": "Permeable surface replacement to reduce urban heat island and flooding.",
         "cost_usd": 1800000,
         "visual_params": {"building_count": 0, "height_floors": 0, "area_m2": 9000}},
    ]
    actions = []
    for idx, (dlat, dlng) in enumerate(offsets):
        t = templates[idx % len(templates)].copy()
        t["id"] = f"action_{idx+1:03d}"
        t["latitude"] = round(lat + dlat, 6)
        t["longitude"] = round(lng + dlng, 6)
        actions.append(t)
    return actions
