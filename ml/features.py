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

DIRECTION_CODES = {"long": 1.0, "short": -1.0, "monitor": 0.0}


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
        COMMODITY_CODES.get(signal.commodity, 5) / 5.0,
    ]


def trade_idea_feature_vector(
    *,
    sentiment: float,
    relevance: float,
    confidence: float,
    urgency: str,
    commodity: str,
    direction: str,
    contrarian_adj: float = 0.0,
    perplexity_factor: float = 1.0,
) -> list[float]:
    urg = {"low": 0, "medium": 1, "high": 2}.get(urgency, 0) / 2.0
    return [
        sentiment,
        relevance,
        confidence,
        urg,
        0.0,
        0.0,
        COMMODITY_CODES.get(commodity, 5) / 5.0,
        DIRECTION_CODES.get(direction, 0.0),
        max(-1.0, min(1.0, contrarian_adj)),
        max(0.0, min(1.0, perplexity_factor)),
    ]
