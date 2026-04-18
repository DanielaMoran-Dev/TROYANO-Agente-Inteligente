"""
Wiki Service — medical knowledge for Gemini triage prompts.

Static (always-injected, small):
  wiki_triage.json           Manchester triage levels
  wiki_sistema_salud_mx.json Mexican health system structure

Semantic RAG (vector search on wiki_chunks MongoDB collection):
  wiki/raw/gpc_*.txt         Full CENETEC clinical practice guidelines (chunked)
  wiki/raw/manchester_triage.txt
  wiki_sintomas.json         Symptom entries (each as a chunk)
  wiki_gpc.json              Condensed GPC summaries (each as a chunk)

On-demand fallback (keyword match, used when vector search is unavailable):
  wiki_cie10.json            ICD-10 codes
  wiki_sintomas.json
  wiki_gpc.json
"""

import json
import os
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# Whether vector search for wiki is available (set to False if index not yet created)
WIKI_RAG_ENABLED = True

_WIKI_DIR = os.path.join(os.path.dirname(__file__), "../wiki")


def _load(filename: str) -> dict | list:
    path = os.path.join(_WIKI_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _triage() -> dict:
    return _load("wiki_triage.json")


@lru_cache(maxsize=1)
def _sintomas() -> list:
    return _load("wiki_sintomas.json")


@lru_cache(maxsize=1)
def _sistema_salud() -> dict:
    return _load("wiki_sistema_salud_mx.json")


@lru_cache(maxsize=1)
def _gpc() -> dict:
    return _load("wiki_gpc.json")


@lru_cache(maxsize=1)
def _cie10() -> list:
    return _load("wiki_cie10.json")


def search_cie10(query: str, max_results: int = 10) -> list[dict]:
    """Return CIE-10 entries whose description matches any word in the query."""
    words = [w.lower() for w in query.split() if len(w) > 3]
    if not words:
        return []
    results = []
    for entry in _cie10():
        desc = entry["descripcion"].lower()
        if any(w in desc for w in words):
            results.append(entry)
            if len(results) >= max_results:
                break
    return results


async def retrieve_wiki_rag(symptoms: str, limit: int = 6) -> list[dict]:
    """
    Semantic retrieval: embed the symptom query and vector-search wiki_chunks.
    Returns list of {condition, cie10, text, score} sorted by relevance.
    Falls back to empty list if index is not yet available.
    """
    if not WIKI_RAG_ENABLED:
        return []
    try:
        from services import gemini_service, mongo_service
        embedding = gemini_service.embed(symptoms)
        return await mongo_service.vector_search_wiki(embedding, limit=limit)
    except Exception as e:
        logger.warning("Wiki RAG vector search unavailable: %s", e)
        return []


def build_triage_context(symptoms: str, rag_passages: list[dict] | None = None) -> str:
    """
    Build the context string injected into the triage system prompt.

    Args:
        symptoms:     Patient symptom text (used for keyword fallback).
        rag_passages: Pre-fetched semantic passages from retrieve_wiki_rag().
                      When provided, replaces keyword-matched GPC/symptom sections
                      with richer, semantically relevant clinical text.
    """
    parts = []

    # 1. Manchester triage levels (always injected — small and universally relevant)
    t = _triage()
    triage_summary = []
    for lvl in t["niveles"]:
        conditions_sample = "; ".join(lvl["condiciones"][:8])
        triage_summary.append(
            f"PRIORIDAD {lvl['prioridad']} ({lvl['color']} — {lvl['nombre']}): "
            f"Tiempo máx: {lvl['tiempo_maximo_atencion']}. "
            f"Condiciones: {conditions_sample}."
        )
    parts.append("## SISTEMA DE TRIAJE MANCHESTER\n" + "\n".join(triage_summary))

    # 2a. Semantic RAG passages (preferred when available)
    if rag_passages:
        seen_conditions: set[str] = set()
        rag_lines = []
        for p in rag_passages:
            condition = p.get("condition", "")
            text = p.get("text", "")
            score = p.get("score", 0)
            if score < 0.55:   # skip low-relevance passages
                continue
            rag_lines.append(f"- {text}")
            seen_conditions.add(condition)
        if rag_lines:
            parts.append("## GUÍAS CLÍNICAS Y SÍNTOMAS RELEVANTES (RAG SEMÁNTICO)\n" + "\n".join(rag_lines))

    # 2b. Keyword fallback for symptoms not covered by RAG
    keywords = symptoms.lower()
    matched_sintomas = []
    for s in _sintomas():
        if s["sintoma"].lower() in keywords or any(kw in keywords for kw in s["palabras_clave"]):
            matched_sintomas.append(s)

    if matched_sintomas and not rag_passages:
        lines = []
        for s in matched_sintomas[:4]:
            alarmas = "; ".join(s["señales_alarma"])
            lines.append(
                f"- {s['sintoma'].upper()}: triaje base={s['triaje_default']}, "
                f"con alarma={s['triaje_con_alarma']}. "
                f"Señales de alarma: {alarmas}. "
                f"Acción: {s['accion']}. "
                f"Especialidad: {s['especialidad']}."
            )
        parts.append("## SÍNTOMAS RELEVANTES (BÚSQUEDA POR PALABRAS CLAVE)\n" + "\n".join(lines))

    # 3. GPC keyword fallback (only when RAG is not available)
    if not rag_passages:
        gpc_data = _gpc()
        matched_gpcs = []
        for key, g in gpc_data.items():
            cond = g["condicion"].lower()
            if any(w in keywords for w in cond.split() if len(w) > 4):
                matched_gpcs.append(g)
        if matched_gpcs:
            lines = []
            for g in matched_gpcs[:3]:
                alarmas = "; ".join(g.get("signos_alarma", []))
                lines.append(
                    f"- {g['condicion']} ({g['cie10']}): nivel={g['nivel_atencion']}. "
                    f"Señales de alarma: {alarmas}."
                )
            parts.append("## GUÍAS CLÍNICAS (GPC CENETEC — FALLBACK)\n" + "\n".join(lines))

    # 4. Mexican health system (always)
    s = _sistema_salud()
    niveles_str = " | ".join(
        f"Nivel {n['nivel']}: {n['nombre']} ({', '.join(n['unidades'][:2])})"
        for n in s["niveles_atencion"]
    )
    parts.append(f"## SISTEMA DE SALUD MEXICANO\n{niveles_str}\n{s['urgencias']}")

    # 5. CIE-10 codes (keyword matched — lightweight, always useful)
    cie10_matches = search_cie10(symptoms, max_results=6)
    if cie10_matches:
        codes = "; ".join(f"{e['codigo']}: {e['descripcion']}" for e in cie10_matches)
        parts.append(f"## CÓDIGOS CIE-10 RELEVANTES\n{codes}")

    return "\n\n".join(parts)


def get_static_context() -> str:
    """Full static context (triage + system + all GPCs) for agents that don't have dynamic symptoms yet."""
    parts = []

    t = _triage()
    for lvl in t["niveles"]:
        c = "; ".join(lvl["condiciones"][:6])
        parts.append(f"PRIORIDAD {lvl['prioridad']} {lvl['color']}/{lvl['nombre']} (≤{lvl['tiempo_maximo_atencion']}): {c}")

    s = _sistema_salud()
    for inst in s["instituciones"]:
        parts.append(f"INSTITUCIÓN {inst['clave'].upper()}: {inst['nombre_completo']} — {inst['poblacion']}")

    gpc_data = _gpc()
    for g in gpc_data.values():
        alarmas = "; ".join(g.get("signos_alarma", [])[:4])
        parts.append(f"GPC {g['condicion']} ({g['cie10']}): nivel={g['nivel_atencion']}. Alarmas: {alarmas}")

    return "\n".join(parts)
