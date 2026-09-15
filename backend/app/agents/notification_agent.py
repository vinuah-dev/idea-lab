"""Notification Agent — routes updates to the right roles/people over in-app, SMS and e-mail channels."""
from __future__ import annotations

from sqlalchemy import select

from ..models import User
from ..services.activity import notify
from .base import AgentContext, AgentResult, BaseAgent


class NotificationAgent(BaseAgent):
    key = "notification"
    name = "Notification Agent"
    description = "Composes and routes alerts, approval requests and patient messages to the right people and channels."
    capabilities = ["role-based routing", "approval requests", "critical alerts", "patient SMS/e-mail (simulated)"]
    icon = "bell-ring"
    color = "orange"

    def act_dispatch(self, ctx: AgentContext, approvals: list[dict] | None = None, executed: list[dict] | None = None) -> AgentResult:
        db = ctx.db
        approvals = approvals or []
        executed = executed or []
        sent = []
        link = f"/agents?request={ctx.request.id}"

        triage = ctx.blackboard.get("triage")
        p = ctx.patient
        if triage and triage["triage_level"] <= 2:
            lvl = triage["triage_level"]
            for role in ("doctor", "nurse"):
                notify(db, f"{'🚨 CODE — ' if lvl == 1 else ''}Emergency L{lvl}: {p.name if p else 'patient'}",
                       f"NEWS2 {triage['news2']}, {triage['triage_label']}. {', '.join(triage['red_flags']) or 'See triage details'}.",
                       level="critical", category="emergency", role=role, link="/emergency")
                sent.append({"to": f"all {role}s", "channel": "in-app", "level": "critical"})

        by_roles: dict[tuple, list[dict]] = {}
        for a in approvals:
            by_roles.setdefault(tuple(a["required_roles"]), []).append(a)
        for roles, items in by_roles.items():
            for role in roles:
                if role == "admin":
                    continue
                notify(db, f"{len(items)} AI action(s) awaiting your approval",
                       "; ".join(i["title"] for i in items)[:400], level="warning", category="approval", role=role, link="/approvals")
                sent.append({"to": f"{role}s", "channel": "in-app", "level": "warning", "items": len(items)})
        if approvals:
            notify(db, f"Request #{ctx.request.id}: {len(approvals)} approval(s) pending",
                   "; ".join(a["title"] for a in approvals)[:400], level="info", category="approval", role="admin", link="/approvals")

        alloc = ctx.blackboard.get("allocation")
        if alloc and alloc.get("nurse_id"):
            nurse_user = db.scalar(select(User).where(User.staff_id == alloc["nurse_id"]))
            if nurse_user:
                notify(db, "Incoming patient", f"{p.name if p else 'Patient'} → {alloc['bed_code']} (pending approval)",
                       level="info", category="bed", user_id=nurse_user.id, link="/beds")
                sent.append({"to": alloc["nurse"], "channel": "in-app"})

        for e in executed:
            if e["action_type"] == "book_appointment" and p:
                appt = ctx.blackboard.get("appointment") or {}
                msg = f"Dear {p.name}, your appointment with {appt.get('doctor', 'the doctor')} is confirmed for {str(appt.get('slot', ''))[:16].replace('T', ' ')}."
                notify(db, "Appointment confirmed (SMS)", msg, level="success", category="patient", channel="sms", role="receptionist")
                patient_user = db.scalar(select(User).where(User.patient_id == p.id))
                if patient_user:
                    notify(db, "Appointment confirmed", msg, level="success", category="appointment", user_id=patient_user.id, link="/portal")
                sent.append({"to": f"{p.name} ({p.phone or 'no phone'})", "channel": "sms"})
        if ctx.blackboard.get("capacity_alert"):
            notify(db, "Capacity alert", "No suitable bed available for an incoming patient — review discharges / step-downs.",
                   level="critical", category="capacity", role="admin", link="/beds")
            sent.append({"to": "administrators", "channel": "in-app", "level": "critical"})
        return AgentResult(agent=self.key, summary=f"Dispatched {len(sent)} notification(s) across in-app / SMS channels.",
                           data={"sent": sent})
