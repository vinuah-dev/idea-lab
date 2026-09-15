from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..database import get_db
from ..events import bus
from ..models import Appointment, Department, Staff, User
from ..security import STAFF_ROLES, require_roles
from ..services.activity import log_audit
from ..services.queueing import minutes_between, mmc_expected_wait, peak_hourly_rate, priority_score

router = APIRouter(prefix="/api", tags=["appointments & queue"])


class AppointmentIn(BaseModel):
    patient_id: int
    doctor_id: int
    scheduled_at: datetime
    priority: int = 3
    reason: str = ""


@router.get("/departments")
def departments(db: Session = Depends(get_db)):
    return [ser.department(d) for d in db.scalars(select(Department).order_by(Department.name)).all()]


@router.get("/appointments")
def list_appointments(day: str | None = None, department_id: int | None = None, doctor_id: int | None = None,
                      status: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    start = datetime.fromisoformat(day) if day else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = select(Appointment).where(Appointment.scheduled_at >= start, Appointment.scheduled_at < start + timedelta(days=1))
    if department_id:
        stmt = stmt.where(Appointment.department_id == department_id)
    if doctor_id:
        stmt = stmt.where(Appointment.doctor_id == doctor_id)
    if status:
        stmt = stmt.where(Appointment.status == status)
    return [ser.appointment(a) for a in db.scalars(stmt.order_by(Appointment.scheduled_at)).all()]


@router.post("/appointments")
def create_appointment(body: AppointmentIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "receptionist", "doctor", "nurse"))):
    doc = db.get(Staff, body.doctor_id)
    if not doc or doc.role != "doctor":
        raise HTTPException(400, "Invalid doctor")
    clash = db.scalar(select(Appointment).where(Appointment.doctor_id == doc.id, Appointment.scheduled_at == body.scheduled_at,
                                                Appointment.status.not_in(["cancelled", "no_show"])))
    if clash:
        raise HTTPException(409, "Doctor already has an appointment at this time")
    day = body.scheduled_at.replace(hour=0, minute=0, second=0, microsecond=0)
    n = db.query(Appointment).filter(Appointment.doctor_id == doc.id, Appointment.scheduled_at >= day,
                                     Appointment.scheduled_at < day + timedelta(days=1)).count()
    a = Appointment(patient_id=body.patient_id, doctor_id=doc.id, department_id=doc.department_id, scheduled_at=body.scheduled_at,
                    priority=body.priority, reason=body.reason, queue_number=n + 1, booked_by=user.role)
    db.add(a)
    db.flush()
    log_audit(db, user.full_name, "user", "book_appointment", "appointment", a.id, {"doctor": doc.name})
    db.commit()
    bus.publish("refresh", {"scope": ["appointments"]})
    return ser.appointment(a)


TRANSITIONS = {
    "check_in": ({"scheduled"}, "checked_in"), "start": ({"checked_in"}, "in_progress"),
    "complete": ({"in_progress"}, "completed"), "cancel": ({"scheduled", "checked_in"}, "cancelled"),
    "no_show": ({"scheduled"}, "no_show"),
}


@router.post("/appointments/{aid}/{action}")
def appointment_action(aid: int, action: str, db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFF_ROLES))):
    a = db.get(Appointment, aid)
    if not a:
        raise HTTPException(404, "Appointment not found")
    if action not in TRANSITIONS:
        raise HTTPException(400, "Unknown action")
    allowed, new = TRANSITIONS[action]
    if a.status not in allowed:
        raise HTTPException(400, f"Cannot {action} an appointment that is {a.status}")
    now = datetime.now()
    a.status = new
    if new == "checked_in":
        a.checked_in_at = now
        a.patient.status = "waiting"
    elif new == "in_progress":
        a.started_at = now
        a.patient.status = "in_consultation"
    elif new == "completed":
        a.completed_at = now
        a.patient.status = "registered"
    log_audit(db, user.full_name, "user", f"appointment_{action}", "appointment", aid)
    db.commit()
    bus.publish("refresh", {"scope": ["appointments"]})
    return ser.appointment(a)


@router.get("/queue")
def queue(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    """Live OPD queues: dynamic priority ordering + per-patient ETA + M/M/c department metrics."""
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    appts = db.scalars(select(Appointment).where(Appointment.scheduled_at >= today, Appointment.scheduled_at < today + timedelta(days=1))).all()
    out = []
    for dept in db.scalars(select(Department).order_by(Department.name)).all():
        dept_appts = [a for a in appts if a.department_id == dept.id]
        if not dept_appts:
            continue
        doctors = {}
        for a in dept_appts:
            if a.status in ("checked_in", "in_progress"):
                doctors.setdefault(a.doctor_id, []).append(a)
        entries = []
        for doc_id, items in doctors.items():
            current = [a for a in items if a.status == "in_progress"]
            waiting = [a for a in items if a.status == "checked_in"]
            scored = []
            for a in waiting:
                waited = minutes_between(a.checked_in_at, now)
                overdue = max(0.0, (now - a.scheduled_at).total_seconds() / 60)
                score, factors = priority_score(a.priority, waited, a.patient.age, overdue)
                scored.append((score, factors, waited, a))
            scored.sort(key=lambda x: -x[0])
            remaining = 0.0
            if current:
                remaining = max(0.0, dept.avg_consult_minutes - minutes_between(current[0].started_at, now))
                entries.append(ser.appointment(current[0], {"eta_minutes": 0, "position": 0, "waited_minutes": round(minutes_between(current[0].checked_in_at, now))}))
            for i, (score, factors, waited, a) in enumerate(scored):
                entries.append(ser.appointment(a, {"eta_minutes": round(remaining + i * dept.avg_consult_minutes), "position": i + 1,
                                                   "priority_score": score, "factors": factors, "waited_minutes": round(waited)}))
        on_duty = db.query(Staff).filter(Staff.department_id == dept.id, Staff.role == "doctor", Staff.on_duty.is_(True)).count()
        mmc = mmc_expected_wait(max(on_duty, 1), peak_hourly_rate([a.scheduled_at for a in dept_appts]), dept.avg_consult_minutes)
        out.append({
            "department": ser.department(dept), "doctors_on_duty": on_duty, "queue": entries, "metrics": mmc,
            "waiting": sum(1 for e in entries if e["status"] == "checked_in"),
            "completed": sum(1 for a in dept_appts if a.status == "completed"), "booked": len(dept_appts),
        })
    out.sort(key=lambda d: -d["waiting"])
    return out
