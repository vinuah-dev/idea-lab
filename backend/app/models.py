"""ORM models — the unified Patient / Resource / Workflow data model from the synopsis (§4.1)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now() -> datetime:
    return datetime.now()


# ---------------------------------------------------------------- organisation
class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    floor: Mapped[int] = mapped_column(Integer, default=0)
    avg_consult_minutes: Mapped[int] = mapped_column(Integer, default=12)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str] = mapped_column(String(20), index=True)  # admin|doctor|nurse|receptionist|lab|pharmacist|patient
    password_hash: Mapped[str] = mapped_column(String(256))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Staff(Base):
    __tablename__ = "staff"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), index=True)  # doctor|nurse|technician|pharmacist
    specialization: Mapped[str] = mapped_column(String(80), default="General")
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    seniority: Mapped[str] = mapped_column(String(20), default="mid")  # junior|mid|senior|consultant
    max_patients: Mapped[int] = mapped_column(Integer, default=8)
    current_load: Mapped[int] = mapped_column(Integer, default=0)
    on_duty: Mapped[bool] = mapped_column(Boolean, default=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    department: Mapped[Department | None] = relationship()


class Shift(Base):
    __tablename__ = "shifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    shift_type: Mapped[str] = mapped_column(String(10))  # morning|evening|night
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    generated_by: Mapped[str] = mapped_column(String(40), default="manual")

    staff: Mapped[Staff] = relationship()


# ---------------------------------------------------------------- patients
class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(primary_key=True)
    mrn: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    age: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str] = mapped_column(String(10))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    blood_group: Mapped[str | None] = mapped_column(String(5), nullable=True)
    allergies: Mapped[list] = mapped_column(JSON, default=list)
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="registered", index=True)
    # registered|waiting|in_consultation|admitted|icu|emergency|discharged
    primary_doctor_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    insurance_scheme: Mapped[str] = mapped_column(String(20), default="self")  # self|pmjay|private|cghs
    insurance_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    primary_doctor: Mapped[Staff | None] = relationship()


# ---------------------------------------------------------------- resources
class Ward(Base):
    __tablename__ = "wards"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    ward_type: Mapped[str] = mapped_column(String(20), index=True)  # general|icu|hdu|emergency|pediatric|maternity|isolation|cardiac
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    floor: Mapped[int] = mapped_column(Integer, default=1)
    nurse_ratio: Mapped[float] = mapped_column(Float, default=0.25)  # nurses per bed required

    beds: Mapped[list[Bed]] = relationship(back_populates="ward", order_by="Bed.code")
    department: Mapped[Department | None] = relationship()


class Bed(Base):
    __tablename__ = "beds"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    ward_id: Mapped[int] = mapped_column(ForeignKey("wards.id"), index=True)
    bed_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="available", index=True)
    # available|occupied|reserved|cleaning|maintenance
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True)
    features: Mapped[list] = mapped_column(JSON, default=list)  # monitor|ventilator|oxygen|isolation|cardiac_monitor
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    ward: Mapped[Ward] = relationship(back_populates="beds")
    patient: Mapped[Patient | None] = relationship()


class Resource(Base):
    """Operating rooms, diagnostic modalities and critical equipment."""

    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str] = mapped_column(String(30), index=True)
    # operating_room|ventilator|mri|ct|xray|ultrasound|ecg|dialysis|infusion_pump|defibrillator|lab_analyzer
    status: Mapped[str] = mapped_column(String(20), default="available")  # available|in_use|maintenance
    location: Mapped[str] = mapped_column(String(80), default="")
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    assigned_patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True)
    usage_hours: Mapped[float] = mapped_column(Float, default=0)
    last_maintenance: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_free_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------- workflows
class Admission(Base):
    __tablename__ = "admissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    bed_id: Mapped[int | None] = mapped_column(ForeignKey("beds.id"), nullable=True)
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    nurse_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    acuity: Mapped[str] = mapped_column(String(20), default="moderate")  # low|moderate|high|critical
    admitted_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    expected_discharge: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    discharged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active|discharged

    patient: Mapped[Patient] = relationship()
    bed: Mapped[Bed | None] = relationship()
    doctor: Mapped[Staff | None] = relationship(foreign_keys=[doctor_id])
    nurse: Mapped[Staff | None] = relationship(foreign_keys=[nurse_id])


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)
    # scheduled|checked_in|in_progress|completed|cancelled|no_show
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1 (highest) .. 5
    reason: Mapped[str] = mapped_column(String(255), default="")
    queue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    booked_by: Mapped[str] = mapped_column(String(40), default="reception")

    patient: Mapped[Patient] = relationship()
    doctor: Mapped[Staff | None] = relationship()
    department: Mapped[Department | None] = relationship()


class DiagnosticOrder(Base):
    __tablename__ = "diagnostic_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    ordered_by_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    test_code: Mapped[str] = mapped_column(String(20))
    test_name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(10))  # lab|imaging|cardiac
    priority: Mapped[str] = mapped_column(String(10), default="routine")  # routine|urgent|stat
    status: Mapped[str] = mapped_column(String(20), default="ordered", index=True)
    # ordered|scheduled|in_progress|completed|cancelled
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("resources.id"), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    abnormal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    patient: Mapped[Patient] = relationship()
    ordered_by: Mapped[Staff | None] = relationship()
    resource: Mapped[Resource | None] = relationship()


class Medication(Base):
    __tablename__ = "medications"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    generic: Mapped[str] = mapped_column(String(80))
    drug_class: Mapped[str] = mapped_column(String(60))
    form: Mapped[str] = mapped_column(String(20), default="tablet")
    strength: Mapped[str] = mapped_column(String(30), default="")
    stock: Mapped[int] = mapped_column(Integer, default=0)
    reorder_level: Mapped[int] = mapped_column(Integer, default=50)
    daily_usage: Mapped[float] = mapped_column(Float, default=10)
    unit_price: Mapped[float] = mapped_column(Float, default=1.0)
    expiry: Mapped[date | None] = mapped_column(Date, nullable=True)


class Prescription(Base):
    __tablename__ = "prescriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    medication_id: Mapped[int] = mapped_column(ForeignKey("medications.id"))
    dose: Mapped[str] = mapped_column(String(40), default="")
    frequency: Mapped[str] = mapped_column(String(40), default="BD")
    duration_days: Mapped[int] = mapped_column(Integer, default=5)
    quantity: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|verified|dispensed|rejected
    alerts: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    patient: Mapped[Patient] = relationship()
    doctor: Mapped[Staff | None] = relationship()
    medication: Mapped[Medication] = relationship()


class EmergencyCase(Base):
    __tablename__ = "emergency_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    arrival_mode: Mapped[str] = mapped_column(String(20), default="walk-in")  # walk-in|ambulance|referral
    chief_complaint: Mapped[str] = mapped_column(String(255))
    vitals: Mapped[dict] = mapped_column(JSON, default=dict)
    news2_score: Mapped[int] = mapped_column(Integer, default=0)
    triage_level: Mapped[int] = mapped_column(Integer, default=3)  # 1 resuscitation .. 5 non-urgent
    status: Mapped[str] = mapped_column(String(20), default="triage", index=True)
    # incoming (ambulance pre-alert)|triage|awaiting_bed|in_treatment|admitted|discharged
    assigned_bed_id: Mapped[int | None] = mapped_column(ForeignKey("beds.id"), nullable=True)
    assigned_doctor_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    patient: Mapped[Patient] = relationship()
    assigned_bed: Mapped[Bed | None] = relationship()
    assigned_doctor: Mapped[Staff | None] = relationship()


class CareTask(Base):
    """One step in a patient's care pathway (tracked by the Patient Care Coordinator Agent)."""

    __tablename__ = "care_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    pathway: Mapped[str] = mapped_column(String(40), default="general")  # admission|emergency|opd|discharge|diagnostic
    title: Mapped[str] = mapped_column(String(160))
    step_type: Mapped[str] = mapped_column(String(30))
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|in_progress|done|blocked
    assigned_role: Mapped[str] = mapped_column(String(20), default="nurse")
    created_by: Mapped[str] = mapped_column(String(40), default="system")
    request_id: Mapped[int | None] = mapped_column(ForeignKey("agent_requests.id"), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------------------------------------------------------- AI orchestration
class AgentRequest(Base):
    __tablename__ = "agent_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="console")  # console|emergency|simulation|api|portal
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="received", index=True)
    # received|understanding|planning|running|awaiting_approval|completed|rejected|failed
    intents: Mapped[list] = mapped_column(JSON, default=list)
    entities: Mapped[dict] = mapped_column(JSON, default=dict)
    nlp_engine: Mapped[str] = mapped_column(String(40), default="local")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    plan: Mapped[list] = mapped_column(JSON, default=list)
    trace: Mapped[list] = mapped_column(JSON, default=list)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    conflicts: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    approvals: Mapped[list[Approval]] = relationship(back_populates="request")


class Approval(Base):
    """Human-in-the-loop gate for safety-critical agent actions."""

    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("agent_requests.id"), nullable=True, index=True)
    agent: Mapped[str] = mapped_column(String(40))
    action_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[list] = mapped_column(JSON, default=list)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_level: Mapped[str] = mapped_column(String(10), default="medium")  # low|medium|high|critical
    required_roles: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|approved|rejected|executed|failed
    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    execution_result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    request: Mapped[AgentRequest | None] = relationship(back_populates="approvals")


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    role: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # broadcast to a role
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(10), default="info")  # info|success|warning|critical
    category: Mapped[str] = mapped_column(String(30), default="general")
    channel: Mapped[str] = mapped_column(String(20), default="in-app")  # in-app|sms|email
    link: Mapped[str | None] = mapped_column(String(120), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(120))
    actor_type: Mapped[str] = mapped_column(String(10))  # user|agent|system
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class VitalSign(Base):
    """Bedside observation set; each reading is NEWS2-scored for ward early-warning monitoring."""

    __tablename__ = "vital_signs"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    rr: Mapped[float | None] = mapped_column(Float, nullable=True)
    spo2: Mapped[float | None] = mapped_column(Float, nullable=True)
    sbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    dbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    consciousness: Mapped[str] = mapped_column(String(1), default="A")
    on_oxygen: Mapped[bool] = mapped_column(Boolean, default=False)
    news2: Mapped[int] = mapped_column(Integer, default=0)
    risk: Mapped[str] = mapped_column(String(12), default="low")
    recorded_by: Mapped[str] = mapped_column(String(120), default="")


class Surgery(Base):
    """Operating-theatre booking."""

    __tablename__ = "surgeries"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    surgeon_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    ot_id: Mapped[int | None] = mapped_column(ForeignKey("resources.id"), nullable=True)
    procedure: Mapped[str] = mapped_column(String(120))
    specialty: Mapped[str] = mapped_column(String(60), default="General Surgery")
    priority: Mapped[str] = mapped_column(String(12), default="elective")  # elective|urgent|emergency
    scheduled_start: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(String(15), default="scheduled", index=True)  # scheduled|in_progress|completed|cancelled
    anaesthesia: Mapped[str] = mapped_column(String(20), default="GA")
    notes: Mapped[str] = mapped_column(String(255), default="")
    created_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    patient: Mapped[Patient] = relationship()
    surgeon: Mapped[Staff | None] = relationship()
    ot: Mapped[Resource | None] = relationship()


class ClinicalNote(Base):
    """SOAP progress / handover note. AI-drafted notes stay drafts until a clinician signs them."""

    __tablename__ = "clinical_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    note_type: Mapped[str] = mapped_column(String(20), default="progress")  # progress|handover|discharge
    subjective: Mapped[str] = mapped_column(Text, default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    assessment: Mapped[str] = mapped_column(Text, default="")
    plan: Mapped[str] = mapped_column(Text, default="")
    ai_drafted: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(10), default="signed")  # draft|signed
    author: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


# ---------------------------------------------------------------- billing & insurance
class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    admission_id: Mapped[int | None] = mapped_column(ForeignKey("admissions.id"), nullable=True)
    payer: Mapped[str] = mapped_column(String(20), default="self")  # self|pmjay|private|cghs
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open|final|settled|cancelled
    discount: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    patient: Mapped[Patient] = relationship()
    charges: Mapped[list[Charge]] = relationship(back_populates="invoice", order_by="Charge.id")
    payments: Mapped[list[Payment]] = relationship(back_populates="invoice", order_by="Payment.id")
    claims: Mapped[list[InsuranceClaim]] = relationship(back_populates="invoice", order_by="InsuranceClaim.id")


class Charge(Base):
    __tablename__ = "charges"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    category: Mapped[str] = mapped_column(String(20))  # room|nursing|consultation|diagnostic|pharmacy|procedure|emergency|equipment
    description: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[float] = mapped_column(Float, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    amount: Mapped[float] = mapped_column(Float, default=0)
    source_ref: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)  # e.g. "order:12" (idempotent capture)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    invoice: Mapped[Invoice] = relationship(back_populates="charges")


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(15), default="cash")  # cash|upi|card|insurance
    reference: Mapped[str] = mapped_column(String(60), default="")
    received_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    invoice: Mapped[Invoice] = relationship(back_populates="payments")


class InsuranceClaim(Base):
    __tablename__ = "insurance_claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    scheme: Mapped[str] = mapped_column(String(20))  # pmjay|private|cghs
    package_code: Mapped[str] = mapped_column(String(20), default="")
    package_name: Mapped[str] = mapped_column(String(160), default="")
    claimed_amount: Mapped[float] = mapped_column(Float, default=0)
    approved_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(15), default="submitted", index=True)  # submitted|approved|rejected|settled
    documents: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(String(255), default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    invoice: Mapped[Invoice] = relationship(back_populates="claims")


# ---------------------------------------------------------------- pre-hospital (108 ambulance) coordination
class Ambulance(Base):
    __tablename__ = "ambulances"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True)
    vehicle_type: Mapped[str] = mapped_column(String(4), default="BLS")  # BLS|ALS
    status: Mapped[str] = mapped_column(String(20), default="available", index=True)
    # available|to_scene|on_scene|to_hospital|at_hospital|returning|maintenance
    base: Mapped[str] = mapped_column(String(60))
    base_lat: Mapped[float] = mapped_column(Float)
    base_lng: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    crew: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Dispatch(Base):
    __tablename__ = "dispatches"
    id: Mapped[int] = mapped_column(primary_key=True)
    ambulance_id: Mapped[int] = mapped_column(ForeignKey("ambulances.id"), index=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True)
    emergency_case_id: Mapped[int | None] = mapped_column(ForeignKey("emergency_cases.id"), nullable=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("agent_requests.id"), nullable=True)  # pre-arrival orchestration
    caller: Mapped[str] = mapped_column(String(60), default="")
    locality: Mapped[str] = mapped_column(String(80), default="")
    pickup_lat: Mapped[float] = mapped_column(Float)
    pickup_lng: Mapped[float] = mapped_column(Float)
    complaint: Mapped[str] = mapped_column(String(255))
    severity: Mapped[int] = mapped_column(Integer, default=3)  # predicted triage level 1..5
    vitals: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="to_scene", index=True)
    # to_scene|on_scene|to_hospital|arrived|cancelled
    distance_scene_km: Mapped[float] = mapped_column(Float, default=0)
    distance_hospital_km: Mapped[float] = mapped_column(Float, default=0)
    eta_scene_min: Mapped[float] = mapped_column(Float, default=0)
    eta_hospital_min: Mapped[float] = mapped_column(Float, default=0)
    progress: Mapped[float] = mapped_column(Float, default=0)  # 0..1 of the current leg
    selection: Mapped[list] = mapped_column(JSON, default=list)  # explainable candidate ranking
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    on_scene_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    departed_scene_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    ambulance: Mapped[Ambulance] = relationship()
    patient: Mapped[Patient | None] = relationship()


class Setting(Base):
    """Runtime-configurable policy (e.g. HITL autonomy mode)."""

    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class DailyStat(Base):
    """Historical daily operational metrics, used for analytics and demand forecasting."""

    __tablename__ = "daily_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, unique=True, index=True)
    admissions: Mapped[int] = mapped_column(Integer)
    discharges: Mapped[int] = mapped_column(Integer)
    er_visits: Mapped[int] = mapped_column(Integer)
    opd_visits: Mapped[int] = mapped_column(Integer)
    surgeries: Mapped[int] = mapped_column(Integer)
    bed_occupancy: Mapped[float] = mapped_column(Float)
    icu_occupancy: Mapped[float] = mapped_column(Float)
    avg_wait_minutes: Mapped[float] = mapped_column(Float)
