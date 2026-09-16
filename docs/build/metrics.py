"""Collect real evaluation metrics from the MedOrchestra codebase for the project report."""
import json
import math
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, r"D:\codin\idea lab\backend")

from sqlalchemy import func, select  # noqa: E402

from app.agents.nlp import INTENTS, detect_intents  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import (Admission, Bed, DailyStat, Medication, Patient, Resource, Staff, Surgery, VitalSign)  # noqa: E402
from app.services.forecasting import holt_winters_forecast  # noqa: E402
from app.services.los_model import model_card  # noqa: E402
from app.services.optimizer import BedOption, PatientNeed, optimize_bed_assignment, optimize_roster  # noqa: E402
from app.services.ot_scheduler import optimize_day  # noqa: E402

# held-out utterances (not in the training corpus)
TEST = [
    ("the patient has to be admitted to the high dependency unit", "admission"),
    ("please arrange an inpatient bed for this elderly lady with pneumonia", "admission"),
    ("get him into the ICU, he needs close monitoring", "admission"),
    ("admit baby to the children's ward", "admission"),
    ("man collapsed at the gate, not responding", "emergency"),
    ("ambulance arriving with a burns patient", "emergency"),
    ("severe chest pain patient just walked into casualty", "emergency"),
    ("trauma call: bike accident with head injury", "emergency"),
    ("fix a consultation with the orthopaedic doctor on monday", "appointment"),
    ("I need to see a skin or general doctor this week", "appointment"),
    ("book an OPD visit for my mother with the cardiologist", "appointment"),
    ("schedule a follow-up visit after two weeks", "appointment"),
    ("send blood for CBC and kidney function", "diagnostics"),
    ("book an MRI of the brain", "diagnostics"),
    ("has the x-ray report come back", "diagnostics"),
    ("do an ECG and troponin now", "diagnostics"),
    ("start tablet metformin for the patient", "pharmacy"),
    ("do we have enough ceftriaxone injections", "pharmacy"),
    ("check if aspirin interacts with warfarin", "pharmacy"),
    ("dispense the pending prescriptions", "pharmacy"),
    ("she can go home today, start the discharge", "discharge"),
    ("prepare discharge papers for bed 12", "discharge"),
    ("which patients are ready to be discharged", "discharge"),
    ("discharge planning for tomorrow morning", "discharge"),
    ("are there enough nurses for the night shift", "staffing"),
    ("make next week's duty roster", "staffing"),
    ("which cardiologist is on call right now", "staffing"),
    ("we are short of staff in the emergency department", "staffing"),
    ("any ventilator beds free", "bed_query"),
    ("how full is the ICU", "bed_query"),
    ("list free beds in the maternity ward", "bed_query"),
    ("what is the current bed occupancy", "bed_query"),
    ("optimise how beds are allocated to waiting patients", "optimization"),
    ("rebalance load across the wards", "optimization"),
    ("find the most efficient resource allocation", "optimization"),
    ("improve patient flow in the hospital", "optimization"),
    ("predict how many admissions we will get next week", "analytics"),
    ("show me the ER visit trend", "analytics"),
    ("what are today's bottlenecks", "analytics"),
    ("give me the monthly performance report", "analytics"),
    ("where is the patient right now", "patient_status"),
    ("what tests are still pending for this patient", "patient_status"),
    ("show the care timeline of MRN-1001", "patient_status"),
    ("has this patient finished the admission process", "patient_status"),
    ("book theatre for an appendix operation tomorrow", "surgery"),
    ("we need an operating room for a caesarean now", "surgery"),
    ("plan knee replacement surgery on friday", "surgery"),
    ("reschedule the theatre list to avoid overtime", "surgery"),
]


def nlp_eval():
    per: dict[str, list[int]] = {k: [0, 0] for k in INTENTS}
    correct = 0
    t0 = time.perf_counter()
    for text, gold in TEST:
        intents, _ = detect_intents(text)
        ok = intents[0]["name"] == gold
        correct += ok
        per[gold][0] += ok
        per[gold][1] += 1
    ms = (time.perf_counter() - t0) * 1000 / len(TEST)
    return {"n": len(TEST), "accuracy": round(correct / len(TEST), 3), "per_intent": {k: f"{a}/{b}" for k, (a, b) in per.items() if b},
            "avg_ms": round(ms, 2), "intents": len(INTENTS)}


def forecast_eval(db):
    rows = db.scalars(select(DailyStat).order_by(DailyStat.day)).all()
    out = {}
    for m in ("admissions", "er_visits", "opd_visits", "bed_occupancy", "icu_occupancy"):
        fc = holt_winters_forecast([getattr(r, m) for r in rows], horizon=14)
        # naive seasonal baseline: value 7 days earlier
        y = [getattr(r, m) for r in rows]
        hold = 14
        naive = [y[-hold - 7 + i] for i in range(hold)]
        actual = y[-hold:]
        naive_mape = sum(abs(a - n) / a for a, n in zip(actual, naive) if a) / hold * 100
        out[m] = {"mape": fc.mape, "naive_seasonal_mape": round(naive_mape, 2), "params": fc.params}
    return {"days": len(rows), "metrics": out}


def roster_eval(db):
    staff = db.scalars(select(Staff).where(Staff.role.in_(["doctor", "nurse"]))).all()
    days = [date.today() + timedelta(days=i + 1) for i in range(7)]
    groups = {}
    for s in staff:
        groups[(s.department_id, s.role)] = groups.get((s.department_id, s.role), 0) + 1
    cov = {}
    for (d, r), n in groups.items():
        cov[(d, r, "morning")] = max(1, math.floor(n * 0.30))
        if n >= 2:
            cov[(d, r, "evening")] = max(1, math.floor(n * 0.22))
        if n >= 3:
            cov[(d, r, "night")] = max(1, math.floor(n * 0.16))
    res = optimize_roster([{"id": s.id, "role": s.role, "department_id": s.department_id} for s in staff], days, cov, set(), 5, 8)
    return {k: res[k] for k in ("solver", "status", "required_slots", "shortfall", "coverage_pct", "wall_ms", "variables")} | {
        "staff": len(staff), "shifts": len(res["assignments"]), "min_nights": res.get("min_nights"), "max_nights": res.get("max_nights")}


def bed_eval(db):
    beds = db.scalars(select(Bed).where(Bed.status == "available")).all()
    opts = [BedOption(b.id, b.code, b.ward.name, b.ward.ward_type, b.features or [], b.ward.floor, b.ward.department_id, 0.7) for b in beds]
    needs = [PatientNeed(f"p{i}", f"p{i}", t, f, priority=p) for i, (t, f, p) in enumerate([
        (["icu", "hdu"], ["monitor"], 1), (["general", "hdu"], [], 3), (["emergency", "icu"], [], 1), (["general"], [], 4),
        (["cardiac", "icu"], [], 2), (["pediatric", "general"], [], 3), (["isolation", "icu"], [], 2), (["general"], [], 5)])]
    res = optimize_bed_assignment(needs, opts)
    return {"free_beds": len(opts), "patients": len(needs), "placed": len(res["assignments"]), "solver": res["solver"],
            "status": res["status"], "wall_ms": res["wall_ms"], "feasible_pairs": res["variables"]}


def main():
    db = SessionLocal()
    try:
        counts = {
            "patients": db.scalar(select(func.count(Patient.id))), "beds": db.scalar(select(func.count(Bed.id))),
            "staff": db.scalar(select(func.count(Staff.id))), "medications": db.scalar(select(func.count(Medication.id))),
            "resources": db.scalar(select(func.count(Resource.id))), "active_admissions": db.query(Admission).filter(Admission.status == "active").count(),
            "vitals": db.scalar(select(func.count(VitalSign.id))), "surgeries": db.scalar(select(func.count(Surgery.id))),
        }
        t = time.perf_counter()
        ot = optimize_day(db, date.today() + timedelta(days=1))
        report = {
            "counts": counts, "nlp": nlp_eval(), "forecast": forecast_eval(db), "los": model_card()["metrics"],
            "los_importances": model_card()["importances"], "roster": roster_eval(db), "beds": bed_eval(db),
            "ot": {k: ot.get(k) for k in ("status", "movable", "moved", "before", "after", "wall_ms")},
        }
    finally:
        db.close()
    out = r"C:\Users\HP\AppData\Local\Temp\claude\D--codin-idea-lab\87151ddf-948a-4e83-8159-c0449757400e\scratchpad\metrics.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
