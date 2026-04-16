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

def run(
    validated_actions: list,
    impact_metrics: dict,
    zone_context: str = "",
    intent_types: list = None,
    prompt: str = "",
    brief: dict = None,
) -> dict:
    model = _get_watsonx_model()

    feasible   = [a for a in validated_actions if a.get("feasible")]
    blocked    = [a for a in validated_actions if not a.get("feasible")]
    types_used = list({a.get("type", "unknown") for a in feasible})
    score      = impact_metrics.get("overall_score", "N/A")
    cost_m     = impact_metrics.get("estimated_total_cost_usd", 0) / 1e6
    pop        = impact_metrics.get("affected_population", 0)
    co2        = impact_metrics.get("co2_reduction_tons_per_year", 0)

    # Build a human-readable brief summary for the analysis context
    brief_summary = ""
    if brief:
        budget = brief.get("budget_usd", 0)
        years  = brief.get("timeline_years", 0)
        desc   = brief.get("project_description", "")
        land   = {"extension": "terreno vacío", "infill": "zona edificada", "urban_renewal": "renovación urbana"}.get(
            brief.get("land_status", ""), "zona urbana")
        brief_summary = (
            f"Client brief: {desc[:120]}. "
            f"Land: {land}. "
            f"Budget: ${budget:,} USD. Timeline: {years} years. "
        )

    if not model:
        intent_str = ", ".join(intent_types) if intent_types else "planificación urbana general"
        user_context = f"Client request: \"{prompt[:100]}\"" if prompt else ""
        blocked_str = (
            "  " + "; ".join(a.get('action','?') + ' — ' + (a.get('rejection_reason') or 'normativa') for a in blocked)
            if blocked else "  Ninguna bloqueada."
        )
        feasible_str = "\n".join(f"  • {a.get('action','?')} ({a.get('type','?')}) — ${a.get('cost_usd',0)/1e6:.1f}M" for a in feasible)

        return {
            "final_analysis": (
                f"[CITY_STATE_SYNERGY]\n"
                f"{user_context} {brief_summary}"
                f"Se propusieron {len(validated_actions)} intervenciones de tipo {intent_str}, "
                f"de las cuales {len(feasible)} son factibles. "
                f"Tipos aprobados: {', '.join(types_used) or 'mixto'}. "
                f"Puntuación urbana global: {score}%. Inversión total: ${cost_m:.1f}M USD. "
                f"Población beneficiada: {pop:,} hab.\n"
                f"Intervenciones aprobadas:\n{feasible_str}\n\n"
                f"[CRITICAL_RISK_ASSESSMENT]\n"
                f"Intervenciones bloqueadas por normativa: {blocked_str}\n"
                f"{'Desarrollo de alta densidad requiere varianza PMDU para altura.' if 'housing' in (intent_types or []) else ''} "
                f"{'Espacios verdes sin conflicto normativo detectado.' if 'green_space' in (intent_types or []) else ''} "
                f"Restricciones SIIMP aplicadas: {zone_context[:80] if zone_context else 'Sin restricciones adicionales'}.\n\n"
                f"[LONG_TERM_SUSTAINABILITY_VECTOR]\n"
                f"Reducción proyectada de CO₂: {co2:,} t/año. "
                f"Implementación en fases recomendada según horizonte de {brief.get('timeline_years', 5) if brief else 5} años. "
                f"{'Corredores ecológicos fortalecen la resiliencia urbana.' if 'green_space' in (intent_types or []) else ''} "
                f"{'Incluir unidades accesibles según lineamientos de inclusión social.' if 'housing' in (intent_types or []) else ''}"
            )
        }

    system_prompt = (
        "You are the Lineal Lead City Analyzer. Write a concise technical urban planning report in Spanish.\n"
        "Use exactly these section headers: [CITY_STATE_SYNERGY], [CRITICAL_RISK_ASSESSMENT], [LONG_TERM_SUSTAINABILITY_VECTOR].\n"
        "Each section: 2-3 sentences max. No bullet points. No asterisks. No quotes. Plain text only.\n"
        f"Client request: \"{prompt[:200]}\"\n"
        f"Brief: {brief_summary}\n"
        f"Focus on types: {', '.join(intent_types) if intent_types else 'planificación urbana general'}.\n"
        f"Zone context: {zone_context or 'Sin restricciones.'}"
    )

    try:
        input_data = {
            "actions": validated_actions,
            "metrics": impact_metrics,
            "intent": intent_types,
        }
        response = model.generate_text(
            prompt=f"<|system|>\n{system_prompt}\n<|user|>\nData: {json.dumps(input_data)}\n<|assistant|>\n[CITY_STATE_SYNERGY]"
        )
        if not response.strip().startswith("["):
            response = "[CITY_STATE_SYNERGY]\n" + response
        return {"final_analysis": response.strip()}
    except Exception as e:
        return {"final_analysis": f"ANALYSIS_FAILED: {str(e)}"}
