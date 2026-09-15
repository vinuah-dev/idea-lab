"""Diagnostic Coordination Agent — maps investigations to modalities, schedules slots and tracks turnaround."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from ..models import DiagnosticOrder, Resource
from ..services.clinical import TEST_CATALOG, match_protocols
from .base import AgentContext, AgentResult, BaseAgent, ProposedAction, Recommendation


def schedule_slot(db, modality: str, priority: str, now: datetime | None = None) -> dict:
    """Earliest slot on the least-loaded available machine of a modality."""
    now = now or datetime.now()
    machines = db.scalars(select(Resource).where(Resource.resource_type == modality, Resource.status != "maintenance")).all()
    if not machines:
        return {"resource_id": None, "resource": None, "scheduled_at": None, "queue": 0}
    best = None
    for mch in machines:
        queue = db.query(DiagnosticOrder).filter(DiagnosticOrder.resource_id == mch.id,
                                                  DiagnosticOrder.status.in_(["ordered", "scheduled", "in_progress"])).count()
        free_at = max(now, mch.next_free_at or now) if mch.status == "in_use" else now
        per_slot = {"mri": 45, "ct": 20, "xray": 10, "ultrasound": 20, "ecg": 10}.get(modality, 5)
        wait = 0 if priority == "stat" else queue * per_slot * (0.5 if priority == "urgent" else 1)
        slot = free_at + timedelta(minutes=wait)
        if best is None or slot < best[1]:
            best = (mch, slot, queue)
    mch, slot, queue = best
    return {"resource_id": mch.id, "resource": mch.name, "scheduled_at": slot.replace(second=0, microsecond=0).isoformat(), "queue": queue}


class DiagnosticCoordinationAgent(BaseAgent):
    key = "diagnostic"
    name = "Diagnostic Coordination Agent"
    description = "Coordinates lab and imaging: protocol-based workup suggestions, modality scheduling and result tracking."
    capabilities = ["test ordering", "protocol workup suggestion", "modality scheduling", "turnaround tracking", "result routing"]
    icon = "microscope"
    color = "amber"

    def act_plan_tests(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        explicit = list(dict.fromkeys(ctx.entities.get("tests", [])))
        triage = ctx.blackboard.get("triage")
        suggested: list[str] = []
        protocol_name = None
        if triage or "admission" in ctx.intents or "emergency" in ctx.intents:
            protos = match_protocols(ctx.request.text + " " + (ctx.entities.get("chief_complaint") or ""))
            if protos:
                protocol_name = protos[0]["name"]
                suggested = [t for t in protos[0]["tests"] if t not in explicit]
        if not explicit and not suggested:
            return AgentResult(agent=self.key, status="skipped", summary="No investigations requested or indicated by protocol.")
        urgency = ctx.entities.get("urgency")
        if triage and triage["triage_level"] <= 2:
            priority = "stat"
        elif urgency in ("stat", "urgent"):
            priority = urgency
        else:
            priority = "routine"
        planned = []
        for code, source in [(c, "requested") for c in explicit] + [(c, "protocol") for c in suggested]:
            meta = TEST_CATALOG.get(code)
            if not meta:
                continue
            slot = schedule_slot(db, meta["modality"], priority)
            planned.append({"code": code, "name": meta["name"], "category": meta["category"], "priority": priority,
                            "source": source, "tat_minutes": meta["tat"], **slot})
        ctx.post(self.key, "diagnostic_plan", planned)
        ordered_by = ctx.user.staff_id if ctx.user and ctx.user.staff_id else None
        is_prescriber = ctx.requester_role in ("doctor", "admin")
        actions = []
        requested = [p for p in planned if p["source"] == "requested"]
        proto = [p for p in planned if p["source"] == "protocol"]
        if requested:
            actions.append(ProposedAction(
                action_type="create_diagnostic_orders", title=f"Order {', '.join(p['code'] for p in requested)} ({priority})",
                payload={"patient_id": ctx.patient.id if ctx.patient else None, "orders": requested, "ordered_by_id": ordered_by},
                risk="low", category="clinical", requires_approval=not is_prescriber,
                rationale=["Explicitly requested by " + ctx.requester_name]
                          + ([] if is_prescriber else ["Requester is not a prescriber → doctor must countersign"]),
            ))
        if proto:
            actions.append(ProposedAction(
                action_type="create_diagnostic_orders", title=f"Suggested workup: {', '.join(p['code'] for p in proto)}",
                payload={"patient_id": ctx.patient.id if ctx.patient else None, "orders": proto, "ordered_by_id": ordered_by},
                risk="medium", category="clinical", requires_approval=True,
                rationale=[f"Matched {protocol_name}", "AI-suggested investigations always require clinician review"],
                description="Protocol-based decision support; the treating clinician decides which tests are appropriate.",
            ))
        recs = [Recommendation(f"{p['name']} ({p['code']})", f"{p['resource'] or 'Lab'} at {p['scheduled_at'][11:16] if p['scheduled_at'] else '—'}, "
                               f"TAT ~{p['tat_minutes']} min, {p['source']}") for p in planned]
        if proto:
            ctx.send(self.key, "care", "INFORM", f"{protocol_name}: {len(proto)} investigation(s) suggested for clinician review")
        return AgentResult(agent=self.key, recommendations=recs, actions=actions, data={"planned": planned, "protocol": protocol_name},
                           summary=f"Planned {len(planned)} investigation(s) at {priority} priority"
                                   + (f" ({len(requested)} requested, {len(proto)} suggested by {protocol_name})" if proto else "")
                                   + ". Slots booked on least-loaded modalities.")

    def act_status(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        q = select(DiagnosticOrder).where(DiagnosticOrder.status.not_in(["completed", "cancelled"]))
        if ctx.patient:
            q = q.where(DiagnosticOrder.patient_id == ctx.patient.id)
        orders = db.scalars(q).all()
        now = datetime.now()
        breaches = [o for o in orders if (now - o.created_at).total_seconds() / 60 > TEST_CATALOG.get(o.test_code, {}).get("tat", 120)]
        recs = [Recommendation(f"{o.test_name} for {o.patient.name}", f"{o.status}, ordered {o.created_at:%H:%M} — TAT exceeded") for o in breaches[:5]]
        return AgentResult(agent=self.key, recommendations=recs,
                           summary=f"{len(orders)} pending investigation(s); {len(breaches)} beyond expected turnaround.",
                           data={"pending": len(orders), "breaches": len(breaches)})
