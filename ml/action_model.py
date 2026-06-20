from __future__ import annotations

from typing import Any

from agents.ingestion_agent import _derive_action
from ml.features import signal_feature_vector
from models.events import ClassifiedSignal, Urgency

ACTIONS = ["buy", "sell", "hold", "watch"]
MIN_TRAIN_SAMPLES = 12


def _heuristic_label(signal: ClassifiedSignal) -> str:
    stats = signal.stats or {}
    return _derive_action(
        sentiment=signal.sentiment,
        urgency=signal.urgency,
        pct_change=float(stats.get("pct_change") or 0.0),
        signal_type=signal.signal_type,
        commodity=signal.commodity,
    )


def train_and_predict(
    train_signals: list[ClassifiedSignal],
    predict_signals: list[ClassifiedSignal],
) -> dict[str, Any]:
    if len(train_signals) < MIN_TRAIN_SAMPLES:
        return {
            "model": "heuristic_fallback",
            "train_samples": len(train_signals),
            "accuracy": None,
            "predictions": [
                {
                    "signal_id": s.signal_id,
                    "ml_action": _heuristic_label(s),
                    "ml_action_prob": None,
                    "action_source": "heuristic",
                }
                for s in predict_signals
            ],
        }

    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return _heuristic_predictions(train_signals, predict_signals, model="sklearn_unavailable")

    x_train = np.array([signal_feature_vector(s) for s in train_signals])
    y_train = np.array([_heuristic_label(s) for s in train_signals])

    if len(set(y_train)) < 2:
        return _heuristic_predictions(train_signals, predict_signals, model="single_class_fallback")

    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x_train)

    model = LogisticRegression(max_iter=500)
    try:
        model.fit(x_scaled, y_train)
    except ValueError:
        return _heuristic_predictions(train_signals, predict_signals, model="fit_failed_fallback")

    train_pred = model.predict(x_scaled)
    accuracy = float((train_pred == y_train).mean())

    x_pred = scaler.transform(np.array([signal_feature_vector(s) for s in predict_signals]))
    pred_actions = model.predict(x_pred)
    pred_probs = model.predict_proba(x_pred)
    class_index = {label: idx for idx, label in enumerate(model.classes_)}

    predictions = []
    for signal, action, probs in zip(predict_signals, pred_actions, pred_probs, strict=True):
        idx = class_index[action]
        predictions.append(
            {
                "signal_id": signal.signal_id,
                "ml_action": str(action),
                "ml_action_prob": round(float(probs[idx]), 3),
                "action_source": "logistic_regression",
            }
        )

    return {
        "model": "logistic_regression",
        "train_samples": len(train_signals),
        "accuracy": round(accuracy, 3),
        "classes": list(model.classes_),
        "predictions": predictions,
    }


def _heuristic_predictions(
    train_signals: list[ClassifiedSignal],
    predict_signals: list[ClassifiedSignal],
    *,
    model: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "train_samples": len(train_signals),
        "accuracy": None,
        "predictions": [
            {
                "signal_id": s.signal_id,
                "ml_action": _heuristic_label(s),
                "ml_action_prob": None,
                "action_source": "heuristic",
            }
            for s in predict_signals
        ],
    }


def apply_action_predictions(
    signals: list[ClassifiedSignal], result: dict[str, Any]
) -> list[ClassifiedSignal]:
    by_id = {row["signal_id"]: row for row in result.get("predictions", [])}
    updated: list[ClassifiedSignal] = []
    for signal in signals:
        row = by_id.get(signal.signal_id)
        if not row:
            updated.append(signal)
            continue
        stats = dict(signal.stats)
        stats["heuristic_action"] = signal.action
        stats["ml_action"] = row["ml_action"]
        stats["ml_action_prob"] = row.get("ml_action_prob")
        stats["action_source"] = row.get("action_source", "heuristic")
        updated.append(
            signal.model_copy(
                update={
                    "action": row["ml_action"],
                    "stats": stats,
                }
            )
        )
    return updated
