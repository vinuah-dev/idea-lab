"""Clinical documentation: SOAP progress notes (with AI-drafted, clinician-signed drafts) and SBAR shift handover."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..database import get_db
from ..events import bus
from ..models import Admission, CareTask, ClinicalNote, DiagnosticOrder, EmergencyCase, Patient, Prescription, User, VitalSign, Ward
from ..security import STAFF_ROLES, require_roles
from ..services.activity import log_audit
from ..services.early_warning import monitoring_frequency
from ..services.los_model import predict_los
from ..services.triage import compute_news2

router = APIRouter(prefix="/api", tags=["clinical documentation"])
WRITERS = ("admin", "doctor", "nurse")


class NoteIn(BaseModel):
    note_type: str = "progress"
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""
    ai_drafted: bool = False
    status: str = "signed"


def _trend(vitals: list[VitalSign]) -> str:
    if len(vitals) < 2:
        return "stable (single reading)"
    d = vitals[-1].news2 - vitals[max(0, len(vitals) - 4)].news2
    return "worsening" if d >= 2 else "improving" if d <= -2 else "stable"


def _context(db: Session, p: Patient) -> dict:
    now = datetime.now()
    adm = db.scalar(select(Admission).where(Admission.patient_id == p.id, Admission.status == "active"))
    vit = db.scalars(select(VitalSign).where(VitalSign.patient_id == p.id, VitalSign.recorded_at >= now - timedelta(hours=36))
                     .order_by(VitalSign.recorded_at)).all()
    labs = db.scalars(select(DiagnosticOrder).where(DiagnosticOrder.patient_id == p.id, DiagnosticOrder.created_at >= now - timedelta(days=4))
                      .order_by(DiagnosticOrder.created_at.desc())).all()
    meds = db.scalars(select(Prescription).where(Prescription.patient_id == p.id, Prescription.status.in_(["pending", "verified", "dispensed"]))).all()
    tasks = db.scalars(select(CareTask).where(CareTask.patient_id == p.id, CareTask.status.in_(["pending", "in_progress"]))
                       .order_by(CareTask.due_at)).all()
    er = db.scalar(select(EmergencyCase).where(EmergencyCase.patient_id == p.id).order_by(EmergencyCase.created_at.desc()))
    return {"adm": adm, "vit": vit, "labs": labs, "meds": meds, "tasks": tasks, "er": er, "now": now}


def draft_soap(db: Session, p: Patient) -> dict:
    c = _context(db, p)
    adm, vit, labs, meds, tasks = c["adm"], c["vit"], c["labs"], c["meds"], c["tasks"]
    day = (c["now"] - adm.admitted_at).days + 1 if adm else None
    last = vit[-1] if vit else None
    abnormal = [o for o in labs if o.abnormal and o.result]
    pending = [o for o in labs if o.status not in ("completed", "cancelled")]
    s = (f"Day {day} of admission for {adm.reason.lower() or 'the presenting complaint'}." if adm else
         f"Seen for {c['er'].chief_complaint.lower()}." if c["er"] else "Outpatient review.")
    s += " [Clinician to add the patient's own account of symptoms, pain and sleep.]"
    o = []
    if last:
        o.append(f"Latest obs {last.recorded_at:%H:%M}: HR {last.hr:.0f}, RR {last.rr:.0f}, SpO₂ {last.spo2:.0f}%{' on O₂' if last.on_oxygen else ''}, "
                 f"BP {last.sbp:.0f}/{(last.dbp or 0):.0f}, T {last.temp}°C, ACVPU {last.consciousness}. NEWS2 {last.news2} ({last.risk}); trend {_trend(vit)}.")
    if abnormal:
        o.append("Abnormal results: " + "; ".join(f"{x.test_name}: {x.result}" for x in abnormal[:4]) + ".")
    if pending:
        o.append("Pending: " + ", ".join(x.test_name for x in pending[:5]) + ".")
    if meds:
        o.append("Active medicines: " + ", ".join(f"{m.medication.name} {m.dose} {m.frequency}" for m in meds[:8]) + ".")
    a = []
    if adm:
        a.append(f"{adm.reason or 'Inpatient'} — acuity {adm.acuity}.")
        try:
            pred = predict_los(p.age, adm.bed.ward.ward_type if adm.bed else "general", adm.acuity, len(p.conditions or []), False)
            a.append(f"Predicted length of stay {pred['days']} d (80% interval {pred['low']}–{pred['high']} d); currently day {day}.")
        except Exception:
            pass
    if last:
        _, comps = compute_news2(ser.vital(last))
        freq, _m = monitoring_frequency(last.news2, comps)
        a.append(f"Clinical risk {last.risk} by NEWS2; observations {freq}.")
    if p.allergies:
        a.append("Allergies: " + ", ".join(p.allergies) + ".")
    plan = [f"{t.title} ({t.assigned_role}{', due ' + t.due_at.strftime('%d %b %H:%M') if t.due_at else ''})" for t in tasks[:5]]
    if pending:
        plan.append("Review pending investigations when resulted")
    if adm and adm.expected_discharge and adm.expected_discharge <= c["now"] + timedelta(hours=24):
        plan.append("Discharge expected within 24 h — start discharge checklist and medication reconciliation")
    return {"note_type": "progress", "subjective": s, "objective": "\n".join(o) or "No observations recorded in the last 36 h.",
            "assessment": " ".join(a) or "[Clinician assessment]", "plan": "\n".join(f"- {x}" for x in plan) or "- Continue current management",
            "ai_drafted": True, "status": "draft",
            "disclaimer": "Drafted automatically from chart data for clinician review. It is not a diagnosis; edit and sign before it enters the record."}


@router.get("/patients/{pid}/notes")
def list_notes(pid: int, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    return [ser.note(n) for n in db.scalars(select(ClinicalNote).where(ClinicalNote.patient_id == pid).order_by(ClinicalNote.created_at.desc())).all()]


@router.post("/patients/{pid}/notes/draft")
def draft(pid: int, db: Session = Depends(get_db), _: User = Depends(require_roles(*WRITERS))):
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Patient not found")
    return draft_soap(db, p)


@router.post("/patients/{pid}/notes")
def add_note(pid: int, body: NoteIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*WRITERS))):
    if not db.get(Patient, pid):
        raise HTTPException(404, "Patient not found")
    if not any([body.subjective.strip(), body.objective.strip(), body.assessment.strip(), body.plan.strip()]):
        raise HTTPException(400, "Note is empty")
    n = ClinicalNote(patient_id=pid, note_type=body.note_type, subjective=body.subjective, objective=body.objective,
                     assessment=body.assessment, plan=body.plan, ai_drafted=body.ai_drafted,
                     status="signed" if body.status == "signed" else "draft", author=f"{user.full_name} ({user.role})")
    db.add(n)
    db.flush()
    log_audit(db, user.full_name, "user", "sign_note" if n.status == "signed" else "save_draft_note", "clinical_note", n.id,
              {"patient_id": pid, "ai_drafted": body.ai_drafted})
    db.commit()
    bus.publish("refresh", {"scope": ["patients"]})
    return ser.note(n)


@router.get("/handover")
def handover(ward_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    """SBAR handover for every inpatient of a ward (or all wards)."""
    now = datetime.now()
    adms = [a for a in db.scalars(select(Admission).where(Admission.status == "active")).all() if a.bed and (not ward_id or a.bed.ward_id == ward_id)]
    rows = []
    for a in adms:
        p = a.patient
        c = _context(db, p)
        vit, last = c["vit"], (c["vit"][-1] if c["vit"] else None)
        comps = compute_news2(ser.vital(last))[1] if last else {}
        freq, minutes = monitoring_frequency(last.news2, comps) if last else ("no observations", 0)
        overdue = (not last) or (now - last.recorded_at) > timedelta(minutes=minutes)
        abnormal = [o for o in c["labs"] if o.abnormal and o.result][:3]
        pending = [o for o in c["labs"] if o.status not in ("completed", "cancelled")]
        los = (now - a.admitted_at).days + 1
        flags = []
        if last and last.news2 >= 5:
            flags.append(f"NEWS2 {last.news2}")
        if overdue:
            flags.append("obs overdue")
        if p.allergies:
            flags.append("allergy")
        if a.expected_discharge and a.expected_discharge <= now + timedelta(hours=24):
            flags.append("discharge <24 h")
        rec = [t.title for t in c["tasks"][:3]]
        if last and last.news2 >= 5:
            rec.insert(0, "Hourly observations; escalate to the doctor if NEWS2 rises further")
        if pending:
            rec.append(f"Chase {', '.join(o.test_name for o in pending[:3])}")
        rows.append({
            "admission_id": a.id, "patient": ser.patient_brief(p), "bed": a.bed.code, "ward": a.bed.ward.name, "news2": last.news2 if last else None,
            "trend": _trend(vit), "flags": flags,
            "situation": f"{p.name}, {p.age}{p.gender[:1]}, bed {a.bed.code}, day {los}: {a.reason or 'inpatient care'}."
                         + (f" NEWS2 {last.news2} ({last.risk}), {_trend(vit)}." if last else " No observations yet."),
            "background": ", ".join(filter(None, [f"Conditions: {', '.join(p.conditions)}" if p.conditions else "No known comorbidities",
                                                  f"Allergies: {', '.join(p.allergies)}" if p.allergies else "NKDA",
                                                  f"under {a.doctor.name}" if a.doctor else None,
                                                  f"{len(c['meds'])} active medicines"])) + ".",
            "assessment": (f"Obs {freq}; last {last.recorded_at:%H:%M}" + (" — OVERDUE" if overdue else "") + "." if last else "Needs baseline observations.")
                          + (" Abnormal: " + "; ".join(f"{o.test_name} ({o.result[:40]})" for o in abnormal) + "." if abnormal else ""),
            "recommendation": "; ".join(rec) or "Continue current plan.",
        })
    rows.sort(key=lambda r: (-(r["news2"] if r["news2"] is not None else -1), r["bed"]))
    wards = [{"id": w.id, "name": w.name} for w in db.scalars(select(Ward).order_by(Ward.name)).all() if w.ward_type != "emergency"]
    shift = "Morning → Evening" if 6 <= now.hour < 14 else "Evening → Night" if 14 <= now.hour < 22 else "Night → Morning"
    return {"generated_at": now.isoformat(), "shift": shift, "wards": wards, "patients": rows,
            "summary": {"patients": len(rows), "high_news2": sum(1 for r in rows if (r["news2"] or 0) >= 5),
                        "obs_overdue": sum(1 for r in rows if "obs overdue" in r["flags"]),
                        "discharges_due": sum(1 for r in rows if "discharge <24 h" in r["flags"])}}
