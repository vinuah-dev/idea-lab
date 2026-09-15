"""Notifications, analytics, audit log, system status, simulation and the patient portal."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..agents.llm import llm
from ..agents.optimization_agent import ResourceOptimizationAgent
from ..agents.orchestrator import AGENTS, orchestrator
from ..config import settings
from ..database import get_db
from ..events import bus
from ..models import (Admission, AgentRequest, Appointment, AuditLog, DailyStat, Department, DiagnosticOrder, Notification,
                      Patient, Prescription, Resource, Staff, User, Ward)
from ..security import STAFF_ROLES, get_current_user, require_roles
from ..services.forecasting import holt_winters_forecast
from ..services.los_model import model_card, predict_los
from ..services.settings_store import AUTONOMY_MODES, all_settings, set_setting
from ..services.queueing import mmc_expected_wait, peak_hourly_rate
from ..simulation import simulator

router = APIRouter(prefix="/api", tags=["insights & system"])


# ------------------------------------------------------------------ notifications
def _mine(user: User):
    return or_(Notification.user_id == user.id, Notification.role == user.role, (Notification.user_id.is_(None) & Notification.role.is_(None)))


@router.get("/notifications")
def notifications(limit: int = 50, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(Notification).where(_mine(user)).order_by(Notification.created_at.desc()).limit(limit)).all()
    unread = db.query(Notification).filter(_mine(user), Notification.read.is_(False)).count()
    return {"unread": unread, "items": [ser.notification(n) for n in rows]}


@router.post("/notifications/{nid}/read")
def read_one(nid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.get(Notification, nid)
    if n:
        n.read = True
        db.commit()
    return {"ok": True}


@router.post("/notifications/read-all")
def read_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    for n in db.scalars(select(Notification).where(_mine(user), Notification.read.is_(False))).all():
        n.read = True
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ analytics
@router.get("/analytics/history")
def history(days: int = 90, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    rows = db.scalars(select(DailyStat).order_by(DailyStat.day.desc()).limit(days)).all()[::-1]
    return [{"day": r.day.isoformat(), "admissions": r.admissions, "discharges": r.discharges, "er_visits": r.er_visits,
             "opd_visits": r.opd_visits, "surgeries": r.surgeries, "bed_occupancy": r.bed_occupancy,
             "icu_occupancy": r.icu_occupancy, "avg_wait_minutes": r.avg_wait_minutes} for r in rows]


@router.get("/analytics/forecast")
def forecast(metric: str = "admissions", horizon: int = 14, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    if metric not in ("admissions", "er_visits", "opd_visits", "bed_occupancy", "icu_occupancy", "avg_wait_minutes", "discharges"):
        raise HTTPException(400, "Unknown metric")
    rows = db.scalars(select(DailyStat).order_by(DailyStat.day)).all()
    series = [getattr(r, metric) for r in rows]
    fc = holt_winters_forecast(series, horizon=min(max(horizon, 1), 60))
    last = rows[-1].day
    hist = [{"day": r.day.isoformat(), "actual": getattr(r, metric), "fitted": fc.fitted[i]} for i, r in enumerate(rows)][-60:]
    future = [{"day": (last + timedelta(days=i + 1)).isoformat(), "forecast": fc.forecast[i], "lower": fc.lower[i], "upper": fc.upper[i]}
              for i in range(len(fc.forecast))]
    return {"metric": metric, "history": hist, "forecast": future, "params": fc.params, "mape": fc.mape}


@router.get("/analytics/utilization")
def utilization(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    wards = [ser.ward(w, include_beds=False) for w in db.scalars(select(Ward)).all()]
    res: dict[str, dict] = {}
    for r in db.scalars(select(Resource)).all():
        d = res.setdefault(r.resource_type, {"type": r.resource_type, "total": 0, "in_use": 0, "available": 0, "maintenance": 0})
        d["total"] += 1
        d[r.status] += 1
    staff: dict[str, dict] = {}
    for s in db.scalars(select(Staff).where(Staff.role.in_(["doctor", "nurse"]))).all():
        dept = s.department.name if s.department else "—"
        d = staff.setdefault(dept, {"department": dept, "doctors": 0, "nurses": 0, "load": 0, "capacity": 0, "on_duty": 0})
        d["doctors" if s.role == "doctor" else "nurses"] += 1
        if s.on_duty:
            d["on_duty"] += 1
            d["load"] += s.current_load
            d["capacity"] += s.max_patients
    for d in staff.values():
        d["utilization"] = round(d["load"] / d["capacity"], 3) if d["capacity"] else 0
    return {"wards": wards, "resources": list(res.values()), "staff": sorted(staff.values(), key=lambda d: -d["utilization"])}


@router.get("/analytics/wait-times")
def wait_times(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    for d in db.scalars(select(Department)).all():
        appts = db.scalars(select(Appointment).where(Appointment.department_id == d.id, Appointment.scheduled_at >= today)).all()
        if not appts:
            continue
        waits = [(a.started_at - a.checked_in_at).total_seconds() / 60 for a in appts if a.started_at and a.checked_in_at]
        docs = db.query(Staff).filter(Staff.department_id == d.id, Staff.role == "doctor", Staff.on_duty.is_(True)).count()
        lam = peak_hourly_rate([a.scheduled_at for a in appts])
        out.append({"department": d.name, "observed_avg_wait": round(sum(waits) / len(waits), 1) if waits else None,
                    "patients": len(appts), "doctors": docs, "peak_arrivals_per_hour": lam,
                    **mmc_expected_wait(max(docs, 1), lam, d.avg_consult_minutes)})
    return sorted(out, key=lambda r: -(r["observed_avg_wait"] or 0))


@router.get("/analytics/bottlenecks")
def bottlenecks(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    res = ResourceOptimizationAgent().act_bottlenecks(SimpleNamespace(db=db))
    return res.data["bottlenecks"]


@router.get("/analytics/agents")
def agent_metrics(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    reqs = db.scalars(select(AgentRequest).order_by(AgentRequest.created_at.desc()).limit(200)).all()
    by_intent: dict[str, int] = {}
    for r in reqs:
        for i in r.intents or []:
            by_intent[i["name"]] = by_intent.get(i["name"], 0) + 1
    by_status: dict[str, int] = {}
    for r in reqs:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    durations = [r.duration_ms for r in reqs if r.duration_ms]
    return {"requests": len(reqs), "by_intent": by_intent, "by_status": by_status,
            "avg_duration_ms": round(sum(durations) / len(durations)) if durations else 0,
            "agents": [a.info() for a in AGENTS.values()]}


@router.get("/analytics/los-model")
def los_model(_: User = Depends(require_roles(*STAFF_ROLES))):
    return model_card()


class LosIn(BaseModel):
    age: int
    ward_type: str = "general"
    acuity: str = "moderate"
    comorbidities: int = 0
    emergency: bool = False


@router.post("/analytics/los-predict")
def los_predict(body: LosIn, _: User = Depends(require_roles(*STAFF_ROLES))):
    return predict_los(body.age, body.ward_type, body.acuity, body.comorbidities, body.emergency)


# ------------------------------------------------------------------ global search
@router.get("/search")
def search(q: str, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    q = q.strip()
    if len(q) < 2:
        return []
    like = f"%{q}%"
    out = []
    for p in db.scalars(select(Patient).where(or_(Patient.name.ilike(like), Patient.mrn.ilike(like))).limit(6)).all():
        out.append({"type": "patient", "label": p.name, "sub": f"{p.mrn} · {p.age}{p.gender[:1]} · {p.status}", "link": f"/patients/{p.id}"})
    for s in db.scalars(select(Staff).where(Staff.name.ilike(like)).limit(4)).all():
        out.append({"type": "staff", "label": s.name, "sub": f"{s.role} · {s.department.name if s.department else ''}", "link": "/staff"})
    from ..models import Bed, Medication
    for b in db.scalars(select(Bed).where(Bed.code.ilike(like)).limit(4)).all():
        out.append({"type": "bed", "label": b.code, "sub": f"{b.ward.name} · {b.status}", "link": "/beds"})
    for m in db.scalars(select(Medication).where(or_(Medication.name.ilike(like), Medication.generic.ilike(like))).limit(4)).all():
        out.append({"type": "medicine", "label": f"{m.name} {m.strength}", "sub": f"stock {m.stock}", "link": "/pharmacy"})
    return out


# ------------------------------------------------------------------ settings (HITL policy)
class SettingsIn(BaseModel):
    values: dict


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    return {"values": all_settings(db), "autonomy_modes": AUTONOMY_MODES}


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    try:
        for k, v in body.values.items():
            set_setting(db, k, v)
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    from ..services.activity import log_audit
    log_audit(db, user.full_name, "user", "update_settings", "settings", None, body.values)
    db.commit()
    bus.publish("refresh", {"scope": ["settings"]})
    return {"values": all_settings(db), "autonomy_modes": AUTONOMY_MODES}


# ------------------------------------------------------------------ audit
@router.get("/audit")
def audit(limit: int = 200, actor_type: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    stmt = select(AuditLog)
    if actor_type:
        stmt = stmt.where(AuditLog.actor_type == actor_type)
    return [ser.audit(a) for a in db.scalars(stmt.order_by(AuditLog.timestamp.desc()).limit(limit)).all()]


# ------------------------------------------------------------------ system & simulation
@router.get("/system/status")
def system_status():
    return {"app": settings.app_name, "hospital": settings.hospital_name, "version": "1.0.0",
            "database": "PostgreSQL" if settings.database_url.startswith("postgres") else "SQLite",
            "llm": {"enabled": llm.enabled, "model": settings.llm_model if llm.enabled else None, "last_error": llm.last_error},
            "agents": len(AGENTS), "websocket_clients": bus.count, "simulation": simulator.running}


@router.post("/system/reset")
def reset(_: User = Depends(require_roles("admin"))):
    from ..seed import reset_and_seed
    simulator.stop()
    reset_and_seed()
    bus.publish("refresh", {"scope": ["all"]})
    return {"ok": True}


@router.get("/simulation")
def sim_status(_: User = Depends(require_roles(*STAFF_ROLES))):
    return simulator.status()


@router.post("/simulation/{action}")
def sim_action(action: str, _: User = Depends(require_roles("admin"))):
    if action == "start":
        simulator.start()
    elif action == "stop":
        simulator.stop()
    elif action == "tick":
        simulator.tick()
    elif action == "emergency":
        from ..database import SessionLocal
        import random
        db = SessionLocal()
        try:
            simulator.emergency_arrival(db, random.Random())
        finally:
            db.close()
    else:
        raise HTTPException(400, "Unknown action")
    return simulator.status()


# ------------------------------------------------------------------ patient portal
class PortalBooking(BaseModel):
    department: str
    preferred: datetime | None = None
    reason: str = ""


@router.get("/portal/me")
def portal(db: Session = Depends(get_db), user: User = Depends(require_roles("patient"))):
    p = db.get(Patient, user.patient_id)
    if not p:
        raise HTTPException(404, "No patient record linked to this account")
    appts = db.scalars(select(Appointment).where(Appointment.patient_id == p.id).order_by(Appointment.scheduled_at.desc())).all()
    orders = db.scalars(select(DiagnosticOrder).where(DiagnosticOrder.patient_id == p.id).order_by(DiagnosticOrder.created_at.desc())).all()
    rx = db.scalars(select(Prescription).where(Prescription.patient_id == p.id).order_by(Prescription.created_at.desc())).all()
    adm = db.scalar(select(Admission).where(Admission.patient_id == p.id, Admission.status == "active"))
    now = datetime.now()
    return {"patient": ser.patient(p), "admission": ser.admission(adm) if adm else None,
            "upcoming": [ser.appointment(a) for a in appts if a.scheduled_at >= now - timedelta(hours=2) and a.status in ("scheduled", "checked_in")],
            "past": [ser.appointment(a) for a in appts if a.status == "completed"][:10],
            "reports": [ser.diagnostic(o) for o in orders], "prescriptions": [ser.prescription(r) for r in rx]}


@router.post("/portal/appointments")
def portal_book(body: PortalBooking, db: Session = Depends(get_db), user: User = Depends(require_roles("patient"))):
    p = db.get(Patient, user.patient_id)
    when = f" on {body.preferred:%A %d %B at %I:%M %p}" if body.preferred else " at the earliest slot"
    text = f"Book an appointment in {body.department} for {p.name}{when}. Reason: {body.reason or 'consultation'}"
    extra = {"department": body.department}
    if body.preferred:
        extra["datetime"] = body.preferred.isoformat()
    req = orchestrator.submit(db, text, user, source="portal", patient_id=p.id, forced_intents=["appointment"], extra_entities=extra)
    orchestrator.run_in_background(req.id)
    return {"request_id": req.id}


@router.get("/portal/requests/{rid}")
def portal_request(rid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("patient"))):
    r = db.get(AgentRequest, rid)
    if not r or r.submitted_by != user.id:
        raise HTTPException(404, "Request not found")
    return {"id": r.id, "status": r.status, "summary": r.summary}
