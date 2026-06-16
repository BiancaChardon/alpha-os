from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from pipeline.orchestrator import run_pipeline


def start_scheduler(interval_hours: int = 6) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_pipeline, "interval", hours=interval_hours, id="alpha_pipeline")
    scheduler.start()
    return scheduler
