"""
Verifica que la base de datos MongoDB esté inicializada correctamente.
Lista colecciones, cuenta documentos e imprime índices por colección.

Uso:
  cd backend
  python -m scripts.verify_db
"""

import os
import sys
import asyncio
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE.parent / "services" / ".env")

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "healthapp")

EXPECTED = [
    "users",
    "doctors",
    "clinics",
    "gemini_sessions",
    "conversations",
    "appointments",
]


async def main() -> None:
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB_NAME]

    names = set(await db.list_collection_names())
    print(f"\nBase de datos: {MONGO_DB_NAME}")
    print(f"Colecciones encontradas: {len(names)}\n")

    missing = [c for c in EXPECTED if c not in names]
    if missing:
        print(f"  FALTAN: {missing}")

    for coll_name in EXPECTED:
        if coll_name not in names:
            print(f"  [X] {coll_name:<18} NO EXISTE")
            continue

        coll = db[coll_name]
        count = await coll.count_documents({})
        indexes = await coll.list_indexes().to_list(length=None)
        idx_names = [i["name"] for i in indexes]

        print(f"  [OK] {coll_name:<18} docs={count:<5} indices={len(idx_names)}")
        for idx_name in idx_names:
            print(f"         - {idx_name}")

    # Vector search index
    print("\nVector Search en clinics:")
    try:
        search_idx = await db.clinics.list_search_indexes().to_list(length=None)
        if search_idx:
            for s in search_idx:
                print(f"  [OK] {s.get('name')} status={s.get('status')}")
        else:
            print("  [!] No hay índices de Atlas Search. Crear clinics_vector_index en Atlas UI.")
    except Exception as exc:
        print(f"  [!] No se pudo listar search indexes: {exc}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
