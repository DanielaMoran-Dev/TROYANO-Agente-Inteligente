from pydantic import BaseModel, Field
from typing import Optional
import uuid


class Coords(BaseModel):
    lat: float
    lng: float


class ConsultRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symptoms: str = Field(..., min_length=5, max_length=2000)
    coords: Coords
    insurance: str = Field(..., pattern="^(imss|issste|seguro_popular|ninguno)$")
    budget_level: str = Field(..., pattern=r"^\$+$")


class PatientSession(BaseModel):
    session_id: str
    symptoms: str
    coords: Coords
    insurance: str
    budget_level: str
    triage: Optional[dict] = None
    recommendations: Optional[dict] = None
