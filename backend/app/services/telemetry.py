"""Bedside telemetry simulation for the ICU central monitor.

Streams vitals every ~2 s for patients in critical-care beds (ICU / CCU / HDU) over the WebSocket bus.
Each signal is a mean-reverting random walk anchored on the patient's last charted observation, with
occasional sensor artefacts (motion, probe displacement).

Smart alarms: a limit breach must persist for 3 consecutive readings before it alarms, which suppresses
transient artefacts — a standard alarm-fatigue mitigation. Suppressed transients are counted so the
benefit is measurable.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime

from sqlalchemy import select

from ..config import settings
from ..database import SessionLocal
from ..events import bus
from ..models import Admission
from .early_warning import latest_vitals
from .triage import compute_news2

log = logging.getLogger("medorchestra.telemetry")

CRITICAL_WARDS = ("icu", "cardiac", "hdu")
LIMITS = {  # param: (low, high, label, unit)
    "hr": (45, 130, "Heart rate", "/min"), "spo2": (90, None, "SpO₂", "%"), "sbp": (90, 180, "Systolic BP", "mmHg"),
    "rr": (8, 28, "Resp. rate", "/min"), "temp": (35.5, 38.6, "Temperature", "°C"),
}
PERSISTENCE = 3
DEFAULTS = {"hr": 88.0, "spo2": 96.0, "rr": 18.0, "sbp": 118.0, "dbp": 72.0, "temp": 37.0}
NOISE = {"hr": 2.2, "spo2": 0.6, "rr": 0.8, "sbp": 2.5, "dbp": 1.8, "temp": 0.04}


class TelemetryHub:
    def __init__(self) -> None:
        self.running = False
        self._thread: threading.Thread | None = None
        self._rng = random.Random()
        self.state: dict[int, dict] = {}
        self.last: dict = {"ts": None, "beds": [], "stats": {}}
        self.stats = {"readings": 0, "breach_readings": 0, "alarms": 0, "suppressed": 0}
        self.acks: dict[int, float] = {}
        self._lock = threading.Lock()

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="telemetry")
        self._thread.start()

    def stop(self) -> None:
        self.running = False

    def _loop(self) -> None:
        while self.running:
            try:
                if bus.count > 0:  # nobody watching → no work
                    self.tick()
            except Exception:  # pragma: no cover
                log.exception("telemetry tick failed")
            time.sleep(settings.telemetry_interval)

    def ack(self, patient_id: int) -> None:
        self.acks[patient_id] = time.time()

    def tick(self) -> dict:
        rng = self._rng
        db = SessionLocal()
        try:
            adms = [a for a in db.scalars(select(Admission).where(Admission.status == "active")).all()
                    if a.bed and a.bed.ward.ward_type in CRITICAL_WARDS]
            latest = latest_vitals(db, [a.patient_id for a in adms])
            beds = []
            with self._lock:
                seen = set()
                for a in sorted(adms, key=lambda x: x.bed.code):
                    pid = a.patient_id
                    seen.add(pid)
                    lv = latest.get(pid)
                    anchor = {k: (getattr(lv, k) if lv is not None and getattr(lv, k) is not None else DEFAULTS[k]) for k in DEFAULTS}
                    st = self.state.get(pid)
                    if st is None:
                        st = {"v": dict(anchor), "streak": {k: 0 for k in LIMITS}, "alarm": {}, "on_o2": bool(lv.on_oxygen) if lv else False,
                              "consciousness": lv.consciousness if lv else "A"}
                        self.state[pid] = st
                    v = st["v"]
                    for k in DEFAULTS:
                        v[k] += 0.12 * (anchor[k] - v[k]) + rng.gauss(0, NOISE[k])
                    v["spo2"] = min(100.0, v["spo2"])
                    reading = {k: round(v[k], 1 if k == "temp" else 0) for k in v}
                    if rng.random() < 0.04:  # sensor artefact on one channel for one reading
                        ch = rng.choice(["spo2", "hr"])
                        reading[ch] = reading[ch] - 14 if ch == "spo2" else reading[ch] + 45
                    news2, _ = compute_news2({**reading, "on_oxygen": st["on_o2"], "consciousness": st["consciousness"]})
                    alarms = self._alarms(pid, st, reading)
                    beds.append({"patient_id": pid, "name": a.patient.name, "mrn": a.patient.mrn, "age": a.patient.age,
                                 "gender": a.patient.gender, "bed": a.bed.code, "ward": a.bed.ward.name, "ward_type": a.bed.ward.ward_type,
                                 "reason": a.reason, "on_oxygen": st["on_o2"], "news2": news2, **reading, "alarms": alarms,
                                 "acked": time.time() - self.acks.get(pid, 0) < 120})
                for pid in list(self.state):
                    if pid not in seen:
                        self.state.pop(pid, None)
                self.stats["readings"] += len(beds)
                payload = {"ts": datetime.now().isoformat(), "beds": beds, "stats": dict(self.stats),
                           "persistence": PERSISTENCE}
                self.last = payload
            bus.publish("telemetry", payload)
            return payload
        finally:
            db.close()

    def _alarms(self, pid: int, st: dict, reading: dict) -> list[dict]:
        out = []
        for k, (lo, hi, label, unit) in LIMITS.items():
            val = reading.get(k)
            breach = val is not None and ((lo is not None and val < lo) or (hi is not None and val > hi))
            if breach:
                st["streak"][k] += 1
                self.stats["breach_readings"] += 1
                if st["streak"][k] == PERSISTENCE:
                    self.stats["alarms"] += 1
                    st["alarm"][k] = datetime.now().isoformat()
            else:
                if 0 < st["streak"][k] < PERSISTENCE:
                    self.stats["suppressed"] += 1
                st["streak"][k] = 0
                st["alarm"].pop(k, None)
            if k in st["alarm"]:
                severe = (k == "spo2" and val < 85) or (k == "hr" and (val > 150 or val < 40)) or (k == "sbp" and val < 80)
                out.append({"param": k, "label": label, "value": val, "unit": unit, "level": "critical" if severe else "warning",
                            "since": st["alarm"][k], "message": f"{label} {'low' if lo is not None and val < lo else 'high'}: {val}{unit}"})
        return out


hub = TelemetryHub()
