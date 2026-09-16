"""Billing, payments, insurance / PM-JAY claims and pre-admission cost estimates."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..config import settings
from ..database import get_db
from ..events import bus
from ..models import Admission, InsuranceClaim, Invoice, Patient, User
from ..security import STAFF_ROLES, require_roles
from ..services import billing
from ..services.activity import log_audit, notify

router = APIRouter(prefix="/api/billing", tags=["billing & insurance"])
DESK = ("admin", "receptionist")
VIEW = ("admin", "receptionist", "doctor")


class PaymentIn(BaseModel):
    amount: float = Field(gt=0)
    mode: str = "upi"
    reference: str = ""


class ClaimDecisionIn(BaseModel):
    approve: bool
    approved_amount: float | None = None
    note: str = ""


class EstimateIn(BaseModel):
    age: int = Field(ge=0, le=120)
    ward_type: str = "general"
    acuity: str = "moderate"
    comorbidities: int = 0
    emergency: bool = False
    procedure: str | None = None
    tests: list[str] = []
    payer: str = "self"
    ventilator: bool = False


def _detail(inv: Invoice) -> dict:
    return ser.invoice(inv, billing.summarize(inv), detail=True) | {"hospital": settings.hospital_name}


def _get(db: Session, iid: int) -> Invoice:
    inv = db.get(Invoice, iid)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return inv


@router.get("/summary")
def summary(db: Session = Depends(get_db), _: User = Depends(require_roles(*VIEW))):
    out = billing.revenue_summary(db)
    db.commit()
    return out


@router.get("/invoices")
def invoices(status: str | None = None, payer: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(*VIEW))):
    for adm in db.scalars(select(Admission).where(Admission.status == "active")).all():
        billing.sync_patient(db, adm.patient)
    db.commit()
    stmt = select(Invoice)
    if status:
        stmt = stmt.where(Invoice.status == status)
    if payer:
        stmt = stmt.where(Invoice.payer == payer)
    rows = [ser.invoice(i, billing.summarize(i)) for i in db.scalars(stmt.order_by(Invoice.created_at.desc()).limit(300)).all()]
    return sorted(rows, key=lambda r: -r["summary"]["balance"])


@router.get("/invoices/{iid}")
def invoice(iid: int, db: Session = Depends(get_db), _: User = Depends(require_roles(*VIEW))):
    inv = _get(db, iid)
    billing.sync_patient(db, inv.patient, force=True)
    db.commit()
    return _detail(inv)


@router.get("/patients/{pid}")
def patient_bill(pid: int, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF_ROLES))):
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Patient not found")
    inv = billing.sync_patient(db, p, force=True)
    db.commit()
    history = [ser.invoice(i, billing.summarize(i)) for i in db.scalars(select(Invoice).where(Invoice.patient_id == pid)
                                                                        .order_by(Invoice.created_at.desc())).all()]
    return {"invoice": _detail(inv) if inv else None, "history": history, "payer_label": billing.PAYERS.get(p.insurance_scheme or "self")}


@router.post("/invoices/{iid}/payments")
def pay(iid: int, body: PaymentIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*DESK))):
    inv = _get(db, iid)
    try:
        p = billing.record_payment(db, inv, body.amount, body.mode, body.reference or f"DESK-{inv.id}", user.full_name)
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc))
    log_audit(db, user.full_name, "user", "record_payment", "invoice", inv.id, {"amount": p.amount, "mode": p.mode})
    db.commit()
    bus.publish("refresh", {"scope": ["billing"]})
    return _detail(inv)


@router.post("/invoices/{iid}/claim")
def claim(iid: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*DESK))):
    inv = _get(db, iid)
    billing.sync_patient(db, inv.patient, force=True)
    try:
        c = billing.submit_claim(db, inv)
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc))
    log_audit(db, user.full_name, "user", "submit_claim", "invoice", inv.id, {"claim": c.id, "amount": c.claimed_amount})
    db.commit()
    bus.publish("refresh", {"scope": ["billing"]})
    return _detail(inv)


@router.get("/claims")
def claims(status: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(*VIEW))):
    stmt = select(InsuranceClaim)
    if status:
        stmt = stmt.where(InsuranceClaim.status == status)
    return [ser.claim(c) for c in db.scalars(stmt.order_by(InsuranceClaim.submitted_at.desc()).limit(200)).all()]


@router.post("/claims/{cid}/decide")
def decide_claim(cid: int, body: ClaimDecisionIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    """Record the insurer / TPA response (simulated in the demo)."""
    c = db.get(InsuranceClaim, cid)
    if not c:
        raise HTTPException(404, "Claim not found")
    try:
        billing.decide_claim(db, c, body.approve, body.approved_amount, body.note)
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc))
    log_audit(db, user.full_name, "user", "claim_decision", "insurance_claim", cid,
              {"approve": body.approve, "amount": c.approved_amount, "note": body.note})
    notify(db, f"Claim {c.status}: {c.invoice.number}", f"{c.package_name} — ₹{(c.approved_amount or 0):,.0f} {'settled' if body.approve else 'rejected'}",
           level="success" if body.approve else "warning", category="billing", role="receptionist", link="/billing")
    db.commit()
    bus.publish("refresh", {"scope": ["billing"]})
    return ser.claim(c)


@router.post("/estimate")
def estimate(body: EstimateIn, _: User = Depends(require_roles(*STAFF_ROLES))):
    return billing.estimate(**body.model_dump())


@router.get("/tariff")
def tariff(_: User = Depends(require_roles(*STAFF_ROLES))):
    from ..services.clinical import TEST_CATALOG
    from ..services.ot_scheduler import PROCEDURES
    return {"room": billing.ROOM_TARIFF, "tests": [{"code": k, "name": TEST_CATALOG.get(k, {}).get("name", k), "price": v} for k, v in billing.TEST_PRICES.items()],
            "procedures": [{"key": k, "name": PROCEDURES[k]["name"], "price": v, "pmjay_package": billing.PMJAY_SURGICAL.get(k)} for k, v in billing.PROCEDURE_PRICES.items()],
            "pmjay_medical": [{"level": k, "code": c, "name": n, "per_day": r} for k, (c, n, r) in billing.PMJAY_MEDICAL.items()],
            "payers": billing.PAYERS, "note": "Illustrative demo tariff — not an official rate card."}
