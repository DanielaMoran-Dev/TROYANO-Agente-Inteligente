"""
Prueba end-to-end del índice Vector Search `clinics_vector_index`.

1. Inserta un documento clínica dummy con embedding de 768 dims.
2. Ejecuta $vectorSearch con un vector cercano.
3. Limpia el documento.

Uso:
  cd backend
  python -m scripts.test_vector_search
"""

import os
import sys
import asyncio
import random
from datetime import datetime, timezone
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE.parent / "services" / ".env")

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "healthapp")

DIM = 768
SENTINEL_CLUES = "__TEST_VECTOR__"


def random_unit_vector(dim: int, seed: int = 42) -> list[float]:
    rnd = random.Random(seed)
    v = [rnd.uniform(-1, 1) for _ in range(dim)]
    norm = sum(x * x for x in v) ** 0.5
    return [x / norm for x in v]


async def main() -> None:
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    clinics = db["clinics"]

    print("[1/4] Verificando índice Vector Search...")
    search_idx = await clinics.list_search_indexes().to_list(length=None)
    target = next((i for i in search_idx if i.get("name") == "clinics_vector_index"), None)
    if not target:
        print("  [X] clinics_vector_index no encontrado.")
        sys.exit(1)
    status = target.get("status")
    queryable = target.get("queryable", False)
    print(f"  status={status} queryable={queryable}")
    if status != "READY" or not queryable:
        print("  [!] El índice no está listo para consultas aún.")
        sys.exit(1)

    # Limpia residuos de corridas anteriores
    await clinics.delete_many({"clues_id": SENTINEL_CLUES})

    print("[2/4] Insertando clínica de prueba...")
    embedding = random_unit_vector(DIM, seed=42)
    doc = {
        "clues_id": SENTINEL_CLUES,
        "name": "Clínica de Prueba Vector",
        "type": "Centro de Salud",
        "unit_type": "general",
        "specialty": "medicina_general",
        "services": ["consulta_general"],
        "insurances": ["imss"],
        "price_level": 1,
        "state": "Ciudad de México",
        "municipality": "Benito Juárez",
        "address": "Calle Prueba 123",
        "lat": 19.4100,
        "lng": -99.1650,
        "phone": "00-0000-0000",
        "doctor_id": None,
        "embedding": embedding,
        "embedding_text": "medicina_general consulta test",
        "indexed_at": datetime.now(timezone.utc),
    }
    result = await clinics.insert_one(doc)
    print(f"  insertado _id={result.inserted_id}")

    # Atlas Search necesita ~3-5s para indexar el nuevo doc
    print("[3/4] Esperando indexación del documento (8s)...")
    await asyncio.sleep(8)

    print("[4/4] Ejecutando $vectorSearch...")
    # Query con el mismo vector → debe devolver score ≈ 1.0
    pipeline = [
        {
            "$vectorSearch": {
                "index": "clinics_vector_index",
                "path": "embedding",
                "queryVector": embedding,
                "numCandidates": 50,
                "limit": 3,
            }
        },
        {
            "$project": {
                "_id": 0,
                "clues_id": 1,
                "name": 1,
                "specialty": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    results = await clinics.aggregate(pipeline).to_list(length=3)

    print()
    if not results:
        print("  [X] $vectorSearch devolvió 0 resultados.")
        print("      Verifica que el path 'embedding' y numDimensions=768 estén en el índice.")
        await clinics.delete_many({"clues_id": SENTINEL_CLUES})
        sys.exit(1)

    print(f"  [OK] {len(results)} resultado(s):")
    for r in results:
        print(f"    - {r.get('name'):<35} score={r.get('score'):.4f}")

    top_score = results[0].get("score", 0)
    if top_score >= 0.99:
        print(f"\n  [OK] Vector Search funcional — top score {top_score:.4f} (esperado ~1.0)")
    else:
        print(f"\n  [!] Score top inesperadamente bajo: {top_score:.4f}")

    # Limpieza
    await clinics.delete_many({"clues_id": SENTINEL_CLUES})
    print("\nLimpieza: documento de prueba eliminado.")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
