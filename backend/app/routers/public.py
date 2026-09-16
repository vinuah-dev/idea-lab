"""Unauthenticated endpoints for the OPD token display (waiting-room TV) and the self check-in kiosk.

Privacy by design: the display shows tokens and doctors only — never patient names. The kiosk needs the
MRN *and* the last four digits of the registered phone number, and repeated failures are rate-limited.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..events import bus
from ..models import Appointment, Department, Patient
from ..security import LoginGuard
from ..services.activity import log_audit

router = APIRouter(prefix="/api/public", tags=["public display & kiosk"])
kiosk_guard = LoginGuard()


def token(a: Appointment) -> str:
    code = a.department.code if a.department else "OPD"
    return f"{code}-{a.queue_number or a.id % 100:02d}"


def room(a: Appointment) -> str:
    return f"{a.department.code if a.department else 'OPD'}-{(a.doctor_id or 0) % 9 + 1}"


class CheckinIn(BaseModel):
    mrn: str = Field(min_length=3, max_length=20)
    phone_last4: str = Field(min_length=4, max_length=4)


@router.get("/queue")
def queue(db: Session = Depends(get_db)):
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    appts = db.scalars(select(Appointment).where(Appointment.scheduled_at >= today, Appointment.scheduled_at < today + timedelta(days=1),
                                                 Appointment.status.in_(["checked_in", "in_progress"]))).all()
    by_doc: dict[int, dict] = {}
    for a in appts:
        if not a.doctor:
            continue
        d = by_doc.setdefault(a.doctor_id, {"doctor": a.doctor.name, "department": a.department.name if a.department else "", "room": room(a),
                                            "now_serving": None, "started_at": None, "next": [], "waiting": 0})
        if a.status == "in_progress":
            if not d["started_at"] or (a.started_at and a.started_at.isoformat() > d["started_at"]):
                d["now_serving"], d["started_at"] = token(a), a.started_at.isoformat() if a.started_at else None
        else:
            d["waiting"] += 1
            d["next"].append((a.priority, a.checked_in_at or a.scheduled_at, token(a)))
    rows = []
    for d in by_doc.values():
        d["next"] = [t for _, _, t in sorted(d["next"])[:4]]
        rows.append(d)
    rows.sort(key=lambda r: (r["department"], r["doctor"]))
    recent = sorted((r for r in rows if r["started_at"]), key=lambda r: r["started_at"], reverse=True)[:3]
    return {"hospital": settings.hospital_name, "generated_at": now.isoformat(), "rows": rows,
            "announcements": [{"token": r["now_serving"], "room": r["room"], "doctor": r["doctor"], "at": r["started_at"]} for r in recent],
            "total_waiting": sum(r["waiting"] for r in rows)}


@router.post("/kiosk/checkin")
def kiosk_checkin(body: CheckinIn, request: Request, db: Session = Depends(get_db)):
    key = f"kiosk|{request.client.host if request.client else 'unknown'}"
    wait = kiosk_guard.locked_for(key)
    if wait:
        raise HTTPException(429, f"Too many attempts — please ask the reception desk (try again in {wait} s)")
    mrn = body.mrn.strip().upper()
    if not mrn.startswith("MRN-"):
        mrn = f"MRN-{mrn}"
    p = db.scalar(select(Patient).where(Patient.mrn == mrn))
    digits = "".join(ch for ch in (p.phone or "") if ch.isdigit()) if p else ""
    if not p or not digits.endswith(body.phone_last4):
        kiosk_guard.failure(key)
        raise HTTPException(404, "We could not match those details — please check your MRN and phone number")
    kiosk_guard.success(key)
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    a = db.scalar(select(Appointment).where(Appointment.patient_id == p.id, Appointment.scheduled_at >= today,
                                            Appointment.scheduled_at < today + timedelta(days=1),
                                            Appointment.status.in_(["scheduled", "checked_in"])).order_by(Appointment.scheduled_at))
    if not a:
        raise HTTPException(404, "No appointment found for today — please see the reception desk for a walk-in token")
    if a.status == "scheduled":
        a.status, a.checked_in_at = "checked_in", now
        p.status = "waiting"
        log_audit(db, "Self check-in kiosk", "system", "kiosk_checkin", "appointment", a.id, {"patient_id": p.id})
    ahead = db.query(Appointment).filter(Appointment.doctor_id == a.doctor_id, Appointment.status == "checked_in",
                                         Appointment.scheduled_at >= today, Appointment.id != a.id,
                                         Appointment.priority <= a.priority, Appointment.checked_in_at <= a.checked_in_at).count()
    busy = db.query(Appointment).filter(Appointment.doctor_id == a.doctor_id, Appointment.status == "in_progress").count()
    consult = a.department.avg_consult_minutes if a.department else 12
    db.commit()
    bus.publish("refresh", {"scope": ["appointments"]})
    first = p.name.split()[0]
    return {"greeting": f"Welcome, {first}", "token": token(a), "doctor": a.doctor.name if a.doctor else None,
            "department": a.department.name if a.department else None, "room": room(a), "scheduled_at": a.scheduled_at.isoformat(),
            "position": ahead + 1, "estimated_wait_minutes": (ahead + busy) * consult}
