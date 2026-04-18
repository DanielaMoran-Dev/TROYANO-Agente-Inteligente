"""
Pydantic schemas del doctor.
Alineados con Claude/DATABASE_SCHEMA.md.
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal


Insurance = Literal["imss", "issste", "seguro_popular", "ninguno"]
CalendarProvider = Literal["google", "outlook", "apple"]


VALID_SPECIALTIES = {
    "cardiología", "neurología", "medicina_general", "pediatría",
    "ginecología", "traumatología", "dermatología", "oftalmología",
    "otorrinolaringología", "gastroenterología", "neumología",
    "urología", "nefrología", "psiquiatría", "endocrinología",
}


class DoctorLocation(BaseModel):
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    maps_place_id: Optional[str] = None


class DailySchedule(BaseModel):
    open: str  # "09:00"
    close: str  # "18:00"


class WeeklySchedule(BaseModel):
    monday: Optional[DailySchedule] = None
    tuesday: Optional[DailySchedule] = None
    wednesday: Optional[DailySchedule] = None
    thursday: Optional[DailySchedule] = None
    friday: Optional[DailySchedule] = None
    saturday: Optional[DailySchedule] = None
    sunday: Optional[DailySchedule] = None


class DoctorRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)
    phone: Optional[str] = None
    license_number: str = Field(..., min_length=4, max_length=32)
    specialty: str
    price_level: int = Field(..., ge=1, le=3)
    insurances: list[Insurance] = []
    location: Optional[DoctorLocation] = None
    schedule: Optional[WeeklySchedule] = None
    is_network: bool = False


class DoctorLogin(BaseModel):
    email: EmailStr
    password: str


class DoctorPublic(BaseModel):
    """Campos seguros para exponer; nunca password_hash ni tokens de calendario."""
    doctor_id: str
    email: EmailStr
    name: str
    last_name: str
    phone: Optional[str] = None
    license_number: str
    specialty: str
    price_level: int
    insurances: list[str] = []
    location: Optional[DoctorLocation] = None
    schedule: Optional[WeeklySchedule] = None
    is_active: bool = True
    is_network: bool = False
    calendar_connected: bool = False


class CalendarConnectRequest(BaseModel):
    provider: CalendarProvider
    access_token: str
    refresh_token: Optional[str] = None
    calendar_id: Optional[str] = None
