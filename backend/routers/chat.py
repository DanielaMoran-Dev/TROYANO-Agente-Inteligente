"""
Chat router — WebSocket real-time messenger (doctor ↔ patient).
Uses Redis pub/sub to relay messages between parties.
"""

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services import mongo_service, redis_service

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/chat/{conversation_id}")
async def chat_websocket(websocket: WebSocket, conversation_id: str):
    await websocket.accept()

    # Load conversation history
    try:
        conv = await mongo_service.conversations().find_one(
            {"conversation_id": conversation_id}
        )
        history = conv.get("messages", []) if conv else []
        if history:
            await websocket.send_json({"type": "history", "messages": history})
    except Exception as e:
        logger.warning("Could not load conversation history: %s", e)
        history = []

    # Subscribe to this conversation's channel
    channel = f"chat:{conversation_id}"
    pubsub = await redis_service.subscribe(channel)

    import asyncio

    async def _reader():
        """Forward Redis messages to this WebSocket."""
        try:
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    await websocket.send_text(msg["data"])
        except Exception:
            pass

    reader_task = asyncio.create_task(_reader())

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            # Persist to MongoDB
            message_doc = {
                "conversation_id": conversation_id,
                "sender": payload.get("sender"),
                "text": payload.get("text"),
            }
            await mongo_service.conversations().update_one(
                {"conversation_id": conversation_id},
                {"$push": {"messages": message_doc}},
                upsert=True,
            )

            # Publish to Redis so the other party receives it
            await redis_service.publish(channel, json.dumps(message_doc))

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: conversation_id=%s", conversation_id)
    finally:
        reader_task.cancel()
        await pubsub.unsubscribe(channel)


@router.get("/conversations/{conversation_id}", tags=["chat"])
async def get_conversation(conversation_id: str):
    conv = await mongo_service.conversations().find_one(
        {"conversation_id": conversation_id}, {"_id": 0}
    )
    if not conv:
        return {"conversation_id": conversation_id, "messages": []}
    return conv
