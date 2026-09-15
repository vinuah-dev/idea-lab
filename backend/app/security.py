"""Authentication (JWT) and Role-Based Access Control."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

ROLES = ("admin", "doctor", "nurse", "receptionist", "lab", "pharmacist", "patient")
STAFF_ROLES = ("admin", "doctor", "nurse", "receptionist", "lab", "pharmacist")
CLINICAL_ROLES = ("admin", "doctor", "nurse")

# Which roles may approve which categories of AI-proposed actions (human-in-the-loop policy).
APPROVER_ROLES: dict[str, tuple[str, ...]] = {
    "clinical": ("doctor", "admin"),
    "nursing": ("nurse", "doctor", "admin"),
    "pharmacy": ("pharmacist", "doctor", "admin"),
    "operations": ("admin", "nurse", "receptionist"),
    "staffing": ("admin",),
    "theatre": ("doctor", "admin"),
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_b64, digest_b64 = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user.id), "role": user.role, "name": user.full_name, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise unauthorized
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise unauthorized
    user = db.get(User, int(payload["sub"]))
    if not user or not user.active:
        raise unauthorized
    return user


def require_roles(*roles: str):
    """FastAPI dependency factory enforcing RBAC."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=f"Role '{user.role}' is not permitted for this action")
        return user

    return checker


def can_approve(user: User, required_roles: list[str]) -> bool:
    return user.role == "admin" or user.role in required_roles
