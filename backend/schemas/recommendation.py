from pydantic import BaseModel
from typing import Optional


class Contact(BaseModel):
    type: str  # "chat" | "info"
    doctor_id: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class Recommendation(BaseModel):
    clinic_id: str
    justification: str
    is_network: bool
    priority: int
    contact: Contact
    coords: Optional[dict] = None
    travel_time_min: Optional[float] = None


class RecommendationResponse(BaseModel):
    recommendations: list[Recommendation]
    urgent_message: Optional[str] = None


class AppointmentCreate(BaseModel):
    patient_session_id: str
    doctor_id: str
    clinic_id: str
    datetime_iso: str
    notes: Optional[str] = None


class AppointmentUpdate(BaseModel):
    status: str  # "confirmed" | "cancelled" | "rescheduled"
    datetime_iso: Optional[str] = None
