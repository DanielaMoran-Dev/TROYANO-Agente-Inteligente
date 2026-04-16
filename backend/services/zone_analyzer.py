"""
Zone Analyzer — spatial constraint analysis using SIIMP layers.

Given a GeoJSON Polygon (the zone the user drew on the map), this module:
  1. Loads each SIIMP regulatory layer (contencion_urbana, zufos, etc.)
  2. Checks spatial intersection using shapely
  3. Returns a structured ZoneConstraints object that every agent receives.

This is the "what can I build here?" layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ZoneConstraints:
    # Spatial facts about the zone
    inside_urban_boundary: bool = True          # contencion_urbana
    intersects_zufos: bool = False              # ZUFO = future urbanization zone (VACANT extension land)
    intersects_dinamica_especial: bool = False  # innovation/mixed-use zones
    crosses_vialidades: bool = False            # existing road network present
    inside_materiales_petreos: bool = False     # extraction zone (hard block)
    estimated_area_m2: float = 0.0

    # Land use classification — CRITICAL for correct agent behaviour
    # "extension"   = vacant/undeveloped land designated for new urban growth (ZUFO or outside boundary)
    # "infill"      = inside existing urban fabric — existing buildings likely present
    # "unknown"     = no zone polygon or insufficient data
    land_use_status: str = "unknown"

    # Derived permissions
    allowed_types: List[str] = field(default_factory=list)
    restricted_types: List[str] = field(default_factory=list)
    regulatory_notes: List[str] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        """
        Plain-text summary injected into every agent's system prompt.
        The LAND USE STATUS section is the most important signal — it tells
        agents whether to propose NEW construction on VACANT land or carefully
        planned infill/improvements that do NOT displace existing residents.
        """
        lines = ["=== ZONE REGULATORY CONTEXT ==="]

        if self.estimated_area_m2 > 0:
            lines.append(f"Zone area: {self.estimated_area_m2:,.0f} m²")

        # ── LAND USE STATUS — most critical signal ───────────────────────────
        if self.land_use_status == "extension":
            lines.append(
                "LAND USE: EXTENSION ZONE — This is VACANT/UNDEVELOPED land designated for "
                "new urban growth. There are NO existing buildings to demolish or residents "
                "to displace. All proposed interventions must be NEW construction on empty land."
            )
        elif self.land_use_status == "infill":
            lines.append(
                "LAND USE: EXISTING URBAN AREA — This zone is INSIDE established urban fabric. "
                "Existing buildings, streets, and residents are present. "
                "Proposals must be INFILL, DENSIFICATION, or IMPROVEMENTS to existing structures. "
                "DO NOT propose interventions that require demolishing existing occupied buildings. "
                "Green space proposals are only valid on documented vacant lots or public ROW."
            )
        else:
            lines.append(
                "LAND USE: UNKNOWN — No zone polygon provided or land use status unclear. "
                "Use conservative assumptions: treat as existing urban area. "
                "Only propose interventions that work in EITHER vacant OR built contexts."
            )

        # ── Urban boundary ───────────────────────────────────────────────────
        if not self.inside_urban_boundary:
            lines.append(
                "RESTRICTION: Zone is OUTSIDE the urban containment boundary. "
                "High-density residential and commercial development NOT allowed. "
                "Only agriculture, low-density rural, or ecological uses permitted."
            )

        # ── Hard blocks ─────────────────────────────────────────────────────
        if self.inside_materiales_petreos:
            lines.append(
                "HARD BLOCK: Zone overlaps a Materiales Pétreos extraction zone. "
                "ALL construction is prohibited. Only remediation projects allowed."
            )

        # ── Growth zones / special zones ─────────────────────────────────────
        if self.intersects_zufos:
            lines.append(
                "ZUFO OVERLAP: Zone is a designated Zona de Urbanización Futura — "
                "this CONFIRMS it is EXTENSION/VACANT land. Development requires PMDU special-use permit. "
                "Low-density housing, green corridors, and basic infrastructure are preferred for first phase."
            )

        if self.intersects_dinamica_especial:
            lines.append(
                "OPPORTUNITY: Zone overlaps a Zona Dinámica Especial. "
                "Mixed-use, innovation, and commercial development are actively supported here."
            )

        if self.crosses_vialidades:
            lines.append(
                "EXISTING ROADS: The road network crosses or borders this zone. "
                "Transport improvements and accessibility are relevant, but respect the existing vialidades — "
                "do NOT propose road interventions that overlap with already-built streets."
            )

        if self.allowed_types:
            lines.append(f"ALLOWED types for this zone: {', '.join(self.allowed_types)}")
        if self.restricted_types:
            lines.append(f"RESTRICTED types: {', '.join(self.restricted_types)}")

        for note in self.regulatory_notes:
            lines.append(f"NOTE: {note}")

        return "\n".join(lines)


def analyze(zone: Optional[dict]) -> ZoneConstraints:
    """
    Analyse the spatial constraints for a GeoJSON Polygon zone.
    Falls back to permissive defaults if SIIMP data is unavailable.
    """
    constraints = ZoneConstraints()

    if not zone:
        # No zone drawn — conservative default: treat as existing urban area
        constraints.land_use_status = "unknown"
        constraints.allowed_types = ["housing", "green_space", "transport", "flood_management", "infrastructure"]
        constraints.regulatory_notes.append(
            "No zone polygon provided — assuming existing urban area. "
            "Proposals should respect current urban fabric."
        )
        return constraints

    # Try to compute area estimate (degrees² → m² rough conversion at lat 21°N)
    zone_shape = None
    try:
        from shapely.geometry import shape as shp_shape
        zone_shape = shp_shape(zone)
        # 1° lat ≈ 111_320 m, 1° lng ≈ 104_600 m at lat 21°N
        deg2_to_m2 = 111_320 * 104_600
        constraints.estimated_area_m2 = abs(zone_shape.area) * deg2_to_m2
        logger.info("Zone shape area: %.8f deg² = %.0f m²", zone_shape.area, constraints.estimated_area_m2)
    except Exception as exc:
        logger.warning("Zone shape construction failed: %s", exc)

    if zone_shape is None:
        constraints.land_use_status = "unknown"
        constraints.allowed_types = ["housing", "green_space", "transport", "flood_management", "infrastructure"]
        constraints.regulatory_notes.append("Zone polygon could not be parsed — treating as existing urban area.")
        return constraints

    # Load SIIMP layers and check intersection
    from services import geodata_service

    def _intersects(layer_name: str) -> bool:
        try:
            geojson = geodata_service.get_layer(layer_name)
            features = geojson.get("features", [])
            if not features:
                return False
            from shapely.geometry import shape as shp
            for feat in features:
                geom = feat.get("geometry")
                if not geom:
                    continue
                try:
                    if zone_shape.intersects(shp(geom)):
                        return True
                except Exception:
                    continue
            return False
        except Exception as exc:
            logger.warning("Zone analysis: could not load layer '%s': %s", layer_name, exc)
            return False

    logger.info("Zone analysis: checking SIIMP intersections…")

    constraints.inside_urban_boundary     = not _intersects("contencion_urbana") or True
    # contencion_urbana marks the BOUNDARY LINE — if zone is inside the city
    # it will typically NOT intersect the outer boundary polygon.
    # Simpler heuristic: assume inside unless explicit outside indicator.
    constraints.intersects_zufos              = _intersects("zufos")
    constraints.intersects_dinamica_especial  = _intersects("zonas_dinamica_especial")
    constraints.crosses_vialidades            = _intersects("vialidades")
    constraints.inside_materiales_petreos     = _intersects("materiales_petreos")

    # ── Land use status classification ──────────────────────────────────────
    # EXTENSION: ZUFO overlap = explicitly designated vacant growth land.
    # EXTENSION: Outside urban boundary = rural/undeveloped by definition.
    # INFILL: Inside urban boundary, no ZUFO = existing urban fabric.
    if constraints.intersects_zufos or not constraints.inside_urban_boundary:
        constraints.land_use_status = "extension"
    else:
        # Inside the city boundary without ZUFO designation → treat as existing urban area
        constraints.land_use_status = "infill"

    # Derive allowed / restricted types from spatial facts
    all_types = ["housing", "green_space", "transport", "flood_management", "infrastructure"]
    blocked   = set()

    if constraints.inside_materiales_petreos:
        blocked = set(all_types)  # hard block everything
        constraints.regulatory_notes.append(
            "No development permitted — extraction zone (Materiales Pétreos)."
        )

    if not constraints.inside_urban_boundary:
        blocked.update(["housing", "infrastructure"])
        constraints.regulatory_notes.append(
            "Outside urban boundary: housing and infrastructure blocked by PMDU."
        )

    if constraints.intersects_zufos:
        constraints.regulatory_notes.append(
            "ZUFO: zona de extensión vacante designada para nuevo crecimiento urbano. "
            "Prioridad: vivienda baja densidad, espacios verdes e infraestructura básica."
        )
    elif constraints.land_use_status == "infill":
        constraints.regulatory_notes.append(
            "Zona urbana consolidada: propuestas deben respetar el tejido edificado existente. "
            "No se permite demolición de vivienda ocupada ni construcción sobre lotes habitados."
        )

    if constraints.intersects_dinamica_especial:
        constraints.regulatory_notes.append(
            "Zona Dinámica Especial: proyectos mixtos e innovación activamente apoyados."
        )

    constraints.allowed_types  = [t for t in all_types if t not in blocked]
    constraints.restricted_types = list(blocked)

    logger.info(
        "Zone analysis complete — area: %.0f m², allowed: %s, restricted: %s",
        constraints.estimated_area_m2,
        constraints.allowed_types,
        constraints.restricted_types,
    )
    return constraints
