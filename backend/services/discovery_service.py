"""
Discovery Service — IBM Watson Discovery Integration Skeleton
Provides RAG (Retrieval-Augmented Generation) capabilities for urban
planning regulations, building codes, and zoning laws.

Phase 1: Skeleton with mock responses and local PDF catalog.
Phase 2: Full Watson Discovery API integration.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — Watson Discovery credentials (to be filled in Phase 2)
# ---------------------------------------------------------------------------

DISCOVERY_API_KEY = os.getenv("WATSON_DISCOVERY_API_KEY", "")
DISCOVERY_URL = os.getenv("WATSON_DISCOVERY_URL", "https://api.us-south.discovery.watson.cloud.ibm.com")
DISCOVERY_PROJECT_ID = os.getenv("WATSON_DISCOVERY_PROJECT_ID", "")
DISCOVERY_COLLECTION_ID = os.getenv("WATSON_DISCOVERY_COLLECTION_ID", "")

# ---------------------------------------------------------------------------
# Local Knowledge Base (PDF catalog for demo/fallback)
# These PDFs are stored in backend/PDFS/ and will be ingested into
# Watson Discovery during Phase 2.
# ---------------------------------------------------------------------------

PDF_CATALOG = {
    "PMDU_2017": {
        "file": "04_02_1.2_PMDU2017_Guiametodologica.pdf",
        "title": "Guía Metodológica PMDU 2017",
        "topics": ["zoning", "land_use", "urban_development", "planning"],
        "jurisdiction": "Federal",
    },
    "INUNDACIONES": {
        "file": "3-FASCCULOINUNDACIONES-ilovepdf-compressed.pdf",
        "title": "Fascículo de Inundaciones",
        "topics": ["flood_management", "risk", "resilience", "drainage"],
        "jurisdiction": "Federal",
    },
    "EDO_4_123": {
        "file": "EDO-4-123.pdf",
        "title": "EDO-4-123 — Norma Estatal",
        "topics": ["construction", "building_codes", "structural"],
        "jurisdiction": "State",
    },
    "MANUAL_CALLES": {
        "file": "Manual_de_calles_2019.pdf",
        "title": "Manual de Calles 2019",
        "topics": ["transport", "roads", "pedestrian", "mobility", "vialidades"],
        "jurisdiction": "Federal",
    },
    "NOM_001_SEDATU": {
        "file": "NOM-001-SEDATU-2021.pdf",
        "title": "NOM-001-SEDATU-2021",
        "topics": ["housing", "urban_standards", "zoning", "sedatu"],
        "jurisdiction": "Federal",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_configured() -> bool:
    """Check if Watson Discovery credentials are set."""
    return bool(DISCOVERY_API_KEY and DISCOVERY_PROJECT_ID)


def query(question: str, topics: list[str] | None = None, max_results: int = 3) -> dict:
    """
    Query the knowledge base for relevant regulatory passages.

    In Phase 1 (skeleton), this returns mock results from the local PDF catalog
    matched by topic keywords. In Phase 2, this will call the Watson Discovery
    API for real RAG retrieval.

    Args:
        question: Natural language query (e.g. "What are flood zone regulations?")
        topics: Optional list of topic tags to filter by.
        max_results: Maximum number of document passages to return.

    Returns:
        dict with 'results' list and 'source' indicator.
    """
    if is_configured():
        return _query_watson_discovery(question, max_results)

    # Fallback: local topic matching
    logger.info("Discovery: Using local PDF catalog (Watson Discovery not configured)")
    return _query_local_catalog(question, topics, max_results)


def list_documents() -> list[dict]:
    """List all documents in the knowledge base."""
    return [
        {
            "id": doc_id,
            "title": doc["title"],
            "file": doc["file"],
            "topics": doc["topics"],
            "jurisdiction": doc["jurisdiction"],
        }
        for doc_id, doc in PDF_CATALOG.items()
    ]


# ---------------------------------------------------------------------------
# Private — Watson Discovery (Phase 2 stub)
# ---------------------------------------------------------------------------


def _query_watson_discovery(question: str, max_results: int) -> dict:
    """
    Phase 2: Real Watson Discovery API call.
    TODO: Implement using ibm_watson.DiscoveryV2
    """
    logger.warning("Watson Discovery query called but not yet implemented.")
    return {
        "results": [],
        "source": "watson_discovery",
        "status": "not_implemented",
        "message": "Watson Discovery integration pending Phase 2 implementation.",
    }


# ---------------------------------------------------------------------------
# Private — Local Catalog Fallback
# ---------------------------------------------------------------------------


def _query_local_catalog(
    question: str, topics: list[str] | None, max_results: int
) -> dict:
    """
    Match PDFs from the local catalog by topic overlap with the question.
    This is a simple keyword match, not semantic search.
    """
    question_lower = question.lower()
    scored = []

    for doc_id, doc in PDF_CATALOG.items():
        score = 0
        # Score by topic keyword presence in the question
        for topic in doc["topics"]:
            if topic.replace("_", " ") in question_lower or topic in question_lower:
                score += 2
        # Score by title keyword presence
        for word in doc["title"].lower().split():
            if len(word) > 3 and word in question_lower:
                score += 1
        # If topics filter provided, boost matches
        if topics:
            for t in topics:
                if t in doc["topics"]:
                    score += 3

        if score > 0:
            scored.append((score, doc_id, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, doc_id, doc in scored[:max_results]:
        results.append({
            "document_id": doc_id,
            "title": doc["title"],
            "file": doc["file"],
            "relevance_score": round(score / 10, 2),
            "passage": f"[Demo] Relevant content from '{doc['title']}' would be retrieved here via Watson Discovery RAG.",
            "jurisdiction": doc["jurisdiction"],
        })

    return {
        "results": results,
        "source": "local_catalog",
        "total_matched": len(scored),
    }
