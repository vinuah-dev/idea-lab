"""Pre-hospital coordination: 108 calls, live fleet, dispatch tracking and pre-arrival alerts."""
import random

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..agents.orchestrator import orchestrator
from ..database import get_db
from ..events import bus
from ..models import Ambulance, Dispatch, User
from ..security import STAFF_ROLES, require_roles
from ..services import dispatch as dsp
from ..services.activity import log_audit

router = APIRouter(prefix="/api/ambulance", tags=["pre-hospital"])
CONTROL = ("admin", "doctor", "nurse", "receptionist")


class CallIn(BaseModel):
    locality: str | None = None
    lat: float | None = None
    lng: float | None = None
    complaint: str = Field(default="", max_length=250)
    caller: str = ""
    vitals: dict = {}
    random_call: bool = False


@router.get("/fleet")
def fleet(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    ambs = db.scalars(select(Ambulance).order_by(Ambulance.code)).all()
    recent = db.scalars(select(Dispatch).where(Dispatch.status.in_(["arrived", "cancelled"])).order_by(Dispatch.created_at.desc()).limit(8)).all()
    active = db.scalars(select(Dispatch).where(Dispatch.status.in_(["to_scene", "on_scene", "to_hospital"])).order_by(Dispatch.created_at)).all()
    done = [d for d in db.scalars(select(Dispatch).where(Dispatch.status == "arrived")).all() if d.arrived_at and d.created_at]
    by: dict[str, int] = {}
    for a in ambs:
        by[a.status] = by.get(a.status, 0) + 1
    return {"hospital": dsp.HOSPITAL, "localities": [{"name": k, "lat": v[0], "lng": v[1]} for k, v in dsp.LOCALITIES.items()],
            "ambulances": [ser.ambulance(a) for a in ambs], "dispatches": [ser.dispatch(d) for d in active],
            "recent": [ser.dispatch(d) for d in recent], "scenarios": [c for c, _ in dsp.CALL_SCENARIOS],
            "stats": {"by_status": by, "active": len(active), "completed": len(done),
                      "avg_response_min": round(sum(d.eta_scene_min for d in done) / len(done), 1) if done else None,
                      "pre_alerted": sum(1 for d in done if d.request_id)}}


@router.post("/calls")
def new_call(body: CallIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*CONTROL))):
    """Register a 108 call. The Ambulance Dispatch Agent picks the unit through the orchestrator (auto-executes: time-critical)."""
    rng = random.Random()
    vitals = dict(body.vitals or {})
    complaint = body.complaint.strip()
    if body.random_call or not complaint:
        complaint, vitals = rng.choice(dsp.CALL_SCENARIOS)
    if body.lat is not None and body.lng is not None:
        locality, lat, lng = body.locality or "Caller location", body.lat, body.lng
    else:
        found = dsp.find_locality(body.locality or "") if body.locality else None
        if not found:
            if not body.random_call:
                raise HTTPException(400, "Unknown locality — pick one from the list or click on the map")
            name = rng.choice(list(dsp.LOCALITIES))
            found = (name, *dsp.LOCALITIES[name])
        locality, lat, lng = found
    text = f"108 call from {locality}: {complaint}. Send an ambulance."
    req = orchestrator.submit(db, text, user, source="108-call", forced_intents=["ambulance"],
                              extra_entities={"locality": locality, "pickup": {"lat": lat, "lng": lng, "label": locality},
                                              "chief_complaint": complaint, "vitals": vitals, "caller": body.caller or "108 control room"})
    orchestrator.run_in_background(req.id)
    return {"request_id": req.id, "locality": locality, "complaint": complaint}


@router.post("/dispatches/{did}/advance")
def advance(did: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*CONTROL))):
    d = db.get(Dispatch, did)
    if not d or d.status not in ("to_scene", "on_scene", "to_hospital"):
        raise HTTPException(400, "Dispatch is not active")
    rid = dsp.advance_stage(db, d)
    log_audit(db, user.full_name, "user", "dispatch_advance", "dispatch", did, {"status": d.status})
    db.commit()
    if rid:
        orchestrator.run_in_background(rid)
    bus.publish("fleet", dsp.fleet_payload(db))
    bus.publish("refresh", {"scope": ["ambulance", "emergency"]})
    return ser.dispatch(d)


@router.post("/dispatches/{did}/cancel")
def cancel(did: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*CONTROL))):
    d = db.get(Dispatch, did)
    if not d or d.status not in ("to_scene", "on_scene", "to_hospital"):
        raise HTTPException(400, "Dispatch is not active")
    d.status = "cancelled"
    d.ambulance.status = "returning"
    log_audit(db, user.full_name, "user", "dispatch_cancel", "dispatch", did)
    db.commit()
    bus.publish("fleet", dsp.fleet_payload(db))
    bus.publish("refresh", {"scope": ["ambulance"]})
    return ser.dispatch(d)
