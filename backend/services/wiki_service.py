"""
Wiki Service — loads medical knowledge JSONs and builds context for Gemini prompts.

Always-injected (small, universally relevant):
  wiki_triage.json          ~6 KB   Manchester triage levels and conditions
  wiki_sintomas.json        ~7 KB   Symptom → condition → triage → specialty lookup
  wiki_sistema_salud_mx.json ~3 KB  Mexican health system structure
  wiki_gpc.json             ~8 KB   Clinical practice guidelines (6 conditions)

On-demand (too large for every prompt):
  wiki_cie10.json           ~211 KB  ICD-10 codes — keyword-matched and injected selectively
"""

import json
import os
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

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


def build_triage_context(symptoms: str) -> str:
    """
    Build a compact context string to inject into the triage system prompt.
    Includes full triage rules, system structure, symptom lookups, GPCs,
    and relevant CIE-10 codes matched to the patient's symptoms.
    """
    parts = []

    # 1. Manchester triage levels
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

    # 2. Symptom lookup — find matching entries
    keywords = symptoms.lower()
    matched_sintomas = []
    for s in _sintomas():
        if s["sintoma"].lower() in keywords or any(kw in keywords for kw in s["palabras_clave"]):
            matched_sintomas.append(s)

    if matched_sintomas:
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
        parts.append("## SÍNTOMAS RELEVANTES DETECTADOS\n" + "\n".join(lines))

    # 3. Relevant GPCs
    gpc_data = _gpc()
    matched_gpcs = []
    for key, g in gpc_data.items():
        cond = g["condicion"].lower()
        if any(w in keywords for w in cond.split() if len(w) > 4):
            matched_gpcs.append(g)

    if matched_gpcs:
        lines = []
        for g in matched_gpcs[:3]:
            alarmas = "; ".join(g.get("signos_alarma", g.get("signos_alarma_referir_urgencias", [])))
            lines.append(
                f"- {g['condicion']} ({g['cie10']}): nivel={g['nivel_atencion']}. "
                f"Señales de alarma: {alarmas}."
            )
        parts.append("## GUÍAS CLÍNICAS RELEVANTES (GPC CENETEC)\n" + "\n".join(lines))

    # 4. Mexican health system (always)
    s = _sistema_salud()
    niveles_str = " | ".join(
        f"Nivel {n['nivel']}: {n['nombre']} ({', '.join(n['unidades'][:2])})"
        for n in s["niveles_atencion"]
    )
    parts.append(f"## SISTEMA DE SALUD MEXICANO\n{niveles_str}\n{s['urgencias']}")

    # 5. CIE-10 codes matched to symptoms
    cie10_matches = search_cie10(symptoms, max_results=8)
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
