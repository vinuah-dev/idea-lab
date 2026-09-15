"""Patient Care Coordinator Agent — identifies the patient and tracks their journey across departments."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select

from .. import serializers as ser
from ..models import (Admission, Appointment, CareTask, DiagnosticOrder, EmergencyCase, Patient,
                      Prescription)
from ..services.clinical import TEST_CATALOG
from .base import AgentContext, AgentResult, BaseAgent, ProposedAction, Recommendation

PATHWAYS: dict[str, list[tuple[str, str, str]]] = {
    # (title, step_type, role)
    "admission": [
        ("Registration & consent verified", "registration", "receptionist"),
        ("Bed allocated and prepared", "bed", "nurse"),
        ("Admission assessment by doctor", "assessment", "doctor"),
        ("Nursing admission, baseline vitals & NEWS2", "nursing", "nurse"),
        ("Diagnostic workup completed", "diagnostics", "lab"),
        ("Treatment plan documented", "treatment", "doctor"),
        ("Daily clinical review", "review", "doctor"),
        ("Discharge planning initiated", "discharge", "nurse"),
    ],
    "emergency": [
        ("Triage completed (NEWS2 + complaint)", "triage", "nurse"),
        ("Stabilisation in emergency bay", "stabilisation", "nurse"),
        ("Emergency physician assessment", "assessment", "doctor"),
        ("Emergency diagnostics", "diagnostics", "lab"),
        ("Disposition decision (admit / transfer / discharge)", "disposition", "doctor"),
        ("Handover to receiving ward", "handover", "nurse"),
    ],
    "diagnostic": [
        ("Investigation ordered", "order", "doctor"),
        ("Sample collected / scan performed", "collection", "lab"),
        ("Result reported", "report", "lab"),
        ("Result reviewed by doctor", "review", "doctor"),
    ],
    "opd": [
        ("Checked in at reception", "checkin", "receptionist"),
        ("Pre-consultation vitals", "vitals", "nurse"),
        ("Doctor consultation", "consultation", "doctor"),
        ("Follow-up scheduled", "followup", "receptionist"),
    ],
    "discharge": [
        ("Discharge summary prepared", "summary", "doctor"),
        ("Medication reconciliation", "medication", "pharmacist"),
        ("Patient & family education", "education", "nurse"),
        ("Billing clearance", "billing", "receptionist"),
        ("Bed released for cleaning", "bed_release", "nurse"),
        ("Follow-up appointment booked", "followup", "receptionist"),
    ],
}


class PatientCareAgent(BaseAgent):
    key = "care"
    name = "Patient Care Coordinator Agent"
    description = "Identifies patients, builds care pathways and tracks each patient's journey end-to-end."
    capabilities = ["patient identification", "care pathway generation", "journey tracking", "discharge readiness"]
    icon = "heart-pulse"
    color = "rose"

    # ------------------------------------------------------------------ identify patient
    def act_resolve_patient(self, ctx: AgentContext, required: bool = True, allow_create: bool = False) -> AgentResult:
        db, ent = ctx.db, ctx.entities
        patient = None
        how = ""
        if ent.get("patient_id"):
            patient = db.get(Patient, int(ent["patient_id"]))
            how = "explicit patient reference"
        if not patient and ent.get("mrn"):
            patient = db.scalar(select(Patient).where(Patient.mrn == ent["mrn"]))
            how = f"MRN {ent['mrn']}"
        if not patient and ent.get("patient_name"):
            name = ent["patient_name"]
            patient = db.scalar(select(Patient).where(func.lower(Patient.name) == name.lower()))
            if not patient:
                patient = db.scalar(select(Patient).where(Patient.name.ilike(f"%{name}%")))
            how = f"name match '{name}'"

        created = False
        if not patient and allow_create:
            count = db.scalar(select(func.count(Patient.id))) or 0
            name = ent.get("new_patient_name") or ent.get("patient_name")
            provisional = not name
            patient = Patient(
                mrn=f"MRN-{1001 + count}",
                name=name or f"Provisional Patient {count + 1}",
                age=int(ent.get("age") or 40),
                gender=ent.get("gender") or "Unknown",
                status="registered",
                conditions=[],
                allergies=[],
            )
            db.add(patient)
            db.flush()
            created = True
            how = "provisional registration" if provisional else "new registration"
            ctx.log(self.key, f"No existing record — registered {patient.name} ({patient.mrn})")

        if not patient:
            if required:
                return AgentResult(agent=self.key, status="failed",
                                   summary="Patient could not be identified. Please include the patient's name or MRN.")
            return AgentResult(agent=self.key, status="skipped", summary="No patient referenced — proceeding at hospital level.")

        ctx.patient = patient
        ctx.request.patient_id = patient.id
        ctx.post(self.key, "patient", ser.patient_brief(patient))
        active_adm = db.scalar(select(Admission).where(Admission.patient_id == patient.id, Admission.status == "active"))
        if active_adm:
            ctx.post(self.key, "active_admission", {"id": active_adm.id, "bed": active_adm.bed.code if active_adm.bed else None})
        recs = []
        actions = []
        if created and not (ent.get("new_patient_name") or ent.get("patient_name")):
            recs.append(Recommendation("Complete registration details",
                                       "Provisional record created so care is not delayed; reception must capture identity & consent."))
        summary = (f"Identified {patient.name} ({patient.mrn}, {patient.age}{patient.gender[:1]}) via {how}. "
                   f"Current status: {patient.status}.")
        if patient.allergies:
            summary += f" Allergies: {', '.join(patient.allergies)}."
        return AgentResult(agent=self.key, summary=summary, data={"patient": ser.patient(patient), "created": created,
                                                                  "active_admission": bool(active_adm)},
                           recommendations=recs, actions=actions)

    # ------------------------------------------------------------------ care pathway
    def act_create_pathway(self, ctx: AgentContext, pathway: str = "admission") -> AgentResult:
        if not ctx.patient:
            return AgentResult(agent=self.key, status="skipped", summary="No patient in context")
        steps = PATHWAYS.get(pathway, [])
        triage = ctx.blackboard.get("triage")
        now = datetime.now()
        created = []
        for i, (title, step_type, role) in enumerate(steps):
            status = "pending"
            if pathway == "emergency" and step_type == "triage":
                status = "done"
            if pathway == "admission" and step_type == "registration" and ctx.patient.status != "registered":
                status = "done"
            due = now + timedelta(minutes=(10 if triage and triage.get("triage_level", 5) <= 2 else 30) * (i + 1))
            task = CareTask(patient_id=ctx.patient.id, pathway=pathway, title=title, step_type=step_type, sequence=i,
                            status=status, assigned_role=role, created_by=self.name, request_id=ctx.request.id,
                            due_at=due, completed_at=now if status == "done" else None)
            ctx.db.add(task)
            created.append({"title": title, "role": role, "status": status, "due_at": due.isoformat()})
        ctx.db.flush()
        ctx.post(self.key, "pathway", {"name": pathway, "steps": len(created)})
        return AgentResult(agent=self.key, summary=f"Created {pathway} care pathway with {len(created)} tracked steps.",
                           data={"pathway": pathway, "steps": created})

    # ------------------------------------------------------------------ journey tracking
    def act_journey_status(self, ctx: AgentContext) -> AgentResult:
        p = ctx.patient
        if not p:
            return AgentResult(agent=self.key, status="failed", summary="No patient in context")
        db = ctx.db
        now = datetime.now()
        tasks = db.scalars(select(CareTask).where(CareTask.patient_id == p.id).order_by(CareTask.created_at, CareTask.sequence)).all()
        orders = db.scalars(select(DiagnosticOrder).where(DiagnosticOrder.patient_id == p.id)).all()
        adm = db.scalar(select(Admission).where(Admission.patient_id == p.id).order_by(Admission.admitted_at.desc()))
        er = db.scalar(select(EmergencyCase).where(EmergencyCase.patient_id == p.id).order_by(EmergencyCase.created_at.desc()))
        appts = db.scalars(select(Appointment).where(Appointment.patient_id == p.id).order_by(Appointment.scheduled_at.desc())).all()
        rx = db.scalars(select(Prescription).where(Prescription.patient_id == p.id)).all()

        open_tasks = [t for t in tasks if t.status in ("pending", "in_progress", "blocked")]
        done = [t for t in tasks if t.status == "done"]
        overdue = [t for t in open_tasks if t.due_at and t.due_at < now]
        pending_orders = [o for o in orders if o.status not in ("completed", "cancelled")]
        tat_breach = [o for o in pending_orders
                      if (now - o.created_at).total_seconds() / 60 > TEST_CATALOG.get(o.test_code, {}).get("tat", 120)]
        location = "Not in hospital"
        if adm and adm.status == "active":
            location = f"Admitted — {adm.bed.ward.name} / {adm.bed.code}" if adm.bed else "Admitted (bed pending)"
        elif er and er.status in ("triage", "awaiting_bed", "in_treatment"):
            location = f"Emergency department ({er.status.replace('_', ' ')})"
        elif any(a.status in ("checked_in", "in_progress") for a in appts):
            location = "OPD — waiting / in consultation"
        progress = round(100 * len(done) / len(tasks)) if tasks else 0
        next_step = open_tasks[0].title if open_tasks else "No pending steps"
        recs = []
        for t in overdue[:3]:
            recs.append(Recommendation(f"Overdue: {t.title}", f"Assigned to {t.assigned_role}; due {t.due_at:%H:%M}"))
        for o in tat_breach[:3]:
            recs.append(Recommendation(f"Turnaround breach: {o.test_name}", f"Ordered {o.created_at:%d %b %H:%M}, status {o.status}"))
        summary = (f"{p.name} is currently: {location}. Care pathway {progress}% complete; next step: {next_step}. "
                   f"{len(pending_orders)} diagnostic order(s) pending, {len(overdue)} overdue task(s).")
        return AgentResult(agent=self.key, summary=summary, recommendations=recs, data={
            "location": location, "progress": progress, "next_step": next_step,
            "open_tasks": [ser.care_task(t) for t in open_tasks[:10]], "pending_orders": [ser.diagnostic(o) for o in pending_orders],
            "active_prescriptions": len([r for r in rx if r.status in ("pending", "verified", "dispensed")]),
            "bottlenecks": [r.title for r in recs],
        })

    # ------------------------------------------------------------------ discharge readiness
    def act_discharge_readiness(self, ctx: AgentContext) -> AgentResult:
        p = ctx.patient
        if not p:
            return AgentResult(agent=self.key, status="failed", summary="No patient in context")
        db = ctx.db
        adm = db.scalar(select(Admission).where(Admission.patient_id == p.id, Admission.status == "active"))
        if not adm:
            return AgentResult(agent=self.key, status="failed", summary=f"{p.name} has no active admission to discharge.")
        blockers, checks = [], []
        pending_orders = db.scalars(select(DiagnosticOrder).where(
            DiagnosticOrder.patient_id == p.id, DiagnosticOrder.status.not_in(["completed", "cancelled"]))).all()
        abnormal = db.scalars(select(DiagnosticOrder).where(DiagnosticOrder.patient_id == p.id, DiagnosticOrder.abnormal.is_(True))).all()
        pending_rx = db.scalars(select(Prescription).where(Prescription.patient_id == p.id, Prescription.status == "pending")).all()
        if pending_orders:
            blockers.append(f"{len(pending_orders)} investigation(s) still pending: " + ", ".join(o.test_name for o in pending_orders))
        else:
            checks.append("All investigations resulted")
        if abnormal:
            checks.append(f"{len(abnormal)} abnormal result(s) — confirm reviewed by treating doctor")
        if pending_rx:
            blockers.append(f"{len(pending_rx)} prescription(s) awaiting pharmacy verification")
        else:
            checks.append("Medication reconciliation possible")
        los = (datetime.now() - adm.admitted_at).days
        exp = adm.expected_discharge
        if exp and exp > datetime.now() + timedelta(days=1):
            checks.append(f"Expected LOS not yet reached (planned {exp:%d %b}) — early discharge needs doctor sign-off")
        score = max(0, 100 - 30 * len(blockers) - (10 if abnormal else 0))
        ctx.post(self.key, "discharge", {"admission_id": adm.id, "bed_id": adm.bed_id, "readiness": score})
        action = ProposedAction(
            action_type="discharge_patient",
            title=f"Discharge {p.name} from {adm.bed.code if adm.bed else 'ward'}",
            payload={"patient_id": p.id, "admission_id": adm.id},
            risk="medium" if not blockers else "high",
            category="clinical",
            requires_approval=True,
            rationale=[f"Discharge readiness score {score}/100", f"Length of stay {los} day(s)"] + blockers + checks,
            description="Closes the admission, releases the bed for cleaning and triggers the discharge pathway.",
        )
        return AgentResult(agent=self.key, status="success" if not blockers else "partial",
                           summary=f"Discharge readiness {score}/100 for {p.name} (LOS {los} days). "
                                   + (f"Blockers: {'; '.join(blockers)}" if blockers else "No blockers found."),
                           data={"readiness": score, "blockers": blockers, "checks": checks, "admission": ser.admission(adm)},
                           actions=[action])
