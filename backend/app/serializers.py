"""Plain-dict serializers for API responses."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import models as m
from .services.maintenance import maintenance_status
from .services.triage import TRIAGE_LEVELS


def _iso(v: datetime | date | None) -> str | None:
    return v.isoformat() if v else None


def department(d: m.Department | None) -> dict | None:
    if not d:
        return None
    return {"id": d.id, "name": d.name, "code": d.code, "floor": d.floor, "avg_consult_minutes": d.avg_consult_minutes}


def staff(s: m.Staff | None) -> dict | None:
    if not s:
        return None
    return {
        "id": s.id, "name": s.name, "role": s.role, "specialization": s.specialization,
        "department_id": s.department_id, "department": s.department.name if s.department else None,
        "skills": s.skills or [], "seniority": s.seniority, "max_patients": s.max_patients,
        "current_load": s.current_load, "on_duty": s.on_duty, "phone": s.phone,
        "load_pct": round(100 * s.current_load / s.max_patients) if s.max_patients else 0,
    }


def patient(p: m.Patient | None) -> dict | None:
    if not p:
        return None
    return {
        "id": p.id, "mrn": p.mrn, "name": p.name, "age": p.age, "gender": p.gender, "phone": p.phone,
        "blood_group": p.blood_group, "allergies": p.allergies or [], "conditions": p.conditions or [],
        "status": p.status, "risk_score": p.risk_score, "primary_doctor_id": p.primary_doctor_id,
        "primary_doctor": p.primary_doctor.name if p.primary_doctor else None, "created_at": _iso(p.created_at),
        "insurance_scheme": p.insurance_scheme or "self", "insurance_id": p.insurance_id,
    }


def patient_brief(p: m.Patient | None) -> dict | None:
    if not p:
        return None
    return {"id": p.id, "mrn": p.mrn, "name": p.name, "age": p.age, "gender": p.gender, "status": p.status}


def bed(b: m.Bed) -> dict:
    return {
        "id": b.id, "code": b.code, "ward_id": b.ward_id, "ward": b.ward.name if b.ward else None,
        "bed_type": b.bed_type, "status": b.status, "features": b.features or [],
        "patient": patient_brief(b.patient), "updated_at": _iso(b.updated_at),
    }


def ward(w: m.Ward, include_beds: bool = True) -> dict:
    beds = w.beds
    occupied = sum(1 for b in beds if b.status == "occupied")
    data = {
        "id": w.id, "name": w.name, "ward_type": w.ward_type, "floor": w.floor, "department_id": w.department_id,
        "department": w.department.name if w.department else None, "total": len(beds), "occupied": occupied,
        "available": sum(1 for b in beds if b.status == "available"),
        "reserved": sum(1 for b in beds if b.status == "reserved"),
        "cleaning": sum(1 for b in beds if b.status == "cleaning"),
        "maintenance": sum(1 for b in beds if b.status == "maintenance"),
        "occupancy": round(occupied / len(beds), 3) if beds else 0,
    }
    if include_beds:
        data["beds"] = [bed(b) for b in beds]
    return data


def resource(r: m.Resource) -> dict:
    return {
        "id": r.id, "name": r.name, "resource_type": r.resource_type, "status": r.status, "location": r.location,
        "department_id": r.department_id, "assigned_patient_id": r.assigned_patient_id,
        "usage_hours": r.usage_hours, "last_maintenance": _iso(r.last_maintenance), "next_free_at": _iso(r.next_free_at),
        **maintenance_status(r.resource_type, r.last_maintenance, r.usage_hours),
    }


def vital(v: m.VitalSign) -> dict:
    return {
        "id": v.id, "patient_id": v.patient_id, "recorded_at": _iso(v.recorded_at), "hr": v.hr, "rr": v.rr, "spo2": v.spo2,
        "sbp": v.sbp, "dbp": v.dbp, "temp": v.temp, "consciousness": v.consciousness, "on_oxygen": v.on_oxygen,
        "news2": v.news2, "risk": v.risk, "recorded_by": v.recorded_by,
    }


def surgery(s: m.Surgery) -> dict:
    return {
        "id": s.id, "patient": patient_brief(s.patient), "surgeon_id": s.surgeon_id, "surgeon": s.surgeon.name if s.surgeon else None,
        "ot_id": s.ot_id, "ot": s.ot.name if s.ot else None, "procedure": s.procedure, "specialty": s.specialty,
        "priority": s.priority, "scheduled_start": _iso(s.scheduled_start),
        "end": _iso(s.scheduled_start + timedelta(minutes=s.duration_minutes)) if s.scheduled_start else None,
        "duration_minutes": s.duration_minutes, "status": s.status, "anaesthesia": s.anaesthesia, "notes": s.notes,
        "created_by": s.created_by, "started_at": _iso(s.started_at), "completed_at": _iso(s.completed_at),
    }


def admission(a: m.Admission) -> dict:
    return {
        "id": a.id, "patient": patient_brief(a.patient), "bed": a.bed.code if a.bed else None,
        "ward": a.bed.ward.name if a.bed and a.bed.ward else None, "doctor": a.doctor.name if a.doctor else None,
        "nurse": a.nurse.name if a.nurse else None, "reason": a.reason, "acuity": a.acuity,
        "admitted_at": _iso(a.admitted_at), "expected_discharge": _iso(a.expected_discharge),
        "discharged_at": _iso(a.discharged_at), "status": a.status,
    }


def appointment(a: m.Appointment, extra: dict | None = None) -> dict:
    data = {
        "id": a.id, "patient": patient_brief(a.patient), "doctor_id": a.doctor_id,
        "doctor": a.doctor.name if a.doctor else None, "department_id": a.department_id,
        "department": a.department.name if a.department else None, "scheduled_at": _iso(a.scheduled_at),
        "status": a.status, "priority": a.priority, "reason": a.reason, "queue_number": a.queue_number,
        "checked_in_at": _iso(a.checked_in_at), "started_at": _iso(a.started_at),
        "completed_at": _iso(a.completed_at), "booked_by": a.booked_by,
    }
    if extra:
        data.update(extra)
    return data


def diagnostic(o: m.DiagnosticOrder) -> dict:
    return {
        "id": o.id, "patient": patient_brief(o.patient), "test_code": o.test_code, "test_name": o.test_name,
        "category": o.category, "priority": o.priority, "status": o.status,
        "ordered_by": o.ordered_by.name if o.ordered_by else None,
        "resource": o.resource.name if o.resource else None, "scheduled_at": _iso(o.scheduled_at),
        "result": o.result, "abnormal": o.abnormal, "created_at": _iso(o.created_at), "completed_at": _iso(o.completed_at),
    }


def medication(md: m.Medication) -> dict:
    days_left = round(md.stock / md.daily_usage, 1) if md.daily_usage else None
    return {
        "id": md.id, "name": md.name, "generic": md.generic, "drug_class": md.drug_class, "form": md.form,
        "strength": md.strength, "stock": md.stock, "reorder_level": md.reorder_level, "daily_usage": md.daily_usage,
        "unit_price": md.unit_price, "expiry": _iso(md.expiry), "days_of_stock": days_left,
        "low_stock": md.stock <= md.reorder_level,
    }


def prescription(p: m.Prescription) -> dict:
    return {
        "id": p.id, "patient": patient_brief(p.patient), "doctor": p.doctor.name if p.doctor else None,
        "medication": p.medication.name if p.medication else None,
        "generic": p.medication.generic if p.medication else None, "medication_id": p.medication_id,
        "dose": p.dose, "frequency": p.frequency, "duration_days": p.duration_days, "quantity": p.quantity,
        "status": p.status, "alerts": p.alerts or [], "notes": p.notes, "created_at": _iso(p.created_at),
    }


def emergency(e: m.EmergencyCase) -> dict:
    meta = TRIAGE_LEVELS.get(e.triage_level, {})
    waited = (datetime.now() - e.created_at).total_seconds() / 60 if e.created_at else 0
    return {
        "id": e.id, "patient": patient_brief(e.patient), "arrival_mode": e.arrival_mode,
        "chief_complaint": e.chief_complaint, "vitals": e.vitals or {}, "news2_score": e.news2_score,
        "triage_level": e.triage_level, "triage_label": meta.get("label"), "color": meta.get("color"),
        "target_minutes": meta.get("target_minutes"), "status": e.status,
        "bed": e.assigned_bed.code if e.assigned_bed else None,
        "doctor": e.assigned_doctor.name if e.assigned_doctor else None,
        "created_at": _iso(e.created_at), "seen_at": _iso(e.seen_at), "waited_minutes": round(waited),
        "breach": e.status == "triage" and waited > (meta.get("target_minutes") or 0) + 0.5,
    }


def care_task(t: m.CareTask) -> dict:
    return {
        "id": t.id, "patient_id": t.patient_id, "pathway": t.pathway, "title": t.title, "step_type": t.step_type,
        "sequence": t.sequence, "status": t.status, "assigned_role": t.assigned_role, "created_by": t.created_by,
        "request_id": t.request_id, "due_at": _iso(t.due_at), "completed_at": _iso(t.completed_at),
        "created_at": _iso(t.created_at),
    }


def approval(a: m.Approval) -> dict:
    return {
        "id": a.id, "request_id": a.request_id, "agent": a.agent, "action_type": a.action_type, "title": a.title,
        "description": a.description, "rationale": a.rationale or [], "payload": a.payload or {},
        "risk_level": a.risk_level, "required_roles": a.required_roles or [], "status": a.status,
        "decided_by": a.decided_by, "decision_note": a.decision_note, "execution_result": a.execution_result or {},
        "created_at": _iso(a.created_at), "decided_at": _iso(a.decided_at),
    }


def agent_request(r: m.AgentRequest, full: bool = True) -> dict:
    data = {
        "id": r.id, "text": r.text, "source": r.source, "status": r.status, "intents": r.intents or [],
        "nlp_engine": r.nlp_engine, "confidence": r.confidence, "patient_id": r.patient_id, "summary": r.summary,
        "duration_ms": r.duration_ms, "created_at": _iso(r.created_at), "completed_at": _iso(r.completed_at),
        "pending_approvals": sum(1 for a in r.approvals if a.status == "pending"),
    }
    if full:
        data.update({
            "entities": r.entities or {}, "plan": r.plan or [], "trace": r.trace or [], "results": r.results or {},
            "conflicts": r.conflicts or [], "approvals": [approval(a) for a in r.approvals],
        })
    return data


def notification(n: m.Notification) -> dict:
    return {
        "id": n.id, "title": n.title, "message": n.message, "level": n.level, "category": n.category,
        "channel": n.channel, "link": n.link, "read": n.read, "role": n.role, "user_id": n.user_id,
        "created_at": _iso(n.created_at),
    }


def audit(a: m.AuditLog) -> dict:
    return {
        "id": a.id, "actor": a.actor, "actor_type": a.actor_type, "action": a.action, "entity": a.entity,
        "entity_id": a.entity_id, "details": a.details or {}, "timestamp": _iso(a.timestamp),
    }


def user(u: m.User) -> dict:
    return {
        "id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email, "role": u.role,
        "department_id": u.department_id, "staff_id": u.staff_id, "patient_id": u.patient_id,
    }


# ---------------------------------------------------------------- billing
def charge(c: m.Charge) -> dict:
    return {"id": c.id, "category": c.category, "description": c.description, "quantity": c.quantity,
            "unit_price": c.unit_price, "amount": c.amount, "source_ref": c.source_ref, "created_at": _iso(c.created_at)}


def payment(p: m.Payment) -> dict:
    return {"id": p.id, "amount": p.amount, "mode": p.mode, "reference": p.reference, "received_by": p.received_by,
            "created_at": _iso(p.created_at)}


def claim(c: m.InsuranceClaim) -> dict:
    return {"id": c.id, "invoice_id": c.invoice_id, "scheme": c.scheme, "package_code": c.package_code, "package_name": c.package_name,
            "claimed_amount": c.claimed_amount, "approved_amount": c.approved_amount, "status": c.status,
            "documents": c.documents or [], "notes": c.notes, "submitted_at": _iso(c.submitted_at), "decided_at": _iso(c.decided_at),
            "invoice": c.invoice.number if c.invoice else None,
            "patient": patient_brief(c.invoice.patient) if c.invoice else None}


def invoice(inv: m.Invoice, summary: dict | None = None, detail: bool = False) -> dict:
    from .services.billing import PAYERS
    data = {"id": inv.id, "number": inv.number, "patient": patient_brief(inv.patient), "admission_id": inv.admission_id,
            "payer": inv.payer, "payer_label": PAYERS.get(inv.payer, inv.payer), "status": inv.status,
            "created_at": _iso(inv.created_at), "finalized_at": _iso(inv.finalized_at)}
    if summary:
        data["summary"] = summary
    if detail:
        data["charges"] = [charge(c) for c in inv.charges]
        data["payments"] = [payment(p) for p in inv.payments]
        data["claims"] = [claim(c) for c in inv.claims]
    return data


# ---------------------------------------------------------------- pre-hospital
def ambulance(a: m.Ambulance) -> dict:
    return {"id": a.id, "code": a.code, "vehicle_type": a.vehicle_type, "status": a.status, "base": a.base,
            "lat": round(a.lat, 5), "lng": round(a.lng, 5), "crew": a.crew or []}


def dispatch(d: m.Dispatch) -> dict:
    from .services.dispatch import SCENE_MINUTES
    if d.status == "to_scene":
        remaining = d.eta_scene_min * (1 - d.progress) + SCENE_MINUTES + d.eta_hospital_min
    elif d.status == "on_scene":
        remaining = SCENE_MINUTES * (1 - d.progress) + d.eta_hospital_min
    elif d.status == "to_hospital":
        remaining = d.eta_hospital_min * (1 - d.progress)
    else:
        remaining = 0
    return {"id": d.id, "ambulance_id": d.ambulance_id, "ambulance": d.ambulance.code if d.ambulance else None,
            "vehicle_type": d.ambulance.vehicle_type if d.ambulance else None, "patient": patient_brief(d.patient),
            "emergency_case_id": d.emergency_case_id, "request_id": d.request_id, "caller": d.caller, "locality": d.locality,
            "pickup": {"lat": d.pickup_lat, "lng": d.pickup_lng}, "complaint": d.complaint, "severity": d.severity,
            "vitals": d.vitals or {}, "status": d.status, "progress": round(d.progress, 3),
            "distance_scene_km": d.distance_scene_km, "distance_hospital_km": d.distance_hospital_km,
            "eta_scene_min": d.eta_scene_min, "eta_hospital_min": d.eta_hospital_min,
            "minutes_to_hospital": round(remaining, 1), "selection": d.selection or [],
            "created_at": _iso(d.created_at), "on_scene_at": _iso(d.on_scene_at), "departed_scene_at": _iso(d.departed_scene_at),
            "arrived_at": _iso(d.arrived_at)}


def note(n: m.ClinicalNote) -> dict:
    return {"id": n.id, "patient_id": n.patient_id, "note_type": n.note_type, "subjective": n.subjective, "objective": n.objective,
            "assessment": n.assessment, "plan": n.plan, "ai_drafted": n.ai_drafted, "status": n.status, "author": n.author,
            "created_at": _iso(n.created_at)}
