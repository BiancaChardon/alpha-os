from __future__ import annotations

import json

from agents.llm import call_claude, extract_json
from config import settings
from models.events import Briefing, ContrarianReview


def _contrarian_with_rules(briefing: Briefing) -> ContrarianReview:
    if not briefing.ranked_items:
        return ContrarianReview(
            briefing_id=briefing.briefing_id,
            counterarguments=["Insufficient evidence to form a contrarian view."],
            failure_modes=["Sparse or stale signal set"],
            alternative_interpretation="Wait for additional corroborating data before acting.",
            confidence_adjustment=-0.2,
        )

    top = briefing.ranked_items[0]
    counterarguments = [
        f"The top-ranked view ('{top.title}') may overweight recent spikes that revert intraday.",
        "Public headline sources can lag ISO pricing and understate regional basis differences.",
        "Correlated signals from the same event may inflate confidence without independent confirmation.",
    ]
    failure_modes = [
        "Sample bias from fixture-backed ISO snapshots",
        "Sentiment rules may misread neutral regulatory language",
        "Weather forecasts may not translate linearly to power price moves",
    ]
    alternative = (
        "Markets may already price the identified risks; the dominant narrative could be stale "
        "while contrarian opportunities sit in less-covered regional hubs or deferred contracts."
    )
    adjustment = -0.15 if top.confidence > 0.8 else -0.05
    return ContrarianReview(
        briefing_id=briefing.briefing_id,
        counterarguments=counterarguments,
        failure_modes=failure_modes,
        alternative_interpretation=alternative,
        confidence_adjustment=adjustment,
    )


def generate_contrarian_review(briefing: Briefing) -> ContrarianReview:
    system = (
        "You are a contrarian energy analyst. Challenge the synthesis briefing. Return ONLY JSON with: "
        "counterarguments (array of strings), failure_modes (array), alternative_interpretation (string), "
        "confidence_adjustment (float from -1 to 0). Surface reasons the prevailing interpretation could be wrong."
    )
    raw = call_claude(
        settings.anthropic_synthesis_model,
        system,
        briefing.model_dump_json(indent=2),
        max_tokens=2000,
    )
    if raw:
        parsed = extract_json(raw)
        if isinstance(parsed, dict):
            try:
                return ContrarianReview(
                    briefing_id=briefing.briefing_id,
                    counterarguments=parsed.get("counterarguments", []),
                    failure_modes=parsed.get("failure_modes", []),
                    alternative_interpretation=str(parsed.get("alternative_interpretation", "")),
                    confidence_adjustment=float(parsed.get("confidence_adjustment", -0.1)),
                )
            except Exception:
                pass

    return _contrarian_with_rules(briefing)
