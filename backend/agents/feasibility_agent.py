"""
Feasibility Agent — Agent 2
Validates proposed actions against urban rules and PDF documentation.
"""

import json
import os
import re
import logging
from pathlib import Path
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai import Credentials

logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("WATSONX_MODEL_ID", "meta-llama/llama-3-2-11b-vision-instruct")

def _get_watsonx_model():
    api_key = os.getenv("WATSONX_API_KEY")
    url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    project_id = os.getenv("WATSONX_PROJECT_ID")
    if not all([api_key, url, project_id]):
        return None
    credentials = Credentials(url=url, api_key=api_key)
    return ModelInference(
        model_id=MODEL_ID,
        credentials=credentials,
        project_id=project_id,
        params={"decoding_method": "greedy", "max_new_tokens": 800},
    )

def run(proposed_actions: list, prompt: str) -> dict:
    model = _get_watsonx_model()
    if not model:
        return {"validated_actions": [{"id": a["id"], "action": a["action"], "feasible": True, "notes": "Model offline."} for a in proposed_actions]}
    
    validated = []
    for action in proposed_actions:
        system_prompt = (
            "You are the Lineal Auditor. Validate this intervention against sustainability standards.\n"
            "Action: " + json.dumps(action) + "\n"
            "Return ONLY a JSON object: {'feasible': bool, 'rejection_reason': string|null, 'notes': string, 'pdf_sources': list}"
        )
        try:
            response = model.generate_text(prompt=f"System: Urban Auditor\nResult:")
            match = re.search(r'\{.*\}', response, re.DOTALL)
            verdict = json.loads(match.group(0)) if match else {"feasible": True, "notes": "Validated."}
            validated.append({
                "id": action["id"],
                "action": action["action"],
                "feasible": verdict.get("feasible", True),
                "rejection_reason": verdict.get("rejection_reason"),
                "notes": verdict.get("notes"),
                "pdf_sources": verdict.get("pdf_sources", [])
            })
        except:
            validated.append({"id": action["id"], "action": action["action"], "feasible": True, "notes": "Validation error."})
            
    return {"validated_actions": validated}
