"""Responsible-AI governance: human-in-the-loop statistics, model cards, safety events and data-access oversight."""
from __future__ import annotations

import re
import statistics
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.nlp import model_card as nlp_card
from ..agents.orchestrator import AGENTS
from ..database import get_db
from ..models import AgentRequest, Approval, AuditLog, Prescription, User
from ..security import APPROVER_ROLES, require_roles
from ..services.los_model import model_card as los_card
from ..services.readmission import model_card as readmission_card
from ..services.settings_store import ALWAYS_REVIEW, AUTONOMY_MODES, TIME_CRITICAL, get_setting

router = APIRouter(prefix="/api/governance", tags=["AI governance"])


def _bucket() -> dict:
    return {"total": 0, "approved": 0, "modified": 0, "rejected": 0, "failed": 0, "pending": 0}


@router.get("")
def governance(db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "doctor"))):
    approvals = db.scalars(select(Approval)).all()
    by_action: dict[str, dict] = {}
    by_agent: dict[str, dict] = {}
    minutes, fields = [], {}
    totals = _bucket()
    for a in approvals:
        modified = bool(a.decision_note and "[modified:" in a.decision_note)
        key = ("approved" if a.status == "executed" else a.status) if a.status in ("executed", "rejected", "failed", "pending") else "pending"
        for b in (totals, by_action.setdefault(a.action_type, _bucket()), by_agent.setdefault(a.agent, _bucket())):
            b["total"] += 1
            b[key] += 1
            b["modified"] += modified
        if a.decided_at:
            minutes.append((a.decided_at - a.created_at).total_seconds() / 60)
        if modified:
            for f in re.findall(r"\[modified: ([^\]]+)\]", a.decision_note)[0].split(", "):
                fields[f] = fields.get(f, 0) + 1
    decided = totals["approved"] + totals["rejected"] + totals["failed"]
    reqs = db.scalars(select(AgentRequest).order_by(AgentRequest.created_at.desc()).limit(500)).all()
    auto = sum(len((r.results or {}).get("_executed", [])) for r in reqs)
    by_source: dict[str, int] = {}
    engines: dict[str, int] = {}
    for r in reqs:
        by_source[r.source] = by_source.get(r.source, 0) + 1
        engines[r.nlp_engine] = engines.get(r.nlp_engine, 0) + 1
    conf = [r.confidence for r in reqs if r.confidence]
    rx = db.scalars(select(Prescription)).all()
    contraindicated = [p for p in rx if any(al.get("severity") == "contraindicated" for al in p.alerts or [])]
    since = datetime.now() - timedelta(hours=24)
    views = db.scalars(select(AuditLog).where(AuditLog.action == "view_patient", AuditLog.timestamp >= since)).all()
    viewers: dict[str, int] = {}
    for v in views:
        viewers[v.actor] = viewers.get(v.actor, 0) + 1
    return {
        "hitl": {
            "totals": totals, "approval_rate": round(totals["approved"] / decided, 3) if decided else None,
            "modification_rate": round(totals["modified"] / max(totals["approved"], 1), 3) if totals["approved"] else None,
            "rejection_rate": round(totals["rejected"] / decided, 3) if decided else None,
            "median_decision_minutes": round(statistics.median(minutes), 1) if minutes else None,
            "auto_executed": auto, "held_for_approval": len(approvals),
            "autonomy_ratio": round(auto / (auto + len(approvals)), 3) if (auto + len(approvals)) else None,
            "by_action": by_action, "by_agent": by_agent, "modified_fields": fields,
        },
        "requests": {"total": len(reqs), "by_source": by_source, "nlp_engines": engines,
                     "mean_confidence": round(sum(conf) / len(conf), 3) if conf else None,
                     "low_confidence": sum(1 for c in conf if c < 0.5)},
        "safety": {"prescriptions_with_alerts": sum(1 for p in rx if p.alerts), "contraindicated_flagged": len(contraindicated),
                   "contraindicated_dispensed": sum(1 for p in contraindicated if p.status == "dispensed")},
        "privacy": {"record_views_24h": len(views), "top_viewers": sorted(({"actor": k, "views": v} for k, v in viewers.items()), key=lambda d: -d["views"])[:8]},
        "policy": {"autonomy_mode": get_setting(db, "autonomy_mode"), "modes": AUTONOMY_MODES, "always_review": sorted(ALWAYS_REVIEW),
                   "time_critical": sorted(TIME_CRITICAL), "approver_roles": {k: list(v) for k, v in APPROVER_ROLES.items()}},
        "models": {"intent_classifier": nlp_card(), "length_of_stay": los_card(), "readmission": readmission_card()},
        "agents": [a.info() for a in AGENTS.values()],
    }
