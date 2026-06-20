from __future__ import annotations

import sys
from datetime import datetime
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
from ml.trade_probability import compute_trade_probabilities
from pipeline.orchestrator import ingest_all, run_pipeline
from pipeline.store import EventStore
from quant.optimizer import optimize_portfolio

WEB_DIR = ROOT / "ui" / "web"

app = FastAPI(title="Alpha OS API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = EventStore()


def _parse_query_dt(value: str | None, *, end: bool = False) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip().replace("Z", "+00:00")
    if "T" not in cleaned and len(cleaned) >= 10:
        dt = datetime.fromisoformat(cleaned[:10])
        if end:
            return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        return dt
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


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
def signals(
    hours: int | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    start_dt = _parse_query_dt(start)
    end_dt = _parse_query_dt(end, end=True)
    if start_dt or end_dt:
        events = store.get_events(start=start_dt, end=end_dt)
        classified = store.get_classified_signals(start=start_dt, end=end_dt)
    elif hours is not None:
        if hours <= 0:
            events = store.get_events()
            classified = store.get_classified_signals()
        else:
            events = store.get_events(hours=hours)
            classified = store.get_classified_signals(hours=hours)
    else:
        events = store.get_recent_events()
        classified = store.get_recent_classified_signals()
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


@app.get("/trades/probabilities")
def trade_probabilities() -> dict:
    briefing = store.get_latest_briefing()
    if not briefing:
        raise HTTPException(status_code=404, detail="No briefing available")

    classified = store.get_recent_classified_signals(hours=settings.signal_lookback_hours)
    history = store.get_classified_signal_history(limit=500)
    review = store.get_contrarian_for_briefing(briefing.briefing_id)
    px = store.get_perplexity_research(briefing.briefing_id)
    rank_verdicts = px.get("rank_verdicts") if px else None

    return compute_trade_probabilities(
        briefing=briefing,
        classified=classified,
        contrarian=review,
        rank_verdicts=rank_verdicts,
        history=history,
    )


@app.get("/ml/alpha/backtest")
def alpha_backtest() -> dict:
    history = store.get_classified_signal_history(limit=500)
    from ml.alpha_model import walk_forward_backtest

    return walk_forward_backtest(history)


@app.get("/portfolio/optimize")
def portfolio_optimize(
    method: str = "mean_variance",
    max_weight: float = 0.45,
    risk_aversion: float = 2.5,
) -> dict:
    if method not in {"mean_variance", "risk_parity"}:
        raise HTTPException(status_code=400, detail="method must be mean_variance or risk_parity")

    briefing = store.get_latest_briefing()
    if not briefing:
        raise HTTPException(status_code=404, detail="No briefing available")

    classified = store.get_recent_classified_signals(hours=settings.signal_lookback_hours)
    history = store.get_classified_signal_history(limit=500)
    review = store.get_contrarian_for_briefing(briefing.briefing_id)
    px = store.get_perplexity_research(briefing.briefing_id)
    rank_verdicts = px.get("rank_verdicts") if px else None

    prob = compute_trade_probabilities(
        briefing=briefing,
        classified=classified,
        contrarian=review,
        rank_verdicts=rank_verdicts,
        history=history,
    )
    optimized = optimize_portfolio(
        trades=prob["trades"],
        history=history,
        method=method,
        max_weight=max_weight,
        risk_aversion=risk_aversion,
    )
    optimized["briefing_id"] = briefing.briefing_id
    optimized["generated_at"] = briefing.created_at.isoformat()
    optimized["source_trades"] = prob["trades"]
    optimized["alpha_backtest"] = prob.get("backtest")
    return optimized


if WEB_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=WEB_DIR, html=True), name="dashboard")
