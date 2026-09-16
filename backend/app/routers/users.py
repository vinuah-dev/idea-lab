"""User & access management (administrators) and self-service password change."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..database import get_db
from ..models import Staff, User
from ..security import ROLES, get_current_user, hash_password, password_problem, require_roles, verify_password
from ..services.activity import log_audit

router = APIRouter(prefix="/api", tags=["users & access"])


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=2)
    role: str
    password: str = Field(min_length=6)
    email: str | None = None
    staff_id: int | None = None
    patient_id: int | None = None


class UserPatch(BaseModel):
    full_name: str | None = None
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=6)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


def _out(u: User) -> dict:
    return ser.user(u) | {"active": u.active, "created_at": u.created_at.isoformat() if u.created_at else None}


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    return [_out(u) for u in db.scalars(select(User).order_by(User.role, User.username)).all()]


@router.post("/users")
def create_user(body: UserIn, db: Session = Depends(get_db), admin: User = Depends(require_roles("admin"))):
    if body.role not in ROLES:
        raise HTTPException(400, f"Role must be one of {', '.join(ROLES)}")
    if problem := password_problem(body.password):
        raise HTTPException(400, problem)
    username = body.username.strip().lower()
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, "Username already exists")
    dept = db.get(Staff, body.staff_id).department_id if body.staff_id and db.get(Staff, body.staff_id) else None
    u = User(username=username, full_name=body.full_name, role=body.role, password_hash=hash_password(body.password),
             email=body.email, staff_id=body.staff_id, patient_id=body.patient_id, department_id=dept)
    db.add(u)
    db.flush()
    log_audit(db, admin.full_name, "user", "create_user", "user", u.id, {"username": username, "role": body.role})
    db.commit()
    return _out(u)


@router.patch("/users/{uid}")
def patch_user(uid: int, body: UserPatch, db: Session = Depends(get_db), admin: User = Depends(require_roles("admin"))):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id and (body.active is False or (body.role and body.role != "admin")):
        raise HTTPException(400, "You cannot deactivate or demote your own account")
    if body.role and body.role not in ROLES:
        raise HTTPException(400, "Invalid role")
    if body.password and (problem := password_problem(body.password)):
        raise HTTPException(400, problem)
    changes = body.model_dump(exclude_none=True)
    for k in ("full_name", "role", "active"):
        if k in changes:
            setattr(u, k, changes[k])
    if body.password:
        u.password_hash = hash_password(body.password)
    log_audit(db, admin.full_name, "user", "update_user", "user", uid, {k: v for k, v in changes.items() if k != "password"} | ({"password": "reset"} if body.password else {}))
    db.commit()
    return _out(u)


@router.post("/auth/change-password")
def change_password(body: PasswordIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if problem := password_problem(body.new_password):
        raise HTTPException(400, problem)
    user.password_hash = hash_password(body.new_password)
    log_audit(db, user.full_name, "user", "change_password", "user", user.id)
    db.commit()
    return {"ok": True}
