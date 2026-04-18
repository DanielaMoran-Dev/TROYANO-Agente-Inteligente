from typing import List, Optional
from pydantic import BaseModel, Field

VALID_UNIT_TYPES = ["general", "especialidad", "urgencias", "hospital"]
VALID_INSURANCES = ["imss", "issste", "seguro_popular", "ninguno"]

VALID_SPECIALTIES = [
    "medicina_general", "cardiología", "neurología", "pediatría",
    "ginecología", "traumatología", "dermatología", "oftalmología",
    "otorrinolaringología", "gastroenterología", "neumología", "urología",
    "nefrología", "psiquiatría", "endocrinología", "odontología",
    "urgencias", "cirugía_general",
]


class ClinicRegister(BaseModel):
    doctor_ids: List[str] = []
    name: str = Field(..., min_length=2, max_length=200)
    phone: Optional[str] = None
    address: str = Field(..., min_length=5)
    lat: Optional[float] = None
    lng: Optional[float] = None
    specialty: str = "medicina_general"
    unit_type: str = "general"
    insurances: List[str] = []
    price_level: int = Field(2, ge=1, le=3)
    services: List[str] = []
    state: Optional[str] = None
    municipality: Optional[str] = None
    maps_place_id: Optional[str] = None
    formatted_address: Optional[str] = None


class ClinicUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    phone: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    specialty: Optional[str] = None
    unit_type: Optional[str] = None
    insurances: Optional[List[str]] = None
    price_level: Optional[int] = Field(None, ge=1, le=3)
    services: Optional[List[str]] = None
    state: Optional[str] = None
    municipality: Optional[str] = None
    maps_place_id: Optional[str] = None
    formatted_address: Optional[str] = None


class ClinicPublic(BaseModel):
    clinic_id: str
    name: str
    phone: Optional[str] = None
    address: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    specialty: str
    unit_type: str
    insurances: List[str] = []
    price_level: int
    services: List[str] = []
    state: Optional[str] = None
    municipality: Optional[str] = None
    doctor_ids: List[str] = []
    maps_place_id: Optional[str] = None
    formatted_address: Optional[str] = None


class ClinicDoctorLink(BaseModel):
    doctor_id: str


class ClinicDoctorInfo(BaseModel):
    doctor_id: str
    name: str
    specialty: Optional[str] = None
    is_network: bool = False
    is_active: bool = True


class ClinicFromPlace(BaseModel):
    """Create-or-link a clinic from a Google Places result."""
    maps_place_id: str = Field(..., min_length=4)
    name: str = Field(..., min_length=2, max_length=200)
    formatted_address: str = Field(..., min_length=3)
    lat: float
    lng: float
    phone: Optional[str] = None
    state: Optional[str] = None
    municipality: Optional[str] = None
    # Doctor to link after create/lookup (optional — a clinic can exist without doctors)
    doctor_id: Optional[str] = None


class ClinicSearchResult(BaseModel):
    clinic_id: str
    name: str
    address: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    specialty: Optional[str] = None
    unit_type: Optional[str] = None
    doctor_count: int = 0
    has_network_doctor: bool = False
    maps_place_id: Optional[str] = None
    source: str = "db"   # "db" | "clues"
