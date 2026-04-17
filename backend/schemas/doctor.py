from pydantic import BaseModel, Field, EmailStr
from typing import Optional


class DoctorRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    specialty: str
    clinic_id: Optional[str] = None
    insurance: list[str] = []
    price_level: str = Field(default="$$", pattern=r"^\$+$")
    phone: Optional[str] = None


class DoctorProfile(BaseModel):
    doctor_id: str
    name: str
    specialty: str
    email: str
    is_active: bool = True
    calendar_connected: bool = False
    insurance: list[str] = []
    price_level: str


class CalendarConnectRequest(BaseModel):
    provider: str = Field(..., pattern="^(google|outlook|apple)$")
    access_token: str
    refresh_token: Optional[str] = None
