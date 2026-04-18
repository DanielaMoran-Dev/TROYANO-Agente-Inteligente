"""
Triage Agent — classifies patient symptoms using Gemini + medical wiki RAG.
Wiki context is built dynamically from JSON knowledge bases (triage, GPC, CIE-10, síntomas).
"""

import json
import logging

from services import gemini_service, wiki_service

logger = logging.getLogger(__name__)

_BASE_SYSTEM = """Eres un sistema experto de triaje médico para México.
Tu tarea es analizar síntomas en lenguaje natural y clasificarlos con precisión clínica.
Usa el conocimiento médico provisto y el contexto del paciente para determinar urgencia,
especialidad y unidad adecuada. Ten en cuenta edad, antecedentes, alergias y medicamentos
actuales al formular el resumen clínico y las señales de alarma.
Responde ÚNICAMENTE con un JSON válido, sin texto adicional, con esta estructura exacta:
{
  "urgency_level": "low | medium | critical",
  "unit_type": "urgencias | general | especialista",
  "specialty": "<especialidad médica en español>",
  "triage_priority": <número 1-5 según Manchester>,
  "cie10_probable": "<código CIE-10 más probable>",
  "clinical_summary": "<resumen en 2-3 oraciones para el médico, incluyendo contexto del paciente>",
  "reasoning": "<justificación basada en señales de alarma, edad, antecedentes o ausencia de ellos>",
  "red_flags": ["<señal de alarma detectada>"]
}"""


def _build_patient_section(ctx: dict) -> str:
    """Builds patient context block to inject into the system prompt."""
    parts = []
    if ctx.get("age"):
        parts.append(f"Edad: {ctx['age']} años")
    if ctx.get("duration"):
        parts.append(f"Duración de síntomas: {ctx['duration']}")
    if ctx.get("severity"):
        parts.append(f"Severidad percibida por el paciente: {ctx['severity']}")
    if ctx.get("conditions"):
        parts.append(f"Condiciones preexistentes: {', '.join(ctx['conditions'])}")
    if ctx.get("allergies"):
        parts.append(f"⚠️ ALERGIAS CONOCIDAS: {', '.join(ctx['allergies'])}")
    if ctx.get("medications"):
        parts.append(f"Medicamentos actuales: {', '.join(ctx['medications'])}")
    if ctx.get("blood_type"):
        parts.append(f"Tipo de sangre: {ctx['blood_type']}")
    if ctx.get("insurance"):
        parts.append(f"Seguro médico: {ctx['insurance']}")
    if not parts:
        return ""
    return "\n\nCONTEXTO DEL PACIENTE:\n" + "\n".join(parts)


async def run(symptoms: str, patient_context: dict | None = None) -> dict:
    """
    Args:
        symptoms:        Free-text symptom description from the patient.
        patient_context: Optional dict with: age, duration, severity, conditions,
                         allergies, medications, blood_type, insurance.

    Returns:
        dict with urgency_level, unit_type, specialty, triage_priority,
        cie10_probable, clinical_summary, reasoning, red_flags.
    """
    # Semantic RAG: retrieve the most relevant GPC passages for these symptoms
    rag_passages = await wiki_service.retrieve_wiki_rag(symptoms, limit=6)
    if rag_passages:
        logger.info("Wiki RAG: %d passages retrieved for triage", len(rag_passages))
    else:
        logger.info("Wiki RAG unavailable, using keyword fallback")

    wiki_context = wiki_service.build_triage_context(symptoms, rag_passages=rag_passages)
    patient_section = _build_patient_section(patient_context or {})
    system = f"{_BASE_SYSTEM}\n\nCONOCIMIENTO MÉDICO DE REFERENCIA:\n{wiki_context}{patient_section}"
    prompt = f"Síntomas del paciente: {symptoms}"

    try:
        raw = gemini_service.generate(prompt, system=system)
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(raw)
        result.setdefault("red_flags", [])
        return result
    except json.JSONDecodeError as e:
        logger.error("Triage JSON parse error: %s — raw: %s", e, raw)
        return {
            "urgency_level": "medium",
            "unit_type": "general",
            "specialty": "medicina general",
            "triage_priority": 3,
            "cie10_probable": "",
            "clinical_summary": symptoms,
            "reasoning": "Error al parsear respuesta del modelo; triaje por defecto.",
            "red_flags": [],
        }
    except Exception as e:
        logger.error("Triage agent error: %s", e)
        raise
