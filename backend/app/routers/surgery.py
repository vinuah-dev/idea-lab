"""Operating-theatre scheduling endpoints."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..agents.executor import ActionError, apply_ot_schedule, book_surgery
from ..database import get_db
from ..events import bus
from ..models import Patient, Staff, Surgery, User
from ..security import STAFF_ROLES, require_roles
from ..services.activity import log_audit
from ..services.ot_scheduler import PROCEDURES, day_surgeries, find_slots, operating_rooms, optimize_day

router = APIRouter(prefix="/api", tags=["operation theatres"])


class SurgeryIn(BaseModel):
    patient_id: int
    procedure_key: str | None = None
    procedure: str | None = None
    surgeon_id: int | None = None
    priority: str = "elective"
    duration_minutes: int | None = None
    day: date | None = None
    ot_id: int | None = None
    scheduled_start: datetime | None = None
    notes: str = ""


class ApplyIn(BaseModel):
    assignments: list[dict]


@router.get("/ot/procedures")
def procedures():
    return [{"key": k, **{kk: v for kk, v in p.items() if kk != "keywords"}} for k, p in PROCEDURES.items()]


@router.get("/surgeries")
def surgeries(day: date | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    day = day or date.today()
    rows = day_surgeries(db, day)
    return {"day": day.isoformat(), "theatres": [ser.resource(r) for r in operating_rooms(db, include_maintenance=True)],
            "surgeries": [ser.surgery(s) for s in rows]}


@router.get("/ot/slots")
def slots(duration: int = 60, surgeon_id: int | None = None, priority: str = "elective", day: date | None = None,
          db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    return find_slots(db, day or date.today(), duration, surgeon_id, priority)


@router.post("/surgeries")
def create_surgery(body: SurgeryIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "doctor"))):
    if not db.get(Patient, body.patient_id):
        raise HTTPException(404, "Patient not found")
    meta = PROCEDURES.get(body.procedure_key or "", {})
    name = body.procedure or meta.get("name")
    if not name:
        raise HTTPException(400, "Procedure required")
    duration = body.duration_minutes or meta.get("duration", 60)
    surgeon = db.get(Staff, body.surgeon_id) if body.surgeon_id else None
    if body.ot_id and body.scheduled_start:
        ot_id, start = body.ot_id, body.scheduled_start
        ok = find_slots(db, start.date(), duration, surgeon.id if surgeon else None, body.priority, earliest=start, top=10)
        if not any(o["ot_id"] == ot_id and o["start"][:16] == start.isoformat()[:16] for o in ok):
            raise HTTPException(409, "That theatre / surgeon is not free at the requested time")
    else:
        opts = find_slots(db, body.day or date.today(), duration, surgeon.id if surgeon else None, body.priority)
        if not opts:
            raise HTTPException(409, "No feasible theatre slot on that day — try another day or priority")
        ot_id, start = opts[0]["ot_id"], datetime.fromisoformat(opts[0]["start"])
    try:
        res = book_surgery(db, {"patient_id": body.patient_id, "surgeon_id": surgeon.id if surgeon else None, "ot_id": ot_id,
                                "procedure": name, "specialty": meta.get("specialty", surgeon.specialization if surgeon else "General Surgery"),
                                "priority": body.priority, "scheduled_start": start.isoformat(), "duration_minutes": duration,
                                "anaesthesia": meta.get("anaesthesia", "GA"), "notes": body.notes, "created_by": user.full_name})
    except ActionError as exc:
        raise HTTPException(409, str(exc))
    log_audit(db, user.full_name, "user", "book_surgery", "surgery", res["surgery_id"], {"procedure": name})
    db.commit()
    bus.publish("refresh", {"scope": ["surgeries"]})
    return ser.surgery(db.get(Surgery, res["surgery_id"]))


@router.post("/surgeries/{sid}/{action}")
def surgery_action(sid: int, action: str, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "doctor", "nurse"))):
    s = db.get(Surgery, sid)
    if not s:
        raise HTTPException(404, "Surgery not found")
    flow = {"start": ("scheduled", "in_progress"), "complete": ("in_progress", "completed"), "cancel": ("scheduled", "cancelled")}
    if action not in flow or s.status != flow[action][0]:
        raise HTTPException(400, f"Cannot {action} a surgery that is {s.status}")
    s.status = flow[action][1]
    now = datetime.now()
    if action == "start":
        s.started_at = now
        if s.ot:
            s.ot.status = "in_use"
    elif action == "complete":
        s.completed_at = now
        if s.ot:
            s.ot.status = "available"
            s.ot.usage_hours += round((now - (s.started_at or now)).total_seconds() / 3600, 2)
    log_audit(db, user.full_name, "user", f"surgery_{action}", "surgery", sid, {"procedure": s.procedure})
    db.commit()
    bus.publish("refresh", {"scope": ["surgeries", "resources"]})
    return ser.surgery(s)


@router.post("/ot/optimize")
def optimize(day: date | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "doctor"))):
    return optimize_day(db, day or date.today())


@router.post("/ot/optimize/apply")
def apply(body: ApplyIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "doctor"))):
    res = apply_ot_schedule(db, {"assignments": body.assignments})
    log_audit(db, user.full_name, "user", "apply_ot_schedule", "surgery", None, res)
    db.commit()
    bus.publish("refresh", {"scope": ["surgeries"]})
    return res
