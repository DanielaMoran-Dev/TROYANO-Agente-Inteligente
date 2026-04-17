"""
Recommendation Agent — generates empathetic, structured recommendations using Gemini Pro + LLM Wiki.
Identifies which clinics have doctors in the network and routes accordingly.
"""

import json
import logging
import os

from services import gemini_service, mongo_service

logger = logging.getLogger(__name__)

_WIKI_PATH = os.path.join(os.path.dirname(__file__), "../wiki/recommendation_wiki.md")


def _load_wiki() -> str:
    try:
        with open(_WIKI_PATH, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


SYSTEM_PROMPT_TEMPLATE = """Eres un asistente médico empático y claro.
Tu tarea es generar recomendaciones de clínicas y doctores para un paciente.

REGLAS DE TONO Y FORMATO:
{wiki}

Responde ÚNICAMENTE con un JSON válido sin texto adicional.
"""


async def run(routing: list[dict], triage: dict) -> dict:
    """
    Args:
        routing: ranked clinic list from routing_agent.run()
        triage:  output from triage_agent.run()

    Returns:
        dict with recommendations list and optional urgent_message.
    """
    urgency = triage.get("urgency_level", "medium")
    specialty = triage.get("specialty", "")

    # Identify which clinics have doctors in our network
    top_clinics = routing[:5]
    clinic_ids = [c.get("clinic_id", "") for c in top_clinics]

    network_doctor_map: dict[str, dict] = {}
    try:
        cursor = mongo_service.doctors().find(
            {"clinic_id": {"$in": clinic_ids}, "is_active": True},
            {"_id": 0, "doctor_id": {"$toString": "$_id"}, "name": 1, "clinic_id": 1},
        )
        async for doc in cursor:
            network_doctor_map[doc["clinic_id"]] = doc
    except Exception as e:
        logger.warning("Could not query doctors collection: %s", e)

    # Build context for the LLM
    clinics_context = json.dumps(
        [
            {
                "name": c.get("name"),
                "specialty": c.get("specialty"),
                "budget_level": c.get("budget_level"),
                "travel_time_min": c.get("travel_time_min"),
                "phone": c.get("phone"),
                "address": c.get("address"),
                "is_network": c.get("clinic_id", "") in network_doctor_map,
            }
            for c in top_clinics
        ],
        ensure_ascii=False,
    )

    wiki = _load_wiki()
    system = SYSTEM_PROMPT_TEMPLATE.format(wiki=wiki)

    prompt = f"""Nivel de urgencia: {urgency}
Especialidad requerida: {specialty}
Resumen clínico: {triage.get('clinical_summary', '')}

Opciones disponibles (ordenadas por ranking):
{clinics_context}

Genera recomendaciones para máximo 3 opciones. Formato JSON:
{{
  "recommendations": [
    {{
      "clinic_id": "...",
      "justification": "texto empático y claro en español",
      "is_network": true | false,
      "priority": 1,
      "contact": {{
        "type": "chat | info",
        "doctor_id": "... (solo si is_network)",
        "phone": "...",
        "address": "..."
      }},
      "coords": {{ "lat": 0.0, "lng": 0.0 }},
      "travel_time_min": 0
    }}
  ],
  "urgent_message": "texto urgente si urgency=critical, sino null"
}}"""

    try:
        raw = gemini_service.generate(prompt, system=system, model="gemini-1.5-pro")
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(raw)
    except Exception as e:
        logger.error("Recommendation agent error: %s", e)
        result = _fallback_recommendations(top_clinics, network_doctor_map, urgency)

    # Enrich with real doctor_ids and coords from our data
    for rec in result.get("recommendations", []):
        clinic_id = rec.get("clinic_id", "")
        source = next((c for c in top_clinics if c.get("clinic_id") == clinic_id), {})
        if source.get("coords"):
            rec["coords"] = source["coords"]
        if not rec.get("travel_time_min") and source.get("travel_time_min"):
            rec["travel_time_min"] = source["travel_time_min"]
        if clinic_id in network_doctor_map:
            rec["is_network"] = True
            rec.setdefault("contact", {})["doctor_id"] = network_doctor_map[clinic_id].get("doctor_id")
            rec["contact"]["type"] = "chat"

    return result


def _fallback_recommendations(clinics, doctor_map, urgency) -> dict:
    """Minimal fallback when Gemini is unavailable."""
    recs = []
    for i, c in enumerate(clinics[:3], start=1):
        cid = c.get("clinic_id", "")
        is_net = cid in doctor_map
        recs.append({
            "clinic_id": cid,
            "justification": f"Opción recomendada según tu especialidad y ubicación.",
            "is_network": is_net,
            "priority": i,
            "contact": {
                "type": "chat" if is_net else "info",
                "doctor_id": doctor_map[cid].get("doctor_id") if is_net else None,
                "phone": c.get("phone"),
                "address": c.get("address"),
            },
            "coords": c.get("coords", {}),
            "travel_time_min": c.get("travel_time_min"),
        })
    return {
        "recommendations": recs,
        "urgent_message": "Busca atención inmediata." if urgency == "critical" else None,
    }
