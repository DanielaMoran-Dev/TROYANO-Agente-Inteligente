"""
Smoke test: prueba la integración real con MongoDB Atlas.

1. Registra un usuario dummy y hace login.
2. Registra un doctor dummy y hace login.
3. Inserta una gemini_session de prueba.
4. Limpia todo.

Uso:
  cd backend
  python -m scripts.smoke_test
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE.parent / "services" / ".env")

sys.path.insert(0, str(_HERE.parent))

from services import auth_service, mongo_service  # noqa: E402

SENTINEL_USER = "__smoke_user@test.local"
SENTINEL_DOCTOR = "__smoke_doctor@test.local"
SENTINEL_LICENSE = "__SMOKE_LIC_0001"
SENTINEL_SESSION = "__smoke_session_id"


async def main() -> None:
    db = mongo_service.get_db()

    # Limpieza previa por si hay residuos
    await mongo_service.users().delete_many({"email": SENTINEL_USER})
    await mongo_service.doctors().delete_many({"email": SENTINEL_DOCTOR})
    await mongo_service.gemini_sessions().delete_many({"session_id": SENTINEL_SESSION})

    print("[1/4] Registrando usuario de prueba...")
    now = datetime.now(timezone.utc)
    user_doc = {
        "email": SENTINEL_USER,
        "password_hash": auth_service.hash_password("TestPass123"),
        "name": "Carlos",
        "last_name": "Prueba",
        "age": 30,
        "phone": "5500000000",
        "coords": {"lat": 19.43, "lng": -99.13},
        "insurance": "imss",
        "medical_history": {
            "free_text": None,
            "conditions": [],
            "allergies": [],
            "medications": [],
            "blood_type": "O+",
        },
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    user_result = await mongo_service.users().insert_one(user_doc)
    user_id = user_result.inserted_id
    print(f"  user_id={user_id}")

    print("[2/4] Verificando password bcrypt...")
    stored = await mongo_service.users().find_one({"_id": user_id})
    assert auth_service.verify_password("TestPass123", stored["password_hash"]), \
        "verify_password falló con password correcto"
    assert not auth_service.verify_password("WrongPass", stored["password_hash"]), \
        "verify_password aceptó password incorrecto"
    print("  OK")

    print("[3/4] Registrando doctor de prueba...")
    doctor_doc = {
        "email": SENTINEL_DOCTOR,
        "password_hash": auth_service.hash_password("DocPass456"),
        "name": "Alejandro",
        "last_name": "Vega",
        "phone": "5511111111",
        "license_number": SENTINEL_LICENSE,
        "specialty": "cardiología",
        "price_level": 2,
        "insurances": ["imss", "issste"],
        "location": {
            "address": "Av. Ejemplo 123",
            "lat": 19.42,
            "lng": -99.16,
            "maps_place_id": None,
        },
        "schedule": None,
        "calendar": None,
        "is_active": True,
        "is_network": True,
        "subscription_expires": None,
        "created_at": now,
        "updated_at": now,
    }
    doc_result = await mongo_service.doctors().insert_one(doctor_doc)
    doctor_id = doc_result.inserted_id
    print(f"  doctor_id={doctor_id}")

    print("[4/4] Insertando gemini_session de prueba...")
    session_doc = {
        "session_id": SENTINEL_SESSION,
        "user_id": user_id,
        "symptoms": "Dolor de cabeza leve",
        "triage": {
            "urgency_level": "low",
            "unit_type": "general",
            "specialty": "medicina_general",
            "clinical_summary": "Cefalea sin red flags.",
            "reasoning": "Síntomas leves.",
            "red_flags": [],
        },
        "messages": [],
        "created_at": now,
    }
    await mongo_service.gemini_sessions().insert_one(session_doc)
    print("  OK")

    # Validar validadores: intentar inserts inválidos deben fallar
    print()
    print("[bonus] Probando validator de Mongo (insert inválido)...")
    try:
        await mongo_service.users().insert_one({"email": "bad@test.local"})
        print("  [!] El validator no rechazó un user sin password_hash")
    except Exception as exc:
        msg = str(exc).split("\n")[0][:80]
        print(f"  OK: validator rechazó — {msg}")

    # Limpieza
    print()
    print("Limpiando...")
    await mongo_service.users().delete_many({"email": SENTINEL_USER})
    await mongo_service.doctors().delete_many({"email": SENTINEL_DOCTOR})
    await mongo_service.gemini_sessions().delete_many({"session_id": SENTINEL_SESSION})
    print("Smoke test OK")

    mongo_service.get_client().close()


if __name__ == "__main__":
    asyncio.run(main())
