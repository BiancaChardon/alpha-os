from datetime import datetime

from agents.ingestion_agent import classify_events
from ml.action_model import train_and_predict
from ml.cluster import cluster_signals
from ml.forecast import forecast_series
from ml.run import run_ml_pipeline
from models.events import SignalEvent


def _make_series(n: int, base: float, step: float) -> list[tuple[datetime, float]]:
    return [
        (datetime(2026, 6, 1 + i), round(base + step * i, 2))
        for i in range(n)
    ]


def test_logistic_regression_action_model():
    events = []
    for i, h in enumerate(range(16)):
        pct = 8.0 if i < 4 else -6.0 if i < 8 else 0.5
        events.append(
            SignalEvent(
                ts=datetime(2026, 6, 15, h % 24, 0),
                source="eia",
                modality="timeseries",
                commodity="natgas" if i % 2 == 0 else "crude",
                payload={"series": "DHHNGSP", "value": 3.0 + i * 0.05, "pct_change": pct, "z_score": pct / 3},
            )
        )
    signals = classify_events(events)
    result = train_and_predict(signals, signals)
    assert result["predictions"]
    assert result["predictions"][0]["ml_action"] in {"buy", "sell", "hold", "watch"}


def test_kmeans_clustering():
    events = [
        SignalEvent(
            ts=datetime(2026, 6, 15),
            source="pjm",
            modality="timeseries",
            commodity="power",
            payload={"series": "WESTERN_HUB", "value": 40 + i, "pct_change": i - 2, "z_score": i - 1},
        )
        for i in range(8)
    ]
    signals = classify_events(events)
    result = cluster_signals(signals, k=3)
    assert result["model"] == "kmeans"
    assert len(result["assignments"]) == len(signals)
    assert result["clusters"]


def test_prophet_or_fallback_forecast():
    history = _make_series(14, 70.0, 0.5)
    result = forecast_series(history, periods=3)
    assert result["status"] == "ok"
    assert result["engine"] in {"prophet", "linear_fallback"}
    assert len(result["points"]) == 3


def test_ml_pipeline_integration(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "ml.db"))
    monkeypatch.setenv("INGESTION_FIXTURE_MODE", "true")
    from config import settings
    from pipeline.orchestrator import run_pipeline

    settings.database_path = str(tmp_path / "ml.db")
    settings.ingestion_fixture_mode = True
    result = run_pipeline()
    assert result["ml_snapshot_id"]
    assert result["ml_action_model"]
