"""Hospital digital twin: Monte-Carlo 'what-if' simulation of the live hospital."""
from dataclasses import fields

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import STAFF_ROLES, require_roles
from ..services.digital_twin import PRESETS, Scenario, simulate, snapshot

router = APIRouter(prefix="/api/twin", tags=["digital twin"])


class ScenarioIn(BaseModel):
    horizon_hours: int = Field(72, ge=12, le=168)
    surge_pct: float = Field(0, ge=0, le=300)
    surge_start_hour: int = Field(0, ge=0)
    surge_duration_hours: int = Field(0, ge=0)
    mass_casualty_patients: int = Field(0, ge=0, le=80)
    mass_casualty_hour: int = Field(6, ge=0)
    closed_critical_beds: int = Field(0, ge=0, le=30)
    closed_general_beds: int = Field(0, ge=0, le=80)
    staff_absent_pct: float = Field(0, ge=0, le=80)
    extra_critical_beds: int = Field(0, ge=0, le=20)
    extra_general_beds: int = Field(0, ge=0, le=40)
    los_reduction_pct: float = Field(0, ge=0, le=40)
    discharge_lounge: bool = False
    fast_cleaning: bool = False
    defer_electives: bool = False
    replications: int = Field(30, ge=5, le=100)
    recommendations: bool = True


@router.get("/presets")
def presets(_: User = Depends(require_roles(*STAFF_ROLES))):
    return PRESETS


@router.get("/state")
def state(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    s = snapshot(db)
    return {"capacity": s.capacity, "occupied": {g: len(v) for g, v in s.occupied.items()}, "cleaning": s.cleaning,
            "ed_bays": s.ed_bays, "ed_in_workup": len(s.ed_in_workup), "ed_waiting": len(s.ed_waiting), "boarding": s.boarding,
            "ed_arrivals_per_day": round(s.ed_per_day, 1), "electives_per_day": round(s.electives_per_day, 1)}


@router.post("/simulate")
def run(body: ScenarioIn, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    names = {f.name for f in fields(Scenario)}
    sc = Scenario(**{k: v for k, v in body.model_dump().items() if k in names})
    return simulate(db, sc, body.replications, body.recommendations)
