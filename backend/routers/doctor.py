"""
Doctor router — registro/login, perfil, conexión de calendario y citas del doctor.
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException
from pymongo.errors import DuplicateKeyError

from schemas.doctor import (
    CalendarConnectRequest,
    DoctorLogin,
    DoctorPublic,
    DoctorRegister,
    VALID_SPECIALTIES,
)
from services import auth_service, mongo_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/doctors", tags=["doctors"])


def _doctor_to_public(doc: dict) -> dict:
    """Quita password_hash y tokens de calendario; convierte _id a string."""
    if not doc:
        return {}
    sanitized = {k: v for k, v in doc.items() if k not in {"password_hash"}}
    calendar = sanitized.get("calendar")
    sanitized["calendar_connected"] = bool(calendar and calendar.get("access_token"))
    sanitized.pop("calendar", None)
    sanitized["doctor_id"] = str(sanitized.pop("_id"))
    return sanitized


# ────────────────────────────────────────────────────────────
# Registro / login
# ────────────────────────────────────────────────────────────

@router.post("/register", response_model=DoctorPublic)
async def register_doctor(body: DoctorRegister):
    if body.specialty not in VALID_SPECIALTIES:
        raise HTTPException(
            status_code=400,
            detail=f"Especialidad inválida. Válidas: {sorted(VALID_SPECIALTIES)}",
        )

    now = datetime.now(timezone.utc)
    payload = body.model_dump(exclude={"password"})
    payload["password_hash"] = auth_service.hash_password(body.password)
    payload["is_active"] = True
    payload["calendar"] = None
    payload["subscription_expires"] = None
    payload["created_at"] = now
    payload["updated_at"] = now

    try:
        result = await mongo_service.doctors().insert_one(payload)
    except DuplicateKeyError as exc:
        msg = "Email o cédula ya registrados."
        if "email" in str(exc):
            msg = "Este email ya está registrado."
        elif "license_number" in str(exc):
            msg = "Esta cédula profesional ya está registrada."
        raise HTTPException(status_code=409, detail=msg)

    doc = await mongo_service.doctors().find_one({"_id": result.inserted_id})
    return _doctor_to_public(doc)


@router.post("/login", response_model=DoctorPublic)
async def login_doctor(body: DoctorLogin):
    doc = await mongo_service.doctors().find_one({"email": body.email})
    if not doc or not auth_service.verify_password(body.password, doc.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")
    if not doc.get("is_active", True):
        raise HTTPException(status_code=403, detail="Cuenta inactiva.")
    return _doctor_to_public(doc)


# ────────────────────────────────────────────────────────────
# Perfil
# ────────────────────────────────────────────────────────────

@router.get("/profile", response_model=DoctorPublic)
async def get_profile(doctor_id: str):
    try:
        obj_id = ObjectId(doctor_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="doctor_id inválido.")

    doc = await mongo_service.doctors().find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor no encontrado.")
    return _doctor_to_public(doc)


# ────────────────────────────────────────────────────────────
# Calendario
# ────────────────────────────────────────────────────────────

@router.put("/calendar")
async def connect_calendar(doctor_id: str, body: CalendarConnectRequest):
    try:
        obj_id = ObjectId(doctor_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="doctor_id inválido.")

    # TODO: encriptar access_token y refresh_token con Fernet antes de guardar
    calendar_doc = {
        "provider": body.provider,
        "access_token": body.access_token,
        "refresh_token": body.refresh_token,
        "calendar_id": body.calendar_id,
    }
    result = await mongo_service.doctors().update_one(
        {"_id": obj_id},
        {"$set": {"calendar": calendar_doc, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Doctor no encontrado.")
    return {"ok": True, "calendar_connected": True}


# ────────────────────────────────────────────────────────────
# Citas del doctor
# ────────────────────────────────────────────────────────────

@router.get("/{doctor_id}/appointments")
async def list_doctor_appointments(doctor_id: str, status: str | None = None):
    try:
        obj_id = ObjectId(doctor_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="doctor_id inválido.")

    query: dict = {"doctor_id": obj_id}
    if status:
        query["status"] = status

    cursor = mongo_service.appointments().find(query).sort("scheduled_at", 1)
    out = []
    async for doc in cursor:
        doc["appointment_id"] = str(doc.pop("_id"))
        doc["user_id"] = str(doc["user_id"])
        doc["doctor_id"] = str(doc["doctor_id"])
        out.append(doc)
    return {"appointments": out, "count": len(out)}
