"""
Inicialización de MongoDB Atlas — Plataforma Médica.

Crea todas las colecciones e índices definidos en Claude/DATABASE_SCHEMA.md.

Colecciones:
  - users              (pacientes registrados)
  - doctors            (médicos, con is_network)
  - clinics            (CLUES vectorizadas)
  - gemini_sessions    (historial de triaje con IA)
  - conversations      (chat paciente-doctor)
  - appointments       (citas agendadas)

Uso:
  cd backend
  python -m scripts.init_db

Requisitos:
  - MONGO_URI y MONGO_DB_NAME en services/.env
  - El índice Vector Search de `clinics` se crea manualmente en Atlas UI
    (ver instrucciones al final del script).
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure
from dotenv import load_dotenv

# Cargar .env desde backend/services/.env (ubicación actual del usuario)
_HERE = Path(__file__).resolve().parent
_ENV_PATH = _HERE.parent / "services" / ".env"
load_dotenv(_ENV_PATH)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("init_db")


MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "healthapp")

if not MONGO_URI:
    logger.error("MONGO_URI no está definida en %s", _ENV_PATH)
    sys.exit(1)


# ────────────────────────────────────────────────────────────
# JSON Schema Validators
# (MongoDB valida en writes; campos obligatorios del DATABASE_SCHEMA)
# ────────────────────────────────────────────────────────────

VALIDATORS = {
    "users": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["email", "password_hash", "insurance"],
            "properties": {
                "email": {"bsonType": "string"},
                "password_hash": {"bsonType": "string"},
                "name": {"bsonType": "string"},
                "last_name": {"bsonType": "string"},
                "age": {"bsonType": ["int", "null"]},
                "phone": {"bsonType": ["string", "null"]},
                "coords": {
                    "bsonType": ["object", "null"],
                    "properties": {
                        "lat": {"bsonType": ["double", "int"]},
                        "lng": {"bsonType": ["double", "int"]},
                    },
                },
                "insurance": {
                    "enum": ["imss", "issste", "seguro_popular", "ninguno"],
                },
                "medical_history": {
                    "bsonType": ["object", "null"],
                    "properties": {
                        "free_text": {"bsonType": ["string", "null"]},
                        "conditions": {"bsonType": ["array", "null"]},
                        "allergies": {"bsonType": ["array", "null"]},
                        "medications": {"bsonType": ["array", "null"]},
                        "blood_type": {"bsonType": ["string", "null"]},
                    },
                },
                "is_active": {"bsonType": "bool"},
                "created_at": {"bsonType": ["date", "null"]},
                "updated_at": {"bsonType": ["date", "null"]},
            },
        }
    },

    "doctors": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "email",
                "password_hash",
                "license_number",
                "specialty",
                "price_level",
                "insurances",
                "is_network",
            ],
            "properties": {
                "email": {"bsonType": "string"},
                "password_hash": {"bsonType": "string"},
                "name": {"bsonType": "string"},
                "last_name": {"bsonType": "string"},
                "phone": {"bsonType": ["string", "null"]},
                "license_number": {"bsonType": "string"},
                "specialty": {"bsonType": "string"},
                "price_level": {"bsonType": "int", "minimum": 1, "maximum": 3},
                "insurances": {
                    "bsonType": "array",
                    "items": {
                        "enum": ["imss", "issste", "seguro_popular", "ninguno"],
                    },
                },
                "location": {
                    "bsonType": ["object", "null"],
                    "properties": {
                        "address": {"bsonType": ["string", "null"]},
                        "lat": {"bsonType": ["double", "int", "null"]},
                        "lng": {"bsonType": ["double", "int", "null"]},
                        "maps_place_id": {"bsonType": ["string", "null"]},
                    },
                },
                "schedule": {"bsonType": ["object", "null"]},
                "calendar": {
                    "bsonType": ["object", "null"],
                    "properties": {
                        "provider": {"bsonType": ["string", "null"]},
                        "access_token": {"bsonType": ["string", "null"]},
                        "refresh_token": {"bsonType": ["string", "null"]},
                        "calendar_id": {"bsonType": ["string", "null"]},
                    },
                },
                "is_active": {"bsonType": "bool"},
                "is_network": {"bsonType": "bool"},
                "subscription_expires": {"bsonType": ["date", "null"]},
                "created_at": {"bsonType": ["date", "null"]},
                "updated_at": {"bsonType": ["date", "null"]},
            },
        }
    },

    "clinics": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["clues_id", "name", "unit_type", "price_level"],
            "properties": {
                "clues_id": {"bsonType": "string"},
                "name": {"bsonType": "string"},
                "type": {"bsonType": ["string", "null"]},
                "unit_type": {"bsonType": ["string", "null"]},
                "specialty": {"bsonType": ["string", "null"]},
                "services": {"bsonType": ["array", "null"]},
                "insurances": {"bsonType": ["array", "null"]},
                "price_level": {"bsonType": "int", "minimum": 1, "maximum": 3},
                "state": {"bsonType": ["string", "null"]},
                "municipality": {"bsonType": ["string", "null"]},
                "address": {"bsonType": ["string", "null"]},
                "lat": {"bsonType": ["double", "int", "null"]},
                "lng": {"bsonType": ["double", "int", "null"]},
                "phone": {"bsonType": ["string", "null"]},
                "doctor_id": {"bsonType": ["objectId", "null"]},
                "embedding": {"bsonType": ["array", "null"]},
                "embedding_text": {"bsonType": ["string", "null"]},
                "indexed_at": {"bsonType": ["date", "null"]},
            },
        }
    },

    "gemini_sessions": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["session_id", "user_id", "symptoms"],
            "properties": {
                "session_id": {"bsonType": "string"},
                "user_id": {"bsonType": "objectId"},
                "symptoms": {"bsonType": "string"},
                "triage": {
                    "bsonType": ["object", "null"],
                    "properties": {
                        "urgency_level": {
                            "enum": ["low", "medium", "critical"],
                        },
                        "unit_type": {
                            "enum": ["urgencias", "general", "especialista"],
                        },
                        "specialty": {"bsonType": "string"},
                        "clinical_summary": {"bsonType": "string"},
                        "reasoning": {"bsonType": ["string", "null"]},
                        "red_flags": {"bsonType": ["array", "null"]},
                    },
                },
                "messages": {"bsonType": ["array", "null"]},
                "created_at": {"bsonType": ["date", "null"]},
            },
        }
    },

    "conversations": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["conversation_id", "user_id", "doctor_id", "session_id", "status"],
            "properties": {
                "conversation_id": {"bsonType": "string"},
                "user_id": {"bsonType": "objectId"},
                "doctor_id": {"bsonType": "objectId"},
                "clinic_id": {"bsonType": ["string", "null"]},
                "session_id": {"bsonType": "string"},
                "urgency_level": {
                    "enum": ["low", "medium", "critical", None],
                },
                "clinical_summary": {"bsonType": ["string", "null"]},
                "messages": {"bsonType": ["array", "null"]},
                "status": {"enum": ["active", "closed"]},
                "created_at": {"bsonType": ["date", "null"]},
                "updated_at": {"bsonType": ["date", "null"]},
            },
        }
    },

    "wiki_chunks": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["chunk_id", "source", "text"],
            "properties": {
                "chunk_id":  {"bsonType": "string"},
                "source":    {"bsonType": "string"},
                "condition": {"bsonType": ["string", "null"]},
                "cie10":     {"bsonType": ["string", "null"]},
                "text":      {"bsonType": "string"},
                "embedding": {"bsonType": ["array", "null"]},
            },
        }
    },

    "appointments": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "conversation_id",
                "user_id",
                "doctor_id",
                "scheduled_at",
                "duration_min",
                "status",
            ],
            "properties": {
                "conversation_id": {"bsonType": "string"},
                "user_id": {"bsonType": "objectId"},
                "doctor_id": {"bsonType": "objectId"},
                "clinic_id": {"bsonType": ["string", "null"]},
                "scheduled_at": {"bsonType": "date"},
                "duration_min": {"bsonType": "int", "minimum": 5},
                "status": {
                    "enum": ["pending", "confirmed", "cancelled", "completed"],
                },
                "calendar_event_id": {"bsonType": ["string", "null"]},
                "notes": {"bsonType": ["string", "null"]},
                "created_at": {"bsonType": ["date", "null"]},
                "updated_at": {"bsonType": ["date", "null"]},
            },
        }
    },
}


# ────────────────────────────────────────────────────────────
# Índices (clave, unique, tipo)
# ────────────────────────────────────────────────────────────

INDEXES = {
    "users": [
        {"keys": [("email", 1)], "unique": True},
        {"keys": [("is_active", 1)]},
    ],
    "doctors": [
        {"keys": [("email", 1)], "unique": True},
        {"keys": [("license_number", 1)], "unique": True},
        {"keys": [("specialty", 1)]},
        {"keys": [("is_network", 1)]},
        {"keys": [("insurances", 1)]},
        {"keys": [("location.lat", 1), ("location.lng", 1)]},
    ],
    "clinics": [
        {"keys": [("clues_id", 1)], "unique": True},
        {"keys": [("insurances", 1)]},
        {"keys": [("price_level", 1)]},
        {"keys": [("specialty", 1)]},
        {"keys": [("state", 1), ("municipality", 1)]},
        {"keys": [("lat", 1), ("lng", 1)]},
    ],
    "gemini_sessions": [
        {"keys": [("user_id", 1)]},
        {"keys": [("session_id", 1)], "unique": True},
        {"keys": [("created_at", -1)]},
    ],
    "conversations": [
        {"keys": [("user_id", 1)]},
        {"keys": [("doctor_id", 1)]},
        {"keys": [("conversation_id", 1)], "unique": True},
        {"keys": [("status", 1)]},
        {"keys": [("created_at", -1)]},
    ],
    "appointments": [
        {"keys": [("user_id", 1)]},
        {"keys": [("doctor_id", 1)]},
        {"keys": [("status", 1)]},
        {"keys": [("scheduled_at", 1)]},
        {"keys": [("doctor_id", 1), ("scheduled_at", 1)]},
    ],
    "wiki_chunks": [
        {"keys": [("chunk_id", 1)], "unique": True},
        {"keys": [("source", 1)]},
        {"keys": [("cie10", 1)]},
    ],
}


async def ensure_collection(db, name: str, validator: dict) -> None:
    """Crea la colección con validador, o actualiza el validador si ya existe."""
    existing = await db.list_collection_names()

    if name in existing:
        try:
            await db.command({
                "collMod": name,
                "validator": validator,
                "validationLevel": "moderate",  # valida inserts y updates de campos presentes
            })
            logger.info("  · %-18s validator actualizado", name)
        except OperationFailure as exc:
            logger.warning("  · %-18s no se pudo actualizar validator: %s", name, exc)
    else:
        await db.create_collection(
            name,
            validator=validator,
            validationLevel="moderate",
        )
        logger.info("  · %-18s creada con validator", name)


async def ensure_indexes(db, name: str, specs: list[dict]) -> None:
    coll = db[name]
    created = 0
    for spec in specs:
        keys = spec["keys"]
        kwargs = {k: v for k, v in spec.items() if k != "keys"}
        try:
            await coll.create_index(keys, **kwargs)
            created += 1
        except OperationFailure as exc:
            logger.warning("  · %s.%s fallo: %s", name, keys, exc)
    logger.info("  · %-18s %d índice(s) listos", name, created)


async def main() -> None:
    logger.info("Conectando a MongoDB Atlas (db=%s)...", MONGO_DB_NAME)
    client = AsyncIOMotorClient(MONGO_URI)

    try:
        await client.admin.command("ping")
        logger.info("Conexión OK.")
    except Exception as exc:
        logger.error("No se pudo conectar: %s", exc)
        sys.exit(2)

    db = client[MONGO_DB_NAME]

    logger.info("")
    logger.info("[1/2] Creando colecciones con validadores")
    for coll_name, validator in VALIDATORS.items():
        await ensure_collection(db, coll_name, validator)

    logger.info("")
    logger.info("[2/2] Creando índices")
    for coll_name, specs in INDEXES.items():
        await ensure_indexes(db, coll_name, specs)

    logger.info("")
    logger.info("─" * 60)
    logger.info("Inicialización completa. db=%s", MONGO_DB_NAME)
    logger.info("─" * 60)
    logger.info("")
    logger.info("⚠  CONFIGURACIÓN MANUAL PENDIENTE EN ATLAS UI:")
    logger.info("")
    logger.info("  Debes crear el índice de Vector Search en la colección `clinics`.")
    logger.info("  Atlas UI → Database → healthapp → clinics → Atlas Search → Create Search Index")
    logger.info("")
    logger.info("  Tipo: Vector Search")
    logger.info("  Nombre: clinics_vector_index")
    logger.info('  JSON: {"fields":[{"type":"vector","path":"embedding","numDimensions":768,"similarity":"cosine"}]}')
    logger.info("")
    logger.info("  También crea el índice para wiki_chunks:")
    logger.info("  Atlas UI → Database → healthapp → wiki_chunks → Atlas Search → Create Search Index")
    logger.info("  Nombre: wiki_vector_index")
    logger.info('  JSON: {"fields":[{"type":"vector","path":"embedding","numDimensions":768,"similarity":"cosine"}]}')
    logger.info("")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
