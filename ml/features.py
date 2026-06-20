from __future__ import annotations

from models.events import ClassifiedSignal, Urgency

COMMODITY_CODES = {
    "power": 0,
    "natgas": 1,
    "crude": 2,
    "renewables": 3,
    "weather": 4,
    "general": 5,
}

URGENCY_CODES = {Urgency.LOW: 0, Urgency.MEDIUM: 1, Urgency.HIGH: 2}


def signal_feature_vector(signal: ClassifiedSignal) -> list[float]:
    stats = signal.stats or {}
    pct = float(stats.get("pct_change") or 0.0)
    z = float(stats.get("z_score") or 0.0)
    return [
        signal.sentiment,
        signal.relevance_score,
        signal.confidence,
        URGENCY_CODES.get(signal.urgency, 0) / 2.0,
        max(-1.0, min(1.0, pct / 15.0)),
        max(-1.0, min(1.0, z / 3.0)),
        1.0 if signal.signal_type == "forward" else 0.0,
        COMMODITY_CODES.get(signal.commodity, 5) / 5.0,
    ]


def feature_names() -> list[str]:
    return [
        "sentiment",
        "relevance",
        "confidence",
        "urgency",
        "pct_change_norm",
        "z_score_norm",
        "forward_flag",
        "commodity_code",
    ]
