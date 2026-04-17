"""
Triage Agent — classifies patient symptoms using Gemini Pro + LLM Wiki.
No RAG: knowledge is embedded in the system prompt for maximum reliability.
"""

import json
import logging
import os

from services import gemini_service

logger = logging.getLogger(__name__)

_WIKI_PATH = os.path.join(os.path.dirname(__file__), "../wiki/triage_wiki.md")


def _load_wiki() -> str:
    try:
        with open(_WIKI_PATH, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("triage_wiki.md not found, using empty wiki")
        return ""


SYSTEM_PROMPT = f"""Eres un sistema de triaje médico inteligente.
Tu tarea es analizar síntomas descritos en lenguaje natural y clasificarlos.

CONOCIMIENTO DE TRIAJE:
{_load_wiki()}

Responde ÚNICAMENTE con un JSON válido, sin texto adicional, con esta estructura:
{{
  "urgency_level": "low | medium | critical",
  "unit_type": "urgencias | general | especialista",
  "specialty": "<nombre de especialidad médica en español>",
  "clinical_summary": "<resumen estructurado en 2-3 oraciones para el médico>",
  "reasoning": "<justificación de la clasificación en 1-2 oraciones>"
}}
"""


def run(symptoms: str) -> dict:
    """
    Args:
        symptoms: free-text symptom description from the patient.

    Returns:
        dict with urgency_level, unit_type, specialty, clinical_summary, reasoning.
    """
    prompt = f"Síntomas del paciente: {symptoms}"
    try:
        raw = gemini_service.generate(prompt, system=SYSTEM_PROMPT)
        # Strip markdown code fences if present
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Triage JSON parse error: %s — raw: %s", e, raw)
        return {
            "urgency_level": "medium",
            "unit_type": "general",
            "specialty": "medicina general",
            "clinical_summary": symptoms,
            "reasoning": "Error al parsear respuesta del modelo; triaje por defecto.",
        }
    except Exception as e:
        logger.error("Triage agent error: %s", e)
        raise
