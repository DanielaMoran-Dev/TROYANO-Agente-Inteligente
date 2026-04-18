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
Usa el conocimiento médico provisto para determinar urgencia, especialidad y unidad adecuada.
Responde ÚNICAMENTE con un JSON válido, sin texto adicional, con esta estructura exacta:
{
  "urgency_level": "low | medium | critical",
  "unit_type": "urgencias | general | especialista",
  "specialty": "<especialidad médica en español>",
  "triage_priority": <número 1-5 según Manchester>,
  "cie10_probable": "<código CIE-10 más probable>",
  "clinical_summary": "<resumen en 2-3 oraciones para el médico>",
  "reasoning": "<justificación basada en señales de alarma o ausencia de ellas>"
}"""


def run(symptoms: str) -> dict:
    """
    Args:
        symptoms: free-text symptom description from the patient.

    Returns:
        dict with urgency_level, unit_type, specialty, triage_priority,
        cie10_probable, clinical_summary, reasoning.
    """
    wiki_context = wiki_service.build_triage_context(symptoms)
    system = f"{_BASE_SYSTEM}\n\nCONOCIMIENTO MÉDICO DE REFERENCIA:\n{wiki_context}"
    prompt = f"Síntomas del paciente: {symptoms}"

    try:
        raw = gemini_service.generate(prompt, system=system)
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(raw)
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
        }
    except Exception as e:
        logger.error("Triage agent error: %s", e)
        raise
