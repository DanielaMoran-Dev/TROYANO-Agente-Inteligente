"""
Orchestrator Agent — Agent 0
Multi-turn interview chatbot that gathers project requirements from the user.
Produces an orchestrator_brief conforming to backend/schemas/orchestrator_brief.schema.json.
"""

import os
import json
import uuid
import logging
import datetime
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("WATSONX_MODEL_ID", "meta-llama/llama-3-3-70b-instruct")

# In-memory session store: session_id -> {history, turn_count, brief}
_sessions: dict = {}

# ── Model factory ────────────────────────────────────────────────────────────

def _get_model():
    api_key = os.getenv("WATSONX_API_KEY")
    url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    project_id = os.getenv("WATSONX_PROJECT_ID")
    if not all([api_key, url, project_id]):
        return None
    try:
        from ibm_watsonx_ai.foundation_models import ModelInference
        from ibm_watsonx_ai import Credentials
        credentials = Credentials(url=url, api_key=api_key)
        return ModelInference(
            model_id=MODEL_ID,
            credentials=credentials,
            project_id=project_id,
            params={"decoding_method": "greedy", "max_new_tokens": 1200},
        )
    except Exception as e:
        logger.error("Orchestrator Agent: failed to init model: %s", e)
        return None


# ── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Lineal's AI urban planning consultant. You help real estate developers and investors define the best development portfolio for a specific urban zone in Aguascalientes, Mexico.

Conduct a friendly, professional interview. Ask ONE focused question per turn. You need to gather:
1. Type of developer/investor (private developer, social housing, commercial portfolio, government/public, mixed)
2. Current land status of the zone: Is the land VACANT/UNDEVELOPED (extension), or does it have EXISTING BUILDINGS (infill/urban renewal)?
3. Primary project interest (residential, commercial, mixed-use, transport, green spaces, etc.)
4. Approximate budget range in USD
5. Timeline preference (short 1-3yr, medium 5yr, long 10yr+)
6. Sustainability priorities (green space importance, renewable energy, social inclusion / affordable housing)

CRITICAL RULE: The land status (question 2) is the most important piece of information.
- If VACANT/EXTENSION: new construction, parks, and infrastructure can be proposed freely.
- If EXISTING URBAN: only infill densification, public space improvements, and vacant-lot interventions are valid. NEVER propose demolishing existing occupied buildings.

### THE SATISFACTION RULE:
Before generating the brief, you MUST:
1. Provide a concise summary of all gathered points (1-5).
2. Ask the user if they are satisfied with this project description or if they want to adjust anything.
3. If the user is satisfied (e.g., "yes", "looks good", "satisfied"), THEN AND ONLY THEN output the <BRIEF_READY> block.

### OUTPUT FORMAT:
Output EXACTLY this JSON block when ready — no extra text before or after the tags:

<BRIEF_READY>
{
  "project_description": "Concise description of the development vision based on the interview",
  "land_status": "extension",
  "intent_mode": "targeted",
  "has_user_requirements": true,
  "candidate_projects": [
    {"project_type": "mixed_use", "priority": "primary"},
    {"project_type": "green_park", "priority": "secondary"}
  ],
  "budget_usd": 5000000,
  "timeline_years": 5,
  "sustainability": {
    "green_space_minimum_percent": 15,
    "affordable_housing_required": false,
    "renewable_energy_encouraged": true
  }
}
</BRIEF_READY>

land_status values: "extension" (vacant/undeveloped), "infill" (existing urban), "urban_renewal" (mixed/redevelopment)

Valid project_type values (pick 2-4 that best match the user's intent):
residential_housing, social_housing, mixed_use, commercial, office, industrial_light,
public_transport_brt, public_transport_light_rail, cycling_infrastructure, pedestrian_infrastructure,
green_park, urban_forest, civic_cultural, education, healthcare, renewable_energy,
mixed_transport_hub, urban_renewal

Rules:
- Keep responses concise (2-3 sentences max per turn)
- Be warm, professional. You can mix English and Spanish naturally
- Do NOT generate the brief until the user explicitly confirms they are satisfied with the summary.
- When the user's answer is vague, ask a clarifying follow-up instead of guessing
"""

# ── Public API ───────────────────────────────────────────────────────────────

def start_session() -> str:
    """Create a new chat session and return its ID."""
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "history": [],
        "turn_count": 0,
        "brief": None,
    }
    return session_id


def get_opening_message() -> str:
    return (
        "¡Hola! Soy **Lineal**, tu consultor de planeación urbana con IA para Aguascalientes. 🏙️\n\n"
        "Con 3 preguntas rápidas diseñaré el portafolio de desarrollo óptimo para tu zona.\n\n"
        "**¿Qué tipo de proyecto quieres desarrollar?**\n"
        "_(ej: vivienda residencial, vivienda social, comercial/retail, usos mixtos, parque urbano, transporte...)_"
    )


def chat(session_id: str, user_message: str) -> dict:
    """
    Process one turn of the interview.
    Returns: { reply: str, done: bool, brief: dict | None }
    """
    # Auto-create session if missing
    if session_id not in _sessions:
        _sessions[session_id] = {"history": [], "turn_count": 0, "brief": None}

    session = _sessions[session_id]

    # Already finished
    if session["brief"] is not None:
        return {
            "reply": "Your planning brief is ready. Click **Start Analysis** to begin the pipeline.",
            "done": True,
            "brief": session["brief"],
        }

    session["history"].append({"role": "user", "content": user_message})
    session["turn_count"] += 1

    model = _get_model()
    if not model:
        return _mock_chat(session, session_id)

    # Build full prompt from conversation history
    prompt = f"<|system|>\n{SYSTEM_PROMPT}\n"
    for msg in session["history"]:
        tag = "user" if msg["role"] == "user" else "assistant"
        prompt += f"<|{tag}|>\n{msg['content']}\n"
    prompt += "<|assistant|>\n"

    try:
        raw_reply = model.generate_text(prompt=prompt).strip()
    except Exception as e:
        logger.error("Orchestrator Agent generate error: %s", e)
        raw_reply = "I had a small issue processing that. Could you repeat your answer?"

    # Detect brief marker
    brief = None
    done = False
    reply = raw_reply

    if "<BRIEF_READY>" in raw_reply and "</BRIEF_READY>" in raw_reply:
        start = raw_reply.index("<BRIEF_READY>") + len("<BRIEF_READY>")
        end = raw_reply.index("</BRIEF_READY>")
        try:
            brief_raw = json.loads(raw_reply[start:end].strip())
            brief = _expand_brief(brief_raw, session_id)
            session["brief"] = brief
            done = True
            # Strip JSON from the visible reply
            reply = raw_reply[: raw_reply.index("<BRIEF_READY>")].strip()
            if not reply:
                reply = "¡Perfecto! I have everything I need. Your **planning brief** is ready — click Start Analysis to begin."
        except json.JSONDecodeError as e:
            logger.warning("Brief JSON parse error: %s\nRaw: %s", e, raw_reply[start:end][:300])

    session["history"].append({"role": "assistant", "content": reply})
    return {"reply": reply, "done": done, "brief": brief}


def chat_stream(session_id: str, messages: list):
    """
    Generator yielding SSE chunks for Vercel AI SDK.
    messages format: [{"role": "user", "content": "..."}, ...]
    """
    if session_id not in _sessions:
        _sessions[session_id] = {"history": [], "turn_count": 0, "brief": None}
    
    session = _sessions[session_id]

    if session["brief"] is not None:
        yield f'0:{json.dumps("Your planning brief is ready. Click **Start Analysis** to begin the pipeline.")}\\n'
        yield f'd:{json.dumps({"brief": session["brief"]})}\\n'
        return

    user_msgs = [m for m in messages if m["role"] == "user"]
    session["turn_count"] = len(user_msgs)

    model = _get_model()
    if not model:
        yield from _mock_chat_stream(session, session_id, messages)
        return

    prompt = f"<|system|>\\n{SYSTEM_PROMPT}\\n"
    for msg in messages:
        role = msg["role"]
        tag = role if role in ["user", "assistant", "system"] else "user"
        content = msg["content"]
        prompt += f"<|{tag}|>\\n{content}\\n"
    prompt += "<|assistant|>\\n"

    try:
        raw_reply = ""
        for chunk in model.generate_text_stream(prompt=prompt):
            raw_reply += chunk
            yield f'0:{json.dumps(chunk)}\\n'

        if "<BRIEF_READY>" in raw_reply and "</BRIEF_READY>" in raw_reply:
            start = raw_reply.index("<BRIEF_READY>") + len("<BRIEF_READY>")
            end = raw_reply.index("</BRIEF_READY>")
            try:
                brief_raw = json.loads(raw_reply[start:end].strip())
                brief = _expand_brief(brief_raw, session_id)
                session["brief"] = brief
                # Vercel AI SDK specific: send data part 'd:' (Data Stream Protocol)
                yield f'd:{json.dumps({"brief": brief})}\\n'
            except json.JSONDecodeError as e:
                logger.warning("Brief JSON parse error: %s", e)
                
        session["history"] = messages + [{"role": "assistant", "content": raw_reply}]
    except Exception as e:
        logger.error("Orchestrator Agent generate error: %s", e)
        yield f'0:{json.dumps("I had a small issue processing that. Could you repeat your answer?")}\\n'


def reset_session(session_id: str) -> None:
    """Delete a session."""
    _sessions.pop(session_id, None)


def get_session_brief(session_id: str) -> Optional[dict]:
    """Return the brief for a session if already completed."""
    session = _sessions.get(session_id)
    return session["brief"] if session else None


# ── Internal helpers ─────────────────────────────────────────────────────────

def _expand_brief(raw: dict, session_id: str) -> dict:
    """Inflate the compact LLM JSON into the full orchestrator_brief schema."""
    now = datetime.datetime.utcnow().isoformat() + "Z"
    brief_id = f"brief-{session_id[:8]}"

    candidates = []
    for i, c in enumerate(raw.get("candidate_projects", [])):
        ptype = c.get("project_type", "mixed_use")
        candidates.append({
            "candidate_id": f"cand-{i + 1:03d}",
            "project_type": ptype,
            "label": ptype.replace("_", " ").title(),
            "priority": c.get("priority", "secondary"),
            "ods11_targets": _default_ods11_for_type(ptype),
            "estimated_profitability_tier": "medium",
            "estimated_viability_tier": "medium",
            "notes": None,
        })

    sus = raw.get("sustainability", {})

    return {
        "schema_version": "1.0.0",
        "payload_type": "orchestrator_brief",
        "request_id": session_id,
        "brief_id": brief_id,
        "generated_at": now,
        "has_user_requirements": raw.get("has_user_requirements", True),
        "intent_mode": raw.get("intent_mode", "targeted"),
        "land_status": raw.get("land_status", "extension"),  # "extension" | "infill" | "urban_renewal"
        "project_description": raw.get("project_description", ""),
        "candidate_projects": candidates,
        "portfolio_criteria": {
            "ranking_weights": {
                "profitability": 0.40,
                "viability": 0.35,
                "ods11_compliance": 0.25,
            },
            "minimum_profitability_score": 0.30,
            "minimum_viability_score": 0.40,
            "minimum_ods11_score": 0.20,
            "prefer_electric_transport": True,
        },
        "ods11_requirements": {
            "targets": ["11.1", "11.2", "11.3", "11.6", "11.7"],
            "minimum_compliance_level": "partial",
            "sustainability_checklist": {
                "green_space_minimum_percent": sus.get("green_space_minimum_percent", 15),
                "transport_access_required": True,
                "renewable_energy_encouraged": sus.get("renewable_energy_encouraged", True),
                "maximum_car_parking_ratio": 0.5,
            },
            "social_inclusion_checklist": {
                "affordable_housing_required": sus.get("affordable_housing_required", False),
                "public_space_required": True,
                "accessibility_required": True,
                "mixed_income_encouraged": True,
            },
        },
        "budget_usd": raw.get("budget_usd"),
        "timeline_years": raw.get("timeline_years", 5),
    }


def _default_ods11_for_type(ptype: str) -> list:
    mapping = {
        "residential_housing": ["11.1", "11.3"],
        "social_housing": ["11.1", "11.3", "11.7"],
        "mixed_use": ["11.3", "11.7"],
        "commercial": ["11.3"],
        "public_transport_brt": ["11.2"],
        "public_transport_light_rail": ["11.2"],
        "cycling_infrastructure": ["11.2", "11.6"],
        "pedestrian_infrastructure": ["11.2", "11.7"],
        "green_park": ["11.6", "11.7"],
        "urban_forest": ["11.6", "11.7"],
        "civic_cultural": ["11.4", "11.7"],
        "education": ["11.3", "11.7"],
        "healthcare": ["11.1", "11.3"],
        "renewable_energy": ["11.6"],
        "urban_renewal": ["11.3", "11.5"],
    }
    return mapping.get(ptype, ["11.3"])


# ── Mock fallback (no watsonx credentials) ───────────────────────────────────
#
# Streamlined to 3 questions + 1 summary/confirm step.
# Keeps the demo fast and impressive for presentations.
_INTERVIEW_QUESTIONS = [
    ("land_status",
     "¿El terreno está **vacío / baldío** (sin construcciones actuales) o ya tiene **edificaciones existentes**?\n"
     "_(Esto determina qué tipo de intervenciones son válidas)_"),
    ("budget",
     "¿Cuál es el **presupuesto aproximado** de inversión en USD?\n"
     "_(ej: $2M, $10M, $50M...)_"),
    ("timeline",
     "¿En qué **plazo** esperas ejecutarlo?\n"
     "_(Corto: 1-3 años · Mediano: 5 años · Largo: 10+ años)_"),
]

# turn index at which we send the summary for confirmation
_SUMMARY_TURN = len(_INTERVIEW_QUESTIONS) + 1   # = 4


def _parse_answers(history: list) -> dict:
    """
    Turn layout (mock mode):
      user[0] → project type    (opening question)
      user[1] → land status     (_INTERVIEW_QUESTIONS[0])
      user[2] → budget          (_INTERVIEW_QUESTIONS[1])
      user[3] → timeline        (_INTERVIEW_QUESTIONS[2])
      user[4] → confirmation    (summary confirm)
    """
    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    project   = user_msgs[0] if len(user_msgs) > 0 else ""
    land_stat = user_msgs[1] if len(user_msgs) > 1 else ""
    budget    = user_msgs[2] if len(user_msgs) > 2 else ""
    timeline  = user_msgs[3] if len(user_msgs) > 3 else ""
    return {
        "land_status_raw":    land_stat,
        "project_type_raw":   project,
        "budget_raw":         budget,
        "timeline_raw":       timeline,
        "sustainability_raw": "",
        "social_raw":         project,   # pick up social keywords from project answer
    }


def _infer_brief_from_answers(answers: dict, session_id: str) -> dict:
    """
    Build a brief by interpreting the user's free-text answers from the interview.
    Uses keyword matching — no model needed.
    """
    ls_raw  = answers.get("land_status_raw", "").lower()
    pt_raw  = answers.get("project_type_raw", "").lower()
    bud_raw = answers.get("budget_raw", "").lower()
    tl_raw  = answers.get("timeline_raw", "").lower()
    sus_raw = answers.get("sustainability_raw", "").lower()
    soc_raw = answers.get("social_raw", "").lower()

    # ── Land status detection ────────────────────────────────────────────────
    if any(w in ls_raw for w in ["vacío", "vacio", "baldío", "baldio", "terreno vacante",
                                  "sin construc", "sin edifici", "extension", "extensión",
                                  "no hay", "nada", "libre", "vacant", "empty", "greenfield"]):
        land_status = "extension"
    elif any(w in ls_raw for w in ["casas", "edificios", "construido", "construcc",
                                    "vivienda existente", "habitado", "infill",
                                    "ya hay", "ocupado", "colonia", "barrio"]):
        land_status = "infill"
    elif any(w in ls_raw for w in ["mezcla", "mix", "parcial", "parte", "algunos"]):
        land_status = "urban_renewal"
    else:
        land_status = "extension"  # default: assume extension if unclear

    # ── Project type detection ───────────────────────────────────────────────
    candidates = []
    if any(w in pt_raw for w in ["vivienda", "housing", "residencial", "apartamento", "depart", "hab", "inmobiliaria"]):
        candidates.append({"project_type": "residential_housing", "priority": "primary"})
    if any(w in pt_raw for w in ["social", "interés social", "popular", "asequible"]):
        candidates.append({"project_type": "social_housing", "priority": "primary"})
    if any(w in pt_raw for w in ["mixto", "mixed", "usos mixtos", "comercial y resid"]):
        candidates.append({"project_type": "mixed_use", "priority": "primary"})
    if any(w in pt_raw for w in ["comercial", "commercial", "oficina", "office", "retail"]):
        candidates.append({"project_type": "commercial", "priority": "primary"})
    if any(w in pt_raw for w in ["parque", "park", "verde", "green", "ecol", "jardín", "árbol", "bosque"]):
        candidates.append({"project_type": "green_park", "priority": "primary"})
    if any(w in pt_raw for w in ["transporte", "transport", "brt", "metro", "tren", "bus", "movilidad"]):
        candidates.append({"project_type": "public_transport_brt", "priority": "primary"})
    if any(w in pt_raw for w in ["ciclov", "bici", "peatonal", "caminar"]):
        candidates.append({"project_type": "cycling_infrastructure", "priority": "secondary"})
    if any(w in pt_raw for w in ["infraestructura", "solar", "energía", "microrred", "servicios"]):
        candidates.append({"project_type": "renewable_energy", "priority": "secondary"})

    # If no type detected, label everything as mixed_use
    if not candidates:
        candidates = [{"project_type": "mixed_use", "priority": "primary"}]

    # Limit to 3 candidate types
    candidates = candidates[:3]

    # ── Budget ───────────────────────────────────────────────────────────────
    import re
    budget = None
    m = re.search(r'[\d,\.]+', bud_raw.replace(",", "").replace(".", ""))
    if m:
        val = int(m.group().replace(",", ""))
        # If number seems too small (thousands), scale up to millions
        if val < 1_000:
            val *= 1_000_000
        elif val < 10_000:
            val *= 100_000
        budget = val
    if not budget:
        if "millón" in bud_raw or "million" in bud_raw or "millon" in bud_raw:
            nums = re.findall(r'\d+', bud_raw)
            budget = int(nums[0]) * 1_000_000 if nums else 5_000_000
        else:
            budget = 5_000_000  # default

    # ── Timeline ─────────────────────────────────────────────────────────────
    if any(w in tl_raw for w in ["corto", "short", "1", "2", "3", "rápido"]):
        timeline = 3
    elif any(w in tl_raw for w in ["largo", "long", "10", "20"]):
        timeline = 10
    else:
        timeline = 5  # medium

    # ── Sustainability ────────────────────────────────────────────────────────
    green_pct = 15
    m2 = re.search(r'(\d+)\s*%', sus_raw)
    if m2:
        green_pct = int(m2.group(1))
    elif any(w in sus_raw for w in ["mucho", "importante", "alto", "high", "muy"]):
        green_pct = 30
    elif any(w in sus_raw for w in ["poco", "bajo", "low", "minimal", "mínimo"]):
        green_pct = 10

    # ── Social housing ────────────────────────────────────────────────────────
    affordable = any(w in soc_raw for w in ["sí", "si", "yes", "require", "necesario", "social", "asequible"])

    # ── Build description ─────────────────────────────────────────────────────
    type_labels = {
        "residential_housing": "vivienda residencial",
        "social_housing": "vivienda de interés social",
        "mixed_use": "desarrollo de usos mixtos",
        "commercial": "espacios comerciales",
        "green_park": "parques y espacios verdes",
        "public_transport_brt": "transporte público BRT",
        "cycling_infrastructure": "infraestructura ciclista",
        "renewable_energy": "infraestructura solar/energética",
    }
    ctype_labels = [type_labels.get(c["project_type"], c["project_type"]) for c in candidates]
    land_label = {
        "extension": "terreno vacío/extensión",
        "infill": "zona urbana consolidada (infill)",
        "urban_renewal": "zona de renovación urbana",
    }.get(land_status, "terreno de estado desconocido")
    desc = (
        f"Desarrollo urbano en {land_label} en Aguascalientes, "
        f"enfocado en {', '.join(ctype_labels)}. "
        f"Presupuesto estimado ${budget:,} USD, horizonte {timeline} años."
        + (" Vivienda de interés social requerida." if affordable else "")
    )
    # NOTE: green_pct lives only in sustainability_checklist — NOT in project_description
    # to avoid false-positive keyword routing to green_space.

    return _expand_brief({
        "project_description": desc,
        "land_status": land_status,
        "intent_mode": "targeted",
        "has_user_requirements": True,
        "candidate_projects": candidates,
        "budget_usd": budget,
        "timeline_years": timeline,
        "sustainability": {
            "green_space_minimum_percent": green_pct,
            "affordable_housing_required": affordable,
            "renewable_energy_encouraged": True,
        },
    }, session_id)


def _mock_chat(session: dict, session_id: str) -> dict:
    turn = session["turn_count"]

    # turns 1–3: interview questions
    if turn <= len(_INTERVIEW_QUESTIONS):
        _, reply = _INTERVIEW_QUESTIONS[turn - 1]
        session["history"].append({"role": "assistant", "content": reply})
        return {"reply": reply, "done": False, "brief": None}

    # turn 4: generate summary and ask for confirmation
    if turn == _SUMMARY_TURN:
        answers = _parse_answers(session["history"])
        brief_preview = _infer_brief_from_answers(answers, session_id)
        # Store preview so we can reuse it on confirmation
        session["_brief_preview"] = brief_preview
        desc = brief_preview.get("project_description", "Proyecto urbano en Aguascalientes.")
        land = {"extension": "terreno vacío / extensión", "infill": "zona urbanizada existente",
                "urban_renewal": "zona de renovación"}.get(brief_preview.get("land_status",""), "zona")
        budget = brief_preview.get("budget_usd")
        budget_str = f"${budget:,} USD" if budget else "presupuesto por definir"
        years = brief_preview.get("timeline_years", 5)
        reply = (
            f"Perfecto, aquí está el resumen de tu proyecto:\n\n"
            f"📍 **Zona:** {land}\n"
            f"🏗 **Programa:** {desc}\n"
            f"💰 **Inversión:** {budget_str}\n"
            f"📅 **Horizonte:** {years} años\n\n"
            f"¿Todo correcto? _(Responde **sí** para iniciar el análisis, o cuéntame qué ajustar)_"
        )
        session["history"].append({"role": "assistant", "content": reply})
        return {"reply": reply, "done": False, "brief": None}

    # turn 5+: user confirmed — generate brief
    user_msgs = [m["content"] for m in session["history"] if m["role"] == "user"]
    last_user = user_msgs[-1].lower() if user_msgs else ""
    import re as _re
    _CONFIRM_WORDS = [r"\bsí\b", r"\bsi\b", r"\byes\b", r"\bok\b", r"\bconfirmo\b",
                      r"\bcorrecto\b", r"\badelante\b", r"\blisto\b", r"\bbien\b"]
    if any(_re.search(p, last_user) for p in _CONFIRM_WORDS):
        brief = session.get("_brief_preview") or _infer_brief_from_answers(
            _parse_answers(session["history"]), session_id
        )
        session["brief"] = brief
        reply = "¡Excelente! 🚀 Iniciando análisis multi-agente — el mapa se actualizará en unos segundos."
        session["history"].append({"role": "assistant", "content": reply})
        return {"reply": reply, "done": True, "brief": brief}
    else:
        # User wants to adjust — ask the first question again
        reply = (
            "Entendido, ajustemos. "
            "**¿Qué tipo de proyecto quieres desarrollar?**\n"
            "_(ej: vivienda residencial, comercial, usos mixtos, parque, transporte...)_"
        )
        # Reset turn count so the interview restarts
        session["turn_count"] = 0
        session["history"] = []
        session["history"].append({"role": "assistant", "content": reply})
        return {"reply": reply, "done": False, "brief": None}


def _mock_chat_stream(session: dict, session_id: str, messages: list):
    import time
    turn = len([m for m in messages if m["role"] == "user"])
    if turn <= len(_INTERVIEW_QUESTIONS):
        _, reply = _INTERVIEW_QUESTIONS[turn - 1]
        for word in reply.split(" "):
            yield f'0:{json.dumps(word + " ")}\\n'
            time.sleep(0.04)
        session["history"] = messages + [{"role": "assistant", "content": reply}]
        return

    answers = _parse_answers(messages)
    brief = _infer_brief_from_answers(answers, session_id)
    session["brief"] = brief
    reply = "¡Perfecto! Tengo todo lo que necesito. Tu **brief de planificación** está listo — el análisis comenzará en un momento."
    for word in reply.split(" "):
        yield f'0:{json.dumps(word + " ")}\\n'
        time.sleep(0.04)
    yield f'd:{json.dumps({"brief": brief})}\\n'
    session["history"] = messages + [{"role": "assistant", "content": reply}]
