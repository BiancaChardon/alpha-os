import os

import pytest

os.environ["INGESTION_FIXTURE_MODE"] = "true"


@pytest.fixture(autouse=True)
def fixture_mode(monkeypatch):
    monkeypatch.setenv("INGESTION_FIXTURE_MODE", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")


def test_all_adapters_return_events():
    from adapters import build_registry

    registry = build_registry()
    for adapter in registry.all():
        events = adapter.fetch()
        assert len(events) > 0
        assert events[0].modality in {"timeseries", "text"}


def test_pipeline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    from config import settings
    from pipeline.orchestrator import run_pipeline

    settings.database_path = str(tmp_path / "test.db")
    settings.ingestion_fixture_mode = True
    result = run_pipeline()
    assert result["classified_count"] > 0
    assert result["briefing_id"]
    assert result["review_id"]


def test_eval_runner():
    from eval.runner import run_eval

    report = run_eval()
    assert report["scenario_count"] == 10
    assert report["average_score"] > 0.5
