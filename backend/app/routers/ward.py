"""Inpatient census, bedside observations (NEWS2 early warning) and discharge summaries."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..agents.orchestrator import orchestrator
from ..config import settings
from ..database import get_db
from ..events import bus
from ..models import (Admission, Appointment, CareTask, DiagnosticOrder, Patient, Prescription, Surgery, User, VitalSign)
from ..security import STAFF_ROLES, get_current_user, require_roles
from ..services.early_warning import latest_vitals, monitoring_frequency, record_vitals
from ..services.los_model import predict_los
from ..services.triage import compute_news2

router = APIRouter(prefix="/api", tags=["ward & inpatients"])


class VitalsIn(BaseModel):
    hr: float | None = None
    rr: float | None = None
    spo2: float | None = None
    sbp: float | None = None
    dbp: float | None = None
    temp: float | None = None
    consciousness: str = "A"
    on_oxygen: bool = False


def _can_view(user: User, pid: int) -> None:
    if user.role == "patient" and user.patient_id != pid:
        raise HTTPException(403, "Patients can only view their own record")


@router.get("/patients/{pid}/vitals")
def get_vitals(pid: int, limit: int = 60, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _can_view(user, pid)
    rows = db.scalars(select(VitalSign).where(VitalSign.patient_id == pid).order_by(VitalSign.recorded_at.desc()).limit(limit)).all()
    return [ser.vital(v) for v in reversed(rows)]


@router.post("/patients/{pid}/vitals")
def post_vitals(pid: int, body: VitalsIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "doctor", "nurse"))):
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Patient not found")
    result = record_vitals(db, p, body.model_dump(), user.full_name, user)
    db.commit()
    if result["request_id"]:
        orchestrator.run_in_background(result["request_id"])
    bus.publish("refresh", {"scope": ["patients", "ward"]})
    return result


def _census_row(db: Session, a: Admission, vit: VitalSign | None, now: datetime) -> dict:
    row = ser.admission(a)
    row["patient"] = ser.patient_brief(a.patient) | {"allergies": a.patient.allergies or [], "risk_score": a.patient.risk_score}
    row["ward_type"] = a.bed.ward.ward_type if a.bed else None
    row["los_days"] = round((now - a.admitted_at).total_seconds() / 86400, 1)
    try:
        pred = predict_los(a.patient.age, row["ward_type"] or "general", a.acuity, len(a.patient.conditions or []), False)
    except Exception:  # model unavailable → keep census working
        pred = None
    row["predicted_los"] = pred
    if vit:
        _, comps = compute_news2(ser.vital(vit))
        label, minutes = monitoring_frequency(vit.news2, comps)
        row["vitals"] = ser.vital(vit)
        row["news2"] = vit.news2
        row["monitoring"] = label
        row["obs_overdue"] = (now - vit.recorded_at) > timedelta(minutes=minutes)
    else:
        row["vitals"], row["news2"], row["monitoring"], row["obs_overdue"] = None, None, "no observations", True
    row["discharge_due"] = bool(a.expected_discharge and a.expected_discharge <= now + timedelta(hours=24))
    return row


@router.get("/admissions")
def census(ward_type: str | None = None, doctor_id: int | None = None, db: Session = Depends(get_db),
           _: User = Depends(require_roles(*STAFF_ROLES))):
    now = datetime.now()
    rows = db.scalars(select(Admission).where(Admission.status == "active")).all()
    if ward_type:
        rows = [a for a in rows if a.bed and a.bed.ward.ward_type == ward_type]
    if doctor_id:
        rows = [a for a in rows if a.doctor_id == doctor_id]
    vit = latest_vitals(db, [a.patient_id for a in rows])
    out = [_census_row(db, a, vit.get(a.patient_id), now) for a in rows]
    out.sort(key=lambda r: (-(r["news2"] if r["news2"] is not None else -1), r["bed"] or ""))
    return out


@router.get("/admissions/{aid}/summary")
def discharge_summary(aid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = db.get(Admission, aid)
    if not a:
        raise HTTPException(404, "Admission not found")
    _can_view(user, a.patient_id)
    p = a.patient
    end = a.discharged_at or datetime.now()
    orders = db.scalars(select(DiagnosticOrder).where(DiagnosticOrder.patient_id == p.id, DiagnosticOrder.created_at >= a.admitted_at - timedelta(hours=12),
                                                      DiagnosticOrder.created_at <= end)).all()
    rx = db.scalars(select(Prescription).where(Prescription.patient_id == p.id, Prescription.status != "rejected")).all()
    ops = db.scalars(select(Surgery).where(Surgery.patient_id == p.id, Surgery.scheduled_start >= a.admitted_at - timedelta(days=1),
                                           Surgery.status != "cancelled")).all()
    vit = db.scalars(select(VitalSign).where(VitalSign.patient_id == p.id).order_by(VitalSign.recorded_at)).all()
    follow = db.scalar(select(Appointment).where(Appointment.patient_id == p.id, Appointment.scheduled_at >= end,
                                                 Appointment.status == "scheduled").order_by(Appointment.scheduled_at))
    tasks = db.scalars(select(CareTask).where(CareTask.patient_id == p.id, CareTask.status == "done")).all()
    los = round((end - a.admitted_at).total_seconds() / 86400, 1)
    abnormal = [o for o in orders if o.abnormal]
    narrative = (f"{p.name}, a {p.age}-year-old {p.gender.lower()}, was admitted on {a.admitted_at:%d %b %Y} to "
                 f"{a.bed.ward.name if a.bed else 'the ward'} under {a.doctor.name if a.doctor else 'the treating team'} with "
                 f"{a.reason.lower() or 'the presenting complaint'}. Length of stay {los} day(s). "
                 f"{len(orders)} investigation(s) were performed" + (f", {len(abnormal)} with abnormal findings reviewed by the team" if abnormal else "")
                 + (f"; procedure(s): {', '.join(s.procedure for s in ops)}" if ops else "") + ". "
                 + (f"Last recorded NEWS2 {vit[-1].news2} ({vit[-1].risk} risk). " if vit else "")
                 + ("Discharged in stable condition." if a.status == "discharged" else "Summary prepared ahead of planned discharge."))
    return {
        "hospital": settings.hospital_name, "generated_at": datetime.now().isoformat(),
        "patient": ser.patient(p), "admission": ser.admission(a), "los_days": los, "narrative": narrative,
        "investigations": [ser.diagnostic(o) for o in orders], "medications": [ser.prescription(r) for r in rx],
        "procedures": [ser.surgery(s) for s in ops], "vitals_first": ser.vital(vit[0]) if vit else None,
        "vitals_last": ser.vital(vit[-1]) if vit else None, "follow_up": ser.appointment(follow) if follow else None,
        "care_completed": [t.title for t in tasks][-10:],
        "advice": ["Take medicines exactly as prescribed; do not stop without medical advice.",
                   "Keep the follow-up appointment and bring this summary and all reports.",
                   "Return to the Emergency department immediately for chest pain, breathlessness, high fever, confusion, bleeding or fainting."],
    }
