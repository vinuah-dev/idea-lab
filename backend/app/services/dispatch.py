"""Pre-hospital coordination: 108-style ambulance dispatch, live fleet tracking and pre-arrival alerts.

Nearest-capable-unit selection scores every free ambulance by its estimated time to scene
(haversine distance × road-network factor ÷ time-of-day speed) plus a capability penalty (a BLS unit
for a critical call) and a coverage penalty (keeping the hospital's own ALS unit free for critical calls).

When the crew leaves the scene the hospital receives a *pre-arrival alert*: an 'incoming' emergency case is
created and the multi-agent pipeline triages it and holds a bed and team before the patient arrives.
Map coordinates are approximate localities of Nagpur, Maharashtra (demo geography).
"""
from __future__ import annotations

import logging
import math
import random
import threading
import time
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..events import bus
from ..models import Ambulance, Bed, Dispatch, EmergencyCase, Patient
from .activity import log_audit, notify
from .triage import triage

log = logging.getLogger("medorchestra.dispatch")

HOSPITAL = {"name": settings.hospital_name, "lat": 21.1330, "lng": 79.0760}
LOCALITIES: dict[str, tuple[float, float]] = {
    "Sitabuldi": (21.1446, 79.0849), "Dharampeth": (21.1386, 79.0636), "Sadar": (21.1616, 79.0806),
    "Civil Lines": (21.1560, 79.0700), "Manish Nagar": (21.0870, 79.0822), "Wardhaman Nagar": (21.1508, 79.1339),
    "Hingna": (21.1100, 78.9850), "Mankapur": (21.1741, 79.0795), "Pratap Nagar": (21.1170, 79.0510),
    "Itwari": (21.1540, 79.1130), "Nandanvan": (21.1330, 79.1270), "Trimurti Nagar": (21.1190, 79.0560),
    "Besa": (21.0690, 79.1050), "Katol Road": (21.1840, 79.0590), "Medical Square": (21.1330, 79.1000),
    "Wadi": (21.1550, 79.0050), "Koradi": (21.2250, 79.0950), "Kamptee": (21.2200, 79.2000),
}
FLEET = [  # code, type, base locality
    ("AMB-01", "ALS", "Hospital base"), ("AMB-02", "BLS", "Sadar"), ("AMB-03", "ALS", "Manish Nagar"),
    ("AMB-04", "BLS", "Wardhaman Nagar"), ("AMB-05", "BLS", "Pratap Nagar"), ("AMB-06", "ALS", "Mankapur"),
    ("AMB-07", "BLS", "Itwari"), ("AMB-08", "BLS", "Hingna"),
]
CALL_SCENARIOS = [
    ("Road traffic accident — motorcyclist with head injury, drowsy", {"hr": 118, "rr": 22, "spo2": 94, "sbp": 102, "temp": 36.6, "consciousness": "C"}),
    ("Elderly man collapsed at home with chest pain and sweating", {"hr": 124, "rr": 24, "spo2": 92, "sbp": 94, "temp": 36.9}),
    ("Pregnant woman in active labour", {"hr": 104, "rr": 20, "spo2": 98, "sbp": 128, "temp": 37.0}),
    ("Child with high fever and a seizure", {"hr": 150, "rr": 30, "spo2": 95, "sbp": 96, "temp": 39.8}),
    ("Fall from height at a construction site", {"hr": 112, "rr": 22, "spo2": 96, "sbp": 110, "temp": 36.7}),
    ("Snake bite — swelling of the leg", {"hr": 108, "rr": 20, "spo2": 97, "sbp": 118, "temp": 37.1}),
    ("Severe breathlessness, known COPD", {"hr": 116, "rr": 28, "spo2": 88, "sbp": 132, "temp": 37.4}),
    ("Sudden slurred speech and weakness of the left side", {"hr": 90, "rr": 18, "spo2": 96, "sbp": 182, "temp": 36.8}),
]
ROAD_FACTOR = 1.35       # road distance ≈ 1.35 × straight-line distance in a dense city
SCENE_MINUTES = 4.0      # on-scene stabilisation and loading
TURNOUT_MINUTES = 1.0    # crew turnout after the call is assigned


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def speed_kmh(when: datetime | None = None) -> float:
    h = (when or datetime.now()).hour
    base = 32.0  # average urban emergency-driving speed
    if 8 <= h < 11 or 17 <= h < 21:
        return base * 0.72  # peak traffic
    if h >= 22 or h < 6:
        return base * 1.25
    return base


def road_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return haversine_km(lat1, lng1, lat2, lng2) * ROAD_FACTOR


def eta_minutes(km: float, when: datetime | None = None, turnout: bool = True) -> float:
    return km / speed_kmh(when) * 60 + (TURNOUT_MINUTES if turnout else 0)


def find_locality(text: str) -> tuple[str, float, float] | None:
    t = text.lower()
    for name, (lat, lng) in sorted(LOCALITIES.items(), key=lambda kv: -len(kv[0])):
        if name.lower() in t:
            return name, lat, lng
    return None


def predict_severity(complaint: str, vitals: dict, age: int | None = None) -> dict:
    res = triage(vitals or {}, complaint, age)
    return {"level": res.triage_level, "label": res.triage_label, "news2": res.news2, "red_flags": res.red_flags}


def rank_units(db: Session, lat: float, lng: float, severity: int) -> list[dict]:
    out = []
    now = datetime.now()
    for amb in db.scalars(select(Ambulance).where(Ambulance.status == "available")).all():
        km = road_km(amb.lat, amb.lng, lat, lng)
        eta = eta_minutes(km, now)
        factors = [{"factor": f"{km:.1f} km by road at {speed_kmh(now):.0f} km/h", "cost": round(eta, 1)}]
        if severity <= 2 and amb.vehicle_type == "BLS":
            factors.append({"factor": "BLS unit for a critical call (ALS preferred)", "cost": 6.0})
        if amb.base == "Hospital base" and amb.vehicle_type == "ALS" and severity >= 3:
            factors.append({"factor": "keeps the hospital ALS unit free for critical calls", "cost": 4.0})
        out.append({"ambulance_id": amb.id, "code": amb.code, "type": amb.vehicle_type, "base": amb.base, "km": round(km, 2),
                    "eta": round(eta, 1), "cost": round(sum(f["cost"] for f in factors), 1), "factors": factors})
    return sorted(out, key=lambda o: o["cost"])


def create_dispatch(db: Session, p: dict) -> Dispatch:
    amb = db.get(Ambulance, p["ambulance_id"])
    if amb is None or amb.status != "available":
        raise ValueError(f"Ambulance {amb.code if amb else p['ambulance_id']} is no longer available")
    lat, lng = float(p["lat"]), float(p["lng"])
    km_scene = road_km(amb.lat, amb.lng, lat, lng)
    km_hosp = road_km(lat, lng, HOSPITAL["lat"], HOSPITAL["lng"])
    d = Dispatch(ambulance_id=amb.id, patient_id=p.get("patient_id"), caller=p.get("caller", "")[:60], locality=p.get("locality", "")[:80],
                 pickup_lat=lat, pickup_lng=lng, complaint=p.get("complaint", "")[:255], severity=int(p.get("severity", 3)),
                 vitals=p.get("vitals") or {}, status="to_scene", distance_scene_km=round(km_scene, 2),
                 distance_hospital_km=round(km_hosp, 2), eta_scene_min=round(eta_minutes(km_scene), 1),
                 eta_hospital_min=round(eta_minutes(km_hosp, turnout=False), 1), selection=p.get("selection") or [])
    db.add(d)
    amb.status, amb.updated_at = "to_scene", datetime.now()
    db.flush()
    return d


def _interp(a: tuple[float, float], b: tuple[float, float], f: float) -> tuple[float, float]:
    """Point along a gently curved path from a to b (looks road-like on the map)."""
    lat = a[0] + (b[0] - a[0]) * f
    lng = a[1] + (b[1] - a[1]) * f
    bend = 0.12 * math.sin(math.pi * f)
    return lat - (b[1] - a[1]) * bend, lng + (b[0] - a[0]) * bend


def pre_arrival(db: Session, d: Dispatch, rng: random.Random | None = None) -> int | None:
    """Create the incoming ED case and start multi-agent pre-arrival coordination. Returns the request id."""
    from ..agents.orchestrator import orchestrator  # local import: avoids a cycle

    rng = rng or random.Random()
    amb = d.ambulance
    patient = db.get(Patient, d.patient_id) if d.patient_id else None
    if patient is None:
        count = db.scalar(select(func.count(Patient.id))) or 0
        age = 6 if "child" in d.complaint.lower() else 27 if "pregnan" in d.complaint.lower() else rng.randint(24, 82)
        gender = "Female" if "pregnan" in d.complaint.lower() or "woman" in d.complaint.lower() else "Male" if "man" in d.complaint.lower() else rng.choice(["Male", "Female"])
        patient = Patient(mrn=f"MRN-{1001 + count}", name=f"Ambulance patient {amb.code}-{d.id}", age=age, gender=gender,
                          status="emergency", allergies=[], conditions=[])
        db.add(patient)
        db.flush()
        d.patient_id = patient.id
    res = triage(d.vitals or {}, d.complaint, patient.age)
    case = EmergencyCase(patient_id=patient.id, arrival_mode="ambulance", chief_complaint=d.complaint, vitals=d.vitals or {},
                         news2_score=res.news2, triage_level=res.triage_level, status="incoming")
    db.add(case)
    db.flush()
    d.emergency_case_id = case.id
    patient.status = "emergency"
    eta = d.eta_hospital_min
    notify(db, f"🚑 Incoming in {eta:.0f} min: L{res.triage_level} {res.triage_label}",
           f"{amb.code} ({amb.vehicle_type}) from {d.locality}: {patient.age}{patient.gender[:1]} — {d.complaint}. "
           f"Paramedic vitals HR {d.vitals.get('hr')}, SpO₂ {d.vitals.get('spo2')}%, SBP {d.vitals.get('sbp')}.",
           level="critical" if res.triage_level <= 2 else "warning", category="ambulance", role="nurse", link="/ambulance")
    req = orchestrator.submit(db, f"Pre-arrival alert: {amb.code} bringing a {patient.age}-year-old {patient.gender.lower()} from {d.locality} — "
                                  f"{d.complaint}. ETA {eta:.0f} minutes.", None, source="ambulance", patient_id=patient.id,
                              forced_intents=["emergency"], extra_entities={"case_id": case.id, "chief_complaint": d.complaint,
                                                                            "arrival_mode": "ambulance", "eta_minutes": eta})
    d.request_id = req.id
    log_audit(db, "Ambulance Dispatch Agent", "agent", "pre_arrival_alert", "dispatch", d.id, {"case_id": case.id, "eta": eta})
    return req.id


def arrive(db: Session, d: Dispatch) -> None:
    now = datetime.now()
    d.status, d.arrived_at, d.progress = "arrived", now, 1.0
    amb = d.ambulance
    amb.status, amb.lat, amb.lng, amb.updated_at = "returning", HOSPITAL["lat"], HOSPITAL["lng"], now
    case = db.get(EmergencyCase, d.emergency_case_id) if d.emergency_case_id else None
    if case and case.status == "incoming":
        case.created_at = now  # ED clock starts at the door
        bed = db.get(Bed, case.assigned_bed_id) if case.assigned_bed_id else None
        if bed and bed.patient_id == case.patient_id and bed.status in ("reserved", "occupied"):
            bed.status = "occupied"
            case.status, case.seen_at = "in_treatment", now
            where = f"straight to pre-assigned bay {bed.code}"
        else:
            case.status = "awaiting_bed"
            where = "to triage (no bay pre-assigned)"
        notify(db, f"Ambulance {amb.code} arrived", f"Patient taken {where}. Door-to-bay time saved by pre-arrival coordination.",
               level="success" if case.status == "in_treatment" else "info", category="ambulance", role="nurse", link="/emergency")


def advance_stage(db: Session, d: Dispatch) -> int | None:
    """Jump a dispatch to its next stage (manual control for demos). Returns a new orchestration request id, if any."""
    amb = d.ambulance
    now = datetime.now()
    if d.status == "to_scene":
        d.status, d.on_scene_at, d.progress = "on_scene", now, 0.0
        amb.status, amb.lat, amb.lng = "on_scene", d.pickup_lat, d.pickup_lng
    elif d.status == "on_scene":
        d.status, d.departed_scene_at, d.progress = "to_hospital", now, 0.0
        amb.status = "to_hospital"
        return pre_arrival(db, d)
    elif d.status == "to_hospital":
        arrive(db, d)
    return None


class FleetTracker:
    """Moves ambulances along their legs in (accelerated) real time and pushes positions over the WebSocket bus."""

    def __init__(self) -> None:
        self.running = False
        self._thread: threading.Thread | None = None
        self._rng = random.Random()

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="fleet-tracker")
        self._thread.start()

    def stop(self) -> None:
        self.running = False

    def _loop(self) -> None:
        interval = 1.5
        while self.running:
            try:
                self.step(interval * settings.dispatch_time_scale / 60.0)
            except Exception:  # pragma: no cover - keep tracking alive
                log.exception("fleet step failed")
            time.sleep(interval)

    def step(self, sim_minutes: float) -> None:
        from ..agents.orchestrator import orchestrator

        db = SessionLocal()
        new_requests: list[int] = []
        changed = moved = False
        try:
            active = db.scalars(select(Dispatch).where(Dispatch.status.in_(["to_scene", "on_scene", "to_hospital"]))).all()
            for d in active:
                amb = d.ambulance
                moved = True
                if d.status == "to_scene":
                    d.progress = min(1.0, d.progress + sim_minutes / max(d.eta_scene_min, 0.5))
                    amb.lat, amb.lng = _interp((amb.base_lat, amb.base_lng), (d.pickup_lat, d.pickup_lng), d.progress)
                    if d.progress >= 1.0:
                        advance_stage(db, d)
                        changed = True
                elif d.status == "on_scene":
                    d.progress = min(1.0, d.progress + sim_minutes / SCENE_MINUTES)
                    if d.progress >= 1.0:
                        rid = advance_stage(db, d)
                        if rid:
                            new_requests.append(rid)
                        changed = True
                elif d.status == "to_hospital":
                    d.progress = min(1.0, d.progress + sim_minutes / max(d.eta_hospital_min, 0.5))
                    amb.lat, amb.lng = _interp((d.pickup_lat, d.pickup_lng), (HOSPITAL["lat"], HOSPITAL["lng"]), d.progress)
                    if d.progress >= 1.0:
                        arrive(db, d)
                        changed = True
            step_km = speed_kmh() * sim_minutes / 60 / ROAD_FACTOR
            for amb in db.scalars(select(Ambulance).where(Ambulance.status == "returning")).all():
                moved = True
                dist = haversine_km(amb.lat, amb.lng, amb.base_lat, amb.base_lng)
                if dist <= step_km or dist < 0.05:
                    amb.lat, amb.lng, amb.status = amb.base_lat, amb.base_lng, "available"
                    changed = True
                else:
                    f = step_km / dist
                    amb.lat += (amb.base_lat - amb.lat) * f
                    amb.lng += (amb.base_lng - amb.lng) * f
            if moved:
                db.commit()
                bus.publish("fleet", fleet_payload(db))
            for rid in new_requests:
                orchestrator.run_in_background(rid)
            if changed:
                bus.publish("refresh", {"scope": ["ambulance", "emergency"]})
        finally:
            db.close()


def fleet_payload(db: Session) -> dict:
    from .. import serializers as ser

    return {"ambulances": [ser.ambulance(a) for a in db.scalars(select(Ambulance).order_by(Ambulance.code)).all()],
            "dispatches": [ser.dispatch(d) for d in db.scalars(select(Dispatch).where(Dispatch.status.in_(["to_scene", "on_scene", "to_hospital"]))).all()]}


tracker = FleetTracker()
