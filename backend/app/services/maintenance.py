"""Predictive maintenance heuristic for medical equipment (synopsis future scope, implemented as a baseline).

Risk combines calendar age since last service and usage-hours progress through the service interval.
"""
from __future__ import annotations

from datetime import date, timedelta

# resource_type: (service interval days, service interval usage-hours)
INTERVALS = {
    "ventilator": (180, 2500), "mri": (90, 1500), "ct": (90, 2000), "xray": (180, 3000), "ultrasound": (180, 3000),
    "ecg": (365, 4000), "dialysis": (90, 1500), "defibrillator": (180, 1000), "infusion_pump": (365, 5000),
    "lab_analyzer": (60, 1500), "operating_room": (30, 600),
}


def maintenance_status(resource_type: str, last_maintenance: date | None, usage_hours: float) -> dict:
    days_int, hours_int = INTERVALS.get(resource_type, (180, 3000))
    since = (date.today() - last_maintenance).days if last_maintenance else days_int
    hour_progress = (usage_hours % hours_int) / hours_int
    risk = min(1.0, 0.65 * since / days_int + 0.35 * hour_progress)
    band = "high" if risk >= 0.85 else "medium" if risk >= 0.6 else "low"
    due = (last_maintenance or date.today()) + timedelta(days=days_int)
    return {"maintenance_risk": round(risk, 2), "maintenance_band": band, "maintenance_due": due.isoformat(),
            "maintenance_due_in_days": (due - date.today()).days}
