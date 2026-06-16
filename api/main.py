from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from pipeline.orchestrator import ingest_all, run_pipeline
from pipeline.store import EventStore

app = FastAPI(title="Alpha OS API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = EventStore()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "fixture_mode": settings.ingestion_fixture_mode}


@app.post("/ingest")
def ingest() -> dict:
    return ingest_all(store=store)


@app.post("/pipeline/run")
def pipeline_run() -> dict:
    return run_pipeline(store=store)


@app.get("/signals")
def signals(hours: int | None = None) -> dict:
    events = store.get_recent_events(hours=hours)
    classified = store.get_recent_classified_signals(hours=hours)
    return {
        "events": [e.model_dump(mode="json") for e in events],
        "classified": [s.model_dump(mode="json") for s in classified],
    }


@app.get("/briefings/latest")
def latest_briefing() -> dict:
    briefing = store.get_latest_briefing()
    if not briefing:
        raise HTTPException(status_code=404, detail="No briefing available")
    review = store.get_contrarian_for_briefing(briefing.briefing_id)
    return {
        "briefing": briefing.model_dump(mode="json"),
        "contrarian": review.model_dump(mode="json") if review else None,
    }


@app.get("/runs")
def runs(limit: int = 20) -> dict:
    runs = store.get_ingestion_runs(limit=limit)
    return {"runs": [r.model_dump(mode="json") for r in runs]}
