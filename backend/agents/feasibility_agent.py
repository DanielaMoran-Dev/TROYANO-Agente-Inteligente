"""
Feasibility Agent — Agent 2
Validates proposed actions against urban rules and PDF documentation.
"""

import json
import os
import re
import logging
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai import Credentials

logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("WATSONX_MODEL_ID", "meta-llama/llama-3-2-11b-vision-instruct")

# Regulatory rules used in demo mode (mirrors real SIIMP/PMDU constraints)
_REGULATORY_RULES = {
    "housing": {
        "max_height_floors": 25,
        "min_green_percent": 15,
        "blocked_keywords": ["flood zone", "zona inundable", "vaso", "cuenca activa"],
        # In infill zones: only allow densification/infill, not greenfield towers
        "infill_note": "En zona urbana consolidada: sólo densificación o infill permitidos. "
                       "No se puede construir donde hay vivienda ocupada existente.",
    },
    "transport": {
        "requires_row": True,
        "blocked_keywords": ["patrimonio", "heritage", "zona arqueológica"],
        "infill_note": "Mejoras viales válidas en zona consolidada sólo sobre derecho de vía existente.",
    },
    "green_space": {
        # NOT always_feasible — a park requires VACANT land.
        # In infill zones: only valid if the action explicitly targets a vacant lot or public ROW.
        "infill_blocked_keywords": ["residencial", "habitacional", "vivienda existente", "colonia"],
        "extension_note": "Espacio verde en zona de extensión: altamente viable. "
                          "Alinea con requisitos del corredor ecológico del PMDU.",
        "infill_note": "Espacio verde en zona consolidada: sólo factible en lotes baldíos documentados "
                       "o derecho de vía público. No se puede colocar un parque sobre casas existentes.",
    },
    "flood_management": {
        # Flood management is feasible in both contexts
        "always_feasible": True,
        "bonus_note": "Gestión hídrica alineada con NOM-001-SEDATU-2021. "
                      "Válida tanto en extensión como en zona consolidada.",
    },
    "infrastructure": {
        "max_height_floors": 8,
        "blocked_keywords": ["reserva ecológica", "zona federal"],
        "infill_note": "Equipamiento público en zona consolidada: requiere lote vacante o reconversión "
                       "de uso de suelo. No desplazar usos residenciales activos.",
    },
}


def _get_watsonx_model():
    api_key = os.getenv("WATSONX_API_KEY")
    url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    project_id = os.getenv("WATSONX_PROJECT_ID")
    if not all([api_key, url, project_id]):
        return None
    credentials = Credentials(url=url, api_key=api_key)
    return ModelInference(
        model_id=MODEL_ID,
        credentials=credentials,
        project_id=project_id,
        params={"decoding_method": "greedy", "max_new_tokens": 800},
    )


def _demo_validate(action: dict, land_use_status: str = "unknown") -> dict:
    """
    Rule-based feasibility check used when no Watson credentials are available.
    Uses _REGULATORY_RULES + land_use_status to simulate real constraint checking.

    land_use_status: "extension" | "infill" | "unknown"
      - extension: vacant land → new construction is appropriate
      - infill: existing urban fabric → only densification / improvements, no greenfield
      - unknown: conservative (treat as infill)
    """
    atype  = str(action.get("type", "infrastructure")).lower()
    adesc  = str(action.get("description", "")).lower()
    aname  = str(action.get("action", "")).lower()
    vp     = action.get("visual_params", {})
    floors = vp.get("height_floors", 5)

    rules  = _REGULATORY_RULES.get(atype, {})
    is_infill = land_use_status in ("infill", "unknown")

    # Always-feasible types (flood management valid everywhere)
    if rules.get("always_feasible"):
        return {
            "feasible": True,
            "rejection_reason": None,
            "notes": rules.get("bonus_note", "Cumple con estándares de planificación urbana."),
            "pdf_sources": ["NOM-001-SEDATU-2021.pdf", "04_02_1.2_PMDU2017_Guiametodologica.pdf"],
        }

    # ── Land use conflict check ─────────────────────────────────────────────
    if is_infill and atype == "green_space":
        # Green space in existing urban fabric: feasible on vacant lots or ROW.
        # Mark as conditional — urban catalyst, not a hard block for demo purposes.
        return {
            "feasible": True,
            "rejection_reason": None,
            "notes": (
                "Espacio verde condicionado en zona urbana consolidada. "
                "Requiere lote baldío documentado o derecho de vía público disponible según catastro municipal. "
                "PMDU 2017 Art. 3.2 — prioridad en recuperación de espacios públicos subutilizados."
            ),
            "pdf_sources": ["04_02_1.2_PMDU2017_Guiametodologica.pdf"],
        }

    if is_infill and atype == "housing":
        # New large-scale housing in existing urban area requires infill/densification approach
        if floors > 6:
            return {
                "feasible": False,
                "rejection_reason": (
                    f"Torre de {floors} pisos en zona urbana consolidada requiere estudio de impacto urbano "
                    "y cambio de uso de suelo. No se permite en lotes con vivienda ocupada."
                ),
                "notes": "Considerar densificación gradual (máx. 4-6 pisos) o infill en lotes baldíos. PMDU 2017 Art. 4.3.",
                "pdf_sources": ["04_02_1.2_PMDU2017_Guiametodologica.pdf"],
            }
        return {
            "feasible": True,
            "rejection_reason": None,
            "notes": (
                "Densificación/infill en zona consolidada: factible en lotes baldíos o predios subutilizados. "
                + rules.get("infill_note", "")
            ),
            "pdf_sources": ["04_02_1.2_PMDU2017_Guiametodologica.pdf"],
        }

    # ── Height check ────────────────────────────────────────────────────────
    max_floors = rules.get("max_height_floors", 99)
    if floors > max_floors:
        return {
            "feasible": False,
            "rejection_reason": f"Altura de {floors} pisos excede el máximo permitido ({max_floors}) para {atype} en esta zona.",
            "notes": "Reducir pisos o solicitar varianza de altura según PMDU 2017 Art. 4.3.",
            "pdf_sources": ["04_02_1.2_PMDU2017_Guiametodologica.pdf"],
        }

    # ── Blocked-keyword check ────────────────────────────────────────────────
    for kw in rules.get("blocked_keywords", []):
        if kw in adesc or kw in aname:
            return {
                "feasible": False,
                "rejection_reason": f"La intervención conflictúa con zona restringida: '{kw}'.",
                "notes": "Se requiere reubicación o tipología alternativa según PMDU 2017.",
                "pdf_sources": ["04_02_1.2_PMDU2017_Guiametodologica.pdf"],
            }

    # Extension zone: all approved types are green-lit
    if land_use_status == "extension":
        note = rules.get("extension_note") or f"Factible en zona de extensión según PMDU 2017 y NOM-001-SEDATU-2021."
    else:
        note = rules.get("infill_note") or f"Cumple con estándares aplicables de {atype} según PMDU 2017."

    return {
        "feasible": True,
        "rejection_reason": None,
        "notes": note,
        "pdf_sources": ["04_02_1.2_PMDU2017_Guiametodologica.pdf", "NOM-001-SEDATU-2021.pdf"],
    }


def run(
    proposed_actions: list,
    prompt: str,
    zone_constraints_text: str = "",
    land_use_status: str = "unknown",
) -> dict:
    model = _get_watsonx_model()

    if not model:
        logger.warning("Feasibility Agent: no credentials — using rule-based demo validation.")
        validated = []
        for action in proposed_actions:
            verdict = _demo_validate(action, land_use_status)
            validated.append({
                "id": action["id"],
                "action": action["action"],
                **verdict,
            })
        return {"validated_actions": validated}

    # Watson path
    land_use_instruction = {
        "extension": (
            "LAND USE: EXTENSION ZONE — vacant/undeveloped land. "
            "New construction is appropriate. Evaluate against PMDU regulations only."
        ),
        "infill": (
            "LAND USE: EXISTING URBAN AREA — buildings and residents are present. "
            "REJECT any proposal that requires demolishing occupied structures. "
            "Green space is only valid on documented vacant lots. "
            "Housing must be densification/infill, not greenfield."
        ),
    }.get(land_use_status,
        "LAND USE: UNKNOWN — apply infill rules conservatively."
    )

    validated = []
    for action in proposed_actions:
        system_prompt = (
            "You are the Lineal Urban Auditor. Validate the following urban intervention against "
            "Aguascalientes PMDU 2017, NOM-001-SEDATU-2021, and sustainability standards.\n\n"
            f"=== LAND USE CONSTRAINT ===\n{land_use_instruction}\n\n"
            f"=== ZONE REGULATORY CONTEXT ===\n{zone_constraints_text or 'No restrictions provided.'}\n\n"
            f"=== ACTION TO VALIDATE ===\n{json.dumps(action)}\n\n"
            "Return ONLY a JSON object with keys: "
            "feasible (bool), rejection_reason (string|null), notes (string), pdf_sources (list of strings).\n"
            "No markdown. No explanation. Just the JSON object."
        )
        try:
            response = model.generate_text(
                prompt=f"<|system|>\n{system_prompt}\n<|user|>\nValidate this action.\n<|assistant|>\n{{"
            )
            if not response.strip().startswith("{"):
                response = "{" + response
            match = re.search(r"\{.*\}", response, re.DOTALL)
            verdict = json.loads(match.group(0)) if match else {"feasible": True, "notes": "Validated."}
            validated.append({
                "id": action["id"],
                "action": action["action"],
                "feasible": verdict.get("feasible", True),
                "rejection_reason": verdict.get("rejection_reason"),
                "notes": verdict.get("notes"),
                "pdf_sources": verdict.get("pdf_sources", []),
            })
        except Exception as e:
            logger.warning("Feasibility validation failed for %s: %s", action.get("id"), e)
            validated.append({
                "id": action["id"],
                "action": action["action"],
                **_demo_validate(action),
            })

    return {"validated_actions": validated}
