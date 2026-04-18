"""
Seed MongoDB clinics collection from clinics_wiki.json.

Usage:
    python backend/CLUES/seed_clinics.py [--state AGUASCALIENTES] [--limit 500]

Requires MONGO_URI and GOOGLE_APPLICATION_CREDENTIALS env vars (or backend/services/.env loaded).

Each document gets a Gemini embedding on (name + specialty + unit_type + tipologia)
so the routing agent's vector search works.
"""

import argparse
import json
import os
import sys
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Load env from services/.env
from dotenv import load_dotenv
_env = os.path.join(os.path.dirname(__file__), "..", "services", ".env")
load_dotenv(_env, override=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import gemini_service, mongo_service


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--state", default=None, help="Filter by ENTIDAD name (e.g. AGUASCALIENTES)")
    p.add_argument("--limit", type=int, default=None, help="Max number of docs to insert")
    p.add_argument("--batch", type=int, default=50, help="Embedding batch size")
    p.add_argument("--drop", action="store_true", help="Drop existing clinics collection first")
    return p.parse_args()


async def main():
    args = parse_args()

    wiki_path = os.path.join(os.path.dirname(__file__), "clinics_wiki.json")
    logger.info("Loading %s", wiki_path)
    with open(wiki_path, encoding="utf-8") as f:
        clinics = json.load(f)

    if args.state:
        clinics = [c for c in clinics if c["state"].upper() == args.state.upper()]
        logger.info("Filtered to state=%s → %d facilities", args.state, len(clinics))

    if args.limit:
        clinics = clinics[: args.limit]

    logger.info("Total to seed: %d", len(clinics))

    col = mongo_service.clinics()

    if args.drop:
        await col.drop()
        logger.info("Dropped existing clinics collection")

    inserted = 0
    for i in range(0, len(clinics), args.batch):
        batch = clinics[i : i + args.batch]

        for doc in batch:
            embed_text = " ".join(filter(None, [
                doc.get("name", ""),
                doc.get("specialty", ""),
                doc.get("unit_type", ""),
                doc.get("tipologia", ""),
            ]))
            try:
                doc["embedding"] = gemini_service.embed(embed_text)
            except Exception as e:
                logger.warning("Embedding failed for %s: %s", doc["clues"], e)
                doc["embedding"] = []

        try:
            result = await col.insert_many(batch, ordered=False)
            inserted += len(result.inserted_ids)
        except Exception as e:
            logger.error("Insert batch %d failed: %s", i // args.batch, e)

        logger.info("Progress: %d / %d", min(i + args.batch, len(clinics)), len(clinics))

    logger.info("Done. Inserted %d documents.", inserted)


if __name__ == "__main__":
    asyncio.run(main())
