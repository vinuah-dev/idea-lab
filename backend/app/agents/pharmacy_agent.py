"""Pharmacy Agent — medication availability, prescription safety checks and inventory replenishment."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from ..models import Medication, Prescription
from ..services.clinical import check_allergies, check_interactions
from .base import AgentContext, AgentResult, BaseAgent, ProposedAction, Recommendation

MAX_SINGLE_DOSE_MG = {"paracetamol": 1000, "ibuprofen": 800, "metformin": 1000, "aspirin": 325, "amoxicillin": 1000,
                      "diclofenac": 75, "tramadol": 100, "ondansetron": 8}


class PharmacyAgent(BaseAgent):
    key = "pharmacy"
    name = "Pharmacy Agent"
    description = "Checks stock, allergies, drug interactions and dose limits; manages replenishment."
    capabilities = ["stock check", "allergy screening", "drug-interaction screening", "dose check", "reorder planning"]
    icon = "pill"
    color = "emerald"

    def _resolve_meds(self, ctx: AgentContext) -> list[Medication]:
        meds = [ctx.db.get(Medication, m["id"]) for m in ctx.entities.get("medications", [])]
        for name in ctx.entities.get("medication_names", []):
            md = ctx.db.scalar(select(Medication).where(Medication.name.ilike(f"%{name}%") | Medication.generic.ilike(f"%{name}%")))
            if md and md not in meds:
                meds.append(md)
        return [m for m in meds if m]

    def act_verify_prescription(self, ctx: AgentContext) -> AgentResult:
        meds = self._resolve_meds(ctx)
        if not meds:
            return self.act_inventory(ctx)
        p = ctx.patient
        if not p:  # no patient → this is a stock enquiry about specific medicines
            return self.act_inventory(ctx, only=[m.id for m in meds])
        active = ctx.db.scalars(select(Prescription).where(Prescription.patient_id == p.id,
                                                           Prescription.status.in_(["pending", "verified", "dispensed"]))).all()
        current_generics = [r.medication.generic for r in active]
        actions, recs, checked = [], [], []
        for md in meds:
            alerts = check_allergies(md.generic, p.allergies or []) + check_interactions(md.generic, current_generics)
            dose = ctx.entities.get("dose") or md.strength
            try:
                mg = float(str(dose).split()[0])
                limit = MAX_SINGLE_DOSE_MG.get(md.generic.lower())
                if limit and "mg" in str(dose) and mg > limit:
                    alerts.append({"type": "dose", "severity": "major", "with": dose, "message": f"Dose {dose} exceeds usual max single dose {limit} mg"})
            except (ValueError, IndexError):
                pass
            if md.stock <= 0:
                alerts.append({"type": "stock", "severity": "moderate", "with": "inventory", "message": f"{md.name} out of stock"})
            alternatives = []
            if md.stock <= 0 or any(a["type"] == "allergy" for a in alerts):
                alts = ctx.db.scalars(select(Medication).where(Medication.drug_class == md.drug_class, Medication.id != md.id,
                                                               Medication.stock > 0)).all()
                alternatives = [a.name for a in alts if not check_allergies(a.generic, p.allergies or [])][:3]
            worst = max((a["severity"] for a in alerts), key=lambda s: ["moderate", "major", "contraindicated"].index(s)
                        if s in ("moderate", "major", "contraindicated") else -1, default=None)
            checked.append({"medication": md.name, "generic": md.generic, "stock": md.stock, "alerts": alerts, "alternatives": alternatives})
            blocked = worst in ("contraindicated", "major")
            is_prescriber = ctx.requester_role in ("doctor", "admin")
            actions.append(ProposedAction(
                action_type="create_prescription",
                title=f"Prescribe {md.name} {dose} {ctx.entities.get('frequency', 'BD')} for {p.name}",
                payload={"patient_id": p.id, "medication_id": md.id, "dose": dose, "frequency": ctx.entities.get("frequency", "BD"),
                         "duration_days": 5, "alerts": alerts, "doctor_id": ctx.user.staff_id if ctx.user else None},
                risk="critical" if worst == "contraindicated" else "high" if worst == "major" else "low",
                category="clinical", requires_approval=blocked or not is_prescriber,
                rationale=[a["message"] for a in alerts] or ["No allergy, interaction or dose alerts", f"In stock: {md.stock}"],
                description="Prescription enters the pharmacy verification queue after creation.",
            ))
            if alerts:
                recs.append(Recommendation(f"⚠ {md.name}: {len(alerts)} safety alert(s)", "; ".join(a["message"] for a in alerts),
                                           factors=[{"factor": a["type"], "points": a["severity"]} for a in alerts]))
            if alternatives:
                recs.append(Recommendation(f"Alternatives to {md.name}", ", ".join(alternatives)))
            if any(a["severity"] == "contraindicated" for a in alerts):
                ctx.send(self.key, "care", "REFUSE", f"{md.name} contraindicated for {p.name} — held for doctor override")
        n_alerts = sum(len(c["alerts"]) for c in checked)
        return AgentResult(agent=self.key, actions=actions, recommendations=recs, data={"checked": checked},
                           status="partial" if n_alerts else "success",
                           summary=f"Screened {len(meds)} medication(s) against {len(p.allergies or [])} allergy record(s) and "
                                   f"{len(active)} active prescription(s): {n_alerts} alert(s).")

    def act_inventory(self, ctx: AgentContext, only: list[int] | None = None) -> AgentResult:
        meds = ctx.db.scalars(select(Medication)).all()
        if only:
            focus = [m for m in meds if m.id in only]
            meds = focus
            info = [Recommendation(f"{m.name} {m.strength}: {m.stock} {m.form}(s) in stock",
                                   f"~{m.stock / max(m.daily_usage, 1):.1f} days of stock · reorder level {m.reorder_level}"
                                   + (" · LOW" if m.stock <= m.reorder_level else "")) for m in focus]
        else:
            info = []
        low = sorted([m for m in meds if m.stock <= m.reorder_level], key=lambda m: m.stock / max(m.daily_usage, 1))
        expiring = [m for m in meds if m.expiry and m.expiry <= date.today() + timedelta(days=60)]
        actions = []
        orders = []
        for m in low:
            # order enough for 30 days of demand plus safety stock (reorder level)
            qty = int(max(m.daily_usage * 30 + m.reorder_level - m.stock, m.reorder_level))
            orders.append({"medication_id": m.id, "name": m.name, "quantity": qty, "cost": round(qty * m.unit_price, 2)})
        if orders:
            actions.append(ProposedAction(
                action_type="reorder_medication", title=f"Raise purchase order for {len(orders)} low-stock item(s)",
                payload={"orders": orders}, risk="low", category="pharmacy", requires_approval=True,
                rationale=[f"{o['name']}: order {o['quantity']} (₹{o['cost']:,.0f})" for o in orders[:6]]
                          + ["Quantity = 30-day demand + safety stock − current stock"],
            ))
        recs = info or [Recommendation(f"{m.name}: {m.stock} left", f"~{m.stock / max(m.daily_usage, 1):.1f} days of stock") for m in low[:5]]
        recs += [Recommendation(f"{m.name} expires {m.expiry:%d %b %Y}", "Use first / return to supplier") for m in expiring[:3]]
        scope = ", ".join(m.name for m in meds) if only else f"{len(meds)} formulary items"
        return AgentResult(agent=self.key, actions=actions, recommendations=recs,
                           summary=f"{scope}: {len(low)} at/below reorder level, {len(expiring)} expiring within 60 days.",
                           data={"low_stock": [m.name for m in low], "expiring": [m.name for m in expiring], "orders": orders})

    def act_discharge_meds(self, ctx: AgentContext) -> AgentResult:
        if not ctx.patient:
            return AgentResult(agent=self.key, status="skipped", summary="No patient")
        rx = ctx.db.scalars(select(Prescription).where(Prescription.patient_id == ctx.patient.id,
                                                       Prescription.status.in_(["verified", "dispensed", "pending"]))).all()
        items = [f"{r.medication.name} {r.dose} {r.frequency} × {r.duration_days}d" for r in rx]
        return AgentResult(agent=self.key, summary=f"Medication reconciliation: {len(items)} active medicine(s) for the take-home list.",
                           data={"take_home": items})
