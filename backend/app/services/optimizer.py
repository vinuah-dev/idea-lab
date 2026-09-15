"""Constraint optimisation for resource allocation and staff rostering.

* Bed assignment  — weighted bipartite matching solved with Google OR-Tools CP-SAT
                    (falls back to the Hungarian algorithm via SciPy).
* Staff rostering — shift scheduling with coverage, rest and fairness constraints (CP-SAT,
                    greedy fallback).
Every assignment carries an explainable cost breakdown.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date

import numpy as np

try:  # pragma: no cover - import guard
    from ortools.sat.python import cp_model

    HAS_ORTOOLS = True
except ImportError:  # pragma: no cover
    HAS_ORTOOLS = False

from scipy.optimize import linear_sum_assignment

PREMIUM_FEATURES = {"ventilator", "cardiac_monitor"}
INFEASIBLE = 10_000


@dataclass
class BedOption:
    bed_id: int
    code: str
    ward_name: str
    ward_type: str
    features: list[str]
    floor: int
    department_id: int | None
    ward_occupancy: float  # 0..1
    nurse_coverage: float = 1.0  # on-duty nurses / required nurses for the ward (1.0 = fully staffed)


@dataclass
class PatientNeed:
    key: str
    label: str
    bed_types: list[str]
    features: list[str] = field(default_factory=list)
    department_id: int | None = None
    department_floor: int | None = None
    priority: int = 3  # 1 = most urgent
    preferred: list[str] = field(default_factory=list)  # soft feature preferences (e.g. resus-capable bay)


def bed_cost(need: PatientNeed, bed: BedOption) -> tuple[float, list[dict]] | None:
    """Cost of putting `need` into `bed` (lower is better) with factor breakdown; None if infeasible."""
    if bed.ward_type not in need.bed_types:
        return None
    missing = [f for f in need.features if f not in bed.features]
    if missing:
        return None
    factors: list[dict] = []
    rank = need.bed_types.index(bed.ward_type)
    factors.append({"factor": f"bed type preference ({bed.ward_type})", "cost": rank * 12.0})
    if need.department_id and bed.department_id and need.department_id != bed.department_id:
        factors.append({"factor": "ward belongs to another department", "cost": 8.0})
    if need.department_floor is not None:
        factors.append({"factor": "distance from department (floors)", "cost": 2.0 * abs(bed.floor - need.department_floor)})
    factors.append({"factor": f"ward load balancing ({bed.ward_occupancy:.0%} occupied)", "cost": round(bed.ward_occupancy * 15, 1)})
    if bed.nurse_coverage < 1:
        factors.append({"factor": f"nurse coverage {bed.nurse_coverage:.0%} of requirement", "cost": round((1 - bed.nurse_coverage) * 20, 1)})
    lacking = [f for f in need.preferred if f not in bed.features]
    if lacking:
        factors.append({"factor": "lacks preferred " + ", ".join(lacking), "cost": 6.0 * len(lacking)})
    wasted = [f for f in bed.features if f in PREMIUM_FEATURES and f not in need.features and f not in need.preferred]
    if wasted:
        factors.append({"factor": "reserve premium equipment (" + ", ".join(wasted) + ")", "cost": 4.0 * len(wasted)})
    factors = [f for f in factors if f["cost"] > 0] or [{"factor": "ideal match", "cost": 0.0}]
    return round(sum(f["cost"] for f in factors), 1), factors


def rank_beds(need: PatientNeed, beds: list[BedOption], top: int = 5) -> list[dict]:
    ranked = []
    for b in beds:
        res = bed_cost(need, b)
        if res is None:
            continue
        cost, factors = res
        ranked.append({
            "bed_id": b.bed_id, "code": b.code, "ward": b.ward_name, "ward_type": b.ward_type,
            "features": b.features, "cost": cost, "fit_score": max(0, round(100 - cost * 1.5)), "factors": factors,
        })
    ranked.sort(key=lambda r: r["cost"])
    return ranked[:top]


def optimize_bed_assignment(needs: list[PatientNeed], beds: list[BedOption], time_limit: float = 5.0) -> dict:
    t0 = time.perf_counter()
    n, m = len(needs), len(beds)
    if n == 0 or m == 0:
        return {"solver": "none", "status": "trivial", "assignments": [], "unassigned": [x.key for x in needs], "wall_ms": 0}

    cost = np.full((n, m), INFEASIBLE, dtype=float)
    factors: dict[tuple[int, int], list[dict]] = {}
    for i, need in enumerate(needs):
        for j, bed in enumerate(beds):
            res = bed_cost(need, bed)
            if res:
                cost[i, j], factors[(i, j)] = res

    pairs: list[tuple[int, int]] = []
    status = "OPTIMAL"
    if HAS_ORTOOLS:
        solver_name = "Google OR-Tools CP-SAT"
        model = cp_model.CpModel()
        x = {(i, j): model.NewBoolVar(f"x_{i}_{j}") for i in range(n) for j in range(m) if cost[i, j] < INFEASIBLE}
        for i in range(n):
            model.Add(sum(x[i, j] for j in range(m) if (i, j) in x) <= 1)
        for j in range(m):
            model.Add(sum(x[i, j] for i in range(n) if (i, j) in x) <= 1)
        # maximise number of (priority-weighted) placements first, then minimise cost
        model.Maximize(sum(v * int((6 - needs[i].priority) * 1000 - cost[i, j] * 10) for (i, j), v in x.items()))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_workers = 8
        result = solver.Solve(model)
        status = solver.StatusName(result)
        if result in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            pairs = [(i, j) for (i, j), v in x.items() if solver.Value(v)]
    else:  # pragma: no cover - exercised only without OR-Tools
        solver_name = "Hungarian algorithm (SciPy)"
        rows, cols = linear_sum_assignment(cost)
        pairs = [(i, j) for i, j in zip(rows, cols) if cost[i, j] < INFEASIBLE]

    assigned = {i for i, _ in pairs}
    assignments = [{
        "need": needs[i].key, "label": needs[i].label, "bed_id": beds[j].bed_id, "bed_code": beds[j].code,
        "ward": beds[j].ward_name, "ward_type": beds[j].ward_type, "cost": float(cost[i, j]), "factors": factors[(i, j)],
    } for i, j in sorted(pairs)]
    return {
        "solver": solver_name,
        "status": status,
        "assignments": assignments,
        "unassigned": [needs[i].key for i in range(n) if i not in assigned],
        "total_cost": round(sum(a["cost"] for a in assignments), 1),
        "variables": int((cost < INFEASIBLE).sum()),
        "wall_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


# ------------------------------------------------------------------ staff rostering
SHIFTS = ("morning", "evening", "night")


def optimize_roster(
    staff: list[dict],
    days: list[date],
    coverage: dict[tuple[int | None, str, str], int],
    unavailable: set[tuple[int, int]] | None = None,
    max_shifts: int = 5,
    time_limit: float = 10.0,
) -> dict:
    """staff: [{id, role, department_id}], coverage: {(dept_id, role, shift): required_per_day}."""
    t0 = time.perf_counter()
    unavailable = unavailable or set()
    S, D, T = range(len(staff)), range(len(days)), range(len(SHIFTS))
    groups: dict[tuple, list[int]] = {}
    for s in S:
        for t in SHIFTS:
            groups.setdefault((staff[s]["department_id"], staff[s]["role"], t), []).append(s)

    if not HAS_ORTOOLS:  # pragma: no cover
        return _greedy_roster(staff, days, coverage, unavailable, max_shifts, t0)

    model = cp_model.CpModel()
    x = {(s, d, t): model.NewBoolVar(f"x{s}_{d}_{t}") for s in S for d in D for t in T}
    for s in S:
        for d in D:
            model.AddAtMostOne(x[s, d, t] for t in T)
            if (staff[s]["id"], d) in unavailable:
                for t in T:
                    model.Add(x[s, d, t] == 0)
            if d + 1 < len(days):  # no night shift followed by a morning shift (rest rule)
                model.Add(x[s, d, 2] + x[s, d + 1, 0] <= 1)
        model.Add(sum(x[s, d, t] for d in D for t in T) <= max_shifts)

    shortfall = []
    for (dept, role, shift), req in coverage.items():
        members = groups.get((dept, role, shift), [])
        t = SHIFTS.index(shift)
        for d in D:
            sf = model.NewIntVar(0, req, f"sf_{dept}_{role}_{shift}_{d}")
            model.Add(sum(x[s, d, t] for s in members) + sf >= req)
            shortfall.append(sf)

    # fairness: balance night shifts and total shifts within each role
    fairness_terms = []
    for role in {st["role"] for st in staff}:
        members = [s for s in S if staff[s]["role"] == role]
        nights = [sum(x[s, d, 2] for d in D) for s in members]
        totals = [sum(x[s, d, t] for d in D for t in T) for s in members]
        for label, exprs, ub in (("n", nights, len(days)), ("t", totals, max_shifts)):
            hi, lo = model.NewIntVar(0, ub, f"hi_{label}_{role}"), model.NewIntVar(0, ub, f"lo_{label}_{role}")
            for e in exprs:
                model.Add(e <= hi)
                model.Add(e >= lo)
            fairness_terms.append(hi - lo)

    model.Minimize(1000 * sum(shortfall) + 25 * sum(fairness_terms) + sum(x.values()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 8
    result = solver.Solve(model)
    status = solver.StatusName(result)
    if result not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _greedy_roster(staff, days, coverage, unavailable, max_shifts, t0)

    assignments = [
        {"staff_id": staff[s]["id"], "date": days[d].isoformat(), "shift": SHIFTS[t]}
        for (s, d, t), v in x.items() if solver.Value(v)
    ]
    required = sum(req * len(days) for req in coverage.values())
    short = int(sum(solver.Value(v) for v in shortfall))
    nights = {}
    for a in assignments:
        if a["shift"] == "night":
            nights[a["staff_id"]] = nights.get(a["staff_id"], 0) + 1
    return {
        "solver": "Google OR-Tools CP-SAT",
        "status": status,
        "assignments": assignments,
        "required_slots": required,
        "shortfall": short,
        "coverage_pct": round(100 * (required - short) / required, 1) if required else 100.0,
        "max_nights": max(nights.values(), default=0),
        "min_nights": min((nights.get(st["id"], 0) for st in staff), default=0),
        "variables": len(x) + len(shortfall),
        "objective": solver.ObjectiveValue(),
        "wall_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def _greedy_roster(staff, days, coverage, unavailable, max_shifts, t0) -> dict:  # pragma: no cover
    load = {st["id"]: 0 for st in staff}
    last = {}
    assignments, short, required = [], 0, 0
    for d, day in enumerate(days):
        busy = set()
        for (dept, role, shift), req in coverage.items():
            required += req
            pool = [st for st in staff if st["department_id"] == dept and st["role"] == role
                    and st["id"] not in busy and (st["id"], d) not in unavailable and load[st["id"]] < max_shifts
                    and not (shift == "morning" and last.get(st["id"]) == (d - 1, "night"))]
            pool.sort(key=lambda st: load[st["id"]])
            for st in pool[:req]:
                assignments.append({"staff_id": st["id"], "date": day.isoformat(), "shift": shift})
                busy.add(st["id"])
                load[st["id"]] += 1
                last[st["id"]] = (d, shift)
            short += max(0, req - len(pool[:req]))
    return {"solver": "greedy heuristic", "status": "FEASIBLE", "assignments": assignments, "required_slots": required,
            "shortfall": short, "coverage_pct": round(100 * (required - short) / required, 1) if required else 100.0,
            "wall_ms": round((time.perf_counter() - t0) * 1000, 1)}
