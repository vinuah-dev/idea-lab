"""Conversational copilot: multi-turn, Hinglish-aware chat front-end to the multi-agent orchestrator.

* Hinglish normalisation ("ICU mein kitne bed khali hain?") before intent classification.
* Conversation memory: the last patient discussed (or the patient page the user is on) resolves pronouns
  such as "usko" / "him".
* Clarification: patient-level requests with no identifiable patient get a "Which patient?" question with
  fuzzy-matched suggestions instead of a failed workflow.
"""
from __future__ import annotations

import difflib
import re
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..agents.nlp import understand_local
from ..agents.orchestrator import orchestrator
from ..database import get_db
from ..models import Admission, AgentRequest, Patient, User
from ..security import STAFF_ROLES, can_approve, require_roles
from ..services.hinglish import normalize, resolve_pronoun

router = APIRouter(prefix="/api/copilot", tags=["copilot"])

NEEDS_PATIENT = {"discharge", "patient_status", "diagnostics"}
USES_CONTEXT = NEEDS_PATIENT | {"pharmacy", "appointment", "surgery", "billing"}
_CONV: dict[str, dict] = {}
_TTL = 6 * 3600
TERMINAL = {"completed", "awaiting_approval", "failed", "rejected"}


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=600)
    conversation_id: str | None = None
    patient_id: int | None = None  # the patient page the user is looking at, if any


def _conv(cid: str | None, user: User) -> tuple[str, dict]:
    now = time.time()
    for k in [k for k, v in _CONV.items() if now - v["updated"] > _TTL]:
        _CONV.pop(k, None)
    if cid and cid in _CONV and _CONV[cid]["user_id"] == user.id:
        conv = _CONV[cid]
    else:
        cid = uuid.uuid4().hex[:12]
        conv = {"user_id": user.id, "patient_id": None, "patient_name": None, "turns": 0, "updated": now}
        _CONV[cid] = conv
    conv["updated"] = now
    return cid, conv


def _suggest(db: Session, text: str) -> list[dict]:
    words = [w for w in re.findall(r"[A-Za-z]{3,}", text) if w.lower() not in {"the", "patient", "discharge", "where", "status", "order",
                                                                              "tests", "test", "what", "pending", "journey", "for", "and"}]
    admitted = db.scalars(select(Patient).where(Patient.status.in_(["admitted", "icu"]))).all()
    pool = {p.name.lower(): p for p in db.scalars(select(Patient)).all()}
    out: dict[int, Patient] = {}
    for w in words:
        for name in difflib.get_close_matches(w.lower(), [n.split()[0] for n in pool] + [n.split()[-1] for n in pool], n=4, cutoff=0.75):
            for full, p in pool.items():
                if name in full.split() and len(out) < 5:
                    out[p.id] = p
    if not out:
        out = {p.id: p for p in admitted[:4]}
    return [{"patient_id": p.id, "label": f"{p.name} · {p.mrn}", "status": p.status} for p in out.values()]


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFF_ROLES))):
    cid, conv = _conv(body.conversation_id, user)
    conv["turns"] += 1
    if body.patient_id:
        p = db.get(Patient, body.patient_id)
        if p:
            conv["patient_id"], conv["patient_name"] = p.id, p.name
    norm = normalize(body.message)
    text = resolve_pronoun(norm["text"], conv["patient_name"]) if norm["has_pronoun"] else norm["text"]
    patients = [(p.id, p.name, p.mrn) for p in db.scalars(select(Patient)).all()]
    local = understand_local(text, patients, [])
    intents = [i["name"] for i in local["intents"] if i["confidence"] >= 0.25] or [local["intents"][0]["name"]]
    named = local["entities"].get("patient_id") or (local["entities"].get("mrn") and True)
    patient_id, assumed = None, None
    if named:
        patient_id = local["entities"].get("patient_id")
    elif conv["patient_id"] and (norm["has_pronoun"] or set(intents) & USES_CONTEXT) and not set(intents) & {"emergency", "ambulance"}:
        patient_id, assumed = conv["patient_id"], conv["patient_name"]
    if not patient_id and set(intents) & NEEDS_PATIENT and not local["entities"].get("mrn"):
        return {"conversation_id": cid, "type": "clarify", "understood_as": text if norm["hinglish"] else None,
                "reply": "Which patient do you mean? Pick one below or include the name / MRN.", "options": _suggest(db, body.message),
                "pending_text": text}
    req = orchestrator.submit(db, text, user, source="copilot", patient_id=patient_id)
    orchestrator.run_in_background(req.id)
    if patient_id:
        p = db.get(Patient, patient_id)
        conv["patient_id"], conv["patient_name"] = p.id, p.name
    return {"conversation_id": cid, "type": "request", "request_id": req.id, "intents": intents,
            "understood_as": text if (norm["hinglish"] or norm["has_pronoun"]) else None, "hinglish": norm["hinglish"],
            "assumed_patient": assumed}


@router.get("/requests/{rid}")
def request_status(rid: int, conversation_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFF_ROLES))):
    r = db.get(AgentRequest, rid)
    if not r:
        raise HTTPException(404, "Request not found")
    if r.status in TERMINAL and r.patient_id and conversation_id in _CONV and _CONV[conversation_id]["user_id"] == user.id:
        p = db.get(Patient, r.patient_id)
        if p:
            _CONV[conversation_id]["patient_id"], _CONV[conversation_id]["patient_name"] = p.id, p.name
    patient = db.get(Patient, r.patient_id) if r.patient_id else None
    return {"id": r.id, "status": r.status, "summary": r.summary, "intents": r.intents or [], "done": r.status in TERMINAL,
            "patient": ser.patient_brief(patient), "duration_ms": r.duration_ms,
            "executed": [e["title"] for e in (r.results or {}).get("_executed", [])],
            "approvals": [ser.approval(a) | {"can_decide": can_approve(user, a.required_roles or []) and a.status == "pending"} for a in r.approvals]}


@router.get("/suggestions")
def suggestions(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    adm = db.scalar(select(Admission).where(Admission.status == "active").order_by(Admission.admitted_at))
    name = adm.patient.name if adm else "Rohan Mehta"
    return ["ICU mein kitne bed khali hain?", "Rohan Mehta ka bill kitna hua?", f"Where is {name} in the care journey?",
            "Usko kal subah 10 baje cardiology mein book karo", "Sitabuldi mein accident hua hai, ambulance bhejo",
            "What if ER arrivals increase by 50% for the next 3 days?", "60 saal ka aadmi, seene mein dard, BP 90/60, SpO2 91"]
