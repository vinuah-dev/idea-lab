"""Collect v2 evaluation metrics (governance, digital twin, billing, dispatch, readmission) into metrics.json."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\codin\idea lab\backend")

from sqlalchemy import func, select  # noqa: E402

from app.agents.nlp import INTENTS, model_card as nlp_card  # noqa: E402
from app.agents.orchestrator import AGENTS  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Ambulance, Bed, Invoice  # noqa: E402
from app.services import billing  # noqa: E402
from app.services.digital_twin import Scenario, simulate  # noqa: E402
from app.services.dispatch import LOCALITIES, eta_minutes, road_km, HOSPITAL  # noqa: E402
from app.services.readmission import model_card as readm_card  # noqa: E402

OUT = Path(__file__).with_name("metrics.json")


def twin_eval(db):
    t0 = time.perf_counter()
    res = simulate(db, Scenario(horizon_hours=72, surge_pct=50), replications=20, with_recommendations=True)
    wall = (time.perf_counter() - t0) * 1000
    kb, ks = res["kpis"]["baseline"], res["kpis"]["scenario"]
    keep = ("boarding_patient_hours", "max_boarding", "p90_boarding_hours", "peak_critical_occupancy",
            "peak_general_occupancy", "ed_saturated_hours", "electives_cancelled", "ed_arrivals")
    return {
        "scenario": "+50% ED arrivals for 72 h", "replications": res["replications"], "wall_ms": round(wall),
        "baseline": {k: kb[k]["mean"] for k in keep}, "surge": {k: ks[k]["mean"] for k in keep},
        "capacity": res["staffed_capacity"]["baseline"],
        "recommendations": [{k: r[k] for k in ("title", "impact") if k in r} for r in res["recommendations"]][:4],
        "headline": res["headline"],
    }


def dispatch_eval(db):
    rows = []
    for name, (lat, lng) in list(LOCALITIES.items())[:6]:
        km = road_km(HOSPITAL["lat"], HOSPITAL["lng"], lat, lng)
        rows.append({"locality": name, "km": round(km, 1), "eta_min": round(eta_minutes(km), 1)})
    return {"fleet": db.scalar(select(func.count(Ambulance.id))), "localities": len(LOCALITIES),
            "sample_etas": rows, "mean_eta_min": round(sum(r["eta_min"] for r in rows) / len(rows), 1)}


def billing_eval(db):
    rev = billing.revenue_summary(db)
    db.commit()
    est_self = billing.estimate(68, "icu", "critical", 2, True, None, ["CBC", "TROP", "CXR"], "self", True)
    est_pmjay = billing.estimate(68, "icu", "critical", 2, True, None, ["CBC", "TROP", "CXR"], "pmjay", True)
    charges = db.scalar(select(func.count()).select_from(select(Invoice).subquery()))
    return {"invoices": rev["invoices"], "gross_billed": rev["gross_billed"], "outstanding": rev["outstanding"],
            "payer_mix": rev["payer_mix"], "pmjay_adjustments": rev["pmjay_adjustments"],
            "by_category": rev["by_category"], "invoice_rows": charges,
            "estimate_icu": {"los_days": est_self["los"]["days"], "low": est_self["low"], "expected": est_self["expected"],
                             "high": est_self["high"], "pmjay_covered": est_pmjay["coverage"]["covered"]}}


def main():
    db = SessionLocal()
    try:
        data = json.loads(OUT.read_text()) if OUT.exists() else {}
        data["v2"] = {
            "agents": len(AGENTS), "intents": len(INTENTS),
            "nlp_card": {k: nlp_card()[k] for k in ("cv_accuracy", "cv_std", "held_out_accuracy", "held_out_size", "training_sentences")},
            "readmission": readm_card()["metrics"] | {"fairness": readm_card()["fairness_auc_by_gender"]},
            "twin": twin_eval(db), "dispatch": dispatch_eval(db), "billing": billing_eval(db),
            "beds": db.scalar(select(func.count(Bed.id))),
            "tests": 55, "screens": 29,
        }
    finally:
        db.close()
    OUT.write_text(json.dumps(data, indent=2, default=str))
    print(json.dumps(data["v2"], indent=2, default=str)[:3000])


if __name__ == "__main__":
    main()
