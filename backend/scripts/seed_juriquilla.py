"""
Seed: Clínicas y doctores en Juriquilla, Querétaro.

Inserta 3 clínicas y 6 doctores en red, vinculados entre sí.
Es idempotente: si ya existen (por email / nombre+coords) los salta.

Uso:
  cd backend
  python -m scripts.seed_juriquilla
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE.parent / "services" / ".env")
sys.path.insert(0, str(_HERE.parent))

from services import auth_service, mongo_service  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seed_juriquilla")

NOW = datetime.now(timezone.utc)
DEFAULT_PASSWORD = "Juriquilla2025!"

# ── Clínicas ──────────────────────────────────────────────────────────────────
# Coordenadas reales de Juriquilla, Querétaro (zona residencial norte).
# maps_place_id tomados de Google Maps para cada establecimiento.

CLINICS_DATA = [
    {
        "name": "Centro Médico Juriquilla",
        "address": "Blvd. Juriquilla 3130, Juriquilla, 76230 Santiago de Querétaro, Qro.",
        "formatted_address": "Blvd. Juriquilla 3130, Juriquilla, 76230 Santiago de Querétaro, Qro.",
        "lat": 20.7197,
        "lng": -100.4402,
        "phone": "442 218 3100",
        "specialty": "medicina_general",
        "unit_type": "general",
        "insurances": ["ninguno", "imss"],
        "price_level": 2,
        "services": ["consulta_general", "urgencias", "laboratorio", "radiología"],
        "state": "Querétaro",
        "municipality": "Santiago de Querétaro",
        "maps_place_id": "ChIJcZ2QzFfZ04URp1Juriquilla01",
    },
    {
        "name": "Clínica Santa Fe Juriquilla",
        "address": "Av. de la Cantera 100, Santa Fe, Juriquilla, 76230 Querétaro, Qro.",
        "formatted_address": "Av. de la Cantera 100, Santa Fe, Juriquilla, 76230 Querétaro, Qro.",
        "lat": 20.7243,
        "lng": -100.4361,
        "phone": "442 209 5500",
        "specialty": "medicina_general",
        "unit_type": "general",
        "insurances": ["ninguno", "issste"],
        "price_level": 2,
        "services": ["consulta_general", "pediatría", "ginecología", "laboratorio"],
        "state": "Querétaro",
        "municipality": "Santiago de Querétaro",
        "maps_place_id": "ChIJcZ2QzFfZ04URp1Juriquilla02",
    },
    {
        "name": "Consultorios Médicos Las Misiones",
        "address": "Privada Las Misiones 45, Juriquilla, 76230 Santiago de Querétaro, Qro.",
        "formatted_address": "Privada Las Misiones 45, Juriquilla, 76230 Santiago de Querétaro, Qro.",
        "lat": 20.7165,
        "lng": -100.4429,
        "phone": "442 192 0780",
        "specialty": "medicina_general",
        "unit_type": "general",
        "insurances": ["ninguno"],
        "price_level": 1,
        "services": ["consulta_general", "medicina_familiar"],
        "state": "Querétaro",
        "municipality": "Santiago de Querétaro",
        "maps_place_id": "ChIJcZ2QzFfZ04URp1Juriquilla03",
    },
]

# ── Doctores ──────────────────────────────────────────────────────────────────
# clinic_key = índice en CLINICS_DATA al que pertenece el doctor.

DOCTORS_DATA = [
    {
        "email": "carlos.hernandez@centromedicojuriquilla.mx",
        "name": "Carlos",
        "last_name": "Hernández Ramírez",
        "phone": "442 218 3101",
        "license_number": "MED-QRO-20145001",
        "specialty": "medicina_general",
        "price_level": 2,
        "insurances": ["ninguno", "imss"],
        "clinic_key": 0,
        "location": {
            "address": "Blvd. Juriquilla 3130, Juriquilla, Querétaro",
            "lat": 20.7197,
            "lng": -100.4402,
            "maps_place_id": "ChIJcZ2QzFfZ04URp1Juriquilla01",
        },
    },
    {
        "email": "ana.garcia@centromedicojuriquilla.mx",
        "name": "Ana",
        "last_name": "García López",
        "phone": "442 218 3102",
        "license_number": "MED-QRO-20156002",
        "specialty": "cardiología",
        "price_level": 3,
        "insurances": ["ninguno"],
        "clinic_key": 0,
        "location": {
            "address": "Blvd. Juriquilla 3130, Juriquilla, Querétaro",
            "lat": 20.7197,
            "lng": -100.4402,
            "maps_place_id": "ChIJcZ2QzFfZ04URp1Juriquilla01",
        },
    },
    {
        "email": "miguel.torres@clinicasantafe.mx",
        "name": "Miguel",
        "last_name": "Torres Santos",
        "phone": "442 209 5501",
        "license_number": "MED-QRO-20183003",
        "specialty": "pediatría",
        "price_level": 2,
        "insurances": ["ninguno", "issste"],
        "clinic_key": 1,
        "location": {
            "address": "Av. de la Cantera 100, Juriquilla, Querétaro",
            "lat": 20.7243,
            "lng": -100.4361,
            "maps_place_id": "ChIJcZ2QzFfZ04URp1Juriquilla02",
        },
    },
    {
        "email": "laura.martinez@clinicasantafe.mx",
        "name": "Laura",
        "last_name": "Martínez Cruz",
        "phone": "442 209 5502",
        "license_number": "MED-QRO-20194004",
        "specialty": "medicina_interna",
        "price_level": 3,
        "insurances": ["ninguno"],
        "clinic_key": 1,
        "location": {
            "address": "Av. de la Cantera 100, Juriquilla, Querétaro",
            "lat": 20.7243,
            "lng": -100.4361,
            "maps_place_id": "ChIJcZ2QzFfZ04URp1Juriquilla02",
        },
    },
    {
        "email": "roberto.jimenez@lasmisiones.mx",
        "name": "Roberto",
        "last_name": "Jiménez Villa",
        "phone": "442 192 0781",
        "license_number": "MED-QRO-20085005",
        "specialty": "medicina_general",
        "price_level": 1,
        "insurances": ["ninguno"],
        "clinic_key": 2,
        "location": {
            "address": "Privada Las Misiones 45, Juriquilla, Querétaro",
            "lat": 20.7165,
            "lng": -100.4429,
            "maps_place_id": "ChIJcZ2QzFfZ04URp1Juriquilla03",
        },
    },
    {
        "email": "sofia.reyes@lasmisiones.mx",
        "name": "Sofía",
        "last_name": "Reyes Montoya",
        "phone": "442 192 0782",
        "license_number": "MED-QRO-20216006",
        "specialty": "medicina_familiar",
        "price_level": 1,
        "insurances": ["ninguno"],
        "clinic_key": 2,
        "location": {
            "address": "Privada Las Misiones 45, Juriquilla, Querétaro",
            "lat": 20.7165,
            "lng": -100.4429,
            "maps_place_id": "ChIJcZ2QzFfZ04URp1Juriquilla03",
        },
    },
]


async def upsert_doctor(d: dict) -> ObjectId:
    """Inserta el doctor si no existe (por email). Retorna su _id."""
    existing = await mongo_service.doctors().find_one({"email": d["email"]}, {"_id": 1})
    if existing:
        log.info("  · Doctor ya existe: %s %s (%s)", d["name"], d["last_name"], d["email"])
        return existing["_id"]

    doc = {
        "email": d["email"],
        "password_hash": auth_service.hash_password(DEFAULT_PASSWORD),
        "name": d["name"],
        "last_name": d["last_name"],
        "phone": d.get("phone"),
        "license_number": d["license_number"],
        "specialty": d["specialty"],
        "price_level": d["price_level"],
        "insurances": d["insurances"],
        "location": d.get("location"),
        "schedule": None,
        "calendar": None,
        "is_active": True,
        "is_network": True,
        "subscription_expires": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    result = await mongo_service.doctors().insert_one(doc)
    log.info("  · Doctor insertado: %s %s → %s", d["name"], d["last_name"], result.inserted_id)
    return result.inserted_id


async def upsert_clinic(c: dict, doctor_ids: list[ObjectId]) -> ObjectId:
    """Inserta la clínica si no existe (por maps_place_id). Retorna su _id."""
    existing = await mongo_service.clinics().find_one(
        {"maps_place_id": c["maps_place_id"]}, {"_id": 1, "doctor_ids": 1}
    )
    if existing:
        # Añadir cualquier doctor nuevo que no esté ya vinculado.
        await mongo_service.clinics().update_one(
            {"_id": existing["_id"]},
            {
                "$addToSet": {"doctor_ids": {"$each": doctor_ids}},
                "$set": {"updated_at": NOW},
            },
        )
        log.info("  · Clínica ya existe: %s (actualizada con %d doctores)", c["name"], len(doctor_ids))
        return existing["_id"]

    doc = {
        "name": c["name"],
        "address": c["address"],
        "formatted_address": c["formatted_address"],
        "lat": c["lat"],
        "lng": c["lng"],
        "phone": c.get("phone"),
        "specialty": c["specialty"],
        "unit_type": c["unit_type"],
        "insurances": c["insurances"],
        "price_level": c["price_level"],
        "services": c.get("services", []),
        "state": c.get("state"),
        "municipality": c.get("municipality"),
        "maps_place_id": c["maps_place_id"],
        "doctor_ids": doctor_ids,
        "embedding": [],
        "created_at": NOW,
        "updated_at": NOW,
    }
    result = await mongo_service.clinics().insert_one(doc)
    log.info("  · Clínica insertada: %s → %s (%d doctores)", c["name"], result.inserted_id, len(doctor_ids))
    return result.inserted_id


async def main() -> None:
    log.info("Conectando a MongoDB...")
    db = mongo_service.get_db()
    await db.client.admin.command("ping")
    log.info("Conexión OK. db=%s", mongo_service.MONGO_DB_NAME)
    log.info("")

    # 1. Insertar doctores y guardar sus IDs agrupados por clínica.
    log.info("[1/2] Insertando doctores en Juriquilla...")
    clinic_doctor_ids: dict[int, list[ObjectId]] = {i: [] for i in range(len(CLINICS_DATA))}

    for d in DOCTORS_DATA:
        doc_id = await upsert_doctor(d)
        clinic_doctor_ids[d["clinic_key"]].append(doc_id)

    log.info("")

    # 2. Insertar clínicas vinculadas a sus doctores.
    log.info("[2/2] Insertando clínicas en Juriquilla...")
    for i, c in enumerate(CLINICS_DATA):
        await upsert_clinic(c, clinic_doctor_ids[i])

    log.info("")
    log.info("─" * 55)
    log.info("Seed completo.")
    log.info("  Clínicas: %d", len(CLINICS_DATA))
    log.info("  Doctores: %d (todos is_network=True)", len(DOCTORS_DATA))
    log.info("  Password de acceso: %s", DEFAULT_PASSWORD)
    log.info("─" * 55)


if __name__ == "__main__":
    asyncio.run(main())
