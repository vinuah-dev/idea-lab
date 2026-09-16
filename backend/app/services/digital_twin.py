"""Hospital digital twin — Monte-Carlo discrete-event simulation for 'what-if' capacity planning.

The initial state is the *live* hospital: occupied beds with their expected discharge times, beds being
cleaned, active ED cases and patients already boarding in the ED. The model then plays the next hours forward:
ED arrivals (hour-of-day profile) and elective admissions, ED work-up, admission decisions by triage level,
bed assignment, daytime-only discharges and bed turnaround.

A scenario (surge, mass-casualty incident, closed beds, staff absence) is compared with the baseline using
common random numbers — both runs share the same random streams, so differences come from the scenario and
not from noise. A small search over interventions (surge beds, discharge lounge, faster turnaround,
criteria-led discharge, elective deferral) turns the result into prescriptive recommendations.
"""
from __future__ import annotations

import heapq
import itertools
import math
import random
from collections import deque
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Admission, Bed, DailyStat, EmergencyCase

CRITICAL_WARDS = {"icu", "cardiac", "hdu"}
GROUPS = ("critical", "general")
_PROFILE = [0.55, 0.45, 0.40, 0.35, 0.35, 0.45, 0.60, 0.80, 1.00, 1.20, 1.35, 1.40,
            1.35, 1.25, 1.20, 1.20, 1.25, 1.35, 1.45, 1.40, 1.25, 1.05, 0.85, 0.70]
HOURLY_PROFILE = [v / (sum(_PROFILE) / 24) for v in _PROFILE]  # mean 1.0
SEVERITY_MIX = [0.03, 0.14, 0.38, 0.33, 0.12]      # ED triage levels 1..5
MCI_SEVERITY_MIX = [0.15, 0.30, 0.30, 0.20, 0.05]  # mass-casualty incident
ADMIT_P = {1: 0.90, 2: 0.65, 3: 0.30, 4: 0.08, 5: 0.02}
CRITICAL_P = {1: 0.70, 2: 0.35, 3: 0.08, 4: 0.0, 5: 0.0}
LOS_MEAN_DAYS = {"critical": 4.2, "general": 3.1}
LOS_SIGMA = 0.55
ED_WORKUP_MEAN_H = 2.0
CLEAN_H, FAST_CLEAN_H = 0.75, 0.33
ELECTIVE_CRITICAL_P = 0.15
STAFF_BUFFER = 0.9  # a 10% float pool absorbs small absences
DISCHARGE_WINDOW = (9, 20)


@dataclass
class Scenario:
    horizon_hours: int = 72
    surge_pct: float = 0.0
    surge_start_hour: int = 0
    surge_duration_hours: int = 0          # 0 → whole horizon
    mass_casualty_patients: int = 0
    mass_casualty_hour: int = 6
    closed_critical_beds: int = 0
    closed_general_beds: int = 0
    staff_absent_pct: float = 0.0
    extra_critical_beds: int = 0
    extra_general_beds: int = 0
    los_reduction_pct: float = 0.0
    discharge_lounge: bool = False
    fast_cleaning: bool = False
    defer_electives: bool = False


@dataclass
class Snapshot:
    start: datetime
    capacity: dict[str, int]
    occupied: dict[str, list[float | None]]   # remaining hours until expected discharge (None = unknown)
    cleaning: dict[str, int]
    ed_bays: int
    ed_in_workup: list[int] = field(default_factory=list)   # severities of patients being worked up
    ed_waiting: list[int] = field(default_factory=list)
    boarding: dict[str, int] = field(default_factory=lambda: {"critical": 0, "general": 0})
    ed_per_day: float = 50.0
    electives_per_day: float = 8.0


def _group(ward_type: str) -> str:
    return "critical" if ward_type in CRITICAL_WARDS else "general"


def snapshot(db: Session) -> Snapshot:
    now = datetime.now()
    cap = {"critical": 0, "general": 0}
    cleaning = {"critical": 0, "general": 0}
    occupied: dict[str, list[float | None]] = {"critical": [], "general": []}
    ed_bays = 0
    for b in db.scalars(select(Bed)).all():
        if b.bed_type == "emergency":
            ed_bays += b.status != "maintenance"
            continue
        g = _group(b.bed_type)
        if b.status == "maintenance":
            continue
        cap[g] += 1
        if b.status == "cleaning":
            cleaning[g] += 1
        elif b.status == "reserved":
            occupied[g].append(None)
    for a in db.scalars(select(Admission).where(Admission.status == "active")).all():
        if a.bed and a.bed.bed_type != "emergency":
            rem = (a.expected_discharge - now).total_seconds() / 3600 if a.expected_discharge else None
            occupied[_group(a.bed.bed_type)].append(rem)
    snap = Snapshot(start=now, capacity=cap, occupied=occupied, cleaning=cleaning, ed_bays=max(ed_bays, 1))
    for c in db.scalars(select(EmergencyCase).where(EmergencyCase.status.in_(["triage", "awaiting_bed", "in_treatment"]))).all():
        if c.status == "in_treatment":
            snap.ed_in_workup.append(c.triage_level)
        elif c.status == "awaiting_bed":
            snap.boarding["critical" if c.triage_level == 1 else "general"] += 1
        else:
            snap.ed_waiting.append(c.triage_level)
    stats = db.scalars(select(DailyStat).order_by(DailyStat.day.desc()).limit(14)).all()
    if stats:
        snap.ed_per_day = sum(s.er_visits for s in stats) / len(stats)
        adm_per_day = sum(s.admissions for s in stats) / len(stats)
        ed_admit_rate = sum(m * ADMIT_P[i + 1] for i, m in enumerate(SEVERITY_MIX))
        snap.electives_per_day = max(2.0, adm_per_day - snap.ed_per_day * ed_admit_rate)
    return snap


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def _severity(rng: random.Random, mix: list[float]) -> int:
    r, acc = rng.random(), 0.0
    for i, m in enumerate(mix):
        acc += m
        if r <= acc:
            return i + 1
    return len(mix)


class _Run:
    """One stochastic replication."""

    def __init__(self, snap: Snapshot, sc: Scenario, seed: int):
        self.snap, self.sc = snap, sc
        # independent streams per process → common random numbers across scenarios
        self.r_arr, self.r_los, self.r_ed, self.r_misc = (random.Random(seed * 1000 + k) for k in range(4))
        self.t0h = snap.start.hour + snap.start.minute / 60
        staffed = min(1.0, (1 - sc.staff_absent_pct / 100) / STAFF_BUFFER)
        closed = {"critical": sc.closed_critical_beds, "general": sc.closed_general_beds}
        extra = {"critical": sc.extra_critical_beds, "general": sc.extra_general_beds}
        self.cap = {g: max(0, math.floor((snap.capacity[g] - closed[g]) * staffed) + extra[g]) for g in GROUPS}
        self.occ = {g: 0 for g in GROUPS}
        self.free = {g: 0 for g in GROUPS}
        self.boarding: dict[str, deque] = {g: deque() for g in GROUPS}
        self.ed_free = snap.ed_bays
        self.ed_queue: list[tuple[int, float, int]] = []
        self.events: list = []
        self.seq = itertools.count()
        self.board_waits: list[float] = []
        self.ed_waits: list[float] = []
        self.samples: list[dict] = []
        self.counts = {"ed_arrivals": 0, "admissions": 0, "electives_cancelled": 0, "electives_deferred": 0, "mci": 0}

    # ---------------------------------------------------------------- helpers
    def push(self, t: float, kind: str, data=None) -> None:
        heapq.heappush(self.events, (t, next(self.seq), kind, data))

    def hour_of_day(self, t: float) -> float:
        return (self.t0h + t) % 24

    def discharge_time(self, t_ready: float) -> float:
        """Discharges happen in the daytime window; a discharge lounge frees the bed ~1.5 h earlier."""
        h = self.hour_of_day(t_ready)
        lo, hi = DISCHARGE_WINDOW
        if h < lo:
            t_ready += (lo - h) + self.r_los.uniform(0, 3)
        elif h >= hi:
            t_ready += (24 - h + lo) + self.r_los.uniform(0, 3)
        if self.sc.discharge_lounge:
            t_ready -= min(1.5, max(0.0, self.hour_of_day(t_ready) - 8))
        return max(t_ready, 0.05)

    def los_hours(self, g: str) -> float:
        mean = LOS_MEAN_DAYS[g] * (1 - self.sc.los_reduction_pct / 100)
        mu = math.log(mean) - LOS_SIGMA ** 2 / 2
        return self.r_los.lognormvariate(mu, LOS_SIGMA) * 24

    def workup(self) -> float:
        return min(8.0, max(0.5, self.r_ed.expovariate(1 / ED_WORKUP_MEAN_H)))

    def admit(self, g: str, t: float) -> None:
        self.free[g] -= 1
        self.occ[g] += 1
        self.counts["admissions"] += 1
        self.push(self.discharge_time(t + self.los_hours(g)), "discharge", g)

    def release_ed(self, t: float) -> None:
        self.ed_free += 1
        if self.ed_queue and self.ed_free > 0:
            sev, t_arr, _ = heapq.heappop(self.ed_queue)
            self.ed_waits.append(t - t_arr)
            self.ed_free -= 1
            self.push(t + self.workup(), "ed_decision", sev)

    # ---------------------------------------------------------------- set-up
    def setup(self) -> None:
        sc, snap = self.sc, self.snap
        for g in GROUPS:
            for rem in snap.occupied[g]:
                if rem is None:
                    rem = self.los_hours(g)
                elif rem <= 0:
                    rem = self.r_los.uniform(0.5, 8)
                rem *= 1 - sc.los_reduction_pct / 100 * 0.5  # only part of the remaining stay is compressible
                self.occ[g] += 1
                self.push(self.discharge_time(rem), "discharge", g)
            self.free[g] = self.cap[g] - self.occ[g] - snap.cleaning[g]
            for _ in range(snap.cleaning[g]):
                self.push(self.r_misc.uniform(0, 1.0), "bed_free", g)
            for _ in range(snap.boarding[g]):
                self.ed_free -= 1
                self.boarding[g].append(0.0)
        for sev in snap.ed_in_workup:
            self.ed_free -= 1
            self.push(self.r_ed.uniform(0.2, 2.0), "ed_decision", sev)
        for sev in snap.ed_waiting:
            heapq.heappush(self.ed_queue, (sev, 0.0, next(self.seq)))
        while self.ed_free > 0 and self.ed_queue:  # fill any free bays at t=0
            sev, _, _ = heapq.heappop(self.ed_queue)
            self.ed_free -= 1
            self.ed_waits.append(0.0)
            self.push(self.workup(), "ed_decision", sev)
        H = sc.horizon_hours
        per_hour = snap.ed_per_day / 24
        surge_end = sc.surge_start_hour + (sc.surge_duration_hours or H)
        for h in range(H):
            mult = 1 + (sc.surge_pct / 100 if sc.surge_start_hour <= h < surge_end else 0)
            lam = per_hour * HOURLY_PROFILE[int(self.hour_of_day(h)) % 24] * mult
            for _ in range(_poisson(self.r_arr, lam)):
                self.push(h + self.r_arr.random(), "ed_arrival", _severity(self.r_arr, SEVERITY_MIX))
        if sc.mass_casualty_patients:
            for _ in range(sc.mass_casualty_patients):
                self.push(sc.mass_casualty_hour + self.r_misc.uniform(0, 1.0), "ed_arrival", _severity(self.r_misc, MCI_SEVERITY_MIX))
                self.counts["mci"] += 1
        days = math.ceil((H + self.t0h) / 24) + 1
        for d in range(days):
            n = _poisson(self.r_arr, snap.electives_per_day)
            for _ in range(n):
                t = d * 24 - self.t0h + self.r_arr.uniform(8, 14)
                if 0 <= t < H:
                    g = "critical" if self.r_arr.random() < ELECTIVE_CRITICAL_P else "general"
                    if sc.defer_electives:
                        self.counts["electives_deferred"] += 1
                    else:
                        self.push(t, "elective", g)
        for h in range(H + 1):
            self.push(float(h), "sample")

    # ---------------------------------------------------------------- run
    def run(self) -> dict:
        self.setup()
        H = self.sc.horizon_hours
        clean_h = FAST_CLEAN_H if self.sc.fast_cleaning else CLEAN_H
        while self.events:
            t, _, kind, data = heapq.heappop(self.events)
            if t > H:
                break
            if kind == "sample":
                self.samples.append({"hour": t, "critical": self.occ["critical"], "general": self.occ["general"],
                                     "boarding": sum(len(q) for q in self.boarding.values()),
                                     "ed_waiting": len(self.ed_queue), "ed_busy": self.snap.ed_bays - self.ed_free})
            elif kind == "ed_arrival":
                self.counts["ed_arrivals"] += 1
                if self.ed_free > 0:
                    self.ed_free -= 1
                    self.ed_waits.append(0.0)
                    self.push(t + self.workup(), "ed_decision", data)
                else:
                    heapq.heappush(self.ed_queue, (data, t, next(self.seq)))
            elif kind == "ed_decision":
                sev = data
                if self.r_ed.random() < ADMIT_P[sev]:
                    g = "critical" if self.r_ed.random() < CRITICAL_P[sev] else "general"
                    if self.free[g] > 0:
                        self.admit(g, t)
                        self.release_ed(t)
                    else:
                        self.boarding[g].append(t)  # boards in the ED bay until a bed frees up
                else:
                    self.release_ed(t)
            elif kind == "elective":
                if self.free[data] > 0:
                    self.admit(data, t)
                else:
                    self.counts["electives_cancelled"] += 1
            elif kind == "discharge":
                self.occ[data] -= 1
                self.push(t + clean_h, "bed_free", data)
            elif kind == "bed_free":
                g = data
                self.free[g] += 1
                if self.free[g] > 0 and self.boarding[g]:
                    t_req = self.boarding[g].popleft()
                    self.board_waits.append(t - t_req)
                    self.admit(g, t)
                    self.release_ed(t)
        for g in GROUPS:  # still boarding at the horizon (censored waits)
            self.board_waits.extend(H - t_req for t_req in self.boarding[g])
        return self.metrics()

    def metrics(self) -> dict:
        s = self.samples
        cap = self.cap
        bw = sorted(self.board_waits)
        ew = sorted(self.ed_waits)
        return {
            "samples": s,
            "capacity": dict(cap),
            "kpis": {
                "peak_critical_occupancy": round(max((x["critical"] / max(cap["critical"], 1) for x in s), default=0), 3),
                "peak_general_occupancy": round(max((x["general"] / max(cap["general"], 1) for x in s), default=0), 3),
                "hours_critical_full": sum(1 for x in s if x["critical"] >= cap["critical"]),
                "hours_general_full": sum(1 for x in s if x["general"] >= cap["general"]),
                "boarding_patient_hours": round(sum(x["boarding"] for x in s), 1),
                "max_boarding": max((x["boarding"] for x in s), default=0),
                "mean_boarding_hours": round(sum(bw) / len(bw), 2) if bw else 0.0,
                "p90_boarding_hours": round(bw[int(0.9 * (len(bw) - 1))], 2) if bw else 0.0,
                "patients_boarded": len(bw),
                "mean_ed_wait_minutes": round(60 * sum(ew) / len(ew), 1) if ew else 0.0,
                "ed_saturated_hours": sum(1 for x in s if x["ed_waiting"] > 0),
                "electives_cancelled": self.counts["electives_cancelled"],
                "electives_deferred": self.counts["electives_deferred"],
                "ed_arrivals": self.counts["ed_arrivals"],
                "admissions": self.counts["admissions"],
            },
        }


KPI_LABELS = {
    "peak_critical_occupancy": "Peak critical-care occupancy", "peak_general_occupancy": "Peak ward occupancy",
    "hours_critical_full": "Hours critical care full", "hours_general_full": "Hours wards full",
    "boarding_patient_hours": "ED boarding (patient-hours)", "max_boarding": "Max patients boarding",
    "mean_boarding_hours": "Mean boarding wait (h)", "p90_boarding_hours": "P90 boarding wait (h)",
    "mean_ed_wait_minutes": "Mean wait for ED bay (min)", "ed_saturated_hours": "Hours ED saturated",
    "electives_cancelled": "Elective admissions cancelled", "ed_arrivals": "ED arrivals", "admissions": "Admissions",
}


def _replicate(snap: Snapshot, sc: Scenario, reps: int, seed0: int = 0) -> list[dict]:
    return [_Run(snap, sc, seed0 + i).run() for i in range(reps)]


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _pct(vals: list[float], q: float) -> float:
    v = sorted(vals)
    return v[int(q * (len(v) - 1))] if v else 0.0


def _kpi_stats(runs: list[dict]) -> dict:
    out = {}
    for k in runs[0]["kpis"]:
        vals = [r["kpis"][k] for r in runs]
        out[k] = {"mean": round(_mean(vals), 3), "p10": round(_pct(vals, 0.1), 3), "p90": round(_pct(vals, 0.9), 3)}
    return out


def _timeline(base: list[dict], scen: list[dict], start: datetime) -> list[dict]:
    rows = []
    n = min(len(base[0]["samples"]), len(scen[0]["samples"]))
    for i in range(n):
        row = {"hour": i, "t": (start + timedelta(hours=i)).isoformat(timespec="minutes")}
        for tag, runs in (("base", base), ("scn", scen)):
            for key in ("critical", "general"):
                vals = [r["samples"][i][key] / max(r["capacity"][key], 1) * 100 for r in runs]
                row[f"{key}_{tag}"] = round(_mean(vals), 1)
                if tag == "scn":
                    row[f"{key}_{tag}_band"] = [round(_pct(vals, 0.1), 1), round(_pct(vals, 0.9), 1)]
            vals = [r["samples"][i]["boarding"] for r in runs]
            row[f"boarding_{tag}"] = round(_mean(vals), 2)
            if tag == "scn":
                row["boarding_scn_band"] = [round(_pct(vals, 0.1), 1), round(_pct(vals, 0.9), 1)]
            row[f"ed_waiting_{tag}"] = round(_mean([r["samples"][i]["ed_waiting"] for r in runs]), 2)
        rows.append(row)
    return rows


LEVERS = [
    ("extra_general_beds", [4, 8, 12, 16, 20], "Open {v} surge ward beds", "Day-care unit or overflow ward staffed from the float pool"),
    ("extra_critical_beds", [2, 4, 6, 8], "Open {v} surge critical-care beds", "Convert PACU / step-down beds with a critical-care nurse per 2 beds"),
    ("discharge_lounge", [True], "Run a discharge lounge", "Patients awaiting transport or paperwork vacate beds ~1.5 h earlier"),
    ("fast_cleaning", [True], "Rapid bed-turnaround team", "Cleaning time 45 → 20 minutes via housekeeping prioritisation"),
    ("los_reduction_pct", [10], "Criteria-led discharge (−10% LOS)", "Consultant-agreed discharge criteria so nurses can discharge on time"),
    ("defer_electives", [True], "Defer elective admissions", "Postpone non-urgent elective admissions during the surge window"),
]


def _objective(k: dict) -> float:
    """Single number to minimise: boarding patient-hours + ED saturation + cancelled electives."""
    return k["boarding_patient_hours"] + 3 * k["ed_saturated_hours"] + 4 * k["electives_cancelled"]


def recommend(snap: Snapshot, sc: Scenario, reps: int = 10) -> list[dict]:
    ref_runs = _replicate(snap, sc, reps)
    ref = {k: _mean([r["kpis"][k] for r in ref_runs]) for k in ref_runs[0]["kpis"]}
    ref_obj = _objective(ref)
    if ref_obj < 3:
        return [{"title": "Capacity is sufficient", "detail": "No material boarding, ED saturation or cancellations are expected under this scenario.",
                 "impact": 0, "lever": None, "value": None}]
    recs = []
    for attr, values, title, how in LEVERS:
        if getattr(sc, attr):
            continue
        best = None
        for v in values:
            runs = _replicate(snap, replace(sc, **{attr: v}), reps)
            k = {kk: _mean([r["kpis"][kk] for r in runs]) for kk in runs[0]["kpis"]}
            gain = (ref_obj - _objective(k)) / ref_obj
            if best is None or gain > best[1] + 0.05:  # smallest value that still adds a meaningful gain
                best = (v, gain, k)
        if best and best[1] >= 0.1:
            v, gain, k = best
            recs.append({"title": title.format(v=v), "detail": how, "lever": attr, "value": v, "impact": round(gain, 3),
                         "boarding_patient_hours": round(k["boarding_patient_hours"], 1),
                         "ed_saturated_hours": round(k["ed_saturated_hours"], 1),
                         "electives_cancelled": round(k["electives_cancelled"], 1)})
    recs.sort(key=lambda r: -r["impact"])
    return recs[:5] or [{"title": "No single lever helps materially", "detail": "Combine interventions or divert ambulances to partner hospitals.",
                         "impact": 0, "lever": None, "value": None}]


def simulate(db: Session, sc: Scenario, replications: int = 30, with_recommendations: bool = True) -> dict:
    reps = max(5, min(int(replications), 100))
    sc = replace(sc, horizon_hours=max(12, min(int(sc.horizon_hours), 168)))
    snap = snapshot(db)
    base = _replicate(snap, Scenario(horizon_hours=sc.horizon_hours), reps)
    scen = _replicate(snap, sc, reps)
    kb, ks = _kpi_stats(base), _kpi_stats(scen)
    recs = recommend(snap, sc) if with_recommendations else []
    delta = ks["boarding_patient_hours"]["mean"] - kb["boarding_patient_hours"]["mean"]
    headline = (f"Over the next {sc.horizon_hours} h, ED boarding is expected to be {ks['boarding_patient_hours']['mean']:.0f} patient-hours "
                f"({'+' if delta >= 0 else ''}{delta:.0f} vs baseline); peak critical-care occupancy "
                f"{ks['peak_critical_occupancy']['mean']:.0%}, peak ward occupancy {ks['peak_general_occupancy']['mean']:.0%}.")
    if recs and recs[0].get("lever"):
        headline += f" Best single lever: {recs[0]['title'].lower()} (−{recs[0]['impact']:.0%} on the pressure index)."
    return {
        "generated_at": datetime.now().isoformat(), "scenario": asdict(sc), "replications": reps,
        "state": {"capacity": snap.capacity, "occupied": {g: len(v) for g, v in snap.occupied.items()},
                  "cleaning": snap.cleaning, "ed_bays": snap.ed_bays, "ed_in_workup": len(snap.ed_in_workup),
                  "ed_waiting": len(snap.ed_waiting), "boarding": snap.boarding,
                  "ed_arrivals_per_day": round(snap.ed_per_day, 1), "electives_per_day": round(snap.electives_per_day, 1)},
        "staffed_capacity": {"baseline": base[0]["capacity"], "scenario": scen[0]["capacity"]},
        "kpis": {"baseline": kb, "scenario": ks}, "kpi_labels": KPI_LABELS,
        "timeline": _timeline(base, scen, snap.start), "recommendations": recs, "headline": headline,
        "assumptions": [
            f"ED arrivals ≈ {snap.ed_per_day:.0f}/day (14-day mean) with an hour-of-day profile; electives ≈ {snap.electives_per_day:.0f}/day (08:00–14:00).",
            "Admission probability by triage level L1–L5: 90/65/30/8/2%; critical-care need 70/35/8/0/0%.",
            "Length of stay: log-normal, mean 4.2 d (critical care) / 3.1 d (wards); discharges 09:00–20:00 only.",
            "Bed turnaround 45 min; ED work-up ~2 h (exponential); admitted patients board in the ED bay until a bed frees.",
            "Staff absence beyond a 10% float-pool buffer closes beds proportionally.",
        ],
    }


PRESETS = {
    "dengue_surge": {"label": "Monsoon dengue surge (+40% ED for 3 days)", "surge_pct": 40, "horizon_hours": 72},
    "mass_casualty": {"label": "Mass-casualty incident (bus accident, 18 patients)", "mass_casualty_patients": 18, "mass_casualty_hour": 3, "horizon_hours": 48},
    "nurse_absence": {"label": "30% nursing absence (strike / outbreak)", "staff_absent_pct": 30, "horizon_hours": 72},
    "icu_closure": {"label": "4 ICU beds closed for maintenance", "closed_critical_beds": 4, "horizon_hours": 72},
    "festival_weekend": {"label": "Festival weekend (+25% ED, electives deferred)", "surge_pct": 25, "defer_electives": True, "horizon_hours": 72},
}
