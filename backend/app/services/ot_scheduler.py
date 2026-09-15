"""Operating-theatre scheduling.

* `find_slots`   — earliest feasible slot per theatre honouring theatre turnover, surgeon availability and
                   the elective day window (explainable cost per option).
* `optimize_day` — re-plans a day's not-yet-started surgeries with OR-Tools CP-SAT interval scheduling
                   (optional intervals per theatre + NoOverlap per theatre and per surgeon), minimising
                   priority-weighted start times, overtime and makespan.
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Resource, Surgery

try:  # pragma: no cover - import guard
    from ortools.sat.python import cp_model

    HAS_ORTOOLS = True
except ImportError:  # pragma: no cover
    HAS_ORTOOLS = False

PROCEDURES: dict[str, dict] = {
    "appendectomy": {"name": "Laparoscopic appendectomy", "specialty": "General Surgery", "duration": 60, "anaesthesia": "GA",
                     "keywords": ["appendectomy", "appendicectomy", "appendix"]},
    "cholecystectomy": {"name": "Laparoscopic cholecystectomy", "specialty": "General Surgery", "duration": 90, "anaesthesia": "GA",
                        "keywords": ["cholecystectomy", "gallbladder", "gall bladder", "gallstone"]},
    "hernia": {"name": "Inguinal hernia repair", "specialty": "General Surgery", "duration": 75, "anaesthesia": "spinal",
               "keywords": ["hernia repair", "hernia", "hernioplasty"]},
    "laparotomy": {"name": "Exploratory laparotomy", "specialty": "General Surgery", "duration": 150, "anaesthesia": "GA",
                   "keywords": ["laparotomy", "bowel obstruction", "perforation"]},
    "debridement": {"name": "Wound debridement", "specialty": "General Surgery", "duration": 45, "anaesthesia": "local",
                    "keywords": ["debridement", "abscess drainage", "incision and drainage"]},
    "tkr": {"name": "Total knee replacement", "specialty": "Orthopedics", "duration": 150, "anaesthesia": "spinal",
            "keywords": ["knee replacement", "tkr", "total knee"]},
    "hip": {"name": "Hip fracture fixation (DHS)", "specialty": "Orthopedics", "duration": 120, "anaesthesia": "spinal",
            "keywords": ["hip fracture", "hip fixation", "dhs", "hip replacement"]},
    "orif": {"name": "ORIF — long-bone fracture", "specialty": "Orthopedics", "duration": 110, "anaesthesia": "GA",
             "keywords": ["orif", "fracture fixation", "plating", "tibia fracture"]},
    "spine": {"name": "Lumbar spine decompression", "specialty": "Orthopedics", "duration": 180, "anaesthesia": "GA",
              "keywords": ["spine surgery", "laminectomy", "spinal decompression", "discectomy"]},
    "csection": {"name": "Caesarean section (LSCS)", "specialty": "Obstetrics & Gynecology", "duration": 60, "anaesthesia": "spinal",
                 "keywords": ["c-section", "caesarean", "cesarean", "lscs"]},
    "hysterectomy": {"name": "Laparoscopic hysterectomy", "specialty": "Obstetrics & Gynecology", "duration": 150, "anaesthesia": "GA",
                     "keywords": ["hysterectomy"]},
    "craniotomy": {"name": "Craniotomy", "specialty": "Neurology", "duration": 240, "anaesthesia": "GA",
                   "keywords": ["craniotomy", "brain surgery", "subdural"]},
    "cabg": {"name": "Coronary artery bypass (CABG)", "specialty": "Cardiology", "duration": 300, "anaesthesia": "GA",
             "keywords": ["cabg", "bypass surgery", "coronary bypass"]},
    "mastectomy": {"name": "Modified radical mastectomy", "specialty": "Oncology", "duration": 150, "anaesthesia": "GA",
                   "keywords": ["mastectomy", "breast surgery"]},
}

DAY_START, DAY_END, TURNOVER = 8 * 60, 20 * 60, 30  # minutes from midnight; theatre cleaning/turnover
PRIORITY_WEIGHT = {"emergency": 30, "urgent": 6, "elective": 1}


def match_procedure(text: str) -> str | None:
    t = text.lower()
    best: tuple[str, int] | None = None
    for key, p in PROCEDURES.items():
        for kw in p["keywords"]:
            if re.search(rf"\b{re.escape(kw)}\b", t) and (best is None or len(kw) > best[1]):
                best = (key, len(kw))
    return best[0] if best else None


def _base(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time())


def _m(dt: datetime, day: date) -> int:
    return int((dt - _base(day)).total_seconds() // 60)


def _dt(day: date, minutes: int) -> datetime:
    return _base(day) + timedelta(minutes=minutes)


def _round15(m: int) -> int:
    return ((m + 14) // 15) * 15


def operating_rooms(db: Session, include_maintenance: bool = False) -> list[Resource]:
    q = select(Resource).where(Resource.resource_type == "operating_room").order_by(Resource.name)
    rooms = db.scalars(q).all()
    return rooms if include_maintenance else [r for r in rooms if r.status != "maintenance"]


def day_surgeries(db: Session, day: date) -> list[Surgery]:
    start = _base(day)
    return db.scalars(select(Surgery).where(Surgery.scheduled_start >= start, Surgery.scheduled_start < start + timedelta(days=1),
                                            Surgery.status != "cancelled").order_by(Surgery.scheduled_start)).all()


def _busy(surgeries: list[Surgery], day: date, exclude_id: int | None = None):
    ot: dict[int, list[tuple[int, int]]] = {}
    doc: dict[int, list[tuple[int, int]]] = {}
    for s in surgeries:
        if s.id == exclude_id or s.status == "completed":
            continue
        a = _m(s.scheduled_start, day)
        b = a + s.duration_minutes
        if s.ot_id:
            ot.setdefault(s.ot_id, []).append((a, b + TURNOVER))
        if s.surgeon_id:
            doc.setdefault(s.surgeon_id, []).append((a, b + 15))
    return ot, doc


def find_slots(db: Session, day: date, duration: int, surgeon_id: int | None = None, priority: str = "elective",
               earliest: datetime | None = None, exclude_id: int | None = None, top: int = 4) -> list[dict]:
    now = datetime.now()
    rooms = operating_rooms(db)
    ot_busy, doc_busy = _busy(day_surgeries(db, day), day, exclude_id)
    lb = DAY_START
    if day == now.date():
        lead = 0 if priority == "emergency" else 30
        lb = _round15(_m(now, day)) + lead if priority != "emergency" else max(_m(now, day) + 10, 0)
        if priority != "emergency":
            lb = max(lb, DAY_START)
    if earliest is not None and earliest.date() == day:
        lb = max(lb, _m(earliest, day))
    limit = DAY_END if priority == "elective" else 24 * 60
    options = []
    for room in rooms:
        busy = sorted(ot_busy.get(room.id, []))
        used = sum(b - a for a, b in busy)
        util = used / (DAY_END - DAY_START)
        cands = sorted({lb} | {b for _, b in busy if b >= lb} | {b for _, b in doc_busy.get(surgeon_id, []) if b >= lb})
        for c in cands:
            s, e = c, c + duration
            if e > limit:
                break
            if any(s < b and e + TURNOVER > a for a, b in busy):
                continue
            if surgeon_id and any(s < b and e > a for a, b in doc_busy.get(surgeon_id, [])):
                continue
            wait = s - lb
            factors = [{"factor": "minutes until start", "cost": round(wait / 15, 1)},
                       {"factor": f"theatre utilisation {util:.0%}", "cost": round(util * 10, 1)}]
            if e > DAY_END:
                factors.append({"factor": "runs past 20:00 (overtime)", "cost": 15.0})
            if room.status == "in_use" and s < _m(now, day) + 30 and day == now.date():
                factors.append({"factor": "theatre currently in use", "cost": 5.0})
            options.append({"ot_id": room.id, "ot": room.name, "start": _dt(day, s).isoformat(), "end": _dt(day, e).isoformat(),
                            "wait_minutes": wait, "cost": round(sum(f["cost"] for f in factors), 1), "factors": factors})
            break
    options.sort(key=lambda o: o["cost"])
    return options[:top]


def optimize_day(db: Session, day: date, time_limit: float = 5.0) -> dict:
    t0 = time.perf_counter()
    now = datetime.now()
    rooms = operating_rooms(db)
    surgeries = day_surgeries(db, day)
    movable = [s for s in surgeries if s.status == "scheduled" and (day > now.date() or s.scheduled_start >= now)]
    fixed = [s for s in surgeries if s not in movable and s.status != "completed"]
    base = {"day": day.isoformat(), "movable": len(movable), "solver": "Google OR-Tools CP-SAT" if HAS_ORTOOLS else "unavailable"}
    if not movable or not rooms or not HAS_ORTOOLS:
        return base | {"status": "NOTHING_TO_OPTIMIZE" if not movable else "UNAVAILABLE", "assignments": [], "wall_ms": 0}

    lb = DAY_START if day > now.date() else max(DAY_START, _round15(_m(now, day)) + 15)
    horizon = 24 * 60
    model = cp_model.CpModel()
    start, end, pres, ot_iv = {}, {}, {}, {r.id: [] for r in rooms}
    doc_iv: dict[int, list] = {}
    for f in fixed:
        a = _m(f.scheduled_start, day)
        if f.ot_id in ot_iv:
            ot_iv[f.ot_id].append(model.NewFixedSizeIntervalVar(a, f.duration_minutes + TURNOVER, f"fix{f.id}"))
        if f.surgeon_id:
            doc_iv.setdefault(f.surgeon_id, []).append(model.NewFixedSizeIntervalVar(a, f.duration_minutes + 15, f"fixd{f.id}"))
    stability = []
    for s in movable:
        d = s.duration_minutes
        start[s.id] = model.NewIntVar(lb, horizon - d, f"st{s.id}")
        end[s.id] = model.NewIntVar(lb + d, horizon, f"en{s.id}")
        model.Add(end[s.id] == start[s.id] + d)
        for r in rooms:
            p = model.NewBoolVar(f"p{s.id}_{r.id}")
            pres[s.id, r.id] = p
            ot_iv[r.id].append(model.NewOptionalFixedSizeIntervalVar(start[s.id], d + TURNOVER, p, f"iv{s.id}_{r.id}"))
            if s.ot_id != r.id:
                stability.append(p)
        model.AddExactlyOne(pres[s.id, r.id] for r in rooms)
        if s.surgeon_id:
            doc_iv.setdefault(s.surgeon_id, []).append(model.NewFixedSizeIntervalVar(start[s.id], d + 15, f"doc{s.id}"))
    for ivs in ot_iv.values():
        model.AddNoOverlap(ivs)
    for ivs in doc_iv.values():
        model.AddNoOverlap(ivs)
    overtime = []
    for s in movable:
        ov = model.NewIntVar(0, horizon, f"ov{s.id}")
        model.Add(ov >= end[s.id] - DAY_END)
        overtime.append(ov)
    makespan = model.NewIntVar(lb, horizon, "makespan")
    model.AddMaxEquality(makespan, list(end.values()))
    model.Minimize(sum(PRIORITY_WEIGHT.get(s.priority, 1) * start[s.id] for s in movable)
                   + 40 * sum(overtime) + 3 * makespan + 20 * sum(stability))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 8
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return base | {"status": solver.StatusName(status), "assignments": [], "wall_ms": round((time.perf_counter() - t0) * 1000, 1)}

    room_name = {r.id: r.name for r in rooms}
    assignments = []
    for s in movable:
        r_id = next(r.id for r in rooms if solver.Value(pres[s.id, r.id]))
        st = solver.Value(start[s.id])
        assignments.append({
            "surgery_id": s.id, "procedure": s.procedure, "patient": s.patient.name if s.patient else None, "priority": s.priority,
            "ot_id": r_id, "ot": room_name[r_id], "start": _dt(day, st).isoformat(), "end": _dt(day, st + s.duration_minutes).isoformat(),
            "old_ot": room_name.get(s.ot_id), "old_start": s.scheduled_start.isoformat(),
            "moved": r_id != s.ot_id or _dt(day, st) != s.scheduled_start,
        })

    def metrics(items: list[tuple[int | None, int, int, int | None]]) -> dict:
        ends = [e for _, _, e, _ in items]
        conflicts = 0
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if (a[0] and a[0] == b[0] and a[1] < b[2] + TURNOVER and b[1] < a[2] + TURNOVER) or \
                        (a[3] and a[3] == b[3] and a[1] < b[2] and b[1] < a[2]):
                    conflicts += 1
        return {"makespan": _dt(day, max(ends)).strftime("%H:%M") if ends else None,
                "overtime_minutes": sum(max(0, e - DAY_END) for e in ends), "conflicts": conflicts}

    before_items = [(s.ot_id, _m(s.scheduled_start, day), _m(s.scheduled_start, day) + s.duration_minutes, s.surgeon_id) for s in movable]
    after_items = [(a["ot_id"], _m(datetime.fromisoformat(a["start"]), day), _m(datetime.fromisoformat(a["end"]), day),
                    next(s.surgeon_id for s in movable if s.id == a["surgery_id"])) for a in assignments]
    return base | {
        "status": solver.StatusName(status), "assignments": assignments, "moved": sum(1 for a in assignments if a["moved"]),
        "before": metrics(before_items), "after": metrics(after_items),
        "wall_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
