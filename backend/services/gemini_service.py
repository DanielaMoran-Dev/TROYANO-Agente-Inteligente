"""
Gemini Service — single client using google.genai SDK over Vertex AI.

Authentication: service-account JSON pointed to by GOOGLE_APPLICATION_CREDENTIALS.
(API-key auth is also supported as a fallback if GEMINI_API_KEY is set.)
"""

import os
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
SA_CRED_PATH      = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
GCP_PROJECT       = os.getenv("GOOGLE_CLOUD_PROJECT", "")
GCP_LOCATION      = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
DEFAULT_MODEL     = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is not None:
        return _client

    # Prefer Vertex AI + service-account if available (matches the reference setup).
    if SA_CRED_PATH and GCP_PROJECT:
        try:
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(
                SA_CRED_PATH,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            _client = genai.Client(
                vertexai=True,
                project=GCP_PROJECT,
                location=GCP_LOCATION,
                credentials=creds,
            )
            logger.info(
                "Gemini client initialized via Vertex AI (project=%s, location=%s, model=%s)",
                GCP_PROJECT, GCP_LOCATION, DEFAULT_MODEL,
            )
            return _client
        except Exception as exc:
            logger.error("Failed to init Vertex AI client with service account: %s", exc)
            raise

    # Fallback: plain API-key auth against generativelanguage.googleapis.com.
    if GEMINI_API_KEY:
        _client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini client initialized via API key (model=%s)", DEFAULT_MODEL)
        return _client

    raise RuntimeError(
        "Gemini is not configured. Set GOOGLE_APPLICATION_CREDENTIALS + "
        "GOOGLE_CLOUD_PROJECT (Vertex), or GEMINI_API_KEY (API-key mode)."
    )


def is_configured() -> bool:
    return bool((SA_CRED_PATH and GCP_PROJECT) or GEMINI_API_KEY)


def generate(prompt: str, system: str = "", model: str = DEFAULT_MODEL) -> str:
    """Generate a single-turn text response."""
    client = _get_client()
    config = types.GenerateContentConfig(system_instruction=system) if system else None
    response = client.models.generate_content(model=model, contents=prompt, config=config)
    return response.text.strip()


def embed(text: str, model: str = "text-embedding-004") -> list[float]:
    """Generate an embedding vector for the given text."""
    client = _get_client()
    result = client.models.embed_content(model=model, contents=text)
    return result.embeddings[0].values


# ─── Chat sessions ─────────────────────────────────────────────────────────────
# Multi-turn sessions, keyed by an arbitrary id (e.g. patient session_id).
# In-memory only — fine for hackathon scale; for production move to Redis.

_chat_sessions: dict[str, object] = {}


def get_or_create_chat(session_id: str, system: str = "", model: str = DEFAULT_MODEL):
    """Return the existing chat session for `session_id`, or create one."""
    chat = _chat_sessions.get(session_id)
    if chat is not None:
        return chat

    client = _get_client()
    config = types.GenerateContentConfig(system_instruction=system) if system else None
    chat = client.chats.create(model=model, config=config)
    _chat_sessions[session_id] = chat
    logger.info("Chat session created: %s", session_id)
    return chat


def send_chat(session_id: str, message: str, system: str = "", model: str = DEFAULT_MODEL) -> str:
    """Send a user message into the named chat session and return the reply text."""
    chat = get_or_create_chat(session_id, system=system, model=model)
    response = chat.send_message(message)
    return response.text.strip()


def reset_chat(session_id: str) -> None:
    """Drop the chat session so the next message starts fresh."""
    _chat_sessions.pop(session_id, None)
