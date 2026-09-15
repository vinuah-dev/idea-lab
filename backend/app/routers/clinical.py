"""Diagnostics, pharmacy and emergency endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..agents.diagnostic_agent import schedule_slot
from ..agents.orchestrator import orchestrator
from ..database import get_db
from ..events import bus
from ..models import DiagnosticOrder, EmergencyCase, Medication, Patient, Prescription, User
from ..security import STAFF_ROLES, require_roles
from ..services.activity import log_audit, notify
from ..services.clinical import TEST_CATALOG, check_allergies, check_interactions
from ..services.triage import triage

router = APIRouter(prefix="/api", tags=["clinical"])


# ------------------------------------------------------------------ diagnostics
class OrderIn(BaseModel):
    patient_id: int
    test_code: str
    priority: str = "routine"


class OrderPatch(BaseModel):
    status: str | None = None
    result: str | None = None
    abnormal: bool | None = None


@router.get("/diagnostics/catalog")
def catalog():
    return [{"code": k, **{kk: v for kk, v in m.items() if kk != "keywords"}} for k, m in TEST_CATALOG.items()]


@router.get("/diagnostics")
def list_orders(status: str | None = None, category: str | None = None, patient_id: int | None = None, limit: int = 200,
                db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    stmt = select(DiagnosticOrder)
    if status:
        stmt = stmt.where(DiagnosticOrder.status == status)
    if category:
        stmt = stmt.where(DiagnosticOrder.category == category)
    if patient_id:
        stmt = stmt.where(DiagnosticOrder.patient_id == patient_id)
    return [ser.diagnostic(o) for o in db.scalars(stmt.order_by(DiagnosticOrder.created_at.desc()).limit(limit)).all()]


@router.post("/diagnostics")
def create_order(body: OrderIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "doctor"))):
    meta = TEST_CATALOG.get(body.test_code)
    if not meta:
        raise HTTPException(400, "Unknown test code")
    slot = schedule_slot(db, meta["modality"], body.priority)
    o = DiagnosticOrder(patient_id=body.patient_id, ordered_by_id=user.staff_id, test_code=body.test_code, test_name=meta["name"],
                        category=meta["category"], priority=body.priority, resource_id=slot["resource_id"],
                        scheduled_at=datetime.fromisoformat(slot["scheduled_at"]) if slot["scheduled_at"] else None,
                        status="scheduled" if slot["scheduled_at"] else "ordered")
    db.add(o)
    db.flush()
    log_audit(db, user.full_name, "user", "order_test", "diagnostic_order", o.id, {"test": o.test_name})
    db.commit()
    bus.publish("refresh", {"scope": ["diagnostics"]})
    return ser.diagnostic(o)


@router.patch("/diagnostics/{oid}")
def patch_order(oid: int, body: OrderPatch, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "lab", "doctor"))):
    o = db.get(DiagnosticOrder, oid)
    if not o:
        raise HTTPException(404, "Order not found")
    data = body.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(o, k, v)
    if body.result and not body.status:
        o.status = "completed"
    if o.status == "completed" and not o.completed_at:
        o.completed_at = datetime.now()
        notify(db, f"Result ready: {o.test_name}", f"{o.patient.name}: {o.result or 'report available'}",
               level="warning" if o.abnormal else "success", category="diagnostics", role="doctor", link=f"/patients/{o.patient_id}")
    log_audit(db, user.full_name, "user", "update_order", "diagnostic_order", oid, data)
    db.commit()
    bus.publish("refresh", {"scope": ["diagnostics"]})
    return ser.diagnostic(o)


# ------------------------------------------------------------------ pharmacy
class RxIn(BaseModel):
    patient_id: int
    medication_id: int
    dose: str = ""
    frequency: str = "BD"
    duration_days: int = 5


class SafetyIn(BaseModel):
    patient_id: int
    medication_id: int


class StockPatch(BaseModel):
    stock: int = Field(ge=0)


def _safety(db: Session, patient: Patient, med: Medication) -> list[dict]:
    active = db.scalars(select(Prescription).where(Prescription.patient_id == patient.id,
                                                   Prescription.status.in_(["pending", "verified", "dispensed"]))).all()
    return check_allergies(med.generic, patient.allergies or []) + check_interactions(med.generic, [r.medication.generic for r in active])


@router.get("/medications")
def medications(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    return [ser.medication(m) for m in db.scalars(select(Medication).order_by(Medication.name)).all()]


@router.patch("/medications/{mid}")
def patch_medication(mid: int, body: StockPatch, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "pharmacist"))):
    m = db.get(Medication, mid)
    if not m:
        raise HTTPException(404, "Medication not found")
    old = m.stock
    m.stock = body.stock
    log_audit(db, user.full_name, "user", "stock_update", "medication", mid, {"from": old, "to": body.stock})
    db.commit()
    bus.publish("refresh", {"scope": ["pharmacy"]})
    return ser.medication(m)


@router.get("/prescriptions")
def prescriptions(status: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    stmt = select(Prescription)
    if status:
        stmt = stmt.where(Prescription.status == status)
    return [ser.prescription(r) for r in db.scalars(stmt.order_by(Prescription.created_at.desc()).limit(200)).all()]


@router.post("/pharmacy/check")
def safety_check(body: SafetyIn, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    p, m = db.get(Patient, body.patient_id), db.get(Medication, body.medication_id)
    if not p or not m:
        raise HTTPException(404, "Patient or medication not found")
    return {"alerts": _safety(db, p, m), "stock": m.stock}


@router.post("/prescriptions")
def create_rx(body: RxIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "doctor"))):
    p, m = db.get(Patient, body.patient_id), db.get(Medication, body.medication_id)
    if not p or not m:
        raise HTTPException(404, "Patient or medication not found")
    alerts = _safety(db, p, m)
    from ..agents.executor import FREQ_PER_DAY
    rx = Prescription(patient_id=p.id, doctor_id=user.staff_id, medication_id=m.id, dose=body.dose or m.strength,
                      frequency=body.frequency, duration_days=body.duration_days,
                      quantity=FREQ_PER_DAY.get(body.frequency, 2) * body.duration_days, alerts=alerts, status="pending")
    db.add(rx)
    db.flush()
    log_audit(db, user.full_name, "user", "prescribe", "prescription", rx.id, {"medication": m.name, "alerts": len(alerts)})
    db.commit()
    bus.publish("refresh", {"scope": ["pharmacy"]})
    return ser.prescription(rx)


@router.post("/prescriptions/{rid}/{action}")
def rx_action(rid: int, action: str, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "pharmacist"))):
    rx = db.get(Prescription, rid)
    if not rx:
        raise HTTPException(404, "Prescription not found")
    flow = {"verify": ("pending", "verified"), "dispense": ("verified", "dispensed"), "reject": ("pending", "rejected")}
    if action not in flow or rx.status != flow[action][0]:
        raise HTTPException(400, f"Cannot {action} a prescription that is {rx.status}")
    if action == "verify" and any(a.get("severity") == "contraindicated" for a in rx.alerts or []):
        raise HTTPException(400, "Contraindicated — requires prescriber review; reject or ask the doctor to change it")
    if action == "dispense":
        if rx.medication.stock < rx.quantity:
            raise HTTPException(400, f"Insufficient stock ({rx.medication.stock} available)")
        rx.medication.stock -= rx.quantity
        if rx.medication.stock <= rx.medication.reorder_level:
            notify(db, f"Low stock: {rx.medication.name}", f"{rx.medication.stock} left (reorder level {rx.medication.reorder_level})",
                   level="warning", category="pharmacy", role="pharmacist", link="/pharmacy")
    rx.status = flow[action][1]
    log_audit(db, user.full_name, "user", f"rx_{action}", "prescription", rid, {"medication": rx.medication.name})
    db.commit()
    bus.publish("refresh", {"scope": ["pharmacy"]})
    return ser.prescription(rx)


# ------------------------------------------------------------------ emergency
class Vitals(BaseModel):
    hr: float | None = None
    rr: float | None = None
    spo2: float | None = None
    sbp: float | None = None
    temp: float | None = None
    consciousness: str = "A"
    on_oxygen: bool = False


class EmergencyIn(BaseModel):
    patient_id: int | None = None
    name: str | None = None
    age: int | None = None
    gender: str = "Male"
    chief_complaint: str = Field(min_length=3)
    arrival_mode: str = "walk-in"
    vitals: Vitals = Vitals()
    auto_coordinate: bool = True


class TriagePreviewIn(BaseModel):
    chief_complaint: str = ""
    age: int | None = None
    vitals: Vitals = Vitals()


class ErPatch(BaseModel):
    status: str


@router.post("/emergency/triage-preview")
def triage_preview(body: TriagePreviewIn, _: User = Depends(require_roles(*STAFF_ROLES))):
    return triage(body.vitals.model_dump(exclude_none=True), body.chief_complaint, body.age).to_dict()


@router.get("/emergency")
def list_er(active: bool = True, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    stmt = select(EmergencyCase)
    if active:
        stmt = stmt.where(EmergencyCase.status.in_(["triage", "awaiting_bed", "in_treatment"]))
    rows = db.scalars(stmt.order_by(EmergencyCase.triage_level, EmergencyCase.created_at).limit(100)).all()
    return [ser.emergency(e) for e in rows]


@router.post("/emergency")
def new_emergency(body: EmergencyIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "doctor", "nurse", "receptionist"))):
    if body.patient_id:
        p = db.get(Patient, body.patient_id)
        if not p:
            raise HTTPException(404, "Patient not found")
    else:
        count = db.scalar(select(func.count(Patient.id))) or 0
        p = Patient(mrn=f"MRN-{1001 + count}", name=body.name or f"Unknown ER Patient {count + 1}", age=body.age or 40,
                    gender=body.gender, status="emergency", allergies=[], conditions=[])
        db.add(p)
        db.flush()
    vitals = body.vitals.model_dump(exclude_none=True)
    res = triage(vitals, body.chief_complaint, p.age)
    case = EmergencyCase(patient_id=p.id, arrival_mode=body.arrival_mode, chief_complaint=body.chief_complaint, vitals=vitals,
                         news2_score=res.news2, triage_level=res.triage_level, status="triage")
    db.add(case)
    p.status = "emergency"
    log_audit(db, user.full_name, "user", "er_registration", "emergency_case", None, {"patient": p.name, "triage": res.triage_level})
    db.commit()
    request_id = None
    if body.auto_coordinate:
        req = orchestrator.submit(db, f"Emergency: {p.age}-year-old {p.gender.lower()} {p.name} — {body.chief_complaint}", user,
                                  source="emergency", patient_id=p.id, forced_intents=["emergency"],
                                  extra_entities={"case_id": case.id, "chief_complaint": body.chief_complaint})
        orchestrator.run_in_background(req.id)
        request_id = req.id
    bus.publish("refresh", {"scope": ["emergency"]})
    return {"case": ser.emergency(case), "triage": res.to_dict(), "request_id": request_id}


@router.patch("/emergency/{cid}")
def patch_er(cid: int, body: ErPatch, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "doctor", "nurse"))):
    c = db.get(EmergencyCase, cid)
    if not c:
        raise HTTPException(404, "Case not found")
    if body.status not in ("triage", "awaiting_bed", "in_treatment", "admitted", "discharged"):
        raise HTTPException(400, "Invalid status")
    c.status = body.status
    if body.status == "in_treatment" and not c.seen_at:
        c.seen_at = datetime.now()
    if body.status == "discharged":
        c.patient.status = "discharged"
        if c.assigned_bed and c.assigned_bed.patient_id == c.patient_id:
            c.assigned_bed.status, c.assigned_bed.patient_id = "cleaning", None
    log_audit(db, user.full_name, "user", "er_status", "emergency_case", cid, {"status": body.status})
    db.commit()
    bus.publish("refresh", {"scope": ["emergency", "beds"]})
    return ser.emergency(c)
