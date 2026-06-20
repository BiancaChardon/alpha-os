from __future__ import annotations

import re
from typing import Any

from ml.features import signal_feature_vector, trade_idea_feature_vector
from models.events import Briefing, BriefingItem, ClassifiedSignal, ContrarianReview, Urgency

MIN_TRAIN_SAMPLES = 8

COMMOD_KEYWORDS = [
    ("power", re.compile(r"\bpower|pjm|ercot|caiso|lmp|heat rate|demand\b", re.I)),
    ("natgas", re.compile(r"\bnatgas|natural gas|henry hub|storage|bcf|gas\b", re.I)),
    ("crude", re.compile(r"\bcrude|wti|brent|opec|oil|refinery\b", re.I)),
    ("renewables", re.compile(r"\brenewable|solar|curtailment|wind\b", re.I)),
    ("weather", re.compile(r"\bweather|temp|cold|heat|forecast\b", re.I)),
]


def infer_commodity(title: str) -> str:
    prefix = title.split(" — ")[0]
    for key, pattern in COMMOD_KEYWORDS:
        if pattern.search(prefix) or pattern.search(title):
            return key
    return "general"


def infer_direction(title: str, signals: list[ClassifiedSignal]) -> str:
    text = title.lower()
    bullish = bool(re.search(r"\bbullish|rally|firm|spike|tighten|pulls demand|upside|support\b", text))
    bearish = bool(re.search(r"\bbearish|soft|cap|surplus|overhang|range-bound|downside|negative|bleed\b", text))
    if signals:
        avg = sum(s.sentiment for s in signals) / len(signals)
        if avg > 0.15 and not bearish:
            return "long"
        if avg < -0.15 and not bullish:
            return "short"
    if bullish and not bearish:
        return "long"
    if bearish and not bullish:
        return "short"
    return "monitor"


def supporting_signals(item: BriefingItem, classified: list[ClassifiedSignal]) -> list[ClassifiedSignal]:
    ids = set(item.supporting_signal_ids or [])
    matched = [s for s in classified if s.signal_id in ids]
    if matched:
        return matched
    commod = infer_commodity(item.title)
    return [s for s in classified if s.commodity == commod][:4]


def _move_material(stats: dict) -> bool:
    pct = abs(float(stats.get("pct_change") or 0.0))
    z = abs(float(stats.get("z_score") or 0.0))
    spike = bool(stats.get("spike_flag"))
    return spike or pct >= 4.0 or z >= 2.0


def _signal_outcome_label(signal: ClassifiedSignal) -> int | None:
    stats = signal.stats or {}
    if signal.modality == "text":
        if signal.sentiment > 0.2:
            return 1
        return 0

    if not stats:
        return None

    material = _move_material(stats)
    if signal.urgency == Urgency.HIGH:
        return 1 if material else 0
    if signal.urgency == Urgency.LOW:
        return 0 if material else 1

    pct_raw = stats.get("pct_change")
    if pct_raw is None:
        return None
    pct = float(pct_raw)
    if abs(pct) < 0.5:
        return None
    return 1 if (signal.sentiment > 0) == (pct > 0) else 0


def _perplexity_factor(verdict: str | None) -> float:
    return {"corroborate": 1.0, "mixed": 0.72, "challenge": 0.45}.get(verdict or "", 0.65)


def _heuristic_p_win(
    *,
    confidence: float,
    direction: str,
    sentiment: float,
    contrarian_adj: float,
    perplexity_factor: float,
) -> float:
    direction_weight = {"long": 1.0, "short": 0.95, "monitor": 0.55}.get(direction, 0.6)
    sentiment_boost = 0.5 + abs(sentiment) * 0.5
    base = confidence * direction_weight * sentiment_boost * perplexity_factor
    base = base * (1.0 + max(contrarian_adj, -0.35))
    return round(max(0.05, min(0.92, base)), 3)


def _train_calibrated_model(
    train_rows: list[tuple[list[float], int]],
) -> tuple[Any, Any, dict[str, Any]] | None:
    if len(train_rows) < MIN_TRAIN_SAMPLES:
        return None
    labels = [row[1] for row in train_rows]
    if len(set(labels)) < 2:
        return None

    try:
        import numpy as np
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return None

    x = np.array([row[0] for row in train_rows])
    y = np.array(labels)
    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x)
    base = LogisticRegression(max_iter=800, class_weight="balanced")
    model = CalibratedClassifierCV(base, method="sigmoid", cv=min(3, len(set(labels))))
    try:
        model.fit(x_scaled, y)
    except ValueError:
        return None

    train_prob = model.predict_proba(x_scaled)[:, 1]
    brier = float(np.mean((train_prob - y) ** 2))
    accuracy = float((model.predict(x_scaled) == y).mean())
    meta = {
        "train_samples": len(train_rows),
        "brier_score": round(brier, 4),
        "train_accuracy": round(accuracy, 3),
    }
    return model, scaler, meta


def compute_trade_probabilities(
    *,
    briefing: Briefing,
    classified: list[ClassifiedSignal],
    contrarian: ContrarianReview | None = None,
    rank_verdicts: list[dict[str, Any]] | None = None,
    history: list[ClassifiedSignal] | None = None,
) -> dict[str, Any]:
    history = history or classified
    verdict_by_rank = {v.get("rank"): v for v in (rank_verdicts or [])}
    contrarian_adj = contrarian.confidence_adjustment if contrarian else 0.0

    train_rows: list[tuple[list[float], int]] = []
    for signal in history:
        label = _signal_outcome_label(signal)
        if label is None:
            continue
        direction = "long" if signal.sentiment >= 0 else "short"
        feats = signal_feature_vector(signal) + [1.0 if direction == "long" else -1.0, 0.0, 1.0]
        train_rows.append((feats, label))

    if train_rows and len({row[1] for row in train_rows}) < 2:
        flipped: list[tuple[list[float], int]] = []
        for feats, label in train_rows:
            alt = list(feats)
            alt[7] = -alt[7]
            flipped.append((alt, 1 - label))
        train_rows.extend(flipped)

    trained = _train_calibrated_model(train_rows)
    model_meta: dict[str, Any] = {
        "engine": "heuristic_fallback",
        "train_samples": len(train_rows),
        "calibrated": False,
        "label_definition": "Pseudo-outcome: urgency justified by material move, or text sentiment polarity",
    }

    model = scaler = None
    if trained:
        model, scaler, fit_meta = trained
        model_meta.update(
            {
                "engine": "calibrated_logistic_regression",
                "calibrated": True,
                **fit_meta,
            }
        )

    trades: list[dict[str, Any]] = []
    for item in briefing.ranked_items:
        signals = supporting_signals(item, classified)
        commod = infer_commodity(item.title)
        direction = infer_direction(item.title, signals)
        avg_sent = sum(s.sentiment for s in signals) / len(signals) if signals else 0.0
        avg_rel = sum(s.relevance_score for s in signals) / len(signals) if signals else item.confidence
        urgencies = [s.urgency.value for s in signals]
        urgency = "high" if "high" in urgencies else "medium" if "medium" in urgencies else "low"
        px = verdict_by_rank.get(item.rank, {})
        px_factor = _perplexity_factor(px.get("verdict"))

        idea_feats = trade_idea_feature_vector(
            sentiment=avg_sent,
            relevance=avg_rel,
            confidence=item.confidence,
            urgency=urgency,
            commodity=commod,
            direction=direction,
            contrarian_adj=contrarian_adj,
            perplexity_factor=px_factor,
        )

        if model and scaler:
            import numpy as np

            vec = np.array([idea_feats])
            p_win = float(model.predict_proba(scaler.transform(vec))[0][1])
            p_win = max(0.03, min(0.97, p_win))
            source = "calibrated_model"
        else:
            p_win = _heuristic_p_win(
                confidence=item.confidence,
                direction=direction,
                sentiment=avg_sent,
                contrarian_adj=contrarian_adj,
                perplexity_factor=px_factor,
            )
            source = "heuristic_fallback"

        p_adverse = round((1.0 - p_win) * 0.62, 3)
        p_flat = round(max(0.0, 1.0 - p_win - p_adverse), 3)
        expected_value = round((p_win - p_adverse) * item.confidence, 3)

        trades.append(
            {
                "rank": item.rank,
                "title": item.title,
                "commodity": commod,
                "direction": direction,
                "urgency": urgency,
                "confidence": item.confidence,
                "p_win": round(p_win, 3),
                "p_flat": p_flat,
                "p_adverse": p_adverse,
                "expected_value": expected_value,
                "probability_source": source,
                "perplexity_verdict": px.get("verdict"),
                "supporting_signals": len(signals),
            }
        )

    trades.sort(key=lambda row: row["rank"])
    avg_p_win = round(sum(t["p_win"] for t in trades) / len(trades), 3) if trades else 0.0

    return {
        "briefing_id": briefing.briefing_id,
        "generated_at": briefing.created_at.isoformat(),
        "model": model_meta,
        "disclaimer": (
            "Probabilities are calibrated against pseudo-labeled historical signal outcomes, "
            "not realized P&L. For desk research only — not execution advice."
        ),
        "summary": {
            "trade_count": len(trades),
            "avg_p_win": avg_p_win,
            "best_trade_rank": trades[0]["rank"] if trades else None,
            "best_p_win": trades[0]["p_win"] if trades else None,
        },
        "trades": trades,
    }
