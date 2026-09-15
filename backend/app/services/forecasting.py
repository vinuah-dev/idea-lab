"""Demand forecasting with Holt-Winters additive triple exponential smoothing (weekly seasonality).

Implemented directly in NumPy so the model is transparent and dependency-light; parameters
(alpha, beta, gamma) are fitted by grid search on one-step-ahead squared error.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np


@dataclass
class Forecast:
    fitted: list[float]
    forecast: list[float]
    lower: list[float]
    upper: list[float]
    params: dict
    mape: float | None


def _holt_winters(y: np.ndarray, season: int, alpha: float, beta: float, gamma: float, horizon: int):
    n = len(y)
    level = y[:season].mean()
    trend = (y[season:2 * season].mean() - y[:season].mean()) / season if n >= 2 * season else 0.0
    seasonal = list(y[:season] - level)
    fitted = np.zeros(n)
    for t in range(n):
        s = seasonal[t % season]
        fitted[t] = level + trend + s
        prev_level = level
        level = alpha * (y[t] - s) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        seasonal[t % season] = gamma * (y[t] - level) + (1 - gamma) * s
    fc = np.array([level + (h + 1) * trend + seasonal[(n + h) % season] for h in range(horizon)])
    return fitted, fc


def holt_winters_forecast(series: list[float], horizon: int = 14, season: int = 7) -> Forecast:
    y = np.asarray(series, dtype=float)
    if len(y) < 2 * season + 2:
        mean = float(y.mean()) if len(y) else 0.0
        return Forecast(list(y), [mean] * horizon, [mean] * horizon, [mean] * horizon, {"method": "mean"}, None)

    grid = [0.1, 0.2, 0.35, 0.5, 0.7]
    best = None
    warmup = season
    for a, b, g in itertools.product(grid, [0.01, 0.05, 0.15], [0.05, 0.15, 0.3, 0.5]):
        fitted, _ = _holt_winters(y, season, a, b, g, 0)
        sse = float(np.sum((y[warmup:] - fitted[warmup:]) ** 2))
        if best is None or sse < best[0]:
            best = (sse, a, b, g)
    _, a, b, g = best

    # hold-out accuracy on the last 14 points
    hold = min(14, len(y) // 4)
    _, fc_hold = _holt_winters(y[:-hold], season, a, b, g, hold)
    actual = y[-hold:]
    nz = actual != 0
    mape = float(np.mean(np.abs((actual[nz] - fc_hold[nz]) / actual[nz])) * 100) if nz.any() else None

    fitted, fc = _holt_winters(y, season, a, b, g, horizon)
    resid_sd = float(np.std(y[warmup:] - fitted[warmup:]))
    widths = np.array([1.96 * resid_sd * np.sqrt(1 + 0.15 * h) for h in range(horizon)])
    return Forecast(
        fitted=[round(float(v), 2) for v in fitted],
        forecast=[round(float(v), 2) for v in fc],
        lower=[round(float(v), 2) for v in fc - widths],
        upper=[round(float(v), 2) for v in fc + widths],
        params={"method": "holt-winters-additive", "alpha": a, "beta": b, "gamma": g, "season": season},
        mape=round(mape, 2) if mape is not None else None,
    )
