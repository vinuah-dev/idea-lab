"""Billing & insurance: automatic charge capture, LOS-aware cost estimation and PM-JAY / insurance claims.

Charges are captured idempotently from clinical activity (bed-days, nursing, doctor visits, investigations,
dispensed medicines, procedures, emergency care), so the bill is always current without manual entry.
Every captured charge carries a `source_ref` (e.g. "dx:42"), which makes re-syncing safe.

Tariffs and package rates below are illustrative demo values — not an official rate card.
PM-JAY per-day medical package rates follow the structure of the Health Benefit Package (routine ward,
HDU, ICU without / with ventilator); surgical packages are fixed-price bundles.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (Admission, Appointment, Charge, DiagnosticOrder, EmergencyCase, InsuranceClaim, Invoice, Patient,
                      Payment, Prescription, Resource, Surgery)
from .clinical import TEST_CATALOG
from .ot_scheduler import PROCEDURES

ROOM_TARIFF = {"general": 1500, "pediatric": 1800, "maternity": 2000, "isolation": 2500, "hdu": 4500, "cardiac": 6000,
               "icu": 9000, "emergency": 1200}
NURSING_PER_DAY = {"icu": 1500, "cardiac": 1200, "hdu": 1000}
DOCTOR_VISIT_PER_DAY = {"icu": 1500, "cardiac": 1200, "hdu": 1000}
DEFAULT_NURSING, DEFAULT_VISIT = 500, 800
PHARMACY_PER_DAY_ESTIMATE = {"icu": 2600, "cardiac": 1800, "hdu": 1500}
CONSULTATION_FEE = 600
EMERGENCY_FEE = 1500
VENTILATOR_PER_DAY = 3500

TEST_PRICES = {"CBC": 350, "LFT": 700, "KFT": 650, "TROP": 1200, "LIPID": 600, "HBA1C": 550, "ABG": 900, "CRP": 500,
               "BCUL": 1400, "COAG": 450, "NS1": 800, "URINE": 200, "CXR": 450, "CTH": 2800, "CTA": 4500, "MRIB": 7500,
               "USG": 1400, "ECG": 300, "ECHO": 2200}
PROCEDURE_PRICES = {"appendectomy": 45000, "cholecystectomy": 65000, "hernia": 40000, "laparotomy": 90000,
                    "debridement": 15000, "tkr": 220000, "hip": 120000, "orif": 85000, "spine": 180000, "csection": 50000,
                    "hysterectomy": 80000, "craniotomy": 250000, "cabg": 350000, "mastectomy": 110000}

# PM-JAY (Ayushman Bharat) — illustrative package mapping
PMJAY_MEDICAL = {  # per-day medical management packages by level of care
    "general": ("MED-RW", "Medical management — routine ward", 1800),
    "hdu": ("MED-HDU", "Medical management — HDU", 2700),
    "icu": ("MED-ICU", "Medical management — ICU (no ventilator)", 3600),
    "icu_vent": ("MED-ICUV", "Medical management — ICU with ventilator", 4500),
}
PMJAY_SURGICAL = {"appendectomy": 22000, "cholecystectomy": 30000, "hernia": 20000, "laparotomy": 35000, "debridement": 8000,
                  "tkr": 80000, "hip": 45000, "orif": 40000, "spine": 60000, "csection": 12000, "hysterectomy": 30000,
                  "craniotomy": 80000, "cabg": 120000, "mastectomy": 40000}
PMJAY_FAMILY_COVER = 500000
PRIVATE_COPAY, PRIVATE_SUM_INSURED = 0.10, 300000

PAYERS = {"self": "Self-pay", "pmjay": "PM-JAY (Ayushman Bharat)", "private": "Private health insurance (TPA)"}
CLAIM_DOCUMENTS = ["Pre-authorisation form", "Discharge summary", "Investigation reports", "Itemised final bill",
                   "Identity / beneficiary e-card"]

_LEVEL = {"general": 0, "pediatric": 0, "maternity": 0, "isolation": 0, "emergency": 0, "hdu": 1, "cardiac": 1, "icu": 2}
_recent_sync: dict[int, float] = {}


def procedure_key(name: str) -> str | None:
    for key, meta in PROCEDURES.items():
        if meta["name"] == name or key == name:
            return key
    return None


def _days(start: datetime, end: datetime) -> int:
    return max(1, math.ceil((end - start).total_seconds() / 86400))


def _pmjay_level(ward_type: str, ventilator: bool) -> str:
    if ward_type == "icu":
        return "icu_vent" if ventilator else "icu"
    return "hdu" if ward_type in ("hdu", "cardiac") else "general"


# ------------------------------------------------------------------ invoices & charge capture
def _new_number(db: Session) -> str:
    n = (db.scalar(select(func.count(Invoice.id))) or 0) + 1
    return f"INV-{datetime.now():%Y}-{n:05d}"


def open_invoice(db: Session, patient: Patient, admission: Admission | None = None, create: bool = True) -> Invoice | None:
    stmt = select(Invoice).where(Invoice.patient_id == patient.id, Invoice.status.in_(["open", "final"]))
    if admission:
        inv = db.scalar(stmt.where(Invoice.admission_id == admission.id))
        if inv or not create:
            return inv
    else:
        inv = db.scalar(stmt.where(Invoice.admission_id.is_(None)).order_by(Invoice.created_at.desc()))
        if inv or not create:
            return inv
    inv = Invoice(number=_new_number(db), patient_id=patient.id, admission_id=admission.id if admission else None,
                  payer=patient.insurance_scheme or "self", status="open")
    db.add(inv)
    db.flush()
    return inv


def _upsert(db: Session, inv: Invoice, ref: str, category: str, description: str, qty: float, unit: float) -> None:
    ch = next((c for c in inv.charges if c.source_ref == ref), None)
    amount = round(qty * unit, 2)
    if ch is None:
        ch = Charge(invoice_id=inv.id, category=category, source_ref=ref)
        db.add(ch)
        inv.charges.append(ch)
    ch.description, ch.quantity, ch.unit_price, ch.amount = description, qty, unit, amount


def _episode(db: Session, patient: Patient) -> tuple[Admission | None, datetime, datetime]:
    """Current billing episode: the active admission, or one discharged within 7 days, else a 30-day OPD window."""
    now = datetime.now()
    adm = db.scalar(select(Admission).where(Admission.patient_id == patient.id).order_by(Admission.admitted_at.desc()))
    if adm and (adm.status == "active" or (adm.discharged_at and adm.discharged_at > now - timedelta(days=7))):
        return adm, adm.admitted_at - timedelta(hours=12), adm.discharged_at or now
    return None, now - timedelta(days=30), now


def sync_patient(db: Session, patient: Patient, force: bool = False) -> Invoice | None:
    """Capture all billable activity for the patient's current episode (idempotent)."""
    if not force and time.time() - _recent_sync.get(patient.id, 0) < 15:
        adm, _, _ = _episode(db, patient)
        return open_invoice(db, patient, adm, create=False)
    adm, start, end = _episode(db, patient)
    rows: list[tuple] = []  # (ref, category, description, qty, unit)
    if adm:
        ward_type = adm.bed.ward.ward_type if adm.bed else "general"
        ward = adm.bed.ward.name if adm.bed else "Ward"
        days = _days(adm.admitted_at, adm.discharged_at or datetime.now())
        rows.append((f"room:{adm.id}", "room", f"{ward} — bed charges ({days} day{'s' if days > 1 else ''})", days, ROOM_TARIFF.get(ward_type, 1500)))
        rows.append((f"nursing:{adm.id}", "nursing", "Nursing care", days, NURSING_PER_DAY.get(ward_type, DEFAULT_NURSING)))
        rows.append((f"visit:{adm.id}", "consultation", "Consultant daily visits", days, DOCTOR_VISIT_PER_DAY.get(ward_type, DEFAULT_VISIT)))
        for r in db.scalars(select(Resource).where(Resource.assigned_patient_id == patient.id, Resource.resource_type == "ventilator")).all():
            rows.append((f"vent:{r.id}", "equipment", f"Ventilator support ({r.name})", days, VENTILATOR_PER_DAY))
    else:
        for a in db.scalars(select(Appointment).where(Appointment.patient_id == patient.id, Appointment.status == "completed",
                                                      Appointment.scheduled_at >= start)).all():
            rows.append((f"opd:{a.id}", "consultation", f"OPD consultation — {a.department.name if a.department else 'clinic'}", 1, CONSULTATION_FEE))
    for o in db.scalars(select(DiagnosticOrder).where(DiagnosticOrder.patient_id == patient.id, DiagnosticOrder.created_at >= start,
                                                      DiagnosticOrder.status.in_(["in_progress", "completed"]))).all():
        rows.append((f"dx:{o.id}", "diagnostic", o.test_name, 1, TEST_PRICES.get(o.test_code, 500)))
    for r in db.scalars(select(Prescription).where(Prescription.patient_id == patient.id, Prescription.status == "dispensed",
                                                   Prescription.created_at >= start)).all():
        rows.append((f"rx:{r.id}", "pharmacy", f"{r.medication.name} {r.medication.strength}", r.quantity, r.medication.unit_price))
    for s in db.scalars(select(Surgery).where(Surgery.patient_id == patient.id, Surgery.status.in_(["in_progress", "completed"]),
                                              Surgery.scheduled_start >= start)).all():
        key = procedure_key(s.procedure)
        rows.append((f"sx:{s.id}", "procedure", f"{s.procedure} — surgeon, theatre & anaesthesia", 1, PROCEDURE_PRICES.get(key, 50000)))
    for c in db.scalars(select(EmergencyCase).where(EmergencyCase.patient_id == patient.id, EmergencyCase.created_at >= start,
                                                    EmergencyCase.status != "incoming")).all():
        rows.append((f"er:{c.id}", "emergency", f"Emergency care — triage L{c.triage_level}", 1, EMERGENCY_FEE))
    _recent_sync[patient.id] = time.time()
    if not rows:
        return open_invoice(db, patient, adm, create=False)
    inv = open_invoice(db, patient, adm)
    for row in rows:
        _upsert(db, inv, *row)
    db.flush()
    return inv


# ------------------------------------------------------------------ coverage & totals
def coverage(inv: Invoice) -> dict:
    gross = sum(c.amount for c in inv.charges)
    net = max(0.0, gross - (inv.discount or 0))
    payer = inv.payer or "self"
    if payer == "pmjay":
        surg = next((c for c in inv.charges if c.category == "procedure"), None)
        if surg:
            key = next((k for k, m in PROCEDURES.items() if surg.description.startswith(m["name"])), None)
            rate = PMJAY_SURGICAL.get(key or "", 25000)
            code, name, covered = f"SUR-{(key or 'GEN').upper()[:6]}", f"Surgical package — {surg.description.split(' — ')[0]}", float(rate)
        else:
            room = next((c for c in inv.charges if c.category == "room"), None)
            ward_type = "general"
            if room:
                for wt, price in ROOM_TARIFF.items():
                    if price == room.unit_price:
                        ward_type = wt
                        break
            level = _pmjay_level(ward_type, any(c.category == "equipment" for c in inv.charges))
            code, name, per_day = PMJAY_MEDICAL[level]
            days = room.quantity if room else 1
            covered = float(per_day * days)
        covered = min(covered, PMJAY_FAMILY_COVER)
        return {"payer": payer, "payer_label": PAYERS[payer], "package_code": code, "package_name": name,
                "covered": round(covered, 2), "patient_share": 0.0, "adjustment": round(max(0.0, net - covered), 2),
                "note": "Cashless — the hospital is reimbursed the package rate; the difference is a package adjustment."}
    if payer == "private":
        covered = min(net * (1 - PRIVATE_COPAY), PRIVATE_SUM_INSURED)
        return {"payer": payer, "payer_label": PAYERS[payer], "package_code": "TPA", "package_name": "Cashless hospitalisation (10% co-pay)",
                "covered": round(covered, 2), "patient_share": round(net - covered, 2), "adjustment": 0.0,
                "note": f"Sum insured ₹{PRIVATE_SUM_INSURED:,}; co-payment {int(PRIVATE_COPAY * 100)}%."}
    return {"payer": "self", "payer_label": PAYERS["self"], "package_code": "", "package_name": "", "covered": 0.0,
            "patient_share": round(net, 2), "adjustment": 0.0, "note": "Self-pay."}


def summarize(inv: Invoice) -> dict:
    gross = round(sum(c.amount for c in inv.charges), 2)
    net = round(max(0.0, gross - (inv.discount or 0)), 2)
    cov = coverage(inv)
    paid = round(sum(p.amount for p in inv.payments if p.mode != "insurance"), 2)
    insurance_paid = round(sum(p.amount for p in inv.payments if p.mode == "insurance"), 2)
    claim = inv.claims[-1] if inv.claims else None
    rejected = claim is not None and claim.status == "rejected"
    expected_insurance = 0.0 if rejected or cov["payer"] == "self" else cov["covered"]
    if claim and claim.approved_amount is not None and not rejected:
        expected_insurance = claim.approved_amount
    patient_share = net if (rejected or cov["payer"] == "self") else (0.0 if cov["payer"] == "pmjay" else max(0.0, net - expected_insurance))
    balance = round(max(0.0, patient_share - paid), 2)
    by_cat: dict[str, float] = {}
    for c in inv.charges:
        by_cat[c.category] = round(by_cat.get(c.category, 0) + c.amount, 2)
    return {"gross": gross, "discount": inv.discount or 0, "net": net, "coverage": cov, "expected_insurance": round(expected_insurance, 2),
            "insurance_paid": insurance_paid, "patient_share": round(patient_share, 2), "paid": paid, "balance": balance,
            "by_category": dict(sorted(by_cat.items(), key=lambda kv: -kv[1])),
            "claim_status": claim.status if claim else None, "cleared": balance <= 0.5}


# ------------------------------------------------------------------ estimation
def estimate(age: int, ward_type: str = "general", acuity: str = "moderate", comorbidities: int = 0, emergency: bool = False,
             procedure: str | None = None, tests: list[str] | None = None, payer: str = "self", ventilator: bool = False) -> dict:
    """Pre-admission cost estimate. The stay length comes from the LOS model's 10th–90th percentile interval."""
    from .los_model import predict_los

    los = predict_los(age, ward_type, acuity, comorbidities, emergency)
    per_day = (ROOM_TARIFF.get(ward_type, 1500) + NURSING_PER_DAY.get(ward_type, DEFAULT_NURSING)
               + DOCTOR_VISIT_PER_DAY.get(ward_type, DEFAULT_VISIT) + PHARMACY_PER_DAY_ESTIMATE.get(ward_type, 700)
               + (VENTILATOR_PER_DAY if ventilator else 0))
    fixed = []
    if emergency:
        fixed.append(("Emergency care", EMERGENCY_FEE))
    key = procedure_key(procedure) if procedure else None
    if key:
        fixed.append((PROCEDURES[key]["name"], PROCEDURE_PRICES[key]))
    for code in tests or []:
        if code in TEST_PRICES:
            fixed.append((TEST_CATALOG.get(code, {}).get("name", code), TEST_PRICES[code]))
    lab_allowance = 1200 * min(los["days"], 10)  # routine monitoring labs
    fixed_total = sum(v for _, v in fixed) + lab_allowance

    def total(days: float) -> float:
        return round(per_day * max(days, 1) + fixed_total, -2)

    expected, low, high = total(los["days"]), total(los["low"]), total(los["high"])
    breakdown = [{"item": f"Bed, nursing, visits & medicines (₹{per_day:,.0f}/day × {los['days']} days)", "amount": round(per_day * los["days"], -2)},
                 {"item": "Routine monitoring investigations", "amount": round(lab_allowance, -2)}] + [{"item": n, "amount": v} for n, v in fixed]
    cov_payer = payer if payer in PAYERS else "self"
    if cov_payer == "pmjay":
        if key:
            covered = PMJAY_SURGICAL.get(key, 25000)
            pkg = f"Surgical package — {PROCEDURES[key]['name']}"
        else:
            code, pkg, rate = PMJAY_MEDICAL[_pmjay_level(ward_type, ventilator)]
            covered = rate * max(los["days"], 1)
        cov = {"payer": "pmjay", "package_name": pkg, "covered": round(min(covered, PMJAY_FAMILY_COVER), -2), "patient_share": 0}
    elif cov_payer == "private":
        covered = min(expected * (1 - PRIVATE_COPAY), PRIVATE_SUM_INSURED)
        cov = {"payer": "private", "package_name": "Cashless (10% co-pay)", "covered": round(covered, -2), "patient_share": round(expected - covered, -2)}
    else:
        cov = {"payer": "self", "package_name": "", "covered": 0, "patient_share": expected}
    return {"los": los, "per_day": per_day, "expected": expected, "low": low, "high": high, "breakdown": breakdown,
            "coverage": cov | {"payer_label": PAYERS[cov["payer"]]},
            "assumptions": "Illustrative tariff; stay length from the LOS model's 80% prediction interval."}


# ------------------------------------------------------------------ payments & claims
class BillingError(Exception):
    pass


def record_payment(db: Session, inv: Invoice, amount: float, mode: str, reference: str, actor: str) -> Payment:
    if amount <= 0:
        raise BillingError("Amount must be positive")
    if mode not in ("cash", "upi", "card"):
        raise BillingError("Payment mode must be cash, upi or card")
    bal = summarize(inv)["balance"]
    if amount > bal + 1:
        raise BillingError(f"Amount exceeds outstanding balance (₹{bal:,.2f})")
    p = Payment(invoice_id=inv.id, amount=round(amount, 2), mode=mode, reference=reference[:60], received_by=actor)
    db.add(p)
    inv.payments.append(p)
    db.flush()
    _settle_if_cleared(inv)
    return p


def _settle_if_cleared(inv: Invoice) -> None:
    s = summarize(inv)
    pending_claim = inv.claims and inv.claims[-1].status == "submitted"
    if s["cleared"] and not pending_claim and inv.status in ("open", "final") and inv.finalized_at:
        inv.status = "settled"


def submit_claim(db: Session, inv: Invoice) -> InsuranceClaim:
    if (inv.payer or "self") == "self":
        raise BillingError("Self-pay invoice — no insurance scheme on record")
    if inv.claims and inv.claims[-1].status in ("submitted", "approved", "settled"):
        raise BillingError(f"A claim is already {inv.claims[-1].status} for {inv.number}")
    cov = coverage(inv)
    if cov["covered"] <= 0:
        raise BillingError("Nothing billable to claim yet")
    claim = InsuranceClaim(invoice_id=inv.id, scheme=inv.payer, package_code=cov["package_code"], package_name=cov["package_name"],
                           claimed_amount=cov["covered"], status="submitted", documents=list(CLAIM_DOCUMENTS))
    db.add(claim)
    inv.claims.append(claim)
    db.flush()
    return claim


def decide_claim(db: Session, claim: InsuranceClaim, approve: bool, approved_amount: float | None, note: str = "") -> InsuranceClaim:
    if claim.status != "submitted":
        raise BillingError(f"Claim already {claim.status}")
    claim.decided_at = datetime.now()
    claim.notes = note[:255]
    if approve:
        amt = round(min(approved_amount if approved_amount is not None else claim.claimed_amount, claim.claimed_amount), 2)
        claim.approved_amount, claim.status = amt, "settled"
        db.add(Payment(invoice_id=claim.invoice_id, amount=amt, mode="insurance", reference=f"{claim.scheme.upper()}-CLM-{claim.id}",
                       received_by="Insurer / TPA"))
    else:
        claim.status, claim.approved_amount = "rejected", 0
    db.flush()
    db.refresh(claim.invoice)
    _settle_if_cleared(claim.invoice)
    return claim


def finalize(db: Session, inv: Invoice) -> None:
    if inv.status == "open":
        inv.status, inv.finalized_at = "final", datetime.now()
    _settle_if_cleared(inv)


# ------------------------------------------------------------------ hospital-level revenue view
def revenue_summary(db: Session) -> dict:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for adm in db.scalars(select(Admission).where(Admission.status == "active")).all():
        sync_patient(db, adm.patient)
    invoices = db.scalars(select(Invoice).where(Invoice.status != "cancelled")).all()
    outstanding = claims_pending = claims_amount = adjustments = gross = 0.0
    payer_mix: dict[str, int] = {}
    by_cat: dict[str, float] = {}
    for inv in invoices:
        s = summarize(inv)
        gross += s["gross"]
        outstanding += s["balance"]
        adjustments += s["coverage"]["adjustment"]
        payer_mix[inv.payer] = payer_mix.get(inv.payer, 0) + 1
        for k, v in s["by_category"].items():
            by_cat[k] = by_cat.get(k, 0) + v
        if inv.claims and inv.claims[-1].status == "submitted":
            claims_pending += 1
            claims_amount += inv.claims[-1].claimed_amount
    collected_today = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.created_at >= today)) or 0
    billed_today = db.scalar(select(func.coalesce(func.sum(Charge.amount), 0)).where(Charge.created_at >= today)) or 0
    return {"invoices": len(invoices), "gross_billed": round(gross, 2), "outstanding": round(outstanding, 2),
            "collected_today": round(float(collected_today), 2), "captured_today": round(float(billed_today), 2),
            "claims_pending": int(claims_pending), "claims_pending_amount": round(claims_amount, 2),
            "pmjay_adjustments": round(adjustments, 2), "payer_mix": payer_mix,
            "by_category": dict(sorted(((k, round(v, 2)) for k, v in by_cat.items()), key=lambda kv: -kv[1]))}
