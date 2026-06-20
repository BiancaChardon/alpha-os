from __future__ import annotations

from datetime import datetime

from ml.trade_probability import compute_trade_probabilities
from models.events import Briefing, BriefingItem, ClassifiedSignal, ContrarianReview, Urgency


def _signal(**kwargs) -> ClassifiedSignal:
    defaults = {
        "event_id": "e1",
        "ts": datetime.utcnow(),
        "source": "fixture",
        "modality": "timeseries",
        "commodity": "natgas",
        "urgency": Urgency.MEDIUM,
        "sentiment": 0.4,
        "relevance_score": 0.7,
        "confidence": 0.75,
        "one_line_summary": "natgas move",
        "stats": {"pct_change": 3.0, "z_score": 1.2},
    }
    defaults.update(kwargs)
    return ClassifiedSignal(**defaults)


def test_compute_trade_probabilities_returns_trades():
    briefing = Briefing(
        summary="Test briefing",
        ranked_items=[
            BriefingItem(rank=1, title="Natural Gas — bullish storage draw", confidence=0.82),
            BriefingItem(rank=2, title="Crude — bearish surplus overhang", confidence=0.71),
        ],
    )
    classified = [
        _signal(signal_id="s1", commodity="natgas", sentiment=0.5, stats={"pct_change": 4.0, "z_score": 2.0}),
        _signal(signal_id="s2", commodity="crude", sentiment=-0.4, stats={"pct_change": -2.0, "z_score": 1.5}),
    ]
    history = classified * 6
    review = ContrarianReview(
        briefing_id=briefing.briefing_id,
        counterarguments=["Demand may fade"],
        failure_modes=["Weather reversal"],
        alternative_interpretation="Range-bound",
        confidence_adjustment=-0.05,
    )

    result = compute_trade_probabilities(
        briefing=briefing,
        classified=classified,
        contrarian=review,
        rank_verdicts=[{"rank": 1, "verdict": "corroborate"}, {"rank": 2, "verdict": "mixed"}],
        history=history,
    )

    assert result["summary"]["trade_count"] == 2
    assert len(result["trades"]) == 2
    for trade in result["trades"]:
        assert 0.0 < trade["p_win"] < 1.0
        assert abs(trade["p_win"] + trade["p_flat"] + trade["p_adverse"] - 1.0) < 0.02
        assert trade["direction"] in {"long", "short", "monitor"}
