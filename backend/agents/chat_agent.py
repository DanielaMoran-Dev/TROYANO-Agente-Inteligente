"""
Chat Agent — conversational front-end for the consult pipeline.

Two phases, driven by the `has_recommendations` flag passed from the frontend:

1. INTAKE  — build a complete patient profile (clinical data + preferences)
   before the first /consult. Emits action="consult" when data is sufficient.

2. REFINE  — after /consult has shown recommendations, the user can keep
   chatting to adjust preferences (public vs private, radius, budget, seguro).
   Emits action="refine_consult" when a meaningful preference change is
   detected that warrants re-running the pipeline.

The agent is stateless on the server (aside from the Gemini chat session) —
phase and context are re-injected on every turn via `known_profile` +
`current_prefs` + `has_recommendations`.
"""

import json
import logging
import re

from services import gemini_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres MedConnect, un asistente médico conversacional en español.

OBJETIVO
Recolectar la información clínica y las preferencias del paciente para
recomendarle atención médica adecuada, y ayudarle a refinar las
recomendaciones si cambia de opinión durante la conversación.

FASES (el sistema te indica cuál con el flag PHASE en cada turno)
- INTAKE: aún no se han mostrado recomendaciones. Pregunta lo que falte
  para armar el perfil. Cuando tengas lo mínimo, emite action="consult".
- REFINE: ya se mostraron recomendaciones. Escucha si el paciente cambia
  de criterio (quiere sólo clínicas privadas, ampliar el radio, cambiar
  seguro o presupuesto, descartar una especialidad, etc.). Si detectas un
  cambio concreto, confirma en una oración y emite action="refine_consult"
  con las preferencias actualizadas. Si el usuario sólo está comentando
  o haciendo preguntas, responde empáticamente con action="none".

DATOS CLÍNICOS (intake mínimo antes de recomendar):
  - symptoms            — descripción de síntomas principales
  - duration            — desde cuándo / cuánto tiempo llevan
  - severity            — intensidad (leve / moderada / intensa / insoportable)
  - pain_scale          — número 1-10 si hay dolor (null si no aplica)
  - fever               — true | false | null (¿hay fiebre?)
  - associated_symptoms — lista corta opcional de síntomas asociados
  - age                 — edad (omite si KNOWN_PROFILE.age ya existe)
  - location_text       — ciudad / colonia / CP (OMITE si HAS_COORDS=true)

PREFERENCIAS (pregunta solo lo que falte o no tenga default obvio):
  - facility_type       — "public" (IMSS/ISSSTE/SSA) | "private" | "any"
  - insurance           — "imss" | "issste" | "seguro_popular" | "ninguno"
                          Usa KNOWN_PROFILE.insurance si existe; solo
                          reconfirma si el paciente menciona cambio.
  - budget_level        — "$" | "$$" | "$$$" (no preguntes si facility_type=public)
  - radius_m            — 3000 | 5000 | 10000 | 20000 | 50000. No preguntes
                          proactivamente; sólo si el paciente menciona
                          distancia o si el primer intento no dio resultados.

REGLAS DE CONVERSACIÓN
- Una pregunta clara y empática por turno, máximo 2 oraciones.
- NUNCA pidas datos que aparezcan en KNOWN_PROFILE (edad, alergias, etc.).
  Reconócelos de forma natural: "Veo que tienes alergia a penicilina…"
- Si detectas señal de emergencia (dolor de pecho intenso, pérdida de
  conciencia, hemorragia abundante, dificultad respiratoria severa,
  déficit neurológico, signos de ACV/infarto), pon emergency=true y
  emite action="consult" con los datos que tengas SIN preguntar nada más.
- En fase REFINE, no repitas preguntas de intake; céntrate en detectar y
  confirmar cambios de preferencia.
- Cuando el paciente exprese una restricción dura (ej. "no tengo coche",
  "no puedo pagar más de 500 pesos"), reflejarla en preferences
  (radius_m menor, budget_level más bajo) y emitir refine_consult.

FORMATO DE SALIDA (OBLIGATORIO — solo JSON, sin markdown, sin texto extra):
{
  "reply": "<texto a mostrar al usuario>",
  "action": "none" | "consult" | "refine_consult",
  "data": {
    "symptoms":            <string|null>,
    "duration":            <string|null>,
    "severity":            <string|null>,
    "pain_scale":          <number|null>,
    "fever":               <true|false|null>,
    "associated_symptoms": <[string]|null>,
    "age":                 <string|null>,
    "location_text":       <string|null>
  },
  "preferences": {
    "facility_type": "public"|"private"|"any"|null,
    "insurance":     "imss"|"issste"|"seguro_popular"|"ninguno"|null,
    "budget_level":  "$"|"$$"|"$$$"|null,
    "radius_m":      <int|null>
  },
  "emergency": <true|false>
}

REGLAS DE action:
- action="consult" SOLO cuando tengas symptoms + duration + severity y
  (HAS_COORDS=true O location_text presente) y facility_type definido.
- action="refine_consult" SOLO en fase REFINE y cuando al menos una
  preferencia cambie respecto a CURRENT_PREFS.
- action="none" en cualquier otro caso.
"""

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

# Actions that signal the frontend to run the /consult pipeline.
_READY_ACTIONS = {"consult", "refine_consult"}


def _parse(raw: str) -> dict:
    cleaned = _JSON_FENCE.sub("", raw).strip()
    return json.loads(cleaned)


def _build_context_hint(
    has_coords: bool,
    has_recommendations: bool,
    known_profile: dict | None,
    current_prefs: dict | None,
) -> str:
    """Flags injected before the user message so the LLM knows the phase."""
    phase = "REFINE" if has_recommendations else "INTAKE"
    bits = [
        f"[PHASE={phase}]",
        f"[HAS_COORDS={'true' if has_coords else 'false'}]",
    ]

    if known_profile:
        kp = {k: v for k, v in known_profile.items() if v not in (None, "", [], {})}
        if kp:
            bits.append(f"[KNOWN_PROFILE={json.dumps(kp, ensure_ascii=False)}]")
    if current_prefs:
        cp = {k: v for k, v in current_prefs.items() if v not in (None, "", [])}
        if cp:
            bits.append(f"[CURRENT_PREFS={json.dumps(cp, ensure_ascii=False)}]")

    return " ".join(bits)


def reply(
    session_id: str,
    user_message: str,
    has_coords: bool = False,
    has_recommendations: bool = False,
    known_profile: dict | None = None,
    current_prefs: dict | None = None,
) -> dict:
    """
    Drive one turn of the conversation.

    Args:
        session_id:          Keys the Gemini chat session.
        user_message:        Latest user input. "" to bootstrap.
        has_coords:          Frontend already has coords → skip location_text.
        has_recommendations: True once the first /consult has returned →
                             REFINE phase.
        known_profile:       DB-side patient info (age, insurance,
                             conditions, allergies, medications) so the
                             agent doesn't re-ask stored fields.
        current_prefs:       UI-side preferences already in effect; the
                             agent must only emit refine_consult when a
                             preference *changes* relative to these.

    Returns:
        {
          "reply":       str,
          "action":      "none"|"consult"|"refine_consult",
          "ready":       bool     (compat: true iff action in _READY_ACTIONS),
          "data":        dict,
          "preferences": dict,
          "emergency":   bool,
        }
    """
    hint = _build_context_hint(has_coords, has_recommendations, known_profile, current_prefs)

    bootstrap = "[INICIO_DE_SESION] " if not user_message else ""
    payload = f"{hint} {bootstrap}{user_message}".strip() or hint

    raw = gemini_service.send_chat(session_id, payload, system=SYSTEM_PROMPT, json_mode=True)

    try:
        parsed = _parse(raw)
    except json.JSONDecodeError as e:
        logger.error("chat_agent JSON parse error: %s — raw: %s", e, raw)
        # Use whatever text Gemini returned as the reply rather than a generic error
        fallback_reply = raw.strip() if raw.strip() else "Disculpa, tuve un problema. ¿Puedes repetirlo?"
        return {
            "reply": fallback_reply,
            "action": "none",
            "ready": False,
            "data": {},
            "preferences": {},
            "emergency": False,
        }

    parsed.setdefault("data", {})
    parsed.setdefault("preferences", {})
    parsed.setdefault("action", "none")
    parsed.setdefault("emergency", False)
    parsed.setdefault("reply", "")
    parsed["ready"] = parsed["action"] in _READY_ACTIONS
    return parsed


def reset(session_id: str) -> None:
    gemini_service.reset_chat(session_id)
