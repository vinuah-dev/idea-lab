"""30-day readmission risk — LACE index plus a logistic-regression model with a model card.

LACE (van Walraven et al., CMAJ 2010):
  L  length of stay            <1 d: 0 · 1: 1 · 2: 2 · 3: 3 · 4–6: 4 · 7–13: 5 · ≥14: 7
  A  acute (emergent) admission                                               3
  C  Charlson comorbidity index 0: 0 · 1: 1 · 2: 2 · 3: 3 · ≥4: 5
  E  ED visits in the previous 6 months (capped at 4)
A LACE score ≥ 10 is conventionally "high risk". The logistic model adds age, critical-care stay,
polypharmacy and abnormal results at discharge; like the LOS model it is trained on a synthetic cohort
(retrain on local discharge data before real use).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Admission, DiagnosticOrder, EmergencyCase, Patient, Prescription

CHARLSON_WEIGHTS = {  # problem-list approximation of the Charlson comorbidity index
    "coronary artery disease": 1, "heart failure": 1, "copd": 1, "asthma": 1, "type 2 diabetes": 1,
    "ckd stage 3": 2, "atrial fibrillation": 0, "hypertension": 0, "hypothyroidism": 0, "epilepsy": 0,
}
FEATURES = ["LACE score", "age", "critical-care stay", "polypharmacy (≥5 active medicines)", "abnormal result at discharge"]


def _l_points(days: float) -> int:
    d = int(days)
    if d < 1:
        return 0
    if d <= 3:
        return d
    if d <= 6:
        return 4
    if d <= 13:
        return 5
    return 7


def _c_points(charlson: int) -> int:
    return charlson if charlson <= 3 else 5


def charlson(conditions: list[str]) -> int:
    return sum(CHARLSON_WEIGHTS.get(c.lower(), 1) for c in conditions or [])


def lace(los_days: float, emergent: bool, charlson_index: int, ed_visits: int) -> dict:
    parts = {"L": _l_points(los_days), "A": 3 if emergent else 0, "C": _c_points(charlson_index), "E": min(ed_visits, 4)}
    return {"score": sum(parts.values()), "components": parts}


def _synthetic(n: int = 5000, seed: int = 23):
    rng = np.random.default_rng(seed)
    los = rng.gamma(2.2, 2.0, n)
    emergent = rng.random(n) < 0.5
    ch = rng.poisson(1.1, n)
    ed = rng.poisson(0.7, n)
    lace_s = np.array([lace(a, b, c, d)["score"] for a, b, c, d in zip(los, emergent, ch, ed)])
    age = np.clip(rng.normal(56, 18, n), 16, 95)
    icu = rng.random(n) < 0.18
    poly = rng.random(n) < np.clip(0.1 + 0.08 * ch, 0, 0.8)
    abn = rng.random(n) < 0.25
    gender = rng.random(n) < 0.5  # no causal effect — used for the fairness check
    logit = -4.1 + 0.24 * lace_s + 0.012 * (age - 55) + 0.35 * icu + 0.45 * poly + 0.4 * abn
    y = rng.random(n) < 1 / (1 + np.exp(-logit))
    X = np.column_stack([lace_s, age, icu, poly, abn]).astype(float)
    return X, y.astype(int), gender


@lru_cache(maxsize=1)
def _model() -> dict:
    X, y, gender = _synthetic()
    cut = int(len(y) * 0.8)
    clf = LogisticRegression(max_iter=2000).fit(X[:cut], y[:cut])
    p = clf.predict_proba(X[cut:])[:, 1]
    yt, gt = y[cut:], gender[cut:]
    lace_only = X[cut:, 0]
    fairness = {g: round(float(roc_auc_score(yt[gt == flag], p[gt == flag])), 3) for g, flag in (("female", True), ("male", False))}
    return {
        "clf": clf,
        "metrics": {"auc": round(float(roc_auc_score(yt, p)), 3), "lace_only_auc": round(float(roc_auc_score(yt, lace_only)), 3),
                    "brier": round(float(brier_score_loss(yt, p)), 4), "base_rate": round(float(yt.mean()), 3),
                    "train_rows": cut, "test_rows": len(y) - cut},
        "fairness_auc_by_gender": fairness,
        "coefficients": {f: round(float(c), 3) for f, c in zip(FEATURES, clf.coef_[0])},
    }


def model_card() -> dict:
    m = _model()
    return {"model": "Logistic regression on LACE + clinical features (scikit-learn)", "features": FEATURES,
            "metrics": m["metrics"], "fairness_auc_by_gender": m["fairness_auc_by_gender"], "coefficients": m["coefficients"],
            "training_data": "Synthetic discharge cohort (demo) — retrain and recalibrate on local data before clinical use"}


def band(prob: float) -> str:
    return "high" if prob >= 0.2 else "moderate" if prob >= 0.1 else "low"


def follow_up_days(prob: float) -> int:
    return 5 if prob >= 0.2 else 10 if prob >= 0.1 else 14


def predict(lace_score: int, age: float, icu: bool, polypharmacy: bool, abnormal: bool) -> float:
    x = np.array([[lace_score, age, float(icu), float(polypharmacy), float(abnormal)]])
    return float(_model()["clf"].predict_proba(x)[0, 1])


def readmission_risk(db: Session, patient: Patient, admission: Admission | None = None) -> dict:
    adm = admission or db.scalar(select(Admission).where(Admission.patient_id == patient.id).order_by(Admission.admitted_at.desc()))
    now = datetime.now()
    los = ((adm.discharged_at or now) - adm.admitted_at).total_seconds() / 86400 if adm else 0
    since = (adm.admitted_at if adm else now) - timedelta(days=183)
    ed_cases = db.scalars(select(EmergencyCase).where(EmergencyCase.patient_id == patient.id, EmergencyCase.created_at >= since)).all()
    emergent = bool(adm and any(abs((c.created_at - adm.admitted_at).total_seconds()) < 86400 for c in ed_cases)) or (adm is not None and adm.acuity in ("high", "critical"))
    prior_ed = sum(1 for c in ed_cases if not adm or c.created_at < adm.admitted_at - timedelta(days=1))
    ch = charlson(patient.conditions or [])
    lc = lace(los, emergent, ch, prior_ed)
    icu = bool(adm and adm.bed and adm.bed.ward.ward_type in ("icu", "cardiac", "hdu"))
    active_meds = db.query(Prescription).filter(Prescription.patient_id == patient.id,
                                                Prescription.status.in_(["pending", "verified", "dispensed"])).count()
    abnormal = db.query(DiagnosticOrder).filter(DiagnosticOrder.patient_id == patient.id, DiagnosticOrder.abnormal.is_(True),
                                                DiagnosticOrder.created_at >= (adm.admitted_at if adm else now - timedelta(days=30))).count() > 0
    prob = predict(lc["score"], patient.age, icu, active_meds >= 5, abnormal)
    b = band(prob)
    actions = []
    if b == "high":
        actions += ["Nurse phone follow-up within 48 hours", "Pharmacist-led medication reconciliation and teach-back"]
    if active_meds >= 5:
        actions.append(f"Polypharmacy ({active_meds} active medicines) — simplify regimen where possible")
    if abnormal:
        actions.append("Confirm abnormal results were reviewed and communicated before discharge")
    if prior_ed >= 2:
        actions.append(f"{prior_ed} ED visits in 6 months — refer to chronic-disease clinic")
    return {"probability": round(prob, 3), "band": b, "lace": lc, "charlson": ch, "prior_ed_visits": prior_ed,
            "los_days": round(los, 1), "emergent": emergent, "critical_care": icu, "active_medicines": active_meds,
            "abnormal_results": abnormal, "follow_up_days": follow_up_days(prob), "actions": actions,
            "factors": [{"factor": f"Length of stay {los:.1f} d", "points": lc["components"]["L"]},
                        {"factor": "Emergent admission", "points": lc["components"]["A"]},
                        {"factor": f"Charlson index {ch}", "points": lc["components"]["C"]},
                        {"factor": f"ED visits (6 months): {prior_ed}", "points": lc["components"]["E"]}]}
