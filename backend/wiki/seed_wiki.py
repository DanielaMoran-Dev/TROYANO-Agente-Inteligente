"""
Seed MongoDB wiki_chunks collection from raw GPC text files + wiki JSON files.

Each document is a ~600-char passage with a Gemini embedding (768 dims)
so the triage agent can retrieve the most relevant clinical guidelines
for any symptom via vector search instead of keyword matching.

Sources:
  wiki/raw/gpc_*.txt         — Full CENETEC clinical practice guidelines
  wiki/raw/manchester_triage.txt — Manchester triage reference
  wiki/wiki_sintomas.json    — 12 symptom entries (each becomes a chunk)
  wiki/wiki_gpc.json         — 6 condensed GPC summaries

Usage:
  cd backend
  python -m wiki.seed_wiki [--drop] [--batch 20] [--source gpc_diabetes]
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Load env
from dotenv import load_dotenv
_ENV = os.path.join(os.path.dirname(__file__), "..", "services", ".env")
load_dotenv(_ENV, override=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from services import gemini_service, mongo_service

RAW_DIR = os.path.join(os.path.dirname(__file__), "raw")
WIKI_DIR = os.path.dirname(__file__)

# GPC metadata for label enrichment
GPC_META = {
    "gpc_diabetes":              {"condition": "Diabetes Mellitus Tipo 2",          "cie10": "E11"},
    "gpc_hipertension":          {"condition": "Hipertensión Arterial",              "cie10": "I10"},
    "gpc_cardiopatia_isquemica": {"condition": "Cardiopatía Isquémica",              "cie10": "I25"},
    "gpc_evc_stroke":            {"condition": "Enfermedad Vascular Cerebral/Stroke","cie10": "I63"},
    "gpc_infeccion_respiratoria":{"condition": "Infección Respiratoria Aguda",       "cie10": "J06"},
    "gpc_apendicitis":           {"condition": "Apendicitis Aguda",                  "cie10": "K37"},
    "manchester_triage":         {"condition": "Sistema de Triaje Manchester",        "cie10": ""},
}

CHUNK_TARGET = 650   # chars per chunk (soft)
CHUNK_MIN    = 120   # discard chunks shorter than this
BOILERPLATE_SKIP = 2800  # skip first N chars (title, authors, legal boilerplate)

# Patterns that indicate non-clinical boilerplate lines
_SKIP_LINE = re.compile(
    r"^(\d+\s*$"                          # lone page numbers
    r"|ISBN.*"
    r"|www\."
    r"|©|Copyright"
    r"|COORDINADORES?:"
    r"|AUTORES?:"
    r"|REVISORES?:"
    r"|Avenida|Colonia|C\.P\."
    r"|Esta guía puede ser"
    r"|Deberá ser citado"
    r"|Publicado por"
    r"|Editor General"
    r")",
    re.IGNORECASE,
)


def _clean_text(text: str) -> str:
    """Normalize whitespace and remove PDF extraction artifacts."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" \n", "\n", text)
    return text.strip()


def _chunk_text(text: str, source: str) -> list[str]:
    """
    Split text into ~CHUNK_TARGET char passages.
    Merges short paragraphs; discards boilerplate/page-number lines.
    """
    text = text[BOILERPLATE_SKIP:]           # skip header boilerplate
    text = _clean_text(text)
    paragraphs = text.split("\n\n")

    chunks: list[str] = []
    buf = ""

    for para in paragraphs:
        para = para.strip()
        # Skip boilerplate lines
        lines = [l for l in para.splitlines() if not _SKIP_LINE.match(l.strip())]
        para = " ".join(lines).strip()
        if len(para) < 40:
            continue

        if len(buf) + len(para) <= CHUNK_TARGET:
            buf = (buf + " " + para).strip()
        else:
            if len(buf) >= CHUNK_MIN:
                chunks.append(buf)
            buf = para

    if len(buf) >= CHUNK_MIN:
        chunks.append(buf)

    return chunks


def _chunks_from_gpc_file(filename: str) -> list[dict]:
    source_key = filename.replace(".txt", "")
    meta = GPC_META.get(source_key, {"condition": source_key, "cie10": ""})
    path = os.path.join(RAW_DIR, filename)

    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()

    raw_chunks = _chunk_text(text, source_key)
    docs = []
    for i, chunk in enumerate(raw_chunks):
        # Prefix every chunk with its clinical context so the embedding
        # is anchored to the condition even without surrounding passages.
        prefixed = f"[{meta['condition']}] {chunk}"
        docs.append({
            "chunk_id": f"{source_key}_{i:04d}",
            "source": source_key,
            "condition": meta["condition"],
            "cie10": meta["cie10"],
            "text": prefixed,
        })
    return docs


def _chunks_from_sintomas() -> list[dict]:
    path = os.path.join(WIKI_DIR, "wiki_sintomas.json")
    entries = json.load(open(path, encoding="utf-8"))
    docs = []
    for e in entries:
        alarmas = "; ".join(e.get("señales_alarma", []))
        condiciones = ", ".join(e.get("condiciones_posibles", []))
        text = (
            f"[Síntoma: {e['sintoma']}] "
            f"Condiciones posibles: {condiciones}. "
            f"Señales de alarma: {alarmas}. "
            f"Triaje base: {e['triaje_default']}, con alarma: {e['triaje_con_alarma']}. "
            f"Acción: {e.get('accion', '')}. "
            f"Especialidad: {e.get('especialidad', '')}."
        )
        docs.append({
            "chunk_id": f"sintoma_{e['sintoma'].replace(' ', '_')}",
            "source": "wiki_sintomas",
            "condition": e["sintoma"],
            "cie10": "",
            "text": text,
        })
    return docs


def _chunks_from_gpc_json() -> list[dict]:
    path = os.path.join(WIKI_DIR, "wiki_gpc.json")
    gpc_data = json.load(open(path, encoding="utf-8"))
    docs = []
    for key, g in gpc_data.items():
        alarmas = "; ".join(g.get("signos_alarma", []))
        criterios = "; ".join(g.get("criterios_diagnostico", []))
        sintomas = "; ".join(g.get("sintomas_cardinales", []))
        referencia = "; ".join(g.get("referencia_segundo_nivel", []))
        text = (
            f"[GPC: {g['condicion']} ({g['cie10']})] "
            f"Nivel de atención: {g['nivel_atencion']}. "
            f"Especialidad: {g['especialidad']}. "
            f"Síntomas cardinales: {sintomas}. "
            f"Criterios diagnósticos: {criterios}. "
            f"Señales de alarma: {alarmas}. "
            f"Criterios de referencia a segundo nivel: {referencia}."
        )
        docs.append({
            "chunk_id": f"gpc_summary_{key}",
            "source": "wiki_gpc_summary",
            "condition": g["condicion"],
            "cie10": g["cie10"],
            "text": text,
        })
    return docs


def collect_all_chunks(source_filter: str | None) -> list[dict]:
    docs: list[dict] = []

    # Raw GPC + triage files
    for fname in sorted(os.listdir(RAW_DIR)):
        if not fname.endswith(".txt"):
            continue
        key = fname.replace(".txt", "")
        if source_filter and source_filter not in key:
            continue
        logger.info("Chunking %s …", fname)
        chunks = _chunks_from_gpc_file(fname)
        logger.info("  → %d chunks", len(chunks))
        docs.extend(chunks)

    # wiki_sintomas (always included unless filtered to a specific GPC)
    if not source_filter or "sintoma" in source_filter:
        sintoma_chunks = _chunks_from_sintomas()
        logger.info("wiki_sintomas → %d chunks", len(sintoma_chunks))
        docs.extend(sintoma_chunks)

    # wiki_gpc.json summaries
    if not source_filter or "gpc" in source_filter:
        gpc_chunks = _chunks_from_gpc_json()
        logger.info("wiki_gpc summaries → %d chunks", len(gpc_chunks))
        docs.extend(gpc_chunks)

    return docs


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--drop", action="store_true", help="Drop wiki_chunks collection first")
    p.add_argument("--batch", type=int, default=20, help="Embedding batch size")
    p.add_argument("--source", default=None, help="Filter by source key (e.g. gpc_diabetes)")
    return p.parse_args()


async def main():
    args = parse_args()

    docs = collect_all_chunks(args.source)
    logger.info("Total chunks to seed: %d", len(docs))

    col = mongo_service.wiki_chunks()

    if args.drop:
        await col.drop()
        logger.info("Dropped wiki_chunks collection")

    inserted = 0
    skipped = 0

    for i in range(0, len(docs), args.batch):
        batch = docs[i: i + args.batch]

        for doc in batch:
            try:
                doc["embedding"] = gemini_service.embed(doc["text"])
            except Exception as e:
                logger.warning("Embed failed for %s: %s", doc["chunk_id"], e)
                doc["embedding"] = []

        try:
            result = await col.insert_many(batch, ordered=False)
            inserted += len(result.inserted_ids)
        except Exception as e:
            logger.error("Insert batch %d failed: %s", i // args.batch, e)
            skipped += len(batch)

        logger.info("Progress: %d / %d", min(i + args.batch, len(docs)), len(docs))

    logger.info("Done. Inserted %d, skipped %d.", inserted, skipped)
    logger.info("")
    logger.info("⚠  Create the Atlas Vector Search index manually:")
    logger.info("   Collection: wiki_chunks")
    logger.info("   Index name: wiki_vector_index")
    logger.info('   JSON: {"fields":[{"type":"vector","path":"embedding","numDimensions":768,"similarity":"cosine"}]}')


if __name__ == "__main__":
    asyncio.run(main())
