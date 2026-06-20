from __future__ import annotations

from collections import defaultdict
from typing import Any

from models.events import ClassifiedSignal

COMMODITY_ORDER = ["power", "natgas", "crude", "renewables", "weather", "general"]

DEFAULT_COV = {
    "power": 0.04,
    "natgas": 0.03,
    "crude": 0.025,
    "renewables": 0.05,
    "weather": 0.045,
    "general": 0.035,
}


def _commodity_returns(history: list[ClassifiedSignal]) -> dict[str, list[float]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for signal in history:
        stats = signal.stats or {}
        pct = stats.get("pct_change")
        if pct is None:
            continue
        buckets[signal.commodity].append(float(pct) / 100.0)
    return buckets


def build_covariance_matrix(
    commodities: list[str],
    history: list[ClassifiedSignal],
) -> list[list[float]]:
    import numpy as np

    buckets = _commodity_returns(history)
    n = len(commodities)
    cov = np.zeros((n, n))
    for i, ci in enumerate(commodities):
        ri = buckets.get(ci) or []
        var_i = float(np.var(ri)) if len(ri) >= 2 else DEFAULT_COV.get(ci, 0.03)
        cov[i, i] = max(var_i, 1e-4)
        for j, cj in enumerate(commodities):
            if j <= i:
                continue
            rj = buckets.get(cj) or []
            if len(ri) >= 3 and len(rj) >= 3 and len(ri) == len(rj):
                cov_ij = float(np.cov(ri, rj)[0, 1])
            else:
                cov_ij = 0.15 * (cov[i, i] * cov[j, j]) ** 0.5
            cov[i, j] = cov[j, i] = cov_ij
    return cov.tolist()


def expected_returns_from_trades(trades: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for trade in trades:
        direction = trade.get("direction", "monitor")
        if direction == "monitor":
            continue
        sign = 1.0 if direction == "long" else -1.0
        p_win = float(trade.get("p_win", 0.5))
        confidence = float(trade.get("confidence", 0.5))
        edge = sign * (2.0 * p_win - 1.0) * confidence
        commod = trade.get("commodity", "general")
        totals[commod] += edge
        counts[commod] += 1
    return {k: round(totals[k] / counts[k], 4) for k in totals}


def optimize_portfolio(
    *,
    trades: list[dict[str, Any]],
    history: list[ClassifiedSignal],
    method: str = "mean_variance",
    max_weight: float = 0.45,
    risk_aversion: float = 2.5,
) -> dict[str, Any]:
    import numpy as np
    from scipy.optimize import minimize

    mu_map = expected_returns_from_trades(trades)
    commodities = sorted(
        set(mu_map.keys()) | {t.get("commodity", "general") for t in trades},
        key=lambda c: (COMMODITY_ORDER.index(c) if c in COMMODITY_ORDER else 99, c),
    )
    commodities = [c for c in commodities if c in mu_map]
    if not commodities:
        return {
            "status": "empty",
            "message": "No directional trade ideas available for optimization.",
            "allocations": [],
        }

    mu = np.array([mu_map[c] for c in commodities], dtype=float)
    cov = np.array(build_covariance_matrix(commodities, history), dtype=float)
    n = len(commodities)
    max_weight = max(1.0 / n, min(max_weight, 1.0))

    if method == "risk_parity":
        vol = np.sqrt(np.clip(np.diag(cov), 1e-6, None))
        weights = (1.0 / vol) / np.sum(1.0 / vol)
        aligned = float(weights @ mu)
        if aligned < 0:
            weights = weights * np.where(mu < 0, -1.0, 1.0)
            weights = np.abs(weights) / np.sum(np.abs(weights))
    else:
        def objective(weights: np.ndarray) -> float:
            port_return = weights @ mu
            port_var = weights @ cov @ weights
            return -(port_return - 0.5 * risk_aversion * port_var)

        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        bounds = [(0.0, max_weight) for _ in range(n)]
        start = np.ones(n) / n
        result = minimize(objective, start, method="SLSQP", bounds=bounds, constraints=constraints)
        weights = result.x if result.success else start
        weights = np.clip(weights, 0, None)
        weights = weights / weights.sum()

    port_return = float(weights @ mu)
    port_vol = float(np.sqrt(weights @ cov @ weights))
    sharpe = port_return / port_vol if port_vol > 1e-8 else 0.0

    allocations = []
    for idx, commod in enumerate(commodities):
        related = [t for t in trades if t.get("commodity") == commod]
        allocations.append(
            {
                "commodity": commod,
                "weight": round(float(weights[idx]), 4),
                "weight_pct": round(float(weights[idx]) * 100, 1),
                "expected_return": mu_map[commod],
                "risk_contribution": round(float(weights[idx] * cov[idx, idx] ** 0.5), 4),
                "trade_ranks": [t.get("rank") for t in related],
                "directions": [t.get("direction") for t in related],
            }
        )
    allocations.sort(key=lambda row: row["weight"], reverse=True)

    return {
        "status": "ok",
        "method": method,
        "risk_aversion": risk_aversion,
        "max_weight": max_weight,
        "commodities": commodities,
        "summary": {
            "expected_return": round(port_return, 4),
            "volatility": round(port_vol, 4),
            "sharpe_proxy": round(sharpe, 3),
            "gross_exposure": round(float(weights.sum()), 3),
            "largest_weight": allocations[0]["commodity"] if allocations else None,
        },
        "covariance": cov.tolist(),
        "expected_returns": mu_map,
        "allocations": allocations,
        "disclaimer": "Paper portfolio weights from briefing alpha scores — not execution instructions.",
    }
