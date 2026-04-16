"""
Intent Router — decides which agent types to invoke based on user intent.

Input: the user's prompt string + (optionally) the full orchestrator brief dict.
Output: a list of intervention type strings, e.g. ["housing", "green_space"].

Priority order:
  1. brief.candidate_projects  (structured output from the chat interview)
  2. Keyword scan of the prompt text
  3. Default: all types
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

ALL_TYPES = ["housing", "green_space", "transport", "flood_management", "infrastructure"]

# Maps brief project_type values → our intervention types
_BRIEF_TYPE_MAP: Dict[str, str] = {
    "mixed_use":              "housing",
    "residential":            "housing",
    "residential_housing":    "housing",
    "housing":                "housing",
    "vivienda":               "housing",
    "social_housing":         "housing",
    "green_park":         "green_space",
    "park":               "green_space",
    "green_space":        "green_space",
    "ecology":            "green_space",
    "parque":             "green_space",
    "transport":          "transport",
    "transit":            "transport",
    "mobility":           "transport",
    "road":               "transport",
    "brt":                "transport",
    "flood":              "flood_management",
    "flood_management":   "flood_management",
    "water":              "flood_management",
    "hydraulic":          "flood_management",
    "retention":          "flood_management",
    "infrastructure":     "infrastructure",
    "commercial":         "infrastructure",
    "services":           "infrastructure",
    "energy":             "infrastructure",
    "solar":              "infrastructure",
}

# Keyword → type mapping for raw prompt scanning
_KEYWORD_MAP: Dict[str, str] = {
    # Housing
    "vivienda": "housing",        "housing": "housing",
    "residencial": "housing",     "edificio": "housing",
    "apartamento": "housing",     "departamento": "housing",
    "condominio": "housing",      "torre residencial": "housing",
    "conjunto habitacional": "housing", "inmobiliaria": "housing",
    "desarrollo habitacional": "housing", "plurifamiliar": "housing",
    # Green
    "parque": "green_space",    "park": "green_space",
    "verde": "green_space",     "jardín": "green_space",
    "jardin": "green_space",    "árbol": "green_space",
    "arbol": "green_space",     "ecolog": "green_space",
    "bosque": "green_space",    "vegetac": "green_space",
    "corredor verde": "green_space",
    # Transport
    "vialidad": "transport",    "transporte": "transport",
    "calle": "transport",       "avenida": "transport",
    "boulevard": "transport",   "ciclovía": "transport",
    "ciclovia": "transport",    "brt": "transport",
    "movilidad": "transport",   "carretera": "transport",
    "metro": "transport",       "tren": "transport",
    # Flood / hydraulic  (NOTE: "agua" excluded — too common in "Aguascalientes")
    "inundac": "flood_management",
    "drenaje": "flood_management","pluvial": "flood_management",
    "cuenca": "flood_management", "retención": "flood_management",
    "retencion": "flood_management","hidro": "flood_management",
    "vaso de ret": "flood_management","gestión hídrica": "flood_management",
    "gestion hidrica": "flood_management","manejo de agua": "flood_management",
    # Infrastructure
    "infraestructura": "infrastructure","solar": "infrastructure",
    "energía": "infrastructure", "energia": "infrastructure",
    "equipamiento": "infrastructure","servicio": "infrastructure",
    "microrred": "infrastructure","mercado": "infrastructure",
    "comercial": "infrastructure","mixto": "infrastructure",
}


def route(prompt: str, brief: Optional[Dict] = None) -> List[str]:
    """
    Return the list of intervention types the pipeline should generate,
    in priority order (most requested type first).
    """
    types: list[str] = []

    # 1. Brief candidate_projects (highest confidence — user confirmed this in chat)
    # Extract all types from brief, THEN also scan the full description for any
    # additional types the user mentioned that weren't captured in candidate_projects.
    if brief and isinstance(brief.get("candidate_projects"), list):
        for proj in brief["candidate_projects"]:
            if isinstance(proj, str):
                pt = proj.lower().replace("-", "_").replace(" ", "_")
            else:
                pt = str(proj.get("project_type", "")).lower().replace("-", "_").replace(" ", "_")
            mapped = _BRIEF_TYPE_MAP.get(pt)
            if mapped and mapped not in types:
                types.append(mapped)

        # Also scan project_description for types NOT already captured by candidate_projects.
        # This catches cases like "parque con casas y vialidades" where the description
        # mentions types beyond what candidate_projects encoded.
        desc = str(brief.get("project_description", "")).lower()
        kw_desc: list[str] = []
        for kw, t in _KEYWORD_MAP.items():
            if kw in desc and t not in types and t not in kw_desc:
                kw_desc.append(t)
        for t in kw_desc:
            if t not in types:
                types.append(t)

        if types:
            logger.info("Intent from brief (candidates + description scan): %s", types)
            return types

    # 2. Keyword scan of the prompt (only when brief didn't specify types)
    p = prompt.lower()
    kw_types: list[str] = []
    for kw, t in _KEYWORD_MAP.items():
        if kw in p and t not in kw_types:
            kw_types.append(t)

    for t in kw_types:
        if t not in types:
            types.append(t)

    if types:
        logger.info("Final intent from keyword scan: %s", types)
        return types

    # 3. Default: include all types (no clear signal)
    logger.info("No specific intent detected — defaulting to all types.")
    return ALL_TYPES
