from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..database import get_db
from ..events import bus
from ..models import Shift, Staff, User
from ..security import STAFF_ROLES, require_roles
from ..services.activity import log_audit

router = APIRouter(prefix="/api", tags=["staff"])


class StaffPatch(BaseModel):
    on_duty: bool | None = None
    max_patients: int | None = None


@router.get("/staff")
def list_staff(role: str | None = None, department_id: int | None = None, on_duty: bool | None = None,
               db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    stmt = select(Staff)
    if role:
        stmt = stmt.where(Staff.role == role)
    if department_id:
        stmt = stmt.where(Staff.department_id == department_id)
    if on_duty is not None:
        stmt = stmt.where(Staff.on_duty.is_(on_duty))
    return [ser.staff(s) for s in db.scalars(stmt.order_by(Staff.role, Staff.name)).all()]


@router.patch("/staff/{sid}")
def patch_staff(sid: int, body: StaffPatch, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    s = db.get(Staff, sid)
    if not s:
        raise HTTPException(404, "Staff not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    log_audit(db, user.full_name, "user", "update_staff", "staff", sid, body.model_dump(exclude_none=True))
    db.commit()
    bus.publish("refresh", {"scope": ["staff"]})
    return ser.staff(s)


@router.get("/shifts")
def shifts(start: date | None = None, days: int = 7, department_id: int | None = None, db: Session = Depends(get_db),
           _: User = Depends(require_roles(*STAFF_ROLES))):
    start = start or date.today()
    stmt = select(Shift).where(Shift.date >= start, Shift.date < start + timedelta(days=days))
    if department_id:
        stmt = stmt.where(Shift.department_id == department_id)
    rows = db.scalars(stmt).all()
    return [{"id": s.id, "staff_id": s.staff_id, "staff": s.staff.name, "role": s.staff.role, "date": s.date.isoformat(),
             "shift": s.shift_type, "department_id": s.department_id, "generated_by": s.generated_by} for s in rows]
