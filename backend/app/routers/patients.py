from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..database import get_db
from ..events import bus
from ..models import (Admission, Appointment, CareTask, DiagnosticOrder, EmergencyCase, Patient, Prescription, Surgery, User)
from ..security import STAFF_ROLES, get_current_user, require_roles
from ..services.activity import log_audit

router = APIRouter(prefix="/api", tags=["patients"])


class PatientIn(BaseModel):
    name: str = Field(min_length=2)
    age: int = Field(ge=0, le=120)
    gender: str = "Male"
    phone: str | None = None
    blood_group: str | None = None
    allergies: list[str] = []
    conditions: list[str] = []


class PatientPatch(BaseModel):
    phone: str | None = None
    blood_group: str | None = None
    allergies: list[str] | None = None
    conditions: list[str] | None = None
    status: str | None = None


class TaskPatch(BaseModel):
    status: str


@router.get("/patients")
def list_patients(q: str | None = None, status: str | None = None, limit: int = 100, offset: int = 0,
                  db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    stmt = select(Patient)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Patient.name.ilike(like), Patient.mrn.ilike(like), Patient.phone.ilike(like)))
    if status:
        stmt = stmt.where(Patient.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Patient.risk_score.desc(), Patient.id.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": [ser.patient(p) for p in rows]}


@router.post("/patients")
def create_patient(body: PatientIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "receptionist", "doctor", "nurse"))):
    count = db.scalar(select(func.count(Patient.id))) or 0
    p = Patient(mrn=f"MRN-{1001 + count}", **body.model_dump())
    db.add(p)
    db.flush()
    log_audit(db, user.full_name, "user", "register_patient", "patient", p.id, {"name": p.name})
    db.commit()
    bus.publish("refresh", {"scope": ["patients"]})
    return ser.patient(p)


def _can_view(user: User, patient_id: int) -> None:
    if user.role == "patient" and user.patient_id != patient_id:
        raise HTTPException(403, "Patients can only view their own record")


@router.get("/patients/{pid}")
def patient_detail(pid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _can_view(user, pid)
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Patient not found")
    adms = db.scalars(select(Admission).where(Admission.patient_id == pid).order_by(Admission.admitted_at.desc())).all()
    appts = db.scalars(select(Appointment).where(Appointment.patient_id == pid).order_by(Appointment.scheduled_at.desc())).all()
    orders = db.scalars(select(DiagnosticOrder).where(DiagnosticOrder.patient_id == pid).order_by(DiagnosticOrder.created_at.desc())).all()
    rx = db.scalars(select(Prescription).where(Prescription.patient_id == pid).order_by(Prescription.created_at.desc())).all()
    er = db.scalars(select(EmergencyCase).where(EmergencyCase.patient_id == pid).order_by(EmergencyCase.created_at.desc())).all()
    tasks = db.scalars(select(CareTask).where(CareTask.patient_id == pid, CareTask.status != "cancelled")
                       .order_by(CareTask.created_at.desc(), CareTask.sequence)).all()
    # timeline across all modules
    tl = []
    for a in adms:
        tl.append({"ts": a.admitted_at.isoformat(), "kind": "admission", "title": f"Admitted to {a.bed.ward.name if a.bed else 'ward'} ({a.bed.code if a.bed else '-'})", "detail": a.reason})
        if a.discharged_at:
            tl.append({"ts": a.discharged_at.isoformat(), "kind": "discharge", "title": "Discharged", "detail": ""})
    for a in appts:
        tl.append({"ts": a.scheduled_at.isoformat(), "kind": "appointment", "title": f"OPD: {a.department.name if a.department else ''} with {a.doctor.name if a.doctor else '-'}", "detail": f"{a.status} — {a.reason}"})
    for o in orders:
        tl.append({"ts": o.created_at.isoformat(), "kind": "diagnostic", "title": f"{o.test_name} ({o.priority})", "detail": o.result or o.status})
    for r in rx:
        tl.append({"ts": r.created_at.isoformat(), "kind": "prescription", "title": f"{r.medication.name} {r.dose} {r.frequency}", "detail": r.status})
    for e in er:
        tl.append({"ts": e.created_at.isoformat(), "kind": "emergency", "title": f"ER triage L{e.triage_level} (NEWS2 {e.news2_score})", "detail": e.chief_complaint})
    tl.sort(key=lambda x: x["ts"], reverse=True)
    latest_pathway = tasks[0].pathway if tasks else None
    current = [t for t in tasks if t.pathway == latest_pathway and (not tasks[0].request_id or t.request_id == tasks[0].request_id)] if tasks else []
    current.sort(key=lambda t: t.sequence)
    ops = db.scalars(select(Surgery).where(Surgery.patient_id == pid).order_by(Surgery.scheduled_start.desc())).all()
    for s in ops:
        tl.append({"ts": s.scheduled_start.isoformat(), "kind": "surgery", "title": f"Surgery: {s.procedure} ({s.ot.name if s.ot else 'OT'})",
                   "detail": f"{s.status} — {s.surgeon.name if s.surgeon else ''}"})
    tl.sort(key=lambda x: x["ts"], reverse=True)
    active = next((a for a in adms if a.status == "active"), None)
    return {
        "patient": ser.patient(p),
        "active_admission_id": active.id if active else None,
        "surgeries": [ser.surgery(s) for s in ops],
        "admissions": [ser.admission(a) for a in adms],
        "appointments": [ser.appointment(a) for a in appts],
        "diagnostics": [ser.diagnostic(o) for o in orders],
        "prescriptions": [ser.prescription(r) for r in rx],
        "emergency": [ser.emergency(e) for e in er],
        "pathway": {"name": latest_pathway, "steps": [ser.care_task(t) for t in current],
                    "progress": round(100 * sum(1 for t in current if t.status == "done") / len(current)) if current else 0},
        "timeline": tl[:60],
    }


@router.patch("/patients/{pid}")
def patch_patient(pid: int, body: PatientPatch, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "receptionist", "doctor", "nurse"))):
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Patient not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    log_audit(db, user.full_name, "user", "update_patient", "patient", pid, body.model_dump(exclude_none=True))
    db.commit()
    return ser.patient(p)


@router.patch("/care-tasks/{tid}")
def patch_task(tid: int, body: TaskPatch, db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFF_ROLES))):
    t = db.get(CareTask, tid)
    if not t:
        raise HTTPException(404, "Task not found")
    t.status = body.status
    t.completed_at = datetime.now() if body.status == "done" else None
    log_audit(db, user.full_name, "user", "update_care_task", "care_task", tid, {"status": body.status, "title": t.title})
    db.commit()
    bus.publish("refresh", {"scope": ["patients"]})
    return ser.care_task(t)
