"""
Pydantic schemas del paciente (users) y del flujo de consulta.
Alineados con Claude/DATABASE_SCHEMA.md.
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal
import uuid


Insurance = Literal["imss", "issste", "seguro_popular", "ninguno"]
BudgetLevel = Literal["$", "$$", "$$$"]
BloodType = Literal["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]


class Coords(BaseModel):
    lat: float
    lng: float


class MedicalHistory(BaseModel):
    free_text: Optional[str] = None
    conditions: list[str] = []
    allergies: list[str] = []
    medications: list[str] = []
    blood_type: Optional[BloodType] = None


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)
    age: Optional[int] = Field(None, ge=0, le=120)
    phone: Optional[str] = None
    coords: Optional[Coords] = None
    insurance: Insurance = "ninguno"
    medical_history: Optional[MedicalHistory] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    """Campos seguros para exponer en la API (sin password_hash)."""
    user_id: str
    email: EmailStr
    name: str
    last_name: str
    age: Optional[int] = None
    phone: Optional[str] = None
    coords: Optional[Coords] = None
    insurance: Insurance
    medical_history: Optional[MedicalHistory] = None
    is_active: bool = True


class ConsultRequest(BaseModel):
    """
    Entrada al pipeline /consult.
    `user_id` identifica al paciente registrado; `session_id` agrupa la consulta.
    """
    user_id: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symptoms: str = Field(..., min_length=5, max_length=2000)
    coords: Coords
    insurance: Insurance
    budget_level: BudgetLevel
    radius_m: int = Field(5000, ge=500, le=50000)
