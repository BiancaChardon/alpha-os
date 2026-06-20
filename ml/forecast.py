from __future__ import annotations

from datetime import datetime
from typing import Any

FORECAST_SERIES = [
    ("fred", "DCOILWTICO", "WTI crude"),
    ("fred", "DHHNGSP", "Henry Hub spot"),
    ("pjm", "WESTERN_HUB", "PJM Western Hub LMP"),
]


def forecast_series(history: list[tuple[datetime, float]], *, periods: int = 5) -> dict[str, Any]:
    if len(history) < 8:
        return {"status": "insufficient_data", "points": []}

    history = sorted(history, key=lambda row: row[0])
    try:
        import pandas as pd
        from prophet import Prophet

        frame = pd.DataFrame({"ds": [row[0] for row in history], "y": [row[1] for row in history]})
        model = Prophet(daily_seasonality=False, weekly_seasonality=len(history) >= 14)
        model.fit(frame)
        future = model.make_future_dataframe(periods=periods)
        forecast = model.predict(future)
        tail = forecast.tail(periods)
        points = [
            {
                "ds": row.ds.isoformat(),
                "yhat": round(float(row.yhat), 4),
                "yhat_lower": round(float(row.yhat_lower), 4),
                "yhat_upper": round(float(row.yhat_upper), 4),
            }
            for row in tail.itertuples()
        ]
        last_actual = history[-1][1]
        projected = points[-1]["yhat"] if points else last_actual
        pct = ((projected - last_actual) / last_actual * 100) if last_actual else 0.0
        return {
            "status": "ok",
            "engine": "prophet",
            "periods": periods,
            "last_actual": last_actual,
            "projected_change_pct": round(pct, 2),
            "points": points,
        }
    except Exception as exc:
        return _linear_fallback(history, periods=periods, error=str(exc))


def _linear_fallback(
    history: list[tuple[datetime, float]],
    *,
    periods: int,
    error: str,
) -> dict[str, Any]:
    try:
        import numpy as np
    except ImportError:
        return {"status": "failed", "engine": "none", "points": [], "error": error}

    ys = np.array([row[1] for row in history], dtype=float)
    xs = np.arange(len(ys), dtype=float)
    slope, intercept = np.polyfit(xs, ys, 1)
    last_actual = float(ys[-1])
    points = []
    for step in range(1, periods + 1):
        yhat = float(intercept + slope * (len(ys) - 1 + step))
        points.append({"ds": f"t+{step}", "yhat": round(yhat, 4), "yhat_lower": None, "yhat_upper": None})
    projected = points[-1]["yhat"] if points else last_actual
    pct = ((projected - last_actual) / last_actual * 100) if last_actual else 0.0
    return {
        "status": "ok",
        "engine": "linear_fallback",
        "periods": periods,
        "last_actual": last_actual,
        "projected_change_pct": round(pct, 2),
        "points": points,
        "prophet_error": error,
    }


def run_forecasts(store, *, periods: int = 5) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for source, series, label in FORECAST_SERIES:
        history = store.get_series_timestamps(source, series, limit=90)
        forecast = forecast_series(history, periods=periods)
        results.append(
            {
                "source": source,
                "series": series,
                "label": label,
                "key": f"{source}:{series}",
                **forecast,
            }
        )
    return results
