"""
Analyzer Agent — Agent 4
Produces a holistic urban planning report by synthesizing all pipeline outputs.
"""

import os
import json
import logging
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai import Credentials

logger = logging.getLogger(__name__)

def _get_watsonx_model():
    api_key = os.getenv("WATSONX_API_KEY")
    url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    project_id = os.getenv("WATSONX_PROJECT_ID")
    if not all([api_key, url, project_id]):
        return None
    try:
        credentials = Credentials(url=url, api_key=api_key)
        return ModelInference(
            model_id=os.getenv("WATSONX_MODEL_ID", "meta-llama/llama-3-3-70b-instruct"),
            credentials=credentials,
            project_id=project_id,
            params={
                "decoding_method": "greedy",
                "max_new_tokens": 600,
                "stop_sequences": ["END OF REPORT", "---END---", "\n\n\n"],
            },
        )
    except Exception as e:
        logger.error("Failed to initialize analyzer model: %s", e)
        return None

def run(validated_actions: list, impact_metrics: dict) -> dict:
    model = _get_watsonx_model()
    if not model:
        return {
            "final_analysis": (
                "[CITY_STATE_SYNERGY]\n"
                "In demo mode, the synergy analysis reflects a baseline urban model optimization. "
                "The proposed interventions demonstrate a constructive alignment with identified city growth vectors.\n\n"
                "[CRITICAL_RISK_ASSESSMENT]\n"
                "Atmospheric risk levels remain within nominal parameters. Further integration of 'active' mitigation "
                "strategies is recommended for long-term resilience.\n\n"
                "[LONG_TERM_SUSTAINABILITY_VECTOR]\n"
                "The simulation indicates a positive trajectory for carbon sequestration and urban density balance."
            )
        }

    system_prompt = (
        "You are the Lineal Lead City Analyzer. Write a technical urban planning report.\n"
        "Sections: [CITY_STATE_SYNERGY], [CRITICAL_RISK_ASSESSMENT], [LONG_TERM_SUSTAINABILITY_VECTOR].\n"
        "IMPORTANT: Be concise. No repetition. No asterisks. No quotes."
    )

    try:
        input_data = {"actions": validated_actions, "metrics": impact_metrics}
        response = model.generate_text(
            prompt=f"<|system|>\n{system_prompt}\n<|user|>\nData: {json.dumps(input_data)}\n<|assistant|>\n[CITY_STATE_SYNERGY]"
        )
        if not response.strip().startswith('['):
            response = '[CITY_STATE_SYNERGY]\n' + response
        return {"final_analysis": response.strip()}
    except Exception as e:
        return {"final_analysis": f"ANALYSIS_FAILED: {str(e)}"}
