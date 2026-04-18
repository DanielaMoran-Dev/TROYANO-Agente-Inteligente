"""
Patient router — registro/login de usuarios, pipeline de consulta, mapas y citas.
"""

import logging
import traceback
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from schemas.patient import (
    ConsultRequest,
    UserLogin,
    UserPublic,
    UserRegister,
)
from schemas.recommendation import AppointmentCreate, AppointmentUpdate
from agents import triage_agent, routing_agent, recommendation_agent, chat_agent
from services import auth_service, maps_service, mongo_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ────────────────────────────────────────────────────────────
# Usuarios (pacientes)
# ────────────────────────────────────────────────────────────

def _user_to_public(doc: dict) -> dict:
    """Quita password_hash y convierte _id a string."""
    if not doc:
        return {}
    out = {k: v for k, v in doc.items() if k != "password_hash"}
    out["user_id"] = str(out.pop("_id"))
    return out


@router.post("/users/register", tags=["users"], response_model=UserPublic)
async def register_user(body: UserRegister):
    now = datetime.now(timezone.utc)
    payload = body.model_dump(exclude={"password"})
    payload["password_hash"] = auth_service.hash_password(body.password)
    payload["is_active"] = True
    payload["created_at"] = now
    payload["updated_at"] = now

    try:
        result = await mongo_service.users().insert_one(payload)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Este email ya está registrado.")

    doc = await mongo_service.users().find_one({"_id": result.inserted_id})
    return _user_to_public(doc)


@router.post("/users/login", tags=["users"], response_model=UserPublic)
async def login_user(body: UserLogin):
    doc = await mongo_service.users().find_one({"email": body.email})
    if not doc or not auth_service.verify_password(body.password, doc.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")
    if not doc.get("is_active", True):
        raise HTTPException(status_code=403, detail="Cuenta inactiva.")
    return _user_to_public(doc)


@router.get("/users/{user_id}", tags=["users"], response_model=UserPublic)
async def get_user(user_id: str):
    try:
        obj_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="user_id inválido.")

    doc = await mongo_service.users().find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return _user_to_public(doc)


# ────────────────────────────────────────────────────────────
# Chat agent (recolección de datos previo al /consult)
# ────────────────────────────────────────────────────────────

class ChatMessageRequest(BaseModel):
    session_id: str
    message: str = ""
    has_coords: bool = False


@router.post("/chat/message", tags=["chat"])
async def chat_message(body: ChatMessageRequest):
    """Un turno conversacional con el agente de recolección."""
    try:
        return chat_agent.reply(body.session_id, body.message, has_coords=body.has_coords)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chat error: {exc}") from exc


@router.post("/chat/reset", tags=["chat"])
async def chat_reset(body: ChatMessageRequest):
    chat_agent.reset(body.session_id)
    return {"ok": True}


# ────────────────────────────────────────────────────────────
# Pipeline principal: triaje → ruteo → recomendación
# ────────────────────────────────────────────────────────────

@router.post("/consult", tags=["patient"])
async def consult(body: ConsultRequest):
    """
    Pipeline completo. Persiste la sesión en `gemini_sessions`.
    Requiere que el paciente esté registrado (user_id en `users`).
    """
    try:
        user_obj_id = ObjectId(body.user_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="user_id inválido.")

    user_doc = await mongo_service.users().find_one({"_id": user_obj_id}, {"_id": 1})
    if not user_doc:
        raise HTTPException(status_code=404, detail="Usuario no registrado.")

    try:
        # 1. Triaje
        triage = triage_agent.run(body.symptoms)

        # 2. Ruteo (Places nearby + vector search + filtros + travel times)
        routing = await routing_agent.run(
            triage=triage,
            insurance=body.insurance,
            budget_level=body.budget_level,
            coords=body.coords.model_dump(),
            radius_m=body.radius_m,
        )

        # 3. Recomendación
        recs = await recommendation_agent.run(routing=routing, triage=triage)

        # 4. Persistir en gemini_sessions (upsert por session_id)
        session_doc = {
            "session_id": body.session_id,
            "user_id": user_obj_id,
            "symptoms": body.symptoms,
            "triage": triage,
            "messages": [],
            "created_at": datetime.now(timezone.utc),
        }
        await mongo_service.gemini_sessions().update_one(
            {"session_id": body.session_id},
            {"$set": session_doc},
            upsert=True,
        )

        return {
            "session_id": body.session_id,
            "triage": triage,
            "recommendations": recs,
        }

    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}") from exc


@router.get("/sessions/{session_id}", tags=["patient"])
async def get_session(session_id: str):
    """Devuelve una sesión de triaje guardada."""
    doc = await mongo_service.gemini_sessions().find_one({"session_id": session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")
    doc["_id"] = str(doc["_id"])
    doc["user_id"] = str(doc["user_id"])
    return doc


# ────────────────────────────────────────────────────────────
# Maps
# ────────────────────────────────────────────────────────────

@router.get("/maps/search", tags=["maps"])
async def maps_search(q: str):
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required.")
    try:
        return maps_service.search_place(q.strip())
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/maps/routes", tags=["maps"])
async def maps_routes(body: dict):
    try:
        return maps_service.get_routes(
            origin_lat=body["origin_lat"],
            origin_lng=body["origin_lng"],
            destinations=body["destinations"],
            travel_mode=body.get("travel_mode", "DRIVE"),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/maps/key", tags=["maps"])
async def maps_key():
    if not maps_service.is_configured():
        raise HTTPException(status_code=503, detail="Google Maps API key not configured.")
    return {"key": maps_service.GOOGLE_MAPS_API_KEY}


# ────────────────────────────────────────────────────────────
# Citas
# ────────────────────────────────────────────────────────────

@router.post("/appointments", tags=["appointments"])
async def create_appointment(body: AppointmentCreate):
    try:
        user_obj_id = ObjectId(body.user_id)
        doctor_obj_id = ObjectId(body.doctor_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="user_id o doctor_id inválido.")

    now = datetime.now(timezone.utc)
    doc = {
        "conversation_id": body.conversation_id,
        "user_id": user_obj_id,
        "doctor_id": doctor_obj_id,
        "clinic_id": body.clinic_id,
        "scheduled_at": body.scheduled_at,
        "duration_min": body.duration_min,
        "status": "pending",
        "calendar_event_id": None,
        "notes": body.notes,
        "created_at": now,
        "updated_at": now,
    }
    result = await mongo_service.appointments().insert_one(doc)
    return {"appointment_id": str(result.inserted_id), "status": "pending"}


@router.put("/appointments/{appointment_id}", tags=["appointments"])
async def update_appointment(appointment_id: str, body: AppointmentUpdate):
    try:
        obj_id = ObjectId(appointment_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="appointment_id inválido.")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar.")
    updates["updated_at"] = datetime.now(timezone.utc)

    result = await mongo_service.appointments().update_one({"_id": obj_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")
    return {"ok": True}


@router.get("/appointments/{appointment_id}", tags=["appointments"])
async def get_appointment(appointment_id: str):
    try:
        obj_id = ObjectId(appointment_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="appointment_id inválido.")

    doc = await mongo_service.appointments().find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")

    doc["appointment_id"] = str(doc.pop("_id"))
    doc["user_id"] = str(doc["user_id"])
    doc["doctor_id"] = str(doc["doctor_id"])
    return doc
