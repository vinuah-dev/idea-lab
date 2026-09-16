"""Ambulance Dispatch Agent — nearest capable unit, ETA prediction and pre-arrival coordination."""
from __future__ import annotations

from sqlalchemy import select

from ..models import Ambulance, Dispatch
from ..services import dispatch as dsp
from .base import AgentContext, AgentResult, BaseAgent, ProposedAction, Recommendation


class AmbulanceDispatchAgent(BaseAgent):
    key = "ambulance"
    name = "Ambulance Dispatch Agent"
    description = "Handles 108-style calls: pre-triages severity, sends the nearest capable ambulance and pre-alerts the ED before arrival."
    capabilities = ["severity pre-triage", "nearest capable unit", "ETA prediction", "live fleet tracking", "pre-arrival alert"]
    icon = "ambulance"
    color = "fuchsia"

    def act_dispatch(self, ctx: AgentContext) -> AgentResult:
        ent = ctx.entities
        pickup = ent.get("pickup")
        if pickup and pickup.get("lat") is not None:
            locality, lat, lng = ent.get("locality") or pickup.get("label") or "Caller location", float(pickup["lat"]), float(pickup["lng"])
        else:
            found = dsp.find_locality(ent.get("locality") or ctx.request.text)
            if not found:
                return AgentResult(agent=self.key, status="failed",
                                   summary="Pickup location not understood — mention the locality (e.g. 'accident at Sitabuldi').",
                                   recommendations=[Recommendation("Known localities", ", ".join(list(dsp.LOCALITIES)[:10]) + " …")])
            locality, lat, lng = found
        complaint = ent.get("chief_complaint") or ctx.request.text
        sev = dsp.predict_severity(complaint, ent.get("vitals") or {}, ent.get("age"))
        ranked = dsp.rank_units(ctx.db, lat, lng, sev["level"])
        ctx.post(self.key, "call", {"locality": locality, "severity": sev["level"], "lat": lat, "lng": lng})
        if not ranked:
            return AgentResult(agent=self.key, status="failed", summary="No ambulance is free right now.",
                               recommendations=[Recommendation("Request mutual aid", "Escalate to the district 108 control room / partner hospitals")])
        best = ranked[0]
        ctx.send(self.key, "emergency", "INFORM", f"L{sev['level']} call at {locality}; {best['code']} ETA to scene {best['eta']:.0f} min")
        action = ProposedAction(
            action_type="dispatch_ambulance", title=f"Dispatch {best['code']} ({best['type']}) to {locality}",
            payload={"ambulance_id": best["ambulance_id"], "lat": lat, "lng": lng, "locality": locality, "complaint": complaint[:250],
                     "severity": sev["level"], "vitals": ent.get("vitals") or {}, "caller": ent.get("caller", ""),
                     "patient_id": ctx.patient.id if ctx.patient else None, "selection": ranked[:4]},
            risk="low", category="operations", requires_approval=False,
            rationale=[f"Lowest time-to-scene cost {best['cost']} ({best['km']} km, ETA {best['eta']:.0f} min)",
                       f"Pre-triage L{sev['level']} {sev['label']}" + (f" — red flags: {', '.join(sev['red_flags'])}" if sev["red_flags"] else ""),
                       "Time-critical: dispatched without waiting for approval"])
        recs = [Recommendation(f"{u['code']} ({u['type']}, {u['base']}) — ETA {u['eta']:.0f} min", f"{u['km']} km", u["cost"], u["factors"]) for u in ranked[:3]]
        return AgentResult(agent=self.key, actions=[action], recommendations=recs, data={"severity": sev, "candidates": ranked[:5], "locality": locality},
                           summary=f"Call at {locality} pre-triaged L{sev['level']} ({sev['label']}). Nearest capable unit {best['code']} "
                                   f"({best['type']}) — {best['km']} km, ETA {best['eta']:.0f} min. The ED will be pre-alerted when the crew leaves the scene.")

    def act_fleet_status(self, ctx: AgentContext) -> AgentResult:
        fleet = ctx.db.scalars(select(Ambulance)).all()
        by: dict[str, int] = {}
        for a in fleet:
            by[a.status] = by.get(a.status, 0) + 1
        active = ctx.db.scalars(select(Dispatch).where(Dispatch.status.in_(["to_scene", "on_scene", "to_hospital"]))).all()
        recs = [Recommendation(f"{d.ambulance.code} → {d.locality}: {d.status.replace('_', ' ')}",
                               f"{d.complaint}; ETA hospital {d.eta_hospital_min:.0f} min") for d in active]
        return AgentResult(agent=self.key, recommendations=recs, data={"by_status": by, "active": len(active)},
                           summary=f"Fleet: {by.get('available', 0)}/{len(fleet)} ambulances available; {len(active)} active call(s).")
