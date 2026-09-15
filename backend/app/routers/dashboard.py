from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..database import get_db
from ..models import (Admission, AgentRequest, Appointment, Approval, Bed, DailyStat, DiagnosticOrder, EmergencyCase,
                      Medication, Notification, Patient, Prescription, Staff, User, Ward)
from ..security import STAFF_ROLES, require_roles
from ..services.clinical import TEST_CATALOG
from ..services.ot_scheduler import day_surgeries
from .ward import census

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

PRIORITY_ORDER = {"stat": 0, "urgent": 1, "routine": 2}


@router.get("/mywork")
def mywork(db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFF_ROLES))):
    """Role-specific work list for the signed-in user (doctor / nurse / lab / pharmacy / reception / admin)."""
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    out: dict = {"role": user.role}
    if user.role in ("doctor", "admin", "nurse"):
        rows = census(db=db, doctor_id=user.staff_id if user.role == "doctor" else None, _=user)
        out["inpatients"] = rows[:12]
        out["overdue_obs"] = sum(1 for r in rows if r["obs_overdue"])
        out["high_news2"] = sum(1 for r in rows if (r["news2"] or 0) >= 5)
    if user.role in ("doctor", "admin"):
        surg = day_surgeries(db, today.date())
        out["surgeries"] = [ser.surgery(s) for s in surg if user.role == "admin" or s.surgeon_id == user.staff_id][:10]
    if user.role == "doctor" and user.staff_id:
        appts = db.scalars(select(Appointment).where(Appointment.doctor_id == user.staff_id, Appointment.scheduled_at >= today,
                                                     Appointment.scheduled_at < today + timedelta(days=1),
                                                     Appointment.status.in_(["scheduled", "checked_in", "in_progress"]))
                           .order_by(Appointment.scheduled_at)).all()
        out["opd"] = [ser.appointment(a) for a in appts][:10]
    if user.role == "lab":
        orders = db.scalars(select(DiagnosticOrder).where(DiagnosticOrder.status.not_in(["completed", "cancelled"]))).all()
        rows = []
        for o in orders:
            d = ser.diagnostic(o)
            d["tat_breach"] = (now - o.created_at).total_seconds() / 60 > TEST_CATALOG.get(o.test_code, {}).get("tat", 120)
            rows.append(d)
        rows.sort(key=lambda d: (PRIORITY_ORDER.get(d["priority"], 3), d["created_at"]))
        out["orders"] = rows[:12]
        out["tat_breaches"] = sum(1 for r in rows if r["tat_breach"])
    if user.role == "pharmacist":
        rx = db.scalars(select(Prescription).where(Prescription.status.in_(["pending", "verified"])).order_by(Prescription.created_at)).all()
        out["prescriptions"] = sorted([ser.prescription(r) for r in rx], key=lambda r: -len(r["alerts"]))[:12]
        out["low_stock"] = [ser.medication(m) for m in db.scalars(select(Medication).where(Medication.stock <= Medication.reorder_level)).all()]
    if user.role == "receptionist":
        waiting = db.scalars(select(Appointment).where(Appointment.status == "checked_in", Appointment.scheduled_at >= today)
                             .order_by(Appointment.checked_in_at)).all()
        out["waiting"] = [ser.appointment(a, {"waited_minutes": round((now - a.checked_in_at).total_seconds() / 60) if a.checked_in_at else 0})
                          for a in waiting][:15]
        out["registrations_today"] = db.query(Patient).filter(Patient.created_at >= today).count()
        out["upcoming"] = db.query(Appointment).filter(Appointment.status == "scheduled", Appointment.scheduled_at >= now,
                                                       Appointment.scheduled_at < today + timedelta(days=1)).count()
    return out


@router.get("")
def dashboard(db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFF_ROLES))):
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    beds = db.scalars(select(Bed)).all()
    wards = db.scalars(select(Ward)).all()
    by_status = {}
    for b in beds:
        by_status[b.status] = by_status.get(b.status, 0) + 1
    icu = [b for b in beds if b.bed_type == "icu"]
    inpatient = [b for b in beds if b.bed_type != "emergency"]
    er = db.scalars(select(EmergencyCase).where(EmergencyCase.status.in_(["triage", "awaiting_bed", "in_treatment"]))
                    .order_by(EmergencyCase.triage_level, EmergencyCase.created_at)).all()
    appts = db.scalars(select(Appointment).where(Appointment.scheduled_at >= today, Appointment.scheduled_at < today + timedelta(days=1))).all()
    waiting = [a for a in appts if a.status == "checked_in"]
    waits = [(now - a.checked_in_at).total_seconds() / 60 for a in waiting if a.checked_in_at]
    seen = [(a.started_at - a.checked_in_at).total_seconds() / 60 for a in appts if a.started_at and a.checked_in_at]
    staff = db.scalars(select(Staff).where(Staff.on_duty.is_(True))).all()
    stats = db.scalars(select(DailyStat).order_by(DailyStat.day.desc()).limit(30)).all()[::-1]
    pending_approvals = db.query(Approval).filter(Approval.status == "pending").count()
    my_approvals = sum(1 for a in db.scalars(select(Approval).where(Approval.status == "pending")).all()
                       if user.role == "admin" or user.role in (a.required_roles or []))
    alerts = db.scalars(select(Notification).where(Notification.level.in_(["critical", "warning"]))
                        .order_by(Notification.created_at.desc()).limit(8)).all()
    recent = db.scalars(select(AgentRequest).order_by(AgentRequest.created_at.desc()).limit(6)).all()
    adm_today = db.query(Admission).filter(Admission.admitted_at >= today).count()
    dis_today = db.query(Admission).filter(Admission.discharged_at >= today).count()
    return {
        "generated_at": now.isoformat(),
        "kpis": {
            "beds_total": len(inpatient),
            "beds_occupied": sum(1 for b in inpatient if b.status == "occupied"),
            "beds_available": sum(1 for b in inpatient if b.status == "available"),
            "occupancy": round(sum(1 for b in inpatient if b.status == "occupied") / max(len(inpatient), 1), 3),
            "icu_total": len(icu), "icu_available": sum(1 for b in icu if b.status == "available"),
            "ventilator_beds_free": sum(1 for b in beds if b.status == "available" and "ventilator" in (b.features or [])),
            "cleaning": by_status.get("cleaning", 0),
            "er_active": len(er), "er_critical": sum(1 for c in er if c.triage_level <= 2),
            "er_awaiting_bed": sum(1 for c in er if c.status == "awaiting_bed"),
            "opd_today": len(appts), "opd_waiting": len(waiting),
            "opd_avg_wait": round(sum(waits) / len(waits), 1) if waits else 0,
            "opd_avg_door_to_doctor": round(sum(seen) / len(seen), 1) if seen else 0,
            "doctors_on_duty": sum(1 for s in staff if s.role == "doctor"),
            "nurses_on_duty": sum(1 for s in staff if s.role == "nurse"),
            "pending_approvals": pending_approvals, "my_pending_approvals": my_approvals,
            "diagnostics_pending": db.query(DiagnosticOrder).filter(DiagnosticOrder.status.not_in(["completed", "cancelled"])).count(),
            "low_stock": db.query(Medication).filter(Medication.stock <= Medication.reorder_level).count(),
            "admissions_today": adm_today, "discharges_today": dis_today,
        },
        "wards": [ser.ward(w, include_beds=False) for w in wards],
        "emergency": [ser.emergency(c) for c in er[:6]],
        "alerts": [ser.notification(n) for n in alerts],
        "recent_requests": [ser.agent_request(r, full=False) for r in recent],
        "trend": [{"day": s.day.isoformat(), "admissions": s.admissions, "er_visits": s.er_visits, "occupancy": s.bed_occupancy,
                   "wait": s.avg_wait_minutes} for s in stats],
    }
