from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..database import get_db
from ..models import User
from ..security import create_access_token, get_current_user, login_guard, verify_password
from ..services.activity import log_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

DEMO_ACCOUNTS = [
    {"username": "admin", "password": "admin123", "role": "admin", "label": "Administrator"},
    {"username": "doctor", "password": "doctor123", "role": "doctor", "label": "Doctor (Cardiology)"},
    {"username": "er.doctor", "password": "doctor123", "role": "doctor", "label": "ER Doctor"},
    {"username": "nurse", "password": "nurse123", "role": "nurse", "label": "ICU Nurse"},
    {"username": "reception", "password": "reception123", "role": "receptionist", "label": "Reception"},
    {"username": "lab", "password": "lab123", "role": "lab", "label": "Lab Technician"},
    {"username": "pharmacist", "password": "pharma123", "role": "pharmacist", "label": "Pharmacist"},
    {"username": "patient", "password": "patient123", "role": "patient", "label": "Patient Portal"},
]


class LoginIn(BaseModel):
    username: str
    password: str


def _login(db: Session, username: str, password: str, client: str = "unknown") -> dict:
    uname = username.strip().lower()
    key = f"{uname}|{client}"
    wait = login_guard.locked_for(key)
    if wait:
        raise HTTPException(status_code=429, detail=f"Too many failed attempts — try again in {wait} s")
    user = db.scalar(select(User).where(User.username == uname))
    if not user or not verify_password(password, user.password_hash) or not user.active:
        left = login_guard.failure(key)
        log_audit(db, uname or "unknown", "user", "login_failed", "user", user.id if user else None, {"client": client})
        db.commit()
        if not left:
            raise HTTPException(status_code=429, detail="Too many failed attempts — sign-in locked for 5 minutes")
        raise HTTPException(status_code=401, detail="Invalid username or password" + (f" ({left} attempt(s) left)" if left <= 2 else ""))
    login_guard.success(key)
    log_audit(db, user.full_name, "user", "login", "user", user.id, {"client": client})
    db.commit()
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": ser.user(user)}


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    return _login(db, body.username, body.password, _client(request))


@router.post("/token", include_in_schema=True)
def token(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 password flow (used by the Swagger 'Authorize' button)."""
    return _login(db, form.username, form.password, _client(request))


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return ser.user(user)


@router.get("/demo-accounts")
def demo_accounts():
    return DEMO_ACCOUNTS
