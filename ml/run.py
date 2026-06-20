from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from ml.action_model import apply_action_predictions, train_and_predict
from ml.cluster import apply_cluster_assignments, cluster_signals
from ml.forecast import run_forecasts
from models.events import ClassifiedSignal
from pipeline.store import EventStore


def run_ml_pipeline(
    store: EventStore,
    classified: list[ClassifiedSignal],
    *,
    forecast_periods: int = 5,
) -> dict[str, Any]:
    history = store.get_all_classified_signals(limit=400)
    train_pool = history if len(history) >= len(classified) else history + classified
    # dedupe by signal_id
    seen: set[str] = set()
    train_unique: list[ClassifiedSignal] = []
    for signal in train_pool:
        if signal.signal_id in seen:
            continue
        seen.add(signal.signal_id)
        train_unique.append(signal)

    action_result = train_and_predict(train_unique, classified)
    clustered = cluster_signals(classified, k=4)
    forecasts = run_forecasts(store, periods=forecast_periods)

    enriched = apply_action_predictions(classified, action_result)
    enriched = apply_cluster_assignments(enriched, clustered)

    return {
        "snapshot_id": str(uuid4()),
        "created_at": datetime.utcnow().isoformat(),
        "action_model": {
            "model": action_result.get("model"),
            "train_samples": action_result.get("train_samples"),
            "accuracy": action_result.get("accuracy"),
            "classes": action_result.get("classes", []),
        },
        "clusters": clustered,
        "forecasts": forecasts,
        "signal_count": len(enriched),
    }, enriched
