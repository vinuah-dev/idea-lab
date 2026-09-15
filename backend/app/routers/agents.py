from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..agents.executor import ActionError, decide_approval
from ..agents.llm import llm
from ..agents.nlp import INTENTS
from ..agents.orchestrator import AGENTS, orchestrator
from ..config import settings
from ..database import get_db
from ..models import AgentRequest, Approval, User
from ..security import STAFF_ROLES, can_approve, require_roles

router = APIRouter(prefix="/api", tags=["AI agents"])

SCENARIOS = [
    {"title": "ICU admission (synopsis example)", "text": "Patient needs admission and requires ICU monitoring with ventilator support.", "tag": "admission"},
    {"title": "Chest-pain emergency", "text": "Emergency: 58 year old male with chest pain and sweating, BP 92/60, HR 124, SpO2 93%, RR 24", "tag": "emergency"},
    {"title": "Admission + diagnostics", "text": "Admit Rohan Mehta to the cardiac unit and order ECG, troponin and chest x-ray stat", "tag": "multi-intent"},
    {"title": "Book OPD appointment", "text": "Book an appointment with a cardiologist tomorrow at 11 am for Rohan Mehta", "tag": "appointment"},
    {"title": "Prescription safety", "text": "Prescribe amoxicillin 500 mg BD for Rohan Mehta", "tag": "pharmacy"},
    {"title": "Bed availability", "text": "How many ICU beds are available right now?", "tag": "bed query"},
    {"title": "Staff shortage", "text": "We need two more nurses in the ICU tonight", "tag": "staffing"},
    {"title": "Optimise roster", "text": "Generate an optimized staff roster for next week", "tag": "staffing"},
    {"title": "Global bed optimisation", "text": "Optimize bed allocation for all waiting patients and find bottlenecks", "tag": "optimization"},
    {"title": "Demand forecast", "text": "Forecast admissions and ICU demand for the next 14 days", "tag": "analytics"},
    {"title": "Pharmacy stock", "text": "Which medicines are running low? Check stock of insulin", "tag": "pharmacy"},
    {"title": "Schedule surgery", "text": "Schedule a laparoscopic cholecystectomy for Rohan Mehta tomorrow", "tag": "surgery"},
    {"title": "Optimise OT schedule", "text": "Optimize the operation theatre schedule for tomorrow to reduce overtime", "tag": "surgery"},
    {"title": "Patient journey", "text": "Where is Rohan Mehta in his care journey and what is pending?", "tag": "patient status"},
]


class RequestIn(BaseModel):
    text: str = Field(min_length=3, max_length=1000)
    patient_id: int | None = None


class DecisionIn(BaseModel):
    approve: bool
    note: str | None = None
    overrides: dict | None = None


@router.get("/agents")
def agents(_: User = Depends(require_roles(*STAFF_ROLES))):
    return {
        "agents": [a.info() for a in AGENTS.values()],
        "intents": INTENTS,
        "nlp": {"llm_enabled": llm.enabled, "model": settings.llm_model if llm.enabled else None, "last_error": llm.last_error,
                "local": "TF-IDF (word + char n-grams) + Logistic Regression"},
    }


@router.get("/agents/scenarios")
def scenarios():
    return SCENARIOS


@router.post("/agents/requests")
def submit(body: RequestIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFF_ROLES))):
    req = orchestrator.submit(db, body.text, user, source="console", patient_id=body.patient_id)
    orchestrator.run_in_background(req.id)
    return {"id": req.id, "status": req.status}


@router.get("/agents/requests")
def list_requests(limit: int = 30, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    rows = db.scalars(select(AgentRequest).order_by(AgentRequest.created_at.desc()).limit(limit)).all()
    return [ser.agent_request(r, full=False) for r in rows]


@router.get("/agents/requests/{rid}")
def get_request(rid: int, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    r = db.get(AgentRequest, rid)
    if not r:
        raise HTTPException(404, "Request not found")
    return ser.agent_request(r)


@router.get("/approvals")
def approvals(status: str | None = "pending", db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFF_ROLES))):
    stmt = select(Approval)
    if status:
        stmt = stmt.where(Approval.status == status)
    rows = db.scalars(stmt.order_by(Approval.created_at.desc()).limit(100)).all()
    out = []
    for a in rows:
        d = ser.approval(a)
        d["can_decide"] = can_approve(user, a.required_roles or []) and a.status == "pending"
        d["request_text"] = a.request.text if a.request else None
        if a.request and a.action_type in ("admit_patient", "assign_emergency"):
            cands = ((a.request.results or {}).get("bed.find_beds", {}).get("data", {}) or {}).get("candidates", [])
            d["alternatives"] = {"bed_id": [{"value": c["bed_id"], "label": f"{c['code']} — {c['ward']} (fit {c['fit_score']})"} for c in cands]}
            docs = ((a.request.results or {}).get("staff.find_staff", {}).get("data", {}) or {}).get("doctors", [])
            d["alternatives"]["doctor_id"] = [{"value": x["id"], "label": f"{x['name']} (load {x['load']}/{x['max']})"} for x in docs]
        out.append(d)
    return out


@router.post("/approvals/{aid}/decide")
def decide(aid: int, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFF_ROLES))):
    a = db.get(Approval, aid)
    if not a:
        raise HTTPException(404, "Approval not found")
    if not can_approve(user, a.required_roles or []):
        raise HTTPException(403, f"Only {', '.join(a.required_roles)} may decide this action")
    try:
        decide_approval(db, a, user, body.approve, body.note, body.overrides)
    except ActionError as exc:
        raise HTTPException(400, str(exc))
    return ser.approval(a)
