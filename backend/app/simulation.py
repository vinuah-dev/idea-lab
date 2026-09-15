"""Live hospital simulation — generates realistic events so dashboards and agents can be demonstrated live.

Each tick may: admit an OPD walk-in, progress consultations, complete diagnostics, finish bed cleaning,
raise a ward deterioration alert, or bring in an emergency case that is routed through the full
multi-agent pipeline.
"""
from __future__ import annotations

import random
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import func, select

from .config import settings
from .database import SessionLocal
from .events import bus
from .models import Admission, Appointment, Bed, Department, DiagnosticOrder, Patient, Staff, Surgery
from .seed import FIRST_F, FIRST_M, LAST, RESULT_TEMPLATES
from .services.activity import notify
from .services.early_warning import record_vitals

ER_SCENARIOS = [
    ("Crushing chest pain and sweating for 20 minutes", {"hr": 124, "rr": 24, "spo2": 93, "sbp": 96, "temp": 36.9}),
    ("Sudden weakness of right arm and slurred speech", {"hr": 92, "rr": 18, "spo2": 96, "sbp": 178, "temp": 37.0}),
    ("Road accident — head injury, drowsy", {"hr": 118, "rr": 22, "spo2": 94, "sbp": 102, "temp": 36.5, "consciousness": "C"}),
    ("High fever, confusion and low BP — suspected sepsis", {"hr": 128, "rr": 26, "spo2": 92, "sbp": 88, "temp": 39.6}),
    ("Severe breathlessness, known asthmatic", {"hr": 122, "rr": 28, "spo2": 89, "sbp": 130, "temp": 37.2}),
    ("Fall from stairs — ankle swelling", {"hr": 88, "rr": 16, "spo2": 99, "sbp": 128, "temp": 36.8}),
    ("Vomiting and abdominal pain since night", {"hr": 102, "rr": 20, "spo2": 98, "sbp": 118, "temp": 38.2}),
    ("Dengue positive, platelet count dropping, bleeding gums", {"hr": 110, "rr": 21, "spo2": 97, "sbp": 98, "temp": 38.6}),
]


class Simulator:
    def __init__(self) -> None:
        self.running = False
        self.ticks = 0
        self.events: list[dict] = []
        self._thread: threading.Thread | None = None
        self._rng = random.Random()

    def status(self) -> dict:
        return {"running": self.running, "ticks": self.ticks, "interval": settings.simulation_interval, "events": self.events[-25:][::-1]}

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="simulator")
        self._thread.start()

    def stop(self) -> None:
        self.running = False

    def _loop(self) -> None:
        while self.running:
            try:
                self.tick()
            except Exception as exc:  # pragma: no cover - keep simulation alive
                self._log("error", str(exc))
            time.sleep(settings.simulation_interval)

    def _log(self, kind: str, text: str) -> None:
        ev = {"ts": datetime.now().isoformat(), "kind": kind, "text": text}
        self.events.append(ev)
        self.events = self.events[-100:]
        bus.publish("simulation", ev)

    def tick(self) -> None:
        self.ticks += 1
        rng = self._rng
        db = SessionLocal()
        try:
            scope = set()
            now = datetime.now()
            # 1) progress OPD consultations
            ip = db.scalars(select(Appointment).where(Appointment.status == "in_progress")).all()
            for a in ip:
                if a.started_at and (now - a.started_at) > timedelta(minutes=4):
                    a.status, a.completed_at = "completed", now
                    a.patient.status = "registered"
                    self._log("opd", f"{a.patient.name} finished consultation with {a.doctor.name if a.doctor else 'doctor'}")
                    scope.add("appointments")
                    break
            waiting = db.scalars(select(Appointment).where(Appointment.status == "checked_in").order_by(Appointment.priority, Appointment.checked_in_at)).all()
            busy = {a.doctor_id for a in db.scalars(select(Appointment).where(Appointment.status == "in_progress")).all()}
            for a in waiting:
                if a.doctor_id not in busy:
                    a.status, a.started_at = "in_progress", now
                    a.patient.status = "in_consultation"
                    self._log("opd", f"{a.patient.name} called in by {a.doctor.name if a.doctor else 'doctor'}")
                    scope.add("appointments")
                    break
            # 2) new OPD walk-in
            if rng.random() < 0.6:
                dept = rng.choice(db.scalars(select(Department).where(Department.code.in_(["GM", "CAR", "ORT", "PED", "NEU"]))).all())
                doc = rng.choice(db.scalars(select(Staff).where(Staff.role == "doctor", Staff.department_id == dept.id)).all())
                p = self._new_patient(db, rng, child=dept.code == "PED")
                n = db.query(Appointment).filter(Appointment.doctor_id == doc.id, Appointment.scheduled_at >= now.replace(hour=0, minute=0)).count()
                db.add(Appointment(patient_id=p.id, doctor_id=doc.id, department_id=dept.id, scheduled_at=now, status="checked_in",
                                   checked_in_at=now, priority=rng.choice([2, 3, 3, 4]), reason="Walk-in consultation",
                                   queue_number=n + 1, booked_by="walk-in"))
                p.status = "waiting"
                self._log("opd", f"Walk-in: {p.name} checked in to {dept.name}")
                scope.add("appointments")
            # 3) diagnostics progress
            for o in db.scalars(select(DiagnosticOrder).where(DiagnosticOrder.status.in_(["ordered", "scheduled", "in_progress"]))
                                .order_by(DiagnosticOrder.created_at).limit(2)).all():
                if o.status == "in_progress" or rng.random() < 0.4:
                    text, abnormal = rng.choice(RESULT_TEMPLATES.get(o.test_code, [("Within normal limits", False), ("Abnormal — see report", True)]))
                    o.status, o.result, o.abnormal, o.completed_at = "completed", text, abnormal, now
                    self._log("lab", f"{o.test_name} resulted for {o.patient.name}" + (" — ABNORMAL" if abnormal else ""))
                    if abnormal:
                        notify(db, f"Abnormal result: {o.test_name}", f"{o.patient.name}: {text}", level="warning",
                               category="diagnostics", role="doctor", link=f"/patients/{o.patient_id}")
                else:
                    o.status = "in_progress" if o.status == "scheduled" else "scheduled"
                scope.add("diagnostics")
            # 4) bed turnover
            for b in db.scalars(select(Bed).where(Bed.status == "cleaning")).all()[:1]:
                b.status = "available"
                self._log("bed", f"{b.code} cleaned and available")
                scope.add("beds")
            # 5) discharges for patients past their expected date
            if rng.random() < 0.3:
                adm = db.scalar(select(Admission).where(Admission.status == "active", Admission.expected_discharge < now)
                                .order_by(Admission.expected_discharge))
                if adm:
                    adm.status, adm.discharged_at = "discharged", now
                    adm.patient.status = "discharged"
                    if adm.bed:
                        adm.bed.status, adm.bed.patient_id = "cleaning", None
                    for sid in (adm.doctor_id, adm.nurse_id):
                        s = db.get(Staff, sid) if sid else None
                        if s:
                            s.current_load = max(0, s.current_load - 1)
                    self._log("discharge", f"{adm.patient.name} discharged from {adm.bed.code if adm.bed else 'ward'}")
                    scope.update({"beds", "patients"})
            # 6) bedside observations: routine rounds + occasional deterioration (NEWS2 escalation policy)
            inpatients = db.scalars(select(Admission).where(Admission.status == "active")).all()
            transfer_requests = []
            if inpatients and rng.random() < 0.6:
                adm = rng.choice(inpatients)
                vit = {"hr": rng.randint(70, 92), "rr": rng.randint(14, 19), "spo2": rng.randint(96, 99), "sbp": rng.randint(115, 138),
                       "dbp": rng.randint(68, 84), "temp": round(rng.uniform(36.5, 37.4), 1)}
                record_vitals(db, adm.patient, vit, "Bedside monitor (simulation)")
                scope.add("ward")
            if inpatients and rng.random() < 0.15:
                adm = rng.choice([a for a in inpatients if a.bed and a.bed.ward.ward_type != "icu"] or inpatients)
                vit = {"hr": rng.randint(108, 135), "rr": rng.randint(22, 28), "spo2": rng.randint(88, 93), "sbp": rng.randint(86, 104),
                       "dbp": rng.randint(50, 64), "temp": round(rng.uniform(38.2, 39.4), 1)}
                res = record_vitals(db, adm.patient, vit, "Bedside monitor (simulation)")
                self._log("alert", f"NEWS2 {res['news2']} deterioration — {adm.patient.name} ({adm.bed.code if adm.bed else 'ward'})"
                          + (" → ICU transfer proposed" if res["request_id"] else ""))
                if res["request_id"]:
                    transfer_requests.append(res["request_id"])
                scope.update({"ward", "patients"})
            # 7) theatre progress
            for s in db.scalars(select(Surgery).where(Surgery.status.in_(["scheduled", "in_progress"]))).all():
                if s.status == "scheduled" and s.scheduled_start <= now and s.scheduled_start.date() == now.date():
                    s.status, s.started_at = "in_progress", now
                    if s.ot:
                        s.ot.status = "in_use"
                    self._log("theatre", f"{s.procedure} started in {s.ot.name if s.ot else 'theatre'}")
                    scope.add("surgeries")
                elif s.status == "in_progress" and (s.started_at or s.scheduled_start) + timedelta(minutes=s.duration_minutes) <= now:
                    s.status, s.completed_at = "completed", now
                    if s.ot:
                        s.ot.status = "available"
                    self._log("theatre", f"{s.procedure} completed — {s.patient.name} to recovery")
                    scope.add("surgeries")
            db.commit()
            for rid in transfer_requests:
                from .agents.orchestrator import orchestrator
                orchestrator.run_in_background(rid)
            if scope:
                bus.publish("refresh", {"scope": sorted(scope)})
            # 8) emergency arrival → full multi-agent orchestration
            if self.ticks % 4 == 1:
                self.emergency_arrival(db, rng)
        finally:
            db.close()

    def emergency_arrival(self, db, rng) -> int:
        from .agents.orchestrator import orchestrator
        from .models import EmergencyCase
        from .services.triage import triage
        complaint, vitals = rng.choice(ER_SCENARIOS)
        p = self._new_patient(db, rng)
        res = triage(vitals, complaint, p.age)
        case = EmergencyCase(patient_id=p.id, arrival_mode=rng.choice(["ambulance", "walk-in"]), chief_complaint=complaint,
                             vitals=vitals, news2_score=res.news2, triage_level=res.triage_level, status="triage")
        db.add(case)
        db.commit()
        req = orchestrator.submit(db, f"Emergency: {p.age}-year-old {p.gender.lower()} {p.name} — {complaint}", None, source="simulation",
                                  patient_id=p.id, forced_intents=["emergency"], extra_entities={"case_id": case.id, "chief_complaint": complaint})
        self._log("emergency", f"ER arrival: {p.name} ({complaint}) → orchestrator request #{req.id}")
        bus.publish("refresh", {"scope": ["emergency"]})
        orchestrator.run_in_background(req.id)
        return req.id

    @staticmethod
    def _new_patient(db, rng, child: bool = False) -> Patient:
        gender = rng.choice(["Male", "Female"])
        count = db.scalar(select(func.count(Patient.id))) or 0
        p = Patient(mrn=f"MRN-{1001 + count}", name=f"{rng.choice(FIRST_M if gender == 'Male' else FIRST_F)} {rng.choice(LAST)}",
                    age=rng.randint(2, 12) if child else rng.randint(18, 85), gender=gender, phone=f"+91 9{rng.randint(100000000, 999999999)}",
                    blood_group=rng.choice(["A+", "B+", "O+", "AB+"]), allergies=["penicillin"] if rng.random() < 0.1 else [],
                    conditions=[], status="registered")
        db.add(p)
        db.flush()
        return p


simulator = Simulator()
