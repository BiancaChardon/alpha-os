from __future__ import annotations

from datetime import datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def fixture_mode(monkeypatch):
    monkeypatch.setenv("INGESTION_FIXTURE_MODE", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")


def test_get_events_by_date_range(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    from config import settings
    from pipeline.orchestrator import run_pipeline
    from pipeline.store import EventStore

    settings.database_path = str(tmp_path / "test.db")
    settings.ingestion_fixture_mode = True
    run_pipeline()

    store = EventStore()
    now = datetime.utcnow()
    recent = store.get_events(start=now - timedelta(hours=1), end=now + timedelta(hours=1))
    assert recent

    old = store.get_events(start=now - timedelta(days=30), end=now - timedelta(days=29))
    assert old == []
