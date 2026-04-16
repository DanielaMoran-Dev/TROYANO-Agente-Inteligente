"""Gemini Ranker — Agent 5 (Optional). Ranks top 3 feasible interventions."""

import os
import json
import logging
import requests

logger = logging.getLogger(__name__)

_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
_TIMEOUT = 8


def run(proposed_actions: list, validated_actions: list, impact_metrics: dict) -> dict | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.info("Gemini: no key — skip")
        return None

    try:
        # BUG FIX: was outside try — KeyError on missing "id" crashed orchestrator
        feasibility = {v.get("id", ""): v.get("feasible", True) for v in validated_actions}
        scores = {
            m.get("id", ""): m.get("sustainability_score", 50)
            for m in (impact_metrics.get("per_action_metrics", []) if isinstance(impact_metrics, dict) else [])
        }

        feasible = [a for a in proposed_actions if feasibility.get(a.get("id"), True)]
        if len(feasible) < 2:
            logger.info("Gemini: <2 feasible — skip")
            return None

        m = impact_metrics if isinstance(impact_metrics, dict) else {}
        actions_summary = [
            {"id": a.get("id"), "type": a.get("type", ""), "score": scores.get(a.get("id"), 50)}
            for a in feasible
        ]
        metrics_line = (
            f"overall:{m.get('overall_score', 0)}, "
            f"flood:{m.get('flood_reduction_percent', 0)}%, "
            f"sustain:{m.get('sustainability_score', 0)}%"
        )
        prompt = (
            f"Rank top 3 urban interventions by impact. Metrics: {metrics_line}. "
            f"Actions: {json.dumps(actions_summary)}\n"
            'Return ONLY JSON array: [{"id":"...","rank":1,"label":"short title","rationale":"one sentence"}]\n'
            "No markdown. Only JSON."
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 256,
                "responseMimeType": "application/json",
            },
        }

        r = requests.post(f"{_URL}?key={api_key}", json=payload, timeout=_TIMEOUT)
        r.raise_for_status()

        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        ranking = json.loads(raw)

        if not isinstance(ranking, list):
            raise ValueError("not a list")

        valid_ids = {a.get("id") for a in proposed_actions}
        validated = [
            e for e in ranking
            if isinstance(e, dict)
            and e.get("id") in valid_ids
            and feasibility.get(e.get("id"), True)
            and all(k in e for k in ("id", "rank", "rationale"))
        ][:3]

        if not validated:
            return None

        ranked_ids  = [e["id"] for e in sorted(validated, key=lambda x: x.get("rank", 99))]
        # BUG FIX: next() without default raised StopIteration; use fallback empty dict
        top_entry   = next((e for e in validated if e["id"] == ranked_ids[0]), {})
        top_action  = next((a for a in proposed_actions if a.get("id") == ranked_ids[0]), {})
        decision    = {
            # BUG FIX: float(None) raises TypeError when key exists but is None;
            #           "or 0" coerces None → 0 before float()
            "lat":    float(top_action.get("latitude")  or 0),
            "lng":    float(top_action.get("longitude") or 0),
            "score":  round(scores.get(ranked_ids[0], 50) / 10, 2),
            "reason": top_entry.get("rationale", ""),
        }

        logger.info("Gemini: top=%s score=%s", ranked_ids[0], decision["score"])

        return {
            "top":        validated,
            "ranked_ids": ranked_ids,
            "model":      "gemini-1.5-flash",
            "decision":   decision,
        }

    except requests.exceptions.Timeout:
        logger.warning("Gemini: timeout (8s)")
        return None
    except Exception as exc:
        logger.error("Gemini: failed — %s", exc)
        return None
