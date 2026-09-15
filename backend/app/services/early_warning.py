"""Ward early-warning monitoring: record observations, score NEWS2 and escalate per the NEWS2 response policy.

NEWS2 clinical response (RCP 2017):
  0        → minimum 12-hourly observations
  1–4      → 4–6-hourly; nurse assessment
  3 in any single parameter / 5–6 → hourly; urgent review by the ward doctor
  ≥7       → continuous monitoring; emergency response and consideration of critical-care transfer
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Admission, Patient, User, VitalSign
from .activity import log_audit, notify
from .settings_store import get_setting
from .triage import clinical_risk, compute_news2

FIELDS = ("hr", "rr", "spo2", "sbp", "dbp", "temp")


def monitoring_frequency(score: int, components: dict) -> tuple[str, int]:
    if score >= 7:
        return "continuous monitoring", 30
    if score >= 5 or any(v == 3 for v in components.values()):
        return "hourly", 60
    if score >= 1:
        return "every 4–6 hours", 360
    return "every 12 hours", 720


def latest_vitals(db: Session, patient_ids: list[int]) -> dict[int, VitalSign]:
    out: dict[int, VitalSign] = {}
    if not patient_ids:
        return out
    rows = db.scalars(select(VitalSign).where(VitalSign.patient_id.in_(patient_ids)).order_by(VitalSign.recorded_at)).all()
    for v in rows:
        out[v.patient_id] = v
    return out


def previous_vitals(db: Session, patient_id: int, before: datetime) -> VitalSign | None:
    return db.scalar(select(VitalSign).where(VitalSign.patient_id == patient_id, VitalSign.recorded_at < before)
                     .order_by(VitalSign.recorded_at.desc()).limit(1))


def record_vitals(db: Session, patient: Patient, vitals: dict, recorded_by: str, user: User | None = None) -> dict:
    """Store an observation set and apply the escalation policy. Caller commits and, if `request_id`
    is returned, starts the orchestrator in the background."""
    score, comps = compute_news2(vitals)
    risk = clinical_risk(score, comps)
    vs = VitalSign(patient_id=patient.id, news2=score, risk=risk, recorded_by=recorded_by,
                   consciousness=str(vitals.get("consciousness") or "A")[:1].upper(), on_oxygen=bool(vitals.get("on_oxygen")),
                   **{k: (float(vitals[k]) if vitals.get(k) not in (None, "") else None) for k in FIELDS})
    db.add(vs)
    db.flush()
    prev = previous_vitals(db, patient.id, vs.recorded_at)
    patient.risk_score = round(min(1.0, score / 12 + (0.15 if risk in ("medium", "high") else 0)), 2)
    freq_label, _ = monitoring_frequency(score, comps)
    adm = db.scalar(select(Admission).where(Admission.patient_id == patient.id, Admission.status == "active"))
    where = f"{adm.bed.code} ({adm.bed.ward.name})" if adm and adm.bed else "ward"
    escalation, request_id = None, None
    review_t = int(get_setting(db, "news2_review_threshold"))
    esc_t = int(get_setting(db, "news2_escalation_threshold"))
    link = f"/patients/{patient.id}"
    if score >= esc_t:
        escalation = "emergency_response"
        for role in ("doctor", "nurse"):
            notify(db, f"🚨 NEWS2 {score} — emergency response: {patient.name}",
                   f"{where}: HR {vitals.get('hr')}, RR {vitals.get('rr')}, SpO₂ {vitals.get('spo2')}%, SBP {vitals.get('sbp')}. "
                   "Continuous monitoring; consider critical-care transfer.", level="critical", category="deterioration", role=role, link=link)
        in_icu = adm is not None and adm.bed is not None and adm.bed.ward.ward_type == "icu"
        if adm and not in_icu and get_setting(db, "auto_icu_transfer_proposal"):
            from ..agents.orchestrator import orchestrator  # local import: avoids a cycle
            req = orchestrator.submit(db, f"Transfer {patient.name} to ICU — NEWS2 {score} deterioration in {where}", user,
                                      source="early-warning", patient_id=patient.id, forced_intents=["admission"],
                                      extra_entities={"bed_type": "icu"})
            request_id = req.id
    elif score >= review_t or any(v == 3 for v in comps.values()):
        escalation = "urgent_review"
        notify(db, f"Urgent review: NEWS2 {score} — {patient.name}", f"{where}. Hourly observations; ward doctor to review.",
               level="warning", category="deterioration", role="doctor", link=link)
    elif prev is not None and score - prev.news2 >= 2:
        escalation = "rising_trend"
        notify(db, f"Rising NEWS2 ({prev.news2} → {score}) — {patient.name}", f"{where}. Increase observation frequency.",
               level="info", category="deterioration", role="nurse", link=link)
    log_audit(db, recorded_by, "user" if user else "system", "record_vitals", "patient", patient.id,
              {"news2": score, "risk": risk, "escalation": escalation})
    return {"id": vs.id, "news2": score, "risk": risk, "components": comps, "monitoring": freq_label,
            "escalation": escalation, "request_id": request_id, "trend": (score - prev.news2) if prev else None}
