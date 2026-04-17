"""
MongoDB Service — async Motor client + collection accessors.
Collections: patients, doctors, clinics, conversations, appointments
"""

import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "healthapp")

_client: AsyncIOMotorClient = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
        logger.info("MongoDB client created (db=%s)", MONGO_DB_NAME)
    return _client


def get_db():
    return get_client()[MONGO_DB_NAME]


def patients():
    return get_db()["patients"]


def doctors():
    return get_db()["doctors"]


def clinics():
    return get_db()["clinics"]


def conversations():
    return get_db()["conversations"]


def appointments():
    return get_db()["appointments"]


async def vector_search_clinics(embedding: list[float], limit: int = 20) -> list[dict]:
    """
    Atlas Vector Search on the clinics collection.
    Requires a knnVector index named 'clinics_embedding_index' on the 'embedding' field.
    """
    pipeline = [
        {
            "$vectorSearch": {
                "index": "clinics_embedding_index",
                "path": "embedding",
                "queryVector": embedding,
                "numCandidates": limit * 5,
                "limit": limit,
            }
        },
        {
            "$project": {
                "_id": 0,
                "clinic_id": {"$toString": "$_id"},
                "name": 1,
                "specialty": 1,
                "unit_type": 1,
                "insurance": 1,
                "budget_level": 1,
                "coords": 1,
                "phone": 1,
                "address": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    cursor = clinics().aggregate(pipeline)
    return await cursor.to_list(length=limit)
