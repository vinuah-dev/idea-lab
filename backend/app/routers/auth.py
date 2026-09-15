from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..database import get_db
from ..models import User
from ..security import create_access_token, get_current_user, verify_password
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


def _login(db: Session, username: str, password: str) -> dict:
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if not user or not verify_password(password, user.password_hash) or not user.active:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    log_audit(db, user.full_name, "user", "login", "user", user.id)
    db.commit()
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": ser.user(user)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    return _login(db, body.username, body.password)


@router.post("/token", include_in_schema=True)
def token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 password flow (used by the Swagger 'Authorize' button)."""
    return _login(db, form.username, form.password)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return ser.user(user)


@router.get("/demo-accounts")
def demo_accounts():
    return DEMO_ACCOUNTS
