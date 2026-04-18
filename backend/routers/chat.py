"""
Chat router — creación de conversaciones + WebSocket doctor↔paciente.

Una conversación se crea a partir de una sesión de triaje (`gemini_sessions`)
y sólo se permite si el doctor tiene is_network=True (modelo de negocio).
El primer mensaje siempre es del `sender: system` con el perfil clínico.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from schemas.recommendation import ConversationCreate
from services import mongo_service, redis_service

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────

def _serialize_conversation(doc: dict) -> dict:
    """Serializa una conversación para respuesta JSON."""
    doc = dict(doc)
    doc["_id"] = str(doc["_id"])
    doc["user_id"] = str(doc["user_id"])
    doc["doctor_id"] = str(doc["doctor_id"])
    return doc


# ────────────────────────────────────────────────────────────
# Crear conversación (post-recomendación, pre-chat)
# ────────────────────────────────────────────────────────────

@router.post("/conversations")
async def create_conversation(body: ConversationCreate):
    try:
        user_obj_id = ObjectId(body.user_id)
        doctor_obj_id = ObjectId(body.doctor_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="user_id o doctor_id inválido.")

    # Validar doctor en red
    doctor = await mongo_service.doctors().find_one(
        {"_id": doctor_obj_id},
        {"is_active": 1, "is_network": 1},
    )
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor no encontrado.")
    if not doctor.get("is_network") or not doctor.get("is_active", True):
        raise HTTPException(
            status_code=403,
            detail="Sólo doctores en red pueden iniciar conversaciones.",
        )

    # Obtener sesión de triaje + contexto del paciente
    session = await mongo_service.gemini_sessions().find_one(
        {"session_id": body.session_id},
        {"triage": 1, "user_id": 1, "patient_context": 1},
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sesión de triaje no encontrada.")

    triage = session.get("triage") or {}
    clinical_summary = triage.get("clinical_summary", "")
    urgency_level = triage.get("urgency_level")
    red_flags = triage.get("red_flags") or []

    # Enrich with stored patient context (age, allergies, conditions, medications)
    ctx = session.get("patient_context") or {}
    profile_lines = [f"Urgencia: {urgency_level or 'desconocida'}"]
    if ctx.get("age"):
        profile_lines.append(f"Edad: {ctx['age']} años")
    if ctx.get("conditions"):
        profile_lines.append(f"Antecedentes: {', '.join(ctx['conditions'])}")
    if ctx.get("allergies"):
        profile_lines.append(f"⚠️ ALERGIAS: {', '.join(ctx['allergies'])}")
    if ctx.get("medications"):
        profile_lines.append(f"Medicamentos actuales: {', '.join(ctx['medications'])}")
    if ctx.get("blood_type"):
        profile_lines.append(f"Tipo sanguíneo: {ctx['blood_type']}")
    if ctx.get("insurance"):
        profile_lines.append(f"Seguro: {ctx['insurance']}")
    if ctx.get("duration"):
        profile_lines.append(f"Duración de síntomas: {ctx['duration']}")
    if ctx.get("severity"):
        profile_lines.append(f"Severidad: {ctx['severity']}")
    if red_flags:
        profile_lines.append(f"🚨 Señales de alarma: {', '.join(red_flags)}")
    profile_lines.append(f"Resumen clínico: {clinical_summary}")

    now = datetime.now(timezone.utc)
    conversation_id = str(uuid.uuid4())
    system_message = {
        "sender": "system",
        "text": "PERFIL CLÍNICO\n" + "\n".join(profile_lines),
        "timestamp": now,
    }

    doc = {
        "conversation_id": conversation_id,
        "user_id": user_obj_id,
        "doctor_id": doctor_obj_id,
        "clinic_id": body.clinic_id,
        "session_id": body.session_id,
        "urgency_level": urgency_level,
        "clinical_summary": clinical_summary,
        "messages": [system_message],
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    await mongo_service.conversations().insert_one(doc)
    return {"conversation_id": conversation_id, "status": "active"}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    doc = await mongo_service.conversations().find_one({"conversation_id": conversation_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Conversación no encontrada.")
    return _serialize_conversation(doc)


@router.get("/conversations")
async def list_conversations(user_id: str | None = None, doctor_id: str | None = None):
    """
    Lista conversaciones de un paciente (user_id) o un doctor (doctor_id),
    enriquecidas con nombre de la contraparte y último mensaje.
    """
    if not user_id and not doctor_id:
        raise HTTPException(status_code=400, detail="Se requiere user_id o doctor_id.")

    try:
        if user_id:
            oid = ObjectId(user_id)
            query = {"user_id": oid}
        else:
            oid = ObjectId(doctor_id)
            query = {"doctor_id": oid}
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido.")

    cursor = mongo_service.conversations().find(query).sort("updated_at", -1)
    docs = [doc async for doc in cursor]

    # Collect counterpart IDs to batch-fetch names
    if user_id:
        # Patient view → need doctor names
        doctor_oids = list({d["doctor_id"] for d in docs if "doctor_id" in d})
        doctors_map: dict = {}
        if doctor_oids:
            async for doc in mongo_service.doctors().find(
                {"_id": {"$in": doctor_oids}},
                {"_id": 1, "name": 1, "last_name": 1, "specialty": 1},
            ):
                full = " ".join(filter(None, [doc.get("name"), doc.get("last_name")])).strip()
                doctors_map[doc["_id"]] = {"name": full or "Doctor", "specialty": doc.get("specialty")}
    else:
        # Doctor view → need patient names
        user_oids = list({d["user_id"] for d in docs if "user_id" in d})
        users_map: dict = {}
        if user_oids:
            async for doc in mongo_service.users().find(
                {"_id": {"$in": user_oids}},
                {"_id": 1, "name": 1, "last_name": 1},
            ):
                full = " ".join(filter(None, [doc.get("name"), doc.get("last_name")])).strip()
                users_map[doc["_id"]] = full or "Paciente"

    result = []
    for d in docs:
        # Last non-system message preview
        messages = d.get("messages") or []
        last_text = ""
        for m in reversed(messages):
            if m.get("sender") != "system":
                last_text = (m.get("text") or "")[:80]
                break

        entry = {
            "conversation_id": d.get("conversation_id", ""),
            "status": d.get("status", "active"),
            "urgency_level": d.get("urgency_level"),
            "clinical_summary": d.get("clinical_summary"),
            "updated_at": d.get("updated_at").isoformat() if d.get("updated_at") else None,
            "last_message_text": last_text,
            "user_id": str(d["user_id"]),
            "doctor_id": str(d["doctor_id"]),
        }

        if user_id:
            info = doctors_map.get(d.get("doctor_id"), {})
            entry["doctor_name"] = info.get("name", "Doctor")
            entry["doctor_specialty"] = info.get("specialty")
        else:
            entry["patient_name"] = users_map.get(d.get("user_id"), "Paciente")
            entry["doctor_specialty"] = d.get("urgency_level")  # reuse for specialty if needed

        result.append(entry)

    return {"conversations": result}


@router.put("/conversations/{conversation_id}/close")
async def close_conversation(conversation_id: str):
    result = await mongo_service.conversations().update_one(
        {"conversation_id": conversation_id},
        {"$set": {"status": "closed", "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Conversación no encontrada.")
    return {"ok": True, "status": "closed"}


# ────────────────────────────────────────────────────────────
# WebSocket en tiempo real
# ────────────────────────────────────────────────────────────

@router.websocket("/ws/chat/{conversation_id}")
async def chat_websocket(websocket: WebSocket, conversation_id: str):
    await websocket.accept()

    # Historial inicial
    history: list[dict] = []
    try:
        conv = await mongo_service.conversations().find_one(
            {"conversation_id": conversation_id}
        )
        if conv is None:
            await websocket.send_json({
                "type": "error",
                "detail": "Conversación no encontrada.",
            })
            await websocket.close(code=4004)
            return
        if conv.get("status") != "active":
            await websocket.send_json({
                "type": "error",
                "detail": "Esta conversación está cerrada.",
            })
            await websocket.close(code=4003)
            return
        history = conv.get("messages", [])
        if history:
            await websocket.send_json({"type": "history", "messages": _jsonable(history)})
    except Exception as e:
        logger.warning("No se pudo cargar historial: %s", e)

    channel = f"chat:{conversation_id}"
    pubsub = await redis_service.subscribe(channel)

    async def _reader():
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
            sender = payload.get("sender")
            text = payload.get("text", "")

            if sender not in ("patient", "user", "doctor"):
                await websocket.send_json({"type": "error", "detail": "sender inválido."})
                continue
            if not text.strip():
                continue

            stored_sender = "user" if sender == "patient" else sender
            message_doc = {
                "sender": stored_sender,
                "text": text,
                "timestamp": datetime.now(timezone.utc),
            }

            # Persistir en Mongo
            await mongo_service.conversations().update_one(
                {"conversation_id": conversation_id},
                {
                    "$push": {"messages": message_doc},
                    "$set": {"updated_at": message_doc["timestamp"]},
                },
            )

            # Broadcast vía Redis (el timestamp se serializa a ISO)
            await redis_service.publish(channel, json.dumps(_jsonable(message_doc)))

    except WebSocketDisconnect:
        logger.info("WS disconnect: conversation_id=%s", conversation_id)
    finally:
        reader_task.cancel()
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            pass


def _jsonable(obj):
    """Convierte datetimes a ISO strings para envío por WebSocket/Redis."""
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj
