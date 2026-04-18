"""
Recommendation Agent — genera recomendaciones empáticas con Gemini + LLM Wiki.

Relación de red (según DATABASE_SCHEMA.md):
  - `clinics.doctor_id` apunta a `doctors._id`.
  - Una clínica está "en red" cuando su doctor está activo, is_network=True.
"""

import json
import logging
import os

from bson import ObjectId

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


async def _identify_network_doctors(clinic_candidates: list[dict]) -> dict[str, dict]:
    """
    Devuelve {clinic_id: {doctor_id, name, specialty}} para las clínicas
    cuyo doctor_id referencia a un doctor activo en red.
    """
    doctor_ids: list[ObjectId] = []
    clinic_to_doctor: dict[str, ObjectId] = {}

    for c in clinic_candidates:
        did = c.get("doctor_id")
        cid = c.get("clinic_id")
        if did and cid:
            try:
                obj_id = did if isinstance(did, ObjectId) else ObjectId(str(did))
                doctor_ids.append(obj_id)
                clinic_to_doctor[cid] = obj_id
            except Exception:
                continue

    if not doctor_ids:
        return {}

    try:
        cursor = mongo_service.doctors().find(
            {"_id": {"$in": doctor_ids}, "is_active": True, "is_network": True},
            {"_id": 1, "name": 1, "last_name": 1, "specialty": 1},
        )
        active_doctors: dict[ObjectId, dict] = {doc["_id"]: doc async for doc in cursor}
    except Exception as e:
        logger.warning("Could not query doctors collection: %s", e)
        return {}

    network_map: dict[str, dict] = {}
    for clinic_id, obj_id in clinic_to_doctor.items():
        doc = active_doctors.get(obj_id)
        if doc:
            full_name = " ".join(filter(None, [doc.get("name"), doc.get("last_name")]))
            network_map[clinic_id] = {
                "doctor_id": str(obj_id),
                "name": full_name.strip(),
                "specialty": doc.get("specialty"),
            }
    return network_map


def _build_patient_summary(ctx: dict) -> str:
    """Returns a patient profile string for the recommendation prompt."""
    parts = []
    if ctx.get("age"):
        parts.append(f"Edad: {ctx['age']} años")
    if ctx.get("conditions"):
        parts.append(f"Antecedentes: {', '.join(ctx['conditions'])}")
    if ctx.get("allergies"):
        parts.append(f"⚠️ Alergias: {', '.join(ctx['allergies'])}")
    if ctx.get("medications"):
        parts.append(f"Medicamentos actuales: {', '.join(ctx['medications'])}")
    if ctx.get("insurance"):
        parts.append(f"Seguro: {ctx['insurance']}")
    return "\n".join(parts)


async def run(routing: list[dict], triage: dict, patient_context: dict | None = None) -> dict:
    """
    Args:
        routing:         lista rankeada del routing_agent.run()
        triage:          output del triage_agent.run()
        patient_context: optional dict with age, conditions, allergies, medications, insurance

    Returns:
        dict con `recommendations` y opcional `urgent_message`.
    """
    urgency = triage.get("urgency_level", "medium")
    specialty = triage.get("specialty", "")

    top_clinics = routing[:5]
    network_map = await _identify_network_doctors(top_clinics)

    # Contexto para el LLM — sólo datos que el modelo usa para redactar
    clinics_context = json.dumps(
        [
            {
                "clinic_id": c.get("clinic_id"),
                "name": c.get("name"),
                "specialty": c.get("specialty"),
                "price_level": c.get("price_level"),
                "insurances": c.get("insurances") or [],
                "travel_time_min": c.get("travel_time_min"),
                "phone": c.get("phone"),
                "address": c.get("address"),
                "is_network": c.get("clinic_id") in network_map,
            }
            for c in top_clinics
        ],
        ensure_ascii=False,
    )

    patient_summary = _build_patient_summary(patient_context or {})
    patient_block = f"\nPERFIL DEL PACIENTE:\n{patient_summary}\n" if patient_summary else ""

    wiki = _load_wiki()
    system = SYSTEM_PROMPT_TEMPLATE.format(wiki=wiki)

    prompt = f"""Nivel de urgencia: {urgency}
Especialidad requerida: {specialty}
Resumen clínico: {triage.get('clinical_summary', '')}
{patient_block}
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
        raw = gemini_service.generate(prompt, system=system)
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(raw)
    except Exception as e:
        logger.error("Recommendation agent error: %s", e)
        result = _fallback_recommendations(top_clinics, network_map, urgency)

    # Enriquecer con datos reales — la verdad viene de Mongo, no del LLM
    for rec in result.get("recommendations", []):
        clinic_id = rec.get("clinic_id", "")
        source = next((c for c in top_clinics if c.get("clinic_id") == clinic_id), {})

        if source.get("lat") is not None and source.get("lng") is not None:
            rec["coords"] = {"lat": source["lat"], "lng": source["lng"]}
        if not rec.get("travel_time_min") and source.get("travel_time_min"):
            rec["travel_time_min"] = source["travel_time_min"]

        contact = rec.setdefault("contact", {})
        if clinic_id in network_map:
            rec["is_network"] = True
            contact["type"] = "chat"
            contact["doctor_id"] = network_map[clinic_id]["doctor_id"]
        else:
            rec["is_network"] = False
            contact["type"] = "info"
            contact["doctor_id"] = None
            contact["phone"] = source.get("phone")
            contact["address"] = source.get("address")

    return result


def _fallback_recommendations(clinics: list[dict], network_map: dict, urgency: str) -> dict:
    """Recomendaciones mínimas cuando Gemini falla."""
    recs = []
    for i, c in enumerate(clinics[:3], start=1):
        cid = c.get("clinic_id", "")
        is_net = cid in network_map
        recs.append({
            "clinic_id": cid,
            "justification": "Opción recomendada según tu especialidad y ubicación.",
            "is_network": is_net,
            "priority": i,
            "contact": {
                "type": "chat" if is_net else "info",
                "doctor_id": network_map[cid]["doctor_id"] if is_net else None,
                "phone": c.get("phone"),
                "address": c.get("address"),
            },
            "coords": {"lat": c.get("lat"), "lng": c.get("lng")} if c.get("lat") else {},
            "travel_time_min": c.get("travel_time_min"),
        })
    return {
        "recommendations": recs,
        "urgent_message": "Busca atención inmediata." if urgency == "critical" else None,
    }
