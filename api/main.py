from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agents.perplexity_client import is_configured as perplexity_configured
from agents.perplexity_client import research_briefing
from config import settings
from eval.runner import run_eval
from pipeline.orchestrator import ingest_all, run_pipeline
from pipeline.store import EventStore

WEB_DIR = ROOT / "ui" / "web"

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
    return {
        "status": "ok",
        "fixture_mode": settings.ingestion_fixture_mode,
        "perplexity_configured": perplexity_configured(),
        "anthropic_configured": bool(settings.anthropic_api_key),
    }


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


@app.get("/eval/results")
def eval_results() -> dict:
    return run_eval()


@app.get("/perplexity/status")
def perplexity_status() -> dict:
    return {"configured": perplexity_configured()}


@app.get("/perplexity/research")
def perplexity_research(*, refresh: bool = False) -> dict:
    if not perplexity_configured():
        raise HTTPException(status_code=503, detail="PERPLEXITY_API_KEY not configured")
    briefing = store.get_latest_briefing()
    if not briefing:
        raise HTTPException(status_code=404, detail="No briefing available")

    if not refresh:
        cached = store.get_perplexity_research(briefing.briefing_id)
        if cached:
            cached["cached"] = True
            return cached

    classified = store.get_recent_classified_signals(hours=settings.signal_lookback_hours)
    try:
        result = research_briefing(
            summary=briefing.summary,
            ranked_items=[item.model_dump(mode="json") for item in briefing.ranked_items],
            signal_summaries=[signal.one_line_summary for signal in classified],
        )
        result["briefing_id"] = briefing.briefing_id
        result["cached"] = False
        store.save_perplexity_research(briefing.briefing_id, result)
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Perplexity request failed: {exc}") from exc


if WEB_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=WEB_DIR, html=True), name="dashboard")
