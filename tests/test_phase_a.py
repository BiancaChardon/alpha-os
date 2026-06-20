from __future__ import annotations

from datetime import datetime

from ml.alpha_model import walk_forward_backtest
from models.events import ClassifiedSignal, Urgency
from quant.optimizer import expected_returns_from_trades, optimize_portfolio


def _signal(**kwargs) -> ClassifiedSignal:
    defaults = {
        "event_id": "e1",
        "ts": datetime.utcnow(),
        "source": "fixture",
        "modality": "timeseries",
        "commodity": "natgas",
        "urgency": Urgency.MEDIUM,
        "sentiment": 0.4,
        "relevance_score": 0.7,
        "confidence": 0.75,
        "one_line_summary": "natgas move",
        "stats": {"pct_change": 3.0, "z_score": 1.2},
    }
    defaults.update(kwargs)
    return ClassifiedSignal(**defaults)


def test_walk_forward_backtest_runs():
    history = []
    for i in range(40):
        history.append(
            _signal(
                signal_id=f"s{i}",
                ts=datetime(2026, 6, 1, i % 24, 0, 0),
                commodity="natgas" if i % 2 == 0 else "crude",
                sentiment=0.3 if i % 3 else -0.3,
                stats={"pct_change": 5.0 if i % 3 else -5.0, "z_score": 2.5},
                urgency=Urgency.HIGH,
            )
        )
    for i in range(20):
        history.append(
            _signal(
                signal_id=f"t{i}",
                ts=datetime(2026, 6, 2, i % 24, 0, 0),
                modality="text",
                sentiment=0.4 if i % 2 == 0 else 0.0,
            )
        )

    result = walk_forward_backtest(history, folds=4)
    assert result["status"] in {"ok", "no_folds", "insufficient_data"}
    if result["status"] == "ok":
        assert "accuracy" in result["metrics"]


def test_optimize_portfolio_from_trades():
    trades = [
        {"rank": 1, "commodity": "natgas", "direction": "long", "p_win": 0.7, "confidence": 0.8},
        {"rank": 2, "commodity": "crude", "direction": "short", "p_win": 0.62, "confidence": 0.75},
        {"rank": 3, "commodity": "power", "direction": "long", "p_win": 0.58, "confidence": 0.7},
    ]
    history = [
        _signal(commodity="natgas", stats={"pct_change": 2.0}),
        _signal(commodity="crude", stats={"pct_change": -1.5}),
        _signal(commodity="power", stats={"pct_change": 3.0}),
    ]
    mu = expected_returns_from_trades(trades)
    assert "natgas" in mu and mu["natgas"] > 0

    result = optimize_portfolio(trades=trades, history=history, method="mean_variance")
    assert result["status"] == "ok"
    assert result["allocations"]
    assert abs(sum(a["weight"] for a in result["allocations"]) - 1.0) < 0.01
