"""ICU central monitor — live bedside telemetry with smart (persistence-filtered) alarms."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import require_roles
from ..services.activity import log_audit
from ..services.telemetry import LIMITS, PERSISTENCE, hub

router = APIRouter(prefix="/api/telemetry", tags=["ICU central monitor"])
CLINICAL = ("admin", "doctor", "nurse")


@router.get("")
def telemetry(_: User = Depends(require_roles(*CLINICAL))):
    data = hub.last if hub.last.get("ts") else hub.tick()
    return data | {"limits": {k: {"low": lo, "high": hi, "label": label, "unit": unit} for k, (lo, hi, label, unit) in LIMITS.items()},
                   "persistence": PERSISTENCE}


@router.post("/{pid}/ack")
def acknowledge(pid: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*CLINICAL))):
    hub.ack(pid)
    log_audit(db, user.full_name, "user", "alarm_ack", "patient", pid)
    db.commit()
    return {"ok": True}
