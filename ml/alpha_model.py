from __future__ import annotations

from typing import Any

from ml.features import signal_feature_vector
from ml.trade_probability import MIN_TRAIN_SAMPLES, _signal_outcome_label, _train_calibrated_model
from models.events import ClassifiedSignal

DEFAULT_FOLDS = 5


def _build_train_rows(signals: list[ClassifiedSignal]) -> list[tuple[list[float], int]]:
    rows: list[tuple[list[float], int]] = []
    for signal in signals:
        label = _signal_outcome_label(signal)
        if label is None:
            continue
        direction = 1.0 if signal.sentiment >= 0 else -1.0
        feats = signal_feature_vector(signal) + [direction, 0.0, 1.0]
        rows.append((feats, label))
    if rows and len({row[1] for row in rows}) < 2:
        flipped: list[tuple[list[float], int]] = []
        for feats, label in rows:
            alt = list(feats)
            alt[7] = -alt[7]
            flipped.append((alt, 1 - label))
        rows.extend(flipped)
    return rows


def walk_forward_backtest(
    history: list[ClassifiedSignal],
    *,
    folds: int = DEFAULT_FOLDS,
) -> dict[str, Any]:
    labeled = [(signal, label) for signal in history if (label := _signal_outcome_label(signal)) is not None]
    labeled.sort(key=lambda row: row[0].ts)

    if len(labeled) < max(MIN_TRAIN_SAMPLES + 4, folds * 3):
        return {
            "status": "insufficient_data",
            "samples": len(labeled),
            "folds_completed": 0,
            "message": "Need more labeled signal history for walk-forward evaluation.",
        }

    import numpy as np

    fold_size = max(3, len(labeled) // folds)
    y_true: list[int] = []
    y_prob: list[float] = []
    y_pred: list[int] = []
    fold_metrics: list[dict[str, Any]] = []

    for fold_idx in range(1, folds):
        train_end = fold_idx * fold_size
        test_end = min((fold_idx + 1) * fold_size, len(labeled))
        train_slice = labeled[:train_end]
        test_slice = labeled[train_end:test_end]
        if len(test_slice) < 2:
            continue

        train_rows = _build_train_rows([signal for signal, _ in train_slice])
        trained = _train_calibrated_model(train_rows)
        if not trained:
            continue

        model, scaler, _ = trained
        fold_true: list[int] = []
        fold_prob: list[float] = []

        for signal, label in test_slice:
            direction = 1.0 if signal.sentiment >= 0 else -1.0
            feats = np.array([signal_feature_vector(signal) + [direction, 0.0, 1.0]])
            prob = float(model.predict_proba(scaler.transform(feats))[0][1])
            pred = 1 if prob >= 0.5 else 0
            y_true.append(label)
            y_prob.append(prob)
            y_pred.append(pred)
            fold_true.append(label)
            fold_prob.append(prob)

        if fold_true:
            fold_arr = np.array(fold_true)
            prob_arr = np.array(fold_prob)
            pred_arr = (prob_arr >= 0.5).astype(int)
            fold_metrics.append(
                {
                    "fold": fold_idx,
                    "test_samples": len(fold_true),
                    "accuracy": round(float((pred_arr == fold_arr).mean()), 3),
                    "brier_score": round(float(np.mean((prob_arr - fold_arr) ** 2)), 4),
                    "hit_rate": round(float(fold_arr.mean()), 3),
                }
            )

    if not y_true:
        return {
            "status": "no_folds",
            "samples": len(labeled),
            "folds_completed": 0,
            "message": "Walk-forward folds could not be evaluated with current history.",
        }

    truth = np.array(y_true)
    probs = np.array(y_prob)
    preds = np.array(y_pred)
    brier = float(np.mean((probs - truth) ** 2))
    accuracy = float((preds == truth).mean())
    hit_rate = float(truth.mean())
    ic = float(np.corrcoef(probs, truth)[0, 1]) if len(truth) > 2 and truth.std() > 0 else 0.0

    return {
        "status": "ok",
        "method": "walk_forward_calibrated_logistic",
        "samples": len(labeled),
        "folds_completed": len(fold_metrics),
        "out_of_sample_predictions": len(y_true),
        "metrics": {
            "accuracy": round(accuracy, 3),
            "brier_score": round(brier, 4),
            "hit_rate": round(hit_rate, 3),
            "information_coefficient": round(ic, 3),
            "avg_predicted_p_win": round(float(probs.mean()), 3),
        },
        "folds": fold_metrics,
        "disclaimer": "Out-of-sample metrics use pseudo-labeled signal outcomes, not realized P&L.",
    }
