from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..database import get_db
from ..events import bus
from ..models import Admission, Bed, Resource, User, Ward
from ..security import STAFF_ROLES, require_roles
from ..services.activity import log_audit

router = APIRouter(prefix="/api", tags=["beds & resources"])

BED_TRANSITIONS = {
    "available": {"maintenance", "reserved", "cleaning"},
    "reserved": {"available"},
    "cleaning": {"available", "maintenance"},
    "maintenance": {"available", "cleaning"},
    "occupied": {"cleaning"},
}


class StatusPatch(BaseModel):
    status: str


@router.get("/wards")
def wards(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    return [ser.ward(w) for w in db.scalars(select(Ward).order_by(Ward.floor, Ward.id)).all()]


@router.get("/beds")
def beds(status: str | None = None, ward_type: str | None = None, db: Session = Depends(get_db),
         _: User = Depends(require_roles(*STAFF_ROLES))):
    stmt = select(Bed)
    if status:
        stmt = stmt.where(Bed.status == status)
    if ward_type:
        stmt = stmt.where(Bed.bed_type == ward_type)
    return [ser.bed(b) for b in db.scalars(stmt.order_by(Bed.code)).all()]


@router.patch("/beds/{bid}")
def patch_bed(bid: int, body: StatusPatch, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "nurse", "doctor"))):
    b = db.get(Bed, bid)
    if not b:
        raise HTTPException(404, "Bed not found")
    if body.status not in BED_TRANSITIONS.get(b.status, set()):
        raise HTTPException(400, f"Cannot move bed from {b.status} to {body.status}")
    if b.status == "occupied":
        adm = db.scalar(select(Admission).where(Admission.bed_id == b.id, Admission.status == "active"))
        if adm:
            raise HTTPException(400, "Bed has an active admission — discharge or transfer the patient first")
    old = b.status
    b.status = body.status
    if body.status in ("available", "cleaning", "maintenance"):
        b.patient_id = None
    b.updated_at = datetime.now()
    log_audit(db, user.full_name, "user", "bed_status", "bed", bid, {"from": old, "to": body.status, "code": b.code})
    db.commit()
    bus.publish("refresh", {"scope": ["beds"]})
    return ser.bed(b)


@router.get("/resources")
def resources(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    return [ser.resource(r) for r in db.scalars(select(Resource).order_by(Resource.resource_type, Resource.name)).all()]


@router.patch("/resources/{rid}")
def patch_resource(rid: int, body: StatusPatch, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "nurse", "lab", "doctor"))):
    r = db.get(Resource, rid)
    if not r:
        raise HTTPException(404, "Resource not found")
    if body.status not in ("available", "in_use", "maintenance"):
        raise HTTPException(400, "Invalid status")
    old = r.status
    r.status = body.status
    if body.status == "maintenance":
        r.last_maintenance = datetime.now().date()
    log_audit(db, user.full_name, "user", "resource_status", "resource", rid, {"from": old, "to": body.status, "name": r.name})
    db.commit()
    bus.publish("refresh", {"scope": ["resources"]})
    return ser.resource(r)
