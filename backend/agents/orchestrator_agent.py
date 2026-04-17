"""
Orchestrator Agent — Gemini 2.5 Flash via Vertex AI (service account)
Chat directo multi-turno. Agentes comentados temporalmente.
"""

import os
import uuid
import logging

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

_JSON_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../Gemini/nuvia-489723-654f73bcdd7a.json")
)
_PROJECT  = "nuvia-489723"
_LOCATION = "us-central1"
_MODEL    = "gemini-2.5-flash"

# In-memory sessions: session_id -> { chat_session, brief }
_sessions: dict = {}

# ── Gemini client (lazy singleton) ────────────────────────────────────────────

_gemini_client = None


def _get_client():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    try:
        from google import genai
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            _JSON_PATH,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        _gemini_client = genai.Client(
            vertexai=True,
            project=_PROJECT,
            location=_LOCATION,
            credentials=creds,
        )
        logger.info("Gemini: client OK (%s @ %s)", _MODEL, _LOCATION)
        return _gemini_client
    except Exception as e:
        logger.error("Gemini: client init failed — %s", e)
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def start_session() -> str:
    session_id = str(uuid.uuid4())
    client = _get_client()
    chat_session = client.chats.create(model=_MODEL) if client else None
    _sessions[session_id] = {"chat_session": chat_session, "brief": None}
    return session_id


def get_opening_message() -> str:
    return "Hola, soy TROYANO con Gemini 2.5 Flash. ¿En qué puedo ayudarte?"


def chat(session_id: str, user_message: str) -> dict:
    # Auto-create session si no existe
    if session_id not in _sessions:
        client = _get_client()
        chat_session = client.chats.create(model=_MODEL) if client else None
        _sessions[session_id] = {"chat_session": chat_session, "brief": None}

    session = _sessions[session_id]
    chat_session = session.get("chat_session")

    if not chat_session:
        return {
            "reply": "Error: no se pudo conectar con Gemini. Revisa las credenciales.",
            "done": False,
            "brief": None,
        }

    try:
        response = chat_session.send_message(user_message)
        reply = response.text.strip()
    except Exception as e:
        logger.error("Gemini chat error: %s", e)
        reply = f"Error al procesar el mensaje: {e}"

    return {"reply": reply, "done": False, "brief": None}


def reset_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def get_session_brief(session_id: str):
    session = _sessions.get(session_id)
    return session["brief"] if session else None
