from __future__ import annotations

import time
from datetime import datetime

from adapters import build_registry
from agents.contrarian_agent import generate_contrarian_review
from agents.ingestion_agent import classify_events
from agents.synthesis_agent import synthesize_briefing
from config import settings
from ml.run import run_ml_pipeline
from models.events import IngestionRun
from pipeline.normalize import normalize_events
from pipeline.store import EventStore


def ingest_all(store: EventStore | None = None, retries: int = 2) -> dict:
    store = store or EventStore()
    registry = build_registry()
    summary = {"sources": {}, "inserted": 0}

    for adapter in registry.all():
        run = IngestionRun(source=adapter.source, status="running")
        store.save_ingestion_run(run)
        attempt = 0
        while attempt <= retries:
            try:
                events = adapter.fetch()
                normalized = normalize_events(events, store=store)
                inserted = store.save_events(normalized)
                run.status = "success"
                run.events_fetched = len(normalized)
                run.finished_at = datetime.utcnow()
                store.save_ingestion_run(run)
                summary["sources"][adapter.source] = {
                    "fetched": len(normalized),
                    "inserted": inserted,
                    "status": "success",
                }
                summary["inserted"] += inserted
                break
            except Exception as exc:
                attempt += 1
                if attempt > retries:
                    run.status = "failed"
                    run.error = str(exc)
                    run.finished_at = datetime.utcnow()
                    store.save_ingestion_run(run)
                    summary["sources"][adapter.source] = {
                        "fetched": 0,
                        "inserted": 0,
                        "status": "failed",
                        "error": str(exc),
                    }
                else:
                    time.sleep(0.5 * attempt)
    return summary


def run_pipeline(store: EventStore | None = None) -> dict:
    store = store or EventStore()
    ingest_summary = ingest_all(store=store)
    events = store.get_recent_events(hours=settings.signal_lookback_hours)
    classified = classify_events(events)
    ml_snapshot, classified = run_ml_pipeline(store, classified)
    store.save_classified_signals(classified)
    store.save_ml_snapshot(ml_snapshot)
    briefing = synthesize_briefing(classified)
    store.save_briefing(briefing)
    review = generate_contrarian_review(briefing)
    store.save_contrarian_review(review)
    return {
        "ingestion": ingest_summary,
        "classified_count": len(classified),
        "briefing_id": briefing.briefing_id,
        "review_id": review.review_id,
        "summary": briefing.summary,
        "ml_snapshot_id": ml_snapshot.get("snapshot_id"),
        "ml_action_model": ml_snapshot.get("action_model", {}).get("model"),
    }
