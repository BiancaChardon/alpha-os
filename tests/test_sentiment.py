from agents.sentiment import score_sentiment


def test_vader_or_keyword_sentiment():
    bullish = score_sentiment("EIA reports strong storage build and surplus expands")
    bearish = score_sentiment("Pipeline outage causes shortage and price spike")
    assert bullish > bearish
    assert -1.0 <= bullish <= 1.0
    assert -1.0 <= bearish <= 1.0


def test_timeseries_classification_has_action_fields():
    from datetime import datetime

    from agents.ingestion_agent import classify_events
    from models.events import SignalEvent

    event = SignalEvent(
        ts=datetime.utcnow(),
        source="pjm",
        modality="timeseries",
        commodity="power",
        payload={
            "series": "WESTERN_HUB",
            "value": 42.5,
            "pct_change": 5.2,
            "z_score": 2.1,
            "spike_flag": True,
        },
    )
    signals = classify_events([event])
    assert len(signals) == 1
    sig = signals[0]
    assert sig.action in {"buy", "sell", "hold", "watch"}
    assert sig.action_hint
    assert sig.detail_summary
    assert "WESTERN" in sig.one_line_summary or "PJM" in sig.one_line_summary or "42.5" in sig.one_line_summary
    assert sig.signal_type in {"forward", "reactive"}
