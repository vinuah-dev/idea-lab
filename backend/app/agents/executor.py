"""Action executor and human-in-the-loop approval handling.

Agents only *propose* actions. Low-risk, reversible actions are executed automatically;
safety-critical ones become Approval records that an authorised human approves, modifies or rejects.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..events import bus
from ..models import (Admission, AgentRequest, Appointment, Approval, Bed, CareTask, DiagnosticOrder,
                      EmergencyCase, Invoice, Medication, Patient, Prescription, Resource, Shift, Staff, Surgery, User)
from ..services.activity import log_audit, notify

FREQ_PER_DAY = {"OD": 1, "BD": 2, "TDS": 3, "QID": 4, "HS": 1, "SOS": 1, "once daily": 1, "twice daily": 2, "thrice daily": 3}
OVERRIDABLE = {"bed_id", "doctor_id", "nurse_id", "scheduled_at", "dose", "frequency", "duration_days"}


class ActionError(Exception):
    pass


def _bed_free_for(bed: Bed | None, patient_id: int) -> Bed:
    if bed is None:
        raise ActionError("Bed not found")
    if bed.status == "available" or (bed.status == "reserved" and bed.patient_id == patient_id) \
            or (bed.status == "occupied" and bed.patient_id == patient_id):
        return bed
    raise ActionError(f"Bed {bed.code} is no longer available ({bed.status})")


def _load(db: Session, staff_id: int | None, delta: int) -> None:
    if staff_id:
        s = db.get(Staff, staff_id)
        if s:
            s.current_load = max(0, s.current_load + delta)


def _release_other_holds(db: Session, patient_id: int, keep_bed_id: int) -> None:
    for b in db.scalars(select(Bed).where(Bed.patient_id == patient_id, Bed.id != keep_bed_id)).all():
        if b.status == "reserved":
            b.status, b.patient_id = "available", None
        elif b.status == "occupied":
            b.status, b.patient_id = "cleaning", None


def _complete_tasks(db: Session, patient_id: int, step_types: list[str], status: str = "done") -> None:
    for t in db.scalars(select(CareTask).where(CareTask.patient_id == patient_id, CareTask.step_type.in_(step_types),
                                               CareTask.status.in_(["pending", "in_progress"]))).all():
        t.status = status
        if status == "done":
            t.completed_at = datetime.now()


# ------------------------------------------------------------------ executors
def reserve_bed(db: Session, p: dict) -> dict:
    bed = _bed_free_for(db.get(Bed, p["bed_id"]), p["patient_id"])
    if bed.status != "occupied":
        bed.status, bed.patient_id = "reserved", p["patient_id"]
    return {"bed": bed.code, "status": bed.status}


def admit_patient(db: Session, p: dict) -> dict:
    patient = db.get(Patient, p["patient_id"])
    bed = _bed_free_for(db.get(Bed, p["bed_id"]), patient.id)
    existing = db.scalar(select(Admission).where(Admission.patient_id == patient.id, Admission.status == "active"))
    if existing:  # transfer instead of a duplicate admission
        if existing.bed_id and existing.bed_id != bed.id:
            old = db.get(Bed, existing.bed_id)
            old.status, old.patient_id = "cleaning", None
        existing.bed_id = bed.id
        adm = existing
    else:
        adm = Admission(patient_id=patient.id, bed_id=bed.id, doctor_id=p.get("doctor_id"), nurse_id=p.get("nurse_id"),
                        reason=p.get("reason", ""), acuity=p.get("acuity", "moderate"),
                        expected_discharge=datetime.now() + timedelta(days=float(p.get("expected_los_days", 3))))
        db.add(adm)
        _load(db, p.get("doctor_id"), +1)
        _load(db, p.get("nurse_id"), +1)
    _release_other_holds(db, patient.id, bed.id)
    bed.status, bed.patient_id = "occupied", patient.id
    patient.status = "icu" if bed.ward.ward_type == "icu" else "admitted"
    if p.get("doctor_id"):
        patient.primary_doctor_id = p["doctor_id"]
    if p.get("case_id"):
        case = db.get(EmergencyCase, p["case_id"])
        if case:
            case.status, case.assigned_bed_id = "admitted", bed.id
    out = {"admission_id": None, "bed": bed.code, "ward": bed.ward.name}
    if p.get("equipment_id"):
        eq = db.get(Resource, p["equipment_id"])
        if eq and eq.status == "available":
            eq.status, eq.assigned_patient_id, eq.location = "in_use", patient.id, f"{bed.ward.name} / {bed.code}"
            out["equipment"] = eq.name
    _complete_tasks(db, patient.id, ["bed", "registration", "disposition"])
    db.flush()
    out["admission_id"] = adm.id
    return out


def assign_emergency(db: Session, p: dict) -> dict:
    case = db.get(EmergencyCase, p["case_id"])
    if not case:
        raise ActionError("Emergency case not found")
    bed = _bed_free_for(db.get(Bed, p["bed_id"]), case.patient_id)
    _release_other_holds(db, case.patient_id, bed.id)
    if case.status == "incoming":  # ambulance pre-arrival: hold the bay and team until the patient arrives
        if bed.status != "occupied":
            bed.status, bed.patient_id = "reserved", case.patient_id
        case.assigned_bed_id, case.assigned_doctor_id = bed.id, p.get("doctor_id")
        _load(db, p.get("doctor_id"), +1)
        _load(db, p.get("nurse_id"), +1)
        return {"case_id": case.id, "bed": bed.code, "held_until_arrival": True}
    bed.status, bed.patient_id = "occupied", case.patient_id
    case.assigned_bed_id, case.assigned_doctor_id = bed.id, p.get("doctor_id")
    case.status, case.seen_at = "in_treatment", datetime.now()
    _load(db, p.get("doctor_id"), +1)
    _load(db, p.get("nurse_id"), +1)
    _complete_tasks(db, case.patient_id, ["stabilisation"], "in_progress")
    return {"case_id": case.id, "bed": bed.code}


def create_diagnostic_orders(db: Session, p: dict) -> dict:
    ids = []
    for o in p.get("orders", []):
        order = DiagnosticOrder(
            patient_id=p["patient_id"], ordered_by_id=p.get("ordered_by_id"), test_code=o["code"], test_name=o["name"],
            category=o["category"], priority=o.get("priority", "routine"), resource_id=o.get("resource_id"),
            scheduled_at=datetime.fromisoformat(o["scheduled_at"]) if o.get("scheduled_at") else None,
            status="scheduled" if o.get("scheduled_at") else "ordered")
        db.add(order)
        db.flush()
        ids.append(order.id)
    return {"order_ids": ids}


def book_appointment(db: Session, p: dict) -> dict:
    when = datetime.fromisoformat(p["scheduled_at"])
    day = when.replace(hour=0, minute=0, second=0, microsecond=0)
    n = db.query(Appointment).filter(Appointment.doctor_id == p["doctor_id"], Appointment.scheduled_at >= day,
                                     Appointment.scheduled_at < day + timedelta(days=1)).count()
    appt = Appointment(patient_id=p["patient_id"], doctor_id=p["doctor_id"], department_id=p.get("department_id"),
                       scheduled_at=when, priority=p.get("priority", 3), reason=p.get("reason", ""),
                       queue_number=n + 1, booked_by=p.get("booked_by", "AI agent"))
    db.add(appt)
    db.flush()
    return {"appointment_id": appt.id, "queue_number": appt.queue_number}


def create_prescription(db: Session, p: dict) -> dict:
    freq = p.get("frequency", "BD")
    qty = FREQ_PER_DAY.get(freq, 2) * int(p.get("duration_days", 5))
    rx = Prescription(patient_id=p["patient_id"], doctor_id=p.get("doctor_id"), medication_id=p["medication_id"],
                      dose=p.get("dose", ""), frequency=freq, duration_days=int(p.get("duration_days", 5)), quantity=qty,
                      alerts=p.get("alerts", []), status="pending", notes="Created via AI orchestrator")
    db.add(rx)
    db.flush()
    return {"prescription_id": rx.id, "quantity": qty}


def reorder_medication(db: Session, p: dict) -> dict:
    received = []
    for o in p.get("orders", []):
        med = db.get(Medication, o["medication_id"])
        if med:
            med.stock += int(o["quantity"])
            received.append(f"{med.name} +{o['quantity']}")
    return {"received": received}


def discharge_patient(db: Session, p: dict) -> dict:
    adm = db.get(Admission, p["admission_id"])
    if not adm or adm.status != "active":
        raise ActionError("Admission not active")
    adm.status, adm.discharged_at = "discharged", datetime.now()
    patient = db.get(Patient, adm.patient_id)
    patient.status = "discharged"
    if adm.bed:
        adm.bed.status, adm.bed.patient_id = "cleaning", None
    _load(db, adm.doctor_id, -1)
    _load(db, adm.nurse_id, -1)
    for t in db.scalars(select(CareTask).where(CareTask.patient_id == patient.id, CareTask.status.in_(["pending", "in_progress"]))).all():
        t.status, t.completed_at = "done", datetime.now()
    out = {"admission_id": adm.id, "bed_released": adm.bed.code if adm.bed else None}
    fu = p.get("follow_up")
    if fu:
        out["follow_up"] = book_appointment(db, {"patient_id": patient.id, "doctor_id": fu["doctor_id"],
                                                 "department_id": fu.get("department_id"), "scheduled_at": fu["slot"],
                                                 "priority": 3, "reason": "Post-discharge follow-up"})
    from ..services import billing  # final bill; PM-JAY is cashless, so its claim is filed at discharge
    inv = billing.sync_patient(db, patient, force=True)
    if inv:
        billing.finalize(db, inv)
        out["invoice"] = inv.number
        if inv.payer == "pmjay" and not inv.claims:
            try:
                out["claim_id"] = billing.submit_claim(db, inv).id
            except billing.BillingError:
                pass
    return out


def submit_claim(db: Session, p: dict) -> dict:
    from ..services import billing
    inv = db.get(Invoice, p["invoice_id"])
    if inv is None:
        raise ActionError("Invoice not found")
    try:
        claim = billing.submit_claim(db, inv)
    except billing.BillingError as exc:
        raise ActionError(str(exc))
    return {"claim_id": claim.id, "amount": claim.claimed_amount, "package": claim.package_name}


def dispatch_ambulance(db: Session, p: dict) -> dict:
    from ..services import dispatch as dsp
    try:
        d = dsp.create_dispatch(db, p)
    except ValueError as exc:
        raise ActionError(str(exc))
    return {"dispatch_id": d.id, "ambulance": d.ambulance.code, "eta_scene_min": d.eta_scene_min}


def apply_roster(db: Session, p: dict) -> dict:
    start, end = date.fromisoformat(p["start"]), date.fromisoformat(p["end"])
    db.execute(delete(Shift).where(Shift.date >= start, Shift.date <= end))
    dept = {s.id: s.department_id for s in db.scalars(select(Staff)).all()}
    for a in p["assignments"]:
        db.add(Shift(staff_id=a["staff_id"], date=date.fromisoformat(a["date"]), shift_type=a["shift"],
                     department_id=dept.get(a["staff_id"]), generated_by="optimizer"))
    return {"shifts": len(p["assignments"])}


def reassign_staff(db: Session, p: dict) -> dict:
    moved = []
    for sid in p["staff_ids"]:
        s = db.get(Staff, sid)
        if s:
            s.department_id = p["department_id"]
            moved.append(s.name)
    return {"moved": moved}


def apply_bed_allocation(db: Session, p: dict) -> dict:
    done = []
    for a in p["assignments"]:
        bed = db.get(Bed, a["bed_id"])
        if bed is None or bed.status != "available":
            continue
        if a["kind"] == "emergency":
            case = db.get(EmergencyCase, a["id"])
            case.assigned_bed_id, case.status, case.seen_at = bed.id, "in_treatment", case.seen_at or datetime.now()
        else:
            db.get(Admission, a["id"]).bed_id = bed.id
        bed.status, bed.patient_id = "occupied", a["patient_id"]
        done.append(bed.code)
    return {"placed": done}


SURGICAL_PATHWAY = [
    ("Pre-operative assessment & informed consent", "preop", "doctor"),
    ("Anaesthesia review", "anaesthesia", "doctor"),
    ("WHO surgical safety checklist (sign-in / time-out)", "checklist", "nurse"),
    ("Surgery", "surgery", "doctor"),
    ("Recovery (PACU) monitoring", "recovery", "nurse"),
    ("Post-operative ward review", "postop", "doctor"),
]


def book_surgery(db: Session, p: dict) -> dict:
    from ..services.ot_scheduler import TURNOVER
    start = datetime.fromisoformat(p["scheduled_start"])
    dur = int(p.get("duration_minutes", 60))
    end = start + timedelta(minutes=dur)
    nearby = db.scalars(select(Surgery).where(Surgery.status.in_(["scheduled", "in_progress"]),
                                              Surgery.scheduled_start >= start - timedelta(hours=14),
                                              Surgery.scheduled_start <= end + timedelta(hours=1))).all()
    for o in nearby:
        o_end = o.scheduled_start + timedelta(minutes=o.duration_minutes)
        if p.get("ot_id") and o.ot_id == p["ot_id"] and start < o_end + timedelta(minutes=TURNOVER) and o.scheduled_start < end + timedelta(minutes=TURNOVER):
            raise ActionError(f"{o.ot.name if o.ot else 'Theatre'} is booked for {o.procedure} at {o.scheduled_start:%H:%M}")
        if p.get("surgeon_id") and o.surgeon_id == p["surgeon_id"] and start < o_end and o.scheduled_start < end:
            raise ActionError(f"Surgeon is already operating ({o.procedure}) at {o.scheduled_start:%H:%M}")
    s = Surgery(patient_id=p["patient_id"], surgeon_id=p.get("surgeon_id"), ot_id=p.get("ot_id"), procedure=p["procedure"],
                specialty=p.get("specialty", "General Surgery"), priority=p.get("priority", "elective"), scheduled_start=start,
                duration_minutes=dur, anaesthesia=p.get("anaesthesia", "GA"), notes=p.get("notes", ""),
                created_by=p.get("created_by", "Resource Optimization Agent"))
    db.add(s)
    db.flush()
    for i, (title, step, role) in enumerate(SURGICAL_PATHWAY):
        db.add(CareTask(patient_id=s.patient_id, pathway="surgical", title=title if step != "surgery" else f"Surgery: {s.procedure}",
                        step_type=step, sequence=i, status="pending", assigned_role=role, created_by="Resource Optimization Agent",
                        due_at=start + timedelta(minutes=(i - 3) * 45)))
    return {"surgery_id": s.id, "ot": s.ot.name if s.ot else None, "start": start.isoformat()}


def apply_ot_schedule(db: Session, p: dict) -> dict:
    updated = []
    for a in p.get("assignments", []):
        s = db.get(Surgery, a["surgery_id"])
        if s and s.status == "scheduled":
            s.ot_id, s.scheduled_start = a["ot_id"], datetime.fromisoformat(a["start"])
            updated.append(s.procedure)
    return {"updated": len(updated), "surgeries": updated}


EXECUTORS = {
    "reserve_bed": reserve_bed, "admit_patient": admit_patient, "assign_emergency": assign_emergency,
    "create_diagnostic_orders": create_diagnostic_orders, "book_appointment": book_appointment,
    "create_prescription": create_prescription, "reorder_medication": reorder_medication,
    "discharge_patient": discharge_patient, "apply_roster": apply_roster, "reassign_staff": reassign_staff,
    "apply_bed_allocation": apply_bed_allocation, "book_surgery": book_surgery, "apply_ot_schedule": apply_ot_schedule,
    "submit_claim": submit_claim, "dispatch_ambulance": dispatch_ambulance,
}

REFRESH_SCOPE = {
    "reserve_bed": ["beds"], "admit_patient": ["beds", "patients", "staff"], "assign_emergency": ["beds", "emergency"],
    "create_diagnostic_orders": ["diagnostics"], "book_appointment": ["appointments"], "create_prescription": ["pharmacy"],
    "reorder_medication": ["pharmacy"], "discharge_patient": ["beds", "patients"], "apply_roster": ["staff"],
    "reassign_staff": ["staff"], "apply_bed_allocation": ["beds", "emergency"], "book_surgery": ["surgeries", "patients"],
    "apply_ot_schedule": ["surgeries"], "submit_claim": ["billing"], "dispatch_ambulance": ["ambulance"],
}


def execute_action(db: Session, action_type: str, payload: dict, actor: str, actor_type: str = "agent",
                   request_id: int | None = None) -> dict:
    fn = EXECUTORS.get(action_type)
    if fn is None:
        raise ActionError(f"Unknown action {action_type}")
    result = fn(db, payload)
    log_audit(db, actor, actor_type, f"execute:{action_type}", "agent_request", request_id,
              {"payload": {k: v for k, v in payload.items() if k != "assignments"}, "result": result})
    bus.publish("refresh", {"scope": REFRESH_SCOPE.get(action_type, [])})
    return result


def _release_holds_for(db: Session, approval: Approval) -> None:
    bed_id = (approval.payload or {}).get("bed_id")
    patient_id = (approval.payload or {}).get("patient_id")
    if bed_id:
        bed = db.get(Bed, bed_id)
        if bed and bed.status == "reserved" and bed.patient_id == patient_id:
            bed.status, bed.patient_id = "available", None
    if approval.action_type in ("admit_patient", "assign_emergency") and approval.request_id:
        for t in db.scalars(select(CareTask).where(CareTask.request_id == approval.request_id, CareTask.status == "pending")).all():
            t.status = "cancelled"


def refresh_request_status(db: Session, request: AgentRequest | None) -> None:
    if not request:
        return
    statuses = [a.status for a in request.approvals]
    if "pending" in statuses:
        request.status = "awaiting_approval"
    elif statuses and all(s == "rejected" for s in statuses):
        request.status = "rejected"
    else:
        request.status = "completed"
    if request.status != "awaiting_approval" and not request.completed_at:
        request.completed_at = datetime.now()


def decide_approval(db: Session, approval: Approval, user: User, approve: bool, note: str | None = None,
                    overrides: dict | None = None) -> Approval:
    if approval.status != "pending":
        raise ActionError(f"Approval already {approval.status}")
    approval.decided_by = f"{user.full_name} ({user.role})"
    approval.decided_at = datetime.now()
    approval.decision_note = note
    if approve:
        payload = dict(approval.payload or {})
        clean = {k: v for k, v in (overrides or {}).items() if k in OVERRIDABLE and v not in (None, "")}
        if clean:
            if "bed_id" in clean and payload.get("bed_id") and payload["bed_id"] != clean["bed_id"]:
                old = db.get(Bed, payload["bed_id"])
                if old and old.status == "reserved" and old.patient_id == payload.get("patient_id"):
                    old.status, old.patient_id = "available", None
            payload.update(clean)
            approval.payload = payload
            approval.decision_note = (note or "") + f" [modified: {', '.join(clean)}]"
        try:
            with db.begin_nested():
                approval.execution_result = execute_action(db, approval.action_type, payload,
                                                           actor=approval.decided_by, actor_type="user",
                                                           request_id=approval.request_id)
            approval.status = "executed"
        except (ActionError, KeyError, ValueError) as exc:
            approval.status = "failed"
            approval.execution_result = {"error": str(exc)}
    else:
        approval.status = "rejected"
        _release_holds_for(db, approval)
    log_audit(db, approval.decided_by, "user", "approve" if approve else "reject", "approval", approval.id,
              {"title": approval.title, "agent": approval.agent, "note": note, "result": approval.execution_result})
    req = approval.request
    if req:
        trace = list(req.trace or [])
        trace.append({"seq": len(trace) + 1, "kind": "human", "agent": "human",
                      "title": f"{'Approved' if approve else 'Rejected'} by {approval.decided_by}: {approval.title}",
                      "detail": note, "ts": datetime.now().isoformat(),
                      "data": {"approval_id": approval.id, "status": approval.status}})
        req.trace = trace
        refresh_request_status(db, req)
    level = "success" if approval.status == "executed" else "warning" if approval.status == "rejected" else "critical"
    notify(db, f"Approval {approval.status}: {approval.title}", f"Decision by {approval.decided_by}."
           + (f" Error: {approval.execution_result.get('error')}" if approval.status == "failed" else ""),
           level=level, category="approval", role="admin", link="/approvals")
    db.commit()
    bus.publish("approval", {"id": approval.id, "status": approval.status, "request_id": approval.request_id})
    if req:
        bus.publish("agent.request", {"id": req.id, "status": req.status})
    return approval
