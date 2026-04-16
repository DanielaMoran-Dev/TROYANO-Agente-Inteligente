"""
Construction Agent — Agent 1
Generates urban planning actions from a user prompt using IBM watsonx.ai.
Falls back to a prompt-aware simulation when no credentials are configured.
"""

import os
import json
import re
import logging
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai import Credentials

logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("WATSONX_MODEL_ID", "meta-llama/llama-3-3-70b-instruct")


def _get_watsonx_model():
    api_key = os.getenv("WATSONX_API_KEY")
    url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    project_id = os.getenv("WATSONX_PROJECT_ID")
    if not all([api_key, url, project_id]):
        return None
    try:
        credentials = Credentials(url=url, api_key=api_key)
        return ModelInference(
            model_id=MODEL_ID,
            credentials=credentials,
            project_id=project_id,
            params={"decoding_method": "greedy", "max_new_tokens": 1500},
        )
    except Exception as e:
        logger.error("Failed to initialize model '%s': %s", MODEL_ID, e)
        return None


def run(
    prompt: str,
    zone: dict = None,
    center: dict = None,
    types_filter: list = None,
    zone_constraints_text: str = "",
    brief: dict = None,
) -> dict:
    model = _get_watsonx_model()

    lat = center.get("lat", 21.88) if center else 21.88
    lng = center.get("lng", -102.29) if center else -102.29

    if not model:
        logger.warning("Construction Agent: no credentials — using dynamic brief-driven fallback (Demo Mode).")
        return {"proposed_actions": _build_fallback_actions(lat, lng, prompt, zone, types_filter, brief)}

    zone_str = json.dumps(zone) if zone else "Not provided"
    types_str = ", ".join(types_filter) if types_filter else "housing, transport, green_space, flood_management, infrastructure"

    # Budget / timeline from brief if available
    budget_hint = ""
    if brief:
        if brief.get("budget_usd"):
            budget_hint += f"\n  - Budget: ${brief['budget_usd']:,} USD"
        if brief.get("timeline_years"):
            budget_hint += f"\n  - Timeline: {brief['timeline_years']} years"
        if brief.get("sustainability"):
            s = brief["sustainability"]
            budget_hint += f"\n  - Green space minimum: {s.get('green_space_minimum_percent', 0)}%"
            if s.get("affordable_housing_required"):
                budget_hint += "\n  - Affordable housing required"

    # Derive land use status from zone_constraints_text (it's embedded there)
    land_use_line = ""
    if "EXTENSION ZONE" in zone_constraints_text:
        land_use_line = (
            "LAND USE: EXTENSION ZONE — This is VACANT/UNDEVELOPED land. "
            "All interventions must be NEW CONSTRUCTION on empty ground. "
            "There are no existing buildings to demolish or residents to displace."
        )
    elif "EXISTING URBAN AREA" in zone_constraints_text:
        land_use_line = (
            "LAND USE: EXISTING URBAN AREA — Buildings and residents are present here. "
            "ONLY propose interventions for documented vacant lots or public right-of-way. "
            "DO NOT propose large parks over residential blocks. "
            "DO NOT propose new towers where occupied houses already exist. "
            "Focus on densification, infill, and public space improvements."
        )
    else:
        land_use_line = (
            "LAND USE: UNKNOWN — Be conservative. Only propose interventions "
            "that work on vacant lots or public ROW. Do not displace existing residents."
        )

    system_prompt = (
        "You are the Lineal Generative Engine. Design a realistic urban intervention for Aguascalientes, Mexico.\n\n"
        f"=== LAND USE CONSTRAINT (CRITICAL — READ FIRST) ===\n"
        f"{land_use_line}\n\n"
        f"=== MAP & ZONE CONTEXT ===\n"
        f"Map centre: lat={lat:.5f}, lng={lng:.5f}\n"
        f"Zone polygon: {zone_str}\n\n"
        f"=== REGULATORY CONSTRAINTS (SIIMP analysis) ===\n"
        f"{zone_constraints_text or 'No specific restrictions detected.'}\n\n"
        f"=== USER REQUIREMENTS ===\n"
        f"{prompt}{budget_hint}\n\n"
        f"=== TASK ===\n"
        f"Generate 4–6 interventions of ONLY these types: {types_str}\n"
        f"ALL interventions must be INSIDE the zone polygon AND compatible with its land use status.\n"
        f"Coordinates must be realistic Aguascalientes values near lat={lat:.4f}, lng={lng:.4f}.\n"
        f"Respect all regulatory constraints listed above.\n"
        f"Return ONLY a valid JSON array — no markdown, no text outside the array.\n"
        'Format: [{"action":"...","type":"...","description":"...","cost_usd":1000000,'
        f'"latitude":{lat:.5f},"longitude":{lng:.5f},'
        '"visual_params":{"building_count":4,"height_floors":8,"area_m2":5000}}]'
    )

    try:
        response = model.generate_text(
            prompt=f"<|system|>\n{system_prompt}\n<|user|>\n{prompt}\n<|assistant|>\n["
        )
        if not response.strip().startswith("["):
            response = "[" + response
        logger.info("Construction Agent raw response: %s", response[:500])

        start_idx = response.find("[")
        end_idx = response.rfind("]")
        if start_idx == -1 or end_idx == -1:
            raise ValueError("No JSON array found.")

        actions = json.loads(response[start_idx : end_idx + 1])
        for idx, a in enumerate(actions):
            a["id"] = f"action_{idx+1:03d}"
            if "cost_usd" not in a:
                a["cost_usd"] = 1_000_000

        return {"proposed_actions": actions}

    except Exception as e:
        logger.warning("Construction Agent failed (%s), using prompt-aware fallback.", e)
        return {"proposed_actions": _build_fallback_actions(lat, lng, prompt, zone, types_filter)}


# ── Dynamic fallback — generates actions from the user's actual brief + prompt ─
#
# No fixed template names or descriptions. Everything is derived from:
#   • prompt  — the user's free-text project description
#   • brief   — structured interview output (budget, timeline, candidate_projects)
#   • types_filter — which intervention types were routed by the orchestrator
#   • zone    — polygon for positioning and area estimation

def _classify_intent(prompt: str):
    """Return a set of intent tags based on prompt keywords."""
    p = prompt.lower()
    tags = set()
    if any(w in p for w in ["vivienda", "housing", "residencial", "apartamento", "depart", "condominio", "hab"]):
        tags.add("housing")
    if any(w in p for w in ["transporte", "transport", "vialidad", "calle", "avenida", "brt", "metro", "bus", "movilidad", "ciclo"]):
        tags.add("transport")
    if any(w in p for w in ["verde", "green", "parque", "park", "jardín", "arbol", "ecolog", "bosque"]):
        tags.add("green_space")
    if any(w in p for w in ["agua", "flood", "inundac", "drenaje", "pluvial", "cuenca", "retención", "hidro"]):
        tags.add("flood_management")
    if any(w in p for w in ["infraestructura", "infrastructure", "solar", "energía", "equip", "servicio", "micro"]):
        tags.add("infrastructure")
    if any(w in p for w in ["comercial", "commercial", "mixto", "mixed", "oficina", "office"]):
        tags.add("infrastructure")
        tags.add("housing")
    if not tags:
        tags = {"housing", "transport", "green_space", "flood_management", "infrastructure"}
    return tags


# Visual params catalogue — indexed by (type, variant_index)
_VISUAL = {
    "housing":          [
        {"building_count": 6,  "height_floors": 12, "area_m2": 10_000},
        {"building_count": 10, "height_floors": 5,  "area_m2": 12_000},
        {"building_count": 3,  "height_floors": 20, "area_m2": 9_000},
    ],
    "transport":        [
        {"building_count": 0, "height_floors": 0, "area_m2": 8_000},
        {"building_count": 0, "height_floors": 0, "area_m2": 6_500},
    ],
    "green_space":      [
        {"building_count": 0, "height_floors": 0, "area_m2": 15_000},
        {"building_count": 0, "height_floors": 0, "area_m2": 12_000},
    ],
    "flood_management": [
        {"building_count": 0, "height_floors": 0, "area_m2": 13_000},
        {"building_count": 0, "height_floors": 0, "area_m2": 10_000},
    ],
    "infrastructure":   [
        {"building_count": 2, "height_floors": 1,  "area_m2": 8_500},
        {"building_count": 4, "height_floors": 3,  "area_m2": 10_000},
    ],
}

# Per-type cost fractions (share of total budget) and fallback absolute cost
_COST_SHARE = {
    "housing":          0.45,
    "transport":        0.20,
    "green_space":      0.15,
    "flood_management": 0.12,
    "infrastructure":   0.08,
}
_COST_FALLBACK = {
    "housing":          8_000_000,
    "transport":        4_000_000,
    "green_space":      2_500_000,
    "flood_management": 3_500_000,
    "infrastructure":   3_000_000,
}


def _action_label(itype: str, variant: int, prompt: str, brief: dict | None) -> tuple[str, str]:
    """
    Return (action_name, description) dynamically derived from the user's request.
    Uses the brief's project_description and candidate_projects labels first,
    then falls back to reading keywords from the raw prompt.
    """
    p = prompt.lower()
    desc_hint = ""
    if brief:
        desc_hint = (brief.get("project_description") or "").lower()

    combined = p + " " + desc_hint

    # ── HOUSING ─────────────────────────────────────────────────────────────
    if itype == "housing":
        social   = any(w in combined for w in ["social", "interés social", "popular", "asequible", "económi"])
        premium  = any(w in combined for w in ["premium", "lujo", "luxury", "alto segmento", "exclusiv"])
        mixto    = any(w in combined for w in ["mixto", "mixed", "comercial", "usos mix"])
        coliving = any(w in combined for w in ["coliving", "co-living", "jóvenes", "students"])

        # variant 0 → primary typology, variant 1 → complementary typology
        if social:
            if variant == 0:
                return (
                    "Conjunto de Vivienda de Interés Social",
                    (f"Desarrollo de vivienda asequible con acceso a servicios básicos, áreas comunitarias y conectividad peatonal. "
                     f"Responde al brief: {brief.get('project_description','')[:80]}.")
                    if brief else
                    "Conjunto residencial de interés social con áreas comunes y equipamiento básico."
                )
            else:
                return (
                    "Bloque de Vivienda Social Compacta",
                    (f"Tipología compacta de menor densidad para complementar el conjunto principal. "
                     f"Incluye espacios comunitarios y área verde según el brief del cliente.")
                )
        if premium:
            if variant == 0:
                return (
                    "Torre Residencial de Alto Segmento",
                    (f"Torre de usos mixtos orientada al segmento solicitado. "
                     f"Incluye amenidades, estacionamiento inteligente y planta baja comercial activa. "
                     f"Presupuesto base: ${(brief.get('budget_usd') or 0):,} USD.")
                    if brief else
                    "Torre residencial premium con amenidades y planta baja comercial."
                )
            else:
                return (
                    "Edificio de Usos Mixtos — Etapa 2",
                    "Edificio complementario con planta baja comercial activa, vivienda en pisos superiores "
                    "y área de coworking. Completa el conjunto del desarrollador."
                )
        if coliving:
            return (
                "Hub de Co-living Urbano",
                "Residencias compartidas con espacios de trabajo, cultura y convivencia. "
                "Orientado a jóvenes profesionales según el perfil de la solicitud."
            )
        if mixto:
            if variant == 0:
                return (
                    "Desarrollo de Usos Mixtos — Fase Principal",
                    (f"Edificio de usos mixtos con planta baja comercial activa y pisos residenciales. "
                     f"Diseñado conforme al brief: {(brief.get('project_description') or '')[:80]}.")
                    if brief else
                    "Edificio de usos mixtos con comercio en planta baja y vivienda en altura."
                )
            else:
                return (
                    "Pódium Comercial y Residencial",
                    "Volumen de menor altura con amenidades compartidas, comercio local y vivienda. "
                    "Complementa el edificio principal del conjunto."
                )
        # Generic housing
        labels = ["Conjunto Habitacional", "Bloque Residencial Compacto", "Edificio Plurifamiliar"]
        return (
            labels[variant % len(labels)],
            (f"Desarrollo residencial conforme al programa del cliente: "
             f"{(brief.get('project_description') or prompt)[:100]}.")
            if brief else
            "Complejo residencial adaptado al contexto urbano de la zona."
        )

    # ── TRANSPORT ────────────────────────────────────────────────────────────
    if itype == "transport":
        brt     = any(w in combined for w in ["brt", "autobús rápido", "corredor de transporte"])
        ciclo   = any(w in combined for w in ["ciclov", "bicicleta", "ciclismo"])
        peatón  = any(w in combined for w in ["peatonal", "caminar", "boulevard", "andador"])

        if brt or variant == 0:
            return (
                "Corredor de Transporte Rápido",
                f"Eje vial con carril preferencial para autobús, señalización inteligente "
                f"y ciclovía lateral. Integra la zona al sistema de movilidad de la ciudad. "
                f"Horizonte: {(brief.get('timeline_years') or 5)} años."
                if brief else
                "Corredor BRT con infraestructura dedicada e integración peatonal."
            )
        if ciclo:
            return (
                "Red de Ciclovías y Movilidad Activa",
                "Infraestructura para bicicleta y movilidad no motorizada, con estaciones de "
                "préstamo, señalización y conexiones a equipamiento urbano."
            )
        return (
            "Eje Peatonal y Boulevard Urbano",
            "Andador equipado con vegetación, mobiliario, iluminación eficiente y acceso a "
            "transporte público. Estimula la economía local de proximidad."
        )

    # ── GREEN SPACE ──────────────────────────────────────────────────────────
    if itype == "green_space":
        lago    = any(w in combined for w in ["lago", "espejo de agua", "fuente", "estanque"])
        deporte = any(w in combined for w in ["deport", "cancha", "fútbol", "juego", "recreat"])
        bosque  = any(w in combined for w in ["bosque", "arbolado", "forestal", "selva"])
        corredor= any(w in combined for w in ["corredor", "lineal", "franja", "camellón"])

        green_pct = 15
        if brief:
            try:
                green_pct = brief["ods11_requirements"]["sustainability_checklist"]["green_space_minimum_percent"]
            except (KeyError, TypeError):
                pass

        if bosque or variant == 1:
            return (
                "Parque Forestal Urbano",
                f"Plantación de especies nativas, senderos interpretativos y corredor ecológico. "
                f"Aporta el {green_pct}% de espacio verde requerido en el brief del cliente."
                if brief else
                "Bosque urbano con especies nativas y corredores ecológicos."
            )
        if corredor:
            return (
                "Corredor Verde Lineal",
                f"Franja de vegetación nativa sobre camellón o arroyo pluvial. "
                f"Conecta parques existentes y reduce la isla de calor urbano en la zona."
            )
        if deporte:
            return (
                "Parque Deportivo y Recreativo",
                f"Espacio verde con canchas multiusos, área de juegos infantiles y jardín de lluvia. "
                f"Responde a la demanda de equipamiento recreativo señalada en el brief."
                if brief else
                "Parque con canchas, área recreativa y jardín pluvial."
            )
        if lago:
            return (
                "Parque con Espejo de Agua",
                f"Parque urbano con lago artificial, terrazas paisajísticas y vegetación riparia. "
                f"Incorpora el elemento hídrico solicitado en el programa del cliente."
                if brief else
                "Parque con lago artificial y terrazas paisajísticas."
            )
        return (
            "Parque Urbano" + (" de Barrio" if variant == 0 else " Lineal"),
            f"Espacio verde equipado conforme al brief: "
            f"{(brief.get('project_description') or '')[:80]}. "
            f"Mínimo {green_pct}% de superficie permeable."
            if brief else
            "Parque urbano con jardines, senderos y áreas de descanso."
        )

    # ── FLOOD MANAGEMENT ────────────────────────────────────────────────────
    if itype == "flood_management":
        if variant == 0:
            return (
                "Vaso de Retención Pluvial",
                "Cuenca de retención a cielo abierto con taludes naturalizados, zona de "
                "amortiguamiento ecológico y capacidad de recarga de acuífero."
            )
        return (
            "Distrito de Pavimento Permeable",
            "Sustitución de superficies impermeables por pavimento permeable y jardines de lluvia "
            "para reducir escorrentía superficial y mejorar la resiliencia hídrica."
        )

    # ── INFRASTRUCTURE ────────────────────────────────────────────────────────
    if itype == "infrastructure":
        solar  = any(w in combined for w in ["solar", "energía", "renovable", "fotovoltai", "microrred"])
        equip  = any(w in combined for w in ["equipamiento", "servicio", "guardería", "mercado", "salud"])

        if solar and variant == 0:
            return (
                "Hub de Energía Solar y Microrred",
                (f"Sistema fotovoltaico distribuido con almacenamiento en batería. "
                 f"Abastece al conjunto y reduce el costo energético. "
                 f"Alineado con la meta de sustentabilidad del brief.")
                if brief else
                "Microrred solar con almacenamiento y distribución eficiente."
            )
        if equip or variant == 0:
            return (
                "Centro de Servicios y Equipamiento Público",
                (f"Equipamiento integrado: {', '.join(w for w in ['mercado','guardería','oficinas','reciclaje'] if w in combined) or 'servicios comunitarios'}. "
                 f"Responde al programa de usos especificado en el brief del cliente.")
                if brief else
                "Equipamiento público integrado con mercado, guardería y servicios comunitarios."
            )
        return (
            "Nodo de Infraestructura Urbana",
            "Infraestructura de soporte para el conjunto: subestación eléctrica, planta de "
            "tratamiento de agua y servicios de telecomunicaciones. Mejora el índice de "
            "servicios de la zona."
        )

    # Fallback
    return (f"Intervención Urbana — {itype.replace('_',' ').title()}", prompt[:100])


# Spread offsets when no zone polygon is drawn
_OFFSETS = [
    (0.0028,  0.0018), (-0.0025,  0.0032), (0.0012, -0.0038),
    (-0.0032, -0.0010), (0.0040,  0.0005), (-0.0008,  0.0045),
    (0.0020, -0.0022), (-0.0038,  0.0025),
]


def _build_fallback_actions(
    lat: float, lng: float, prompt: str,
    zone: dict = None, types_filter: list = None,
    brief: dict = None,
) -> list:
    if types_filter:
        intent_tags = list(types_filter)
    else:
        intent_tags = list(_classify_intent(prompt))

    if not intent_tags:
        intent_tags = ["housing", "green_space", "transport", "flood_management", "infrastructure"]

    # Budget from brief — used to scale costs per action
    budget = None
    if brief:
        budget = brief.get("budget_usd")

    # Compute zone bbox for positioning
    zone_lngs, zone_lats = [], []
    if zone and zone.get("coordinates"):
        for pt in zone["coordinates"][0]:
            zone_lngs.append(pt[0])
            zone_lats.append(pt[1])

    # Estimate zone area (m²) — bbox area × 0.70 to approximate actual polygon area
    # At lat 21°N: 1° longitude ≈ 104,600 m, 1° latitude ≈ 111,320 m
    zone_area_m2 = 0.0
    if zone_lngs and zone_lats:
        w = (max(zone_lngs) - min(zone_lngs)) * 104_600
        h = (max(zone_lats) - min(zone_lats)) * 111_320
        zone_area_m2 = w * h * 0.70  # polygon rarely fills its full bbox

    # Build one or two actions per requested type (max 8 total)
    # With 1-3 types: 2 variants each (rich detail)
    # With 4+ types: 1-2 variants, capped at 8 total
    plan: list[tuple[str, int]] = []  # (type, variant_index)
    max_actions = 8
    variants_per_type = 2 if len(intent_tags) <= 3 else 1
    for t in intent_tags:
        variants = _VISUAL.get(t, [{}])
        for v in range(min(len(variants), variants_per_type)):
            plan.append((t, v))
            if len(plan) >= max_actions:
                break
        if len(plan) >= max_actions:
            break

    actions = []
    type_variant_counts: dict[str, int] = {}

    for idx, (itype, variant) in enumerate(plan):
        # Dynamic name + description
        action_name, description = _action_label(itype, variant, prompt, brief)

        # Cost: fraction of budget, or absolute fallback
        base_cost = _COST_FALLBACK[itype]
        if budget:
            share = _COST_SHARE.get(itype, 0.15)
            n_of_type = sum(1 for t, _ in plan if t == itype)
            base_cost = int(budget * share / n_of_type)
            # Keep costs realistic: don't go below 300k or above 40M per action
            base_cost = max(300_000, min(40_000_000, base_cost))

        # Visual params — scale area to zone size if available
        vp = _VISUAL.get(itype, [{}])[variant % len(_VISUAL.get(itype, [{}]))].copy()
        if zone_area_m2 > 0 and "area_m2" in vp:
            # Each action gets ~35% of its zone slice — leaves breathing room between shapes
            slice_area = zone_area_m2 / len(plan)
            vp["area_m2"] = max(2_000, min(int(slice_area * 0.35), 80_000))

        # Position inside zone bbox or offset from center
        if zone_lngs and zone_lats:
            min_lng, max_lng = min(zone_lngs), max(zone_lngs)
            min_lat, max_lat = min(zone_lats), max(zone_lats)
            n = len(plan)
            # Inset 15% from each bbox edge so rendered shapes stay inside the zone
            inset = 0.15
            frac_lng = (idx / n + 0.4 / n) % 1.0
            frac_lat = ((idx * 1.618 / n) + 0.3 / n) % 1.0
            lng_pos  = round(min_lng + (max_lng - min_lng) * (inset + frac_lng * (1 - 2 * inset)), 6)
            lat_pos  = round(min_lat + (max_lat - min_lat) * (inset + frac_lat * (1 - 2 * inset)), 6)
        else:
            dlat, dlng = _OFFSETS[idx % len(_OFFSETS)]
            lat_pos = round(lat + dlat, 6)
            lng_pos = round(lng + dlng, 6)

        actions.append({
            "id":          f"action_{idx+1:03d}",
            "type":        itype,
            "action":      action_name,
            "description": description,
            "cost_usd":    base_cost,
            "latitude":    lat_pos,
            "longitude":   lng_pos,
            "visual_params": vp,
        })

    return actions
