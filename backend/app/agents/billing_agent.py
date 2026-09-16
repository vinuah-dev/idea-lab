"""Billing & Insurance Agent — cost estimation, charge capture, PM-JAY / insurance cover and billing clearance."""
from __future__ import annotations

from sqlalchemy import select

from ..models import Admission, Resource
from ..services import billing
from .base import AgentContext, AgentResult, BaseAgent, ProposedAction, Recommendation


def _inr(v: float) -> str:
    return f"₹{v:,.0f}"


class BillingInsuranceAgent(BaseAgent):
    key = "billing"
    name = "Billing & Insurance Agent"
    description = "Estimates treatment cost from the predicted stay, captures charges automatically, maps PM-JAY / insurance cover and prepares claims."
    capabilities = ["LOS-aware cost estimation", "automatic charge capture", "PM-JAY package mapping", "claim preparation", "billing clearance"]
    icon = "receipt"
    color = "amber"

    # ------------------------------------------------------------------ pre-admission estimate
    def act_estimate(self, ctx: AgentContext) -> AgentResult:
        p = ctx.patient
        alloc = ctx.blackboard.get("allocation") or {}
        ward_type = alloc.get("ward_type") or ctx.entities.get("bed_type") or ("icu" if (ctx.blackboard.get("triage") or {}).get("triage_level") == 1 else "general")
        tests = [t if isinstance(t, str) else t.get("code") for t in ctx.entities.get("tests") or []]
        acuity = {1: "critical", 2: "high"}.get((ctx.blackboard.get("triage") or {}).get("triage_level"), "high" if ward_type in ("icu", "hdu", "cardiac") else "moderate")
        vent = "ventilator" in (ctx.entities.get("bed_features") or [])
        payer = p.insurance_scheme if p else "self"
        est = billing.estimate(p.age if p else 45, ward_type, acuity, len((p.conditions if p else []) or []),
                               bool(ctx.blackboard.get("triage")), ctx.entities.get("procedure"), tests, payer, vent)
        cov = est["coverage"]
        ctx.post(self.key, "cost_estimate", {"expected": est["expected"], "low": est["low"], "high": est["high"], "payer": cov["payer"]})
        recs = [Recommendation(b["item"], "", b["amount"]) for b in est["breakdown"][:4]]
        if cov["payer"] == "pmjay":
            recs.insert(0, Recommendation("PM-JAY cashless cover", f"{cov['package_name']} — package {_inr(cov['covered'])}; patient pays nothing"))
        elif cov["payer"] == "private":
            recs.insert(0, Recommendation("Cashless pre-authorisation with TPA", f"Covered ≈ {_inr(cov['covered'])}; co-pay ≈ {_inr(cov['patient_share'])}"))
        elif est["expected"] > 50000:
            recs.insert(0, Recommendation("Financial counselling", "Self-pay estimate above ₹50,000 — check PM-JAY eligibility and offer a deposit plan"))
        who = p.name if p else "the patient"
        return AgentResult(agent=self.key, recommendations=recs, data=est,
                           summary=f"Estimated cost for {who}: {_inr(est['expected'])} (range {_inr(est['low'])}–{_inr(est['high'])}) for "
                                   f"~{est['los']['days']} days in {ward_type.upper() if ward_type in ('icu', 'hdu') else ward_type}; "
                                   f"{cov['payer_label']}" + (f" covers {_inr(cov['covered'])}." if cov["covered"] else "."))

    # ------------------------------------------------------------------ bill status / claims
    def _claim_action(self, ctx: AgentContext, inv, summary: dict) -> ProposedAction | None:
        if inv.payer == "self" or (inv.claims and inv.claims[-1].status in ("submitted", "approved", "settled")) or summary["coverage"]["covered"] <= 0:
            return None
        cov = summary["coverage"]
        return ProposedAction(action_type="submit_claim", title=f"Submit {cov['payer_label']} claim {_inr(cov['covered'])} for {inv.patient.name}",
                              payload={"invoice_id": inv.id, "patient_id": inv.patient_id}, risk="low", category="billing", requires_approval=True,
                              rationale=[f"Package: {cov['package_name']}", f"Invoice {inv.number}: gross {_inr(summary['gross'])}",
                                         "Claims are submitted to the insurer only after front-office verification of documents"],
                              description="Creates the pre-authorisation / claim with the standard document checklist.")

    def act_bill_status(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        p = ctx.patient
        if not p:
            rev = billing.revenue_summary(db)
            return AgentResult(agent=self.key, data=rev,
                               summary=f"{rev['invoices']} open invoices, {_inr(rev['outstanding'])} outstanding; {rev['claims_pending']} claim(s) "
                                       f"pending ({_inr(rev['claims_pending_amount'])}); collected today {_inr(rev['collected_today'])}.",
                               recommendations=[Recommendation(f"{k}: {_inr(v)}") for k, v in list(rev["by_category"].items())[:4]])
        inv = billing.sync_patient(db, p, force=True)
        if inv is None:
            return AgentResult(agent=self.key, summary=f"No billable activity for {p.name} in the current episode.")
        s = billing.summarize(inv)
        actions = [a for a in [self._claim_action(ctx, inv, s)] if a]
        recs = [Recommendation(f"{k.title()}: {_inr(v)}") for k, v in list(s["by_category"].items())[:5]]
        if s["balance"] > 0:
            recs.insert(0, Recommendation(f"Collect {_inr(s['balance'])}", "Patient share outstanding — UPI / card / cash at the billing desk or in the portal"))
        ctx.post(self.key, "bill", {"invoice": inv.number, "balance": s["balance"], "net": s["net"]})
        return AgentResult(agent=self.key, actions=actions, recommendations=recs, data={"invoice_id": inv.id, **s},
                           summary=f"{inv.number} for {p.name}: gross {_inr(s['gross'])}, {s['coverage']['payer_label']} "
                                   f"{_inr(s['expected_insurance'])}, patient share {_inr(s['patient_share'])}, paid {_inr(s['paid'])}, "
                                   f"balance {_inr(s['balance'])}" + (f"; claim {s['claim_status']}" if s["claim_status"] else "") + ".")

    def act_clearance(self, ctx: AgentContext) -> AgentResult:
        p = ctx.patient
        if not p:
            return AgentResult(agent=self.key, status="skipped", summary="No patient")
        inv = billing.sync_patient(ctx.db, p, force=True)
        if inv is None:
            ctx.post(self.key, "billing_clearance", {"cleared": True, "balance": 0})
            return AgentResult(agent=self.key, summary="No charges — billing clearance not required.")
        s = billing.summarize(inv)
        cleared = s["cleared"] or s["coverage"]["payer"] == "pmjay"
        ctx.post(self.key, "billing_clearance", {"cleared": cleared, "balance": s["balance"], "invoice": inv.number})
        actions = [a for a in [self._claim_action(ctx, inv, s)] if a]
        recs = []
        if not cleared:
            recs.append(Recommendation(f"Settle {_inr(s['balance'])} before the patient leaves", "Front office can take UPI / card; the portal also supports payment"))
        if ctx.db.scalar(select(Resource).where(Resource.assigned_patient_id == p.id)):
            recs.append(Recommendation("Return assigned equipment", "Equipment is still linked to the patient — release it so it stops accruing charges"))
        return AgentResult(agent=self.key, status="success" if cleared else "partial", actions=actions, recommendations=recs,
                           data={"invoice_id": inv.id, **s},
                           summary=(f"Billing cleared for {p.name} ({inv.number})." if cleared and s["coverage"]["payer"] != "pmjay"
                                    else f"PM-JAY cashless — package {_inr(s['coverage']['covered'])} claimed on discharge; nothing to collect." if cleared
                                    else f"Billing NOT cleared: {_inr(s['balance'])} outstanding on {inv.number}."))
