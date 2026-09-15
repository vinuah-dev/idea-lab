"""Emergency Support Agent — NEWS2-based triage, prioritisation and rapid resource mobilisation."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from ..models import EmergencyCase
from ..services.triage import triage
from .base import AgentContext, AgentResult, BaseAgent, Recommendation


class EmergencySupportAgent(BaseAgent):
    key = "emergency"
    name = "Emergency Support Agent"
    description = "Triages emergency cases with NEWS2 + red-flag detection and mobilises beds, teams and diagnostics."
    capabilities = ["NEWS2 scoring", "5-level triage", "red-flag detection", "code activation", "ED surge monitoring"]
    icon = "siren"
    color = "red"

    def act_triage(self, ctx: AgentContext, case_id: int | None = None) -> AgentResult:
        db = ctx.db
        p = ctx.patient
        case = db.get(EmergencyCase, case_id) if case_id else None
        vitals = dict(case.vitals) if case and case.vitals else dict(ctx.entities.get("vitals", {}))
        complaint = (case.chief_complaint if case else None) or ctx.entities.get("chief_complaint") or ctx.request.text
        res = triage(vitals, complaint, p.age if p else None)
        if case is None and p is not None:
            case = EmergencyCase(patient_id=p.id, arrival_mode=ctx.entities.get("arrival_mode", "walk-in"),
                                 chief_complaint=complaint[:250], vitals=vitals)
            db.add(case)
        if case is not None:
            case.news2_score, case.triage_level = res.news2, res.triage_level
            case.status = "awaiting_bed" if case.status == "triage" else case.status
            db.flush()
        if p:
            p.status = "emergency"
            p.risk_score = round(min(1.0, res.news2 / 12 + (0.3 if res.triage_level <= 2 else 0)), 2)
        tri = res.to_dict() | {"case_id": case.id if case else None}
        ctx.post(self.key, "triage", tri)
        ctx.entities.setdefault("chief_complaint", complaint)

        ctx.send(self.key, "bed", "REQUEST", f"Need {res.recommended_area} capacity for triage L{res.triage_level}")
        ctx.send(self.key, "staff", "REQUEST", "Assemble emergency team" + (" — senior clinician required" if res.triage_level <= 2 else ""))
        recs = [Recommendation(f"Triage level {res.triage_level}: {res.triage_label}",
                               f"Target time to doctor: {'immediate' if res.target_minutes == 0 else f'{res.target_minutes} min'}",
                               res.news2, [{"factor": k.replace('_', ' '), "points": v} for k, v in res.news2_components.items() if v]),
                ]
        if res.triage_level == 1:
            recs.append(Recommendation("Activate resuscitation team (Code Blue / trauma call)", "Critical — automated alert sent to on-duty doctors and nurses"))
        return AgentResult(agent=self.key, recommendations=recs, data=tri,
                           summary=f"NEWS2 {res.news2} ({res.clinical_risk} risk) → triage L{res.triage_level} {res.triage_label} "
                                   f"({res.color.upper()}); target {'immediate' if res.target_minutes == 0 else f'≤{res.target_minutes} min'}."
                                   + (f" Red flags: {', '.join(res.red_flags)}." if res.red_flags else ""))

    def act_capacity_check(self, ctx: AgentContext) -> AgentResult:
        active = ctx.db.scalars(select(EmergencyCase).where(EmergencyCase.status.in_(["triage", "awaiting_bed", "in_treatment"]))).all()
        now = datetime.now()
        from ..services.triage import TRIAGE_LEVELS
        breaches = [c for c in active if c.status != "in_treatment"
                    and (now - c.created_at).total_seconds() / 60 > TRIAGE_LEVELS[c.triage_level]["target_minutes"]]
        surge = len(active) >= 8
        recs = []
        if surge:
            recs.append(Recommendation("ED surge protocol", "Open overflow bays, call in on-call staff, expedite ward discharges"))
        for c in breaches[:3]:
            recs.append(Recommendation(f"Target time breached: case #{c.id} ({c.patient.name})", f"L{c.triage_level}, status {c.status}"))
        ctx.post(self.key, "ed_load", {"active": len(active), "breaches": len(breaches), "surge": surge})
        return AgentResult(agent=self.key, recommendations=recs,
                           summary=f"ED load: {len(active)} active case(s), {len(breaches)} beyond target time" + (" — SURGE" if surge else "") + ".",
                           data={"active": len(active), "breaches": len(breaches), "surge": surge})
