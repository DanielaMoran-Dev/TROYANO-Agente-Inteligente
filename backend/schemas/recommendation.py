"""
Pydantic schemas de recomendaciones, conversaciones y citas.
Alineados con Claude/DATABASE_SCHEMA.md.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


UrgencyLevel = Literal["low", "medium", "critical"]
AppointmentStatus = Literal["pending", "confirmed", "cancelled", "completed"]
ConversationStatus = Literal["active", "closed"]


class DoctorRef(BaseModel):
    doctor_id: str
    name: str
    specialty: Optional[str] = None


class Contact(BaseModel):
    type: Literal["chat", "info"]
    doctor_id: Optional[str] = None
    doctors: Optional[list["DoctorRef"]] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class Recommendation(BaseModel):
    clinic_id: str
    name: Optional[str] = None
    justification: str
    is_network: bool
    priority: int
    match_score: Optional[int] = None
    contact: Contact
    coords: Optional[dict] = None
    travel_time_min: Optional[float] = None


class RecommendationResponse(BaseModel):
    recommendations: list[Recommendation]
    urgent_message: Optional[str] = None


class ConversationCreate(BaseModel):
    """
    Crea una conversación paciente-doctor a partir de una sesión de triaje.
    El doctor debe ser is_network=True (se valida en el router).
    """
    user_id: str
    doctor_id: str
    session_id: str
    clinic_id: Optional[str] = None


class ChatMessage(BaseModel):
    sender: Literal["system", "user", "doctor"]
    text: str
    timestamp: Optional[datetime] = None


class AppointmentCreate(BaseModel):
    conversation_id: str
    user_id: str
    doctor_id: str
    clinic_id: Optional[str] = None
    scheduled_at: datetime
    duration_min: int = Field(default=30, ge=5, le=240)
    notes: Optional[str] = None


class AppointmentUpdate(BaseModel):
    status: Optional[AppointmentStatus] = None
    scheduled_at: Optional[datetime] = None
    duration_min: Optional[int] = Field(default=None, ge=5, le=240)
    notes: Optional[str] = None
    calendar_event_id: Optional[str] = None
