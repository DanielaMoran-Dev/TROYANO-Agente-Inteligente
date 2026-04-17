"""
Chat Agent — conversational data-collection front-end for the consult pipeline.

Holds a Gemini chat session per patient session_id, asks one question at a time,
and signals `ready: true` when it has gathered enough data to call /consult.
"""

import json
import logging
import re

from services import gemini_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres MedConnect, un asistente médico conversacional en español.

OBJETIVO: Recolectar la información mínima necesaria para recomendar al paciente
una clínica adecuada. NO emitas diagnóstico ni triaje; solo recolecta datos.

DATOS A RECOLECTAR (en este orden, una pregunta por turno):
  1. symptoms        — descripción de los síntomas principales
  2. duration        — desde cuándo / cuánto tiempo llevan
  3. severity        — intensidad o si hay señales de alarma (fiebre alta,
                       dificultad para respirar, dolor en el pecho, sangrado, etc.)
  4. age             — edad del paciente
  5. location_text   — ciudad, colonia o código postal (sólo si el frontend NO
                       envió coordenadas; si te indican que ya hay ubicación,
                       OMITE esta pregunta)

REGLAS DE CONVERSACIÓN:
- Una sola pregunta por turno. Espera la respuesta del usuario antes de seguir.
- Sé empático y breve (máximo 2 oraciones por turno).
- Si el usuario responde algo ambiguo, pide aclaración antes de avanzar.
- Si detectas señales de emergencia (dolor de pecho intenso, pérdida de
  consciencia, hemorragia abundante, dificultad respiratoria severa), marca
  ready=true de inmediato con los datos que tengas y agrega un campo
  "emergency": true.

FORMATO DE SALIDA (OBLIGATORIO):
Responde ÚNICAMENTE con un JSON válido, sin markdown ni texto adicional:
{
  "reply": "<lo que se mostrará al usuario en el chat>",
  "ready": <true|false>,
  "data": {
    "symptoms": "<string o null>",
    "duration": "<string o null>",
    "severity": "<string o null>",
    "age": "<string o null>",
    "location_text": "<string o null>"
  },
  "emergency": <true|false>
}

- ready=false mientras falten datos.
- ready=true SÓLO cuando tengas symptoms + duration + severity + age
  (location_text sólo si el frontend no aportó coords).
- Cuando ready=true, "reply" debe confirmar al usuario que se buscarán
  recomendaciones; nada de preguntas adicionales.
"""

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse(raw: str) -> dict:
    cleaned = _JSON_FENCE.sub("", raw).strip()
    return json.loads(cleaned)


def reply(session_id: str, user_message: str, has_coords: bool = False) -> dict:
    """
    Drive one turn of the conversation.

    Args:
        session_id:   Patient session id (also keys the Gemini chat session).
        user_message: Latest user input. Use "" to bootstrap the conversation.
        has_coords:   True if the frontend already has GPS/geocoded coords —
                      the agent will skip asking for location.

    Returns:
        {"reply": str, "ready": bool, "data": dict, "emergency": bool}
    """
    bootstrap = "[INICIO_DE_SESION] " if not user_message else ""
    coords_hint = " (El frontend YA tiene coordenadas del usuario, NO preguntes ubicación.)" if has_coords else ""
    payload = f"{bootstrap}{user_message}{coords_hint}".strip() or "Inicia la conversación."

    raw = gemini_service.send_chat(session_id, payload, system=SYSTEM_PROMPT)

    try:
        parsed = _parse(raw)
    except json.JSONDecodeError as e:
        logger.error("chat_agent JSON parse error: %s — raw: %s", e, raw)
        return {
            "reply": "Disculpa, tuve un problema procesando tu mensaje. ¿Puedes repetirlo?",
            "ready": False,
            "data": {},
            "emergency": False,
        }

    parsed.setdefault("data", {})
    parsed.setdefault("ready", False)
    parsed.setdefault("emergency", False)
    parsed.setdefault("reply", "")
    return parsed


def reset(session_id: str) -> None:
    gemini_service.reset_chat(session_id)
