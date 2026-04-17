"""Doctor router — registration, profile, calendar connection."""

from fastapi import APIRouter, HTTPException
from schemas.doctor import DoctorRegister, CalendarConnectRequest
from services import mongo_service

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.post("/register")
async def register_doctor(body: DoctorRegister):
    doc = body.model_dump()
    doc["is_active"] = True
    doc["calendar_connected"] = False
    result = await mongo_service.doctors().insert_one(doc)
    return {"doctor_id": str(result.inserted_id), "ok": True}


@router.get("/profile")
async def get_profile(doctor_id: str):
    from bson import ObjectId
    doc = await mongo_service.doctors().find_one({"_id": ObjectId(doctor_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found.")
    doc["doctor_id"] = str(doc.pop("_id"))
    return doc


@router.put("/calendar")
async def connect_calendar(doctor_id: str, body: CalendarConnectRequest):
    from bson import ObjectId
    await mongo_service.doctors().update_one(
        {"_id": ObjectId(doctor_id)},
        {"$set": {
            "calendar_provider": body.provider,
            "calendar_access_token": body.access_token,
            "calendar_refresh_token": body.refresh_token,
            "calendar_connected": True,
        }},
    )
    return {"ok": True}
