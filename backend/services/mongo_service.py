"""
MongoDB Service — async Motor client + accessors por colección.

Colecciones oficiales (ver Claude/DATABASE_SCHEMA.md):
  users, doctors, clinics, gemini_sessions, conversations, appointments

El índice Vector Search de `clinics` se configura manualmente en Atlas UI
(nombre esperado: `clinics_vector_index`, dim=768, similarity=cosine).
"""

import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "healthapp")

# Nombre del índice Vector Search configurado en Atlas UI.
CLINICS_VECTOR_INDEX = "clinics_vector_index"

_client: AsyncIOMotorClient = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
        logger.info("MongoDB client created (db=%s)", MONGO_DB_NAME)
    return _client


def get_db():
    return get_client()[MONGO_DB_NAME]


# ────────────────────────────────────────────────────────────
# Accessors por colección (nombres del DATABASE_SCHEMA.md)
# ────────────────────────────────────────────────────────────

def users():
    return get_db()["users"]


def doctors():
    return get_db()["doctors"]


def clinics():
    return get_db()["clinics"]


def gemini_sessions():
    return get_db()["gemini_sessions"]


def conversations():
    return get_db()["conversations"]


def appointments():
    return get_db()["appointments"]


# Alias de retrocompatibilidad para código existente que usa `patients()`.
# El router original persistía en `patients`; ahora la colección es `users`.
# TODO: migrar llamadas a users() y remover este alias.
def patients():
    return users()


# ────────────────────────────────────────────────────────────
# Vector Search sobre `clinics`
# ────────────────────────────────────────────────────────────

async def vector_search_clinics(embedding: list[float], limit: int = 20) -> list[dict]:
    """
    Atlas Vector Search sobre la colección `clinics`.

    Requiere un índice Vector Search llamado `clinics_vector_index`
    sobre el campo `embedding` (768 dim, cosine). Se crea manualmente
    en la UI de MongoDB Atlas.
    """
    pipeline = [
        {
            "$vectorSearch": {
                "index": CLINICS_VECTOR_INDEX,
                "path": "embedding",
                "queryVector": embedding,
                "numCandidates": max(limit * 5, 150),
                "limit": limit,
            }
        },
        {
            "$project": {
                "_id": 1,
                "clinic_id": {"$toString": "$_id"},
                "clues_id": 1,
                "name": 1,
                "specialty": 1,
                "unit_type": 1,
                "insurances": 1,
                "price_level": 1,
                "lat": 1,
                "lng": 1,
                "phone": 1,
                "address": 1,
                "doctor_id": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    cursor = clinics().aggregate(pipeline)
    return await cursor.to_list(length=limit)
