"""Queueing-theory helpers for OPD wait-time estimation and queue prioritisation."""
from __future__ import annotations

import math
from datetime import datetime


def erlang_c(servers: int, arrival_rate: float, service_rate: float) -> float:
    """Probability an arriving patient has to wait (M/M/c queue)."""
    if servers <= 0 or service_rate <= 0:
        return 1.0
    a = arrival_rate / service_rate  # offered load (Erlangs)
    rho = a / servers
    if rho >= 1:
        return 1.0
    summation = sum(a**k / math.factorial(k) for k in range(servers))
    top = a**servers / math.factorial(servers) / (1 - rho)
    return top / (summation + top)


def mmc_expected_wait(servers: int, arrivals_per_hour: float, consult_minutes: float) -> dict:
    """Expected queueing delay (minutes) for a department modelled as M/M/c."""
    mu = 60.0 / max(consult_minutes, 1)  # patients/hour per doctor
    rho = arrivals_per_hour / (servers * mu) if servers else 1.0
    if servers <= 0 or rho >= 1:
        return {"utilization": round(min(rho, 9.99), 3), "p_wait": 1.0, "wq_minutes": None, "stable": False}
    pw = erlang_c(servers, arrivals_per_hour, mu)
    wq_hours = pw / (servers * mu - arrivals_per_hour)
    return {"utilization": round(rho, 3), "p_wait": round(pw, 3), "wq_minutes": round(wq_hours * 60, 1), "stable": True}


def peak_hourly_rate(times: list[datetime], default: float = 1.0) -> float:
    """Arrival rate λ (patients/hour) during the busiest clock hour — OPD arrivals are bursty, so the
    steady-state model is evaluated at peak load rather than the day's average."""
    if not times:
        return default
    per_hour: dict[int, int] = {}
    for t in times:
        per_hour[t.hour] = per_hour.get(t.hour, 0) + 1
    return float(max(per_hour.values()))


def priority_score(priority: int, waited_minutes: float, age: int | None, overdue_minutes: float = 0) -> tuple[float, list[dict]]:
    """Dynamic queue priority (higher is served first) with an explainable factor breakdown.

    Ageing (waiting time) prevents starvation of low-priority patients.
    """
    factors = [
        {"factor": "clinical priority", "value": priority, "points": (6 - priority) * 20},
        {"factor": "time waited (min)", "value": round(waited_minutes), "points": round(min(waited_minutes, 180) * 0.4, 1)},
    ]
    if age is not None and age >= 65:
        factors.append({"factor": "senior citizen", "value": age, "points": 10})
    if age is not None and age <= 5:
        factors.append({"factor": "young child", "value": age, "points": 8})
    if overdue_minutes > 0:
        factors.append({"factor": "past appointment time", "value": round(overdue_minutes), "points": round(min(overdue_minutes, 60) * 0.2, 1)})
    return round(sum(f["points"] for f in factors), 1), factors


def minutes_between(a: datetime | None, b: datetime) -> float:
    if not a:
        return 0.0
    return max((b - a).total_seconds() / 60.0, 0.0)
