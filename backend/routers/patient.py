"""Patient router — main consultation pipeline and maps endpoints."""

import traceback
from fastapi import APIRouter, HTTPException

from pydantic import BaseModel

from schemas.patient import ConsultRequest
from schemas.recommendation import AppointmentCreate, AppointmentUpdate
from agents import triage_agent, routing_agent, recommendation_agent, chat_agent
from services import maps_service, mongo_service

router = APIRouter()


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str = ""
    has_coords: bool = False


@router.post("/chat/message", tags=["chat"])
async def chat_message(body: ChatMessageRequest):
    """One conversational turn with the data-collection agent."""
    try:
        return chat_agent.reply(body.session_id, body.message, has_coords=body.has_coords)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chat error: {exc}") from exc


@router.post("/chat/reset", tags=["chat"])
async def chat_reset(body: ChatMessageRequest):
    chat_agent.reset(body.session_id)
    return {"ok": True}


@router.post("/consult", tags=["patient"])
async def consult(body: ConsultRequest):
    """
    Full pipeline: triage → routing → recommendation.
    Persists session to MongoDB.
    """
    try:
        # 1. Triage
        triage = triage_agent.run(body.symptoms)

        # 2. Routing
        routing = await routing_agent.run(
            triage=triage,
            insurance=body.insurance,
            budget_level=body.budget_level,
            coords=body.coords.model_dump(),
        )

        # 3. Recommendation
        recs = await recommendation_agent.run(routing=routing, triage=triage)

        # 4. Persist session
        session_doc = {
            "session_id": body.session_id,
            "symptoms": body.symptoms,
            "coords": body.coords.model_dump(),
            "insurance": body.insurance,
            "budget_level": body.budget_level,
            "triage": triage,
            "recommendations": recs,
        }
        await mongo_service.patients().insert_one(session_doc)

        return {
            "session_id": body.session_id,
            "triage": triage,
            "recommendations": recs,
        }

    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}") from exc


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


@router.post("/appointments", tags=["appointments"])
async def create_appointment(body: AppointmentCreate):
    doc = body.model_dump()
    doc["status"] = "pending"
    result = await mongo_service.appointments().insert_one(doc)
    return {"appointment_id": str(result.inserted_id), "status": "pending"}


@router.put("/appointments/{appointment_id}", tags=["appointments"])
async def update_appointment(appointment_id: str, body: AppointmentUpdate):
    from bson import ObjectId
    update = {"$set": body.model_dump(exclude_none=True)}
    await mongo_service.appointments().update_one(
        {"_id": ObjectId(appointment_id)}, update
    )
    return {"ok": True}
