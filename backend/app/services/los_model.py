"""Length-of-stay (LOS) prediction — Gradient Boosting regression with quantile prediction intervals.

The model is trained on a synthetic historical-admissions dataset generated with clinically plausible
effects (ward type, acuity, age, comorbidities, emergency admission). In a real deployment the same
pipeline would be trained on the hospital's own discharge records.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

WARD_TYPES = ["general", "icu", "hdu", "cardiac", "isolation", "pediatric", "maternity"]
ACUITY = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
BASE_LOS = {"general": 3.0, "icu": 5.5, "hdu": 4.0, "cardiac": 4.5, "isolation": 7.0, "pediatric": 2.5, "maternity": 2.5}
FEATURES = ["age", "acuity", "comorbidities", "emergency_admission"] + [f"ward:{w}" for w in WARD_TYPES]


def _row(age: float, ward: str, acuity: int, comorbidities: int, emergency: bool) -> list[float]:
    return [float(age), float(acuity), float(comorbidities), float(bool(emergency))] + [1.0 if ward == w else 0.0 for w in WARD_TYPES]


def _synthetic(n: int = 4000, seed: int = 11):
    rng = np.random.default_rng(seed)
    wards = rng.choice(WARD_TYPES, n, p=[0.42, 0.12, 0.10, 0.10, 0.06, 0.10, 0.10])
    ages = np.where(wards == "pediatric", rng.integers(1, 14, n),
                    np.where(wards == "maternity", rng.integers(20, 40, n), np.clip(rng.normal(55, 18, n), 16, 95))).astype(float)
    acuity = rng.choice(4, n, p=[0.25, 0.40, 0.25, 0.10])
    acuity = np.where(wards == "icu", np.maximum(acuity, 2), acuity)
    comorb = rng.poisson(np.clip((ages - 30) / 25, 0.1, 3))
    emergency = rng.random(n) < 0.45
    base = np.array([BASE_LOS[w] for w in wards])
    mean = base * (1 + 0.012 * np.maximum(ages - 50, 0)) + 0.9 * acuity + 0.45 * comorb + 0.7 * emergency + 0.15 * acuity * comorb
    los = rng.gamma(shape=6.0, scale=mean / 6.0)
    X = np.array([_row(a, w, c, m, e) for a, w, c, m, e in zip(ages, wards, acuity, comorb, emergency)])
    return X, los


@lru_cache(maxsize=1)
def _model() -> dict:
    X, y = _synthetic()
    cut = int(len(y) * 0.8)
    Xtr, Xte, ytr, yte = X[:cut], X[cut:], y[:cut], y[cut:]
    params = dict(n_estimators=180, max_depth=3, learning_rate=0.06, subsample=0.9, random_state=0)
    mid = GradientBoostingRegressor(**params).fit(Xtr, ytr)
    lo = GradientBoostingRegressor(loss="quantile", alpha=0.1, **params).fit(Xtr, ytr)
    hi = GradientBoostingRegressor(loss="quantile", alpha=0.9, **params).fit(Xtr, ytr)
    pred, plo, phi = mid.predict(Xte), lo.predict(Xte), hi.predict(Xte)
    imp: dict[str, float] = {}
    for name, val in zip(FEATURES, mid.feature_importances_):
        key = "ward type" if name.startswith("ward:") else name.replace("_", " ")
        imp[key] = imp.get(key, 0.0) + float(val)
    baseline = float(mean_absolute_error(yte, np.full_like(yte, np.median(ytr))))  # naive "median stay" predictor
    return {
        "mid": mid, "lo": lo, "hi": hi,
        "metrics": {"mae_days": round(float(mean_absolute_error(yte, pred)), 2), "r2": round(float(r2_score(yte, pred)), 3),
                    "baseline_mae_days": round(baseline, 2),
                    "interval_coverage": round(float(np.mean((yte >= plo) & (yte <= phi))), 3),
                    "train_rows": cut, "test_rows": len(y) - cut},
        "importances": dict(sorted(((k, round(v, 3)) for k, v in imp.items()), key=lambda kv: -kv[1])),
    }


def warm() -> None:
    _model()


def predict_los(age: float, ward_type: str, acuity: str | int, comorbidities: int, emergency: bool) -> dict:
    m = _model()
    a = ACUITY.get(acuity, 1) if isinstance(acuity, str) else int(acuity)
    ward = ward_type if ward_type in WARD_TYPES else "general"
    x = np.array([_row(age, ward, a, comorbidities, emergency)])
    days = float(m["mid"].predict(x)[0])
    lo, hi = sorted((float(m["lo"].predict(x)[0]), float(m["hi"].predict(x)[0])))
    return {"days": round(days, 1), "low": round(max(0.5, min(lo, days)), 1), "high": round(max(hi, days), 1),
            "model": "Gradient Boosting regressor (80% quantile interval)"}


def model_card() -> dict:
    m = _model()
    return {"model": "GradientBoostingRegressor (scikit-learn) + quantile models for 10th/90th percentiles",
            "features": FEATURES, "metrics": m["metrics"], "importances": m["importances"],
            "training_data": "Synthetic historical admissions (demo) — retrain on real discharge records in deployment"}
