"""v2 modules: billing & insurance, ambulance pre-arrival, digital twin, copilot / Hinglish, readmission risk,
security hardening, public display & kiosk, clinical documentation, governance and telemetry."""
import time

from test_api import run_request
from test_extended import _wait_request

from app.agents.nlp import classify
from app.database import SessionLocal
from app.models import Admission, Bed, EmergencyCase
from app.services.hinglish import normalize
from app.services.readmission import model_card as readmission_card
from app.services.readmission import readmission_risk
from app.services.telemetry import LIMITS, PERSISTENCE, TelemetryHub


def _admitted(payer: str, skip: int = 0) -> tuple[int, str]:
    db = SessionLocal()
    try:
        for a in db.query(Admission).filter(Admission.status == "active").order_by(Admission.id).all():
            if a.patient.insurance_scheme == payer:
                if skip == 0:
                    return a.patient_id, a.patient.name
                skip -= 1
    finally:
        db.close()
    raise AssertionError(f"no admitted {payer} patient")


# ------------------------------------------------------------------ billing & insurance
def test_charge_capture_is_idempotent_and_payment_reduces_balance(client, admin):
    pid, _ = _admitted("self")
    inv = client.get(f"/api/billing/patients/{pid}", headers=admin).json()["invoice"]
    cats = {c["category"] for c in inv["charges"]}
    assert {"room", "nursing", "consultation"} <= cats and inv["summary"]["gross"] > 0
    again = client.get(f"/api/billing/patients/{pid}", headers=admin).json()["invoice"]
    assert len(again["charges"]) == len(inv["charges"])  # re-sync never duplicates charges
    bal = again["summary"]["balance"]
    assert bal > 0
    assert client.post(f"/api/billing/invoices/{inv['id']}/payments", headers=admin, json={"amount": bal + 5000, "mode": "upi"}).status_code == 400
    after = client.post(f"/api/billing/invoices/{inv['id']}/payments", headers=admin, json={"amount": 1000, "mode": "card"}).json()
    assert abs(after["summary"]["balance"] - (bal - 1000)) < 1


def test_pmjay_is_cashless_and_claim_settles(client, admin, nurse):
    pid, _ = _admitted("pmjay")
    inv = client.get(f"/api/billing/patients/{pid}", headers=admin).json()["invoice"]
    assert inv["summary"]["patient_share"] == 0 and inv["summary"]["coverage"]["package_code"].startswith(("MED", "SUR"))
    detail = client.post(f"/api/billing/invoices/{inv['id']}/claim", headers=admin).json()
    claim = detail["claims"][-1]
    assert claim["status"] == "submitted" and claim["claimed_amount"] > 0
    assert client.post(f"/api/billing/invoices/{inv['id']}/claim", headers=admin).status_code == 400  # no duplicate claims
    assert client.post(f"/api/billing/claims/{claim['id']}/decide", headers=nurse, json={"approve": True}).status_code == 403
    out = client.post(f"/api/billing/claims/{claim['id']}/decide", headers=admin, json={"approve": True}).json()
    assert out["status"] == "settled" and out["approved_amount"] == claim["claimed_amount"]


def test_cost_estimate_uses_los_interval(client, admin):
    est = client.post("/api/billing/estimate", headers=admin, json={"age": 70, "ward_type": "icu", "acuity": "critical", "comorbidities": 2,
                                                                   "emergency": True, "payer": "pmjay"}).json()
    assert est["low"] <= est["expected"] <= est["high"]
    assert est["coverage"]["covered"] > 0 and est["coverage"]["patient_share"] == 0
    assert client.get("/api/billing/summary", headers={"Authorization": "Bearer x"}).status_code == 401


def test_billing_agent_and_discharge_finalises_bill(client, doctor):
    r = run_request("What is the bill for Rohan Mehta?")
    assert r["intents"][0] == "billing" and r["results"]["billing.bill_status"]["status"] == "success"
    pid, name = _admitted("pmjay", skip=1)  # a patient without an earlier claim
    r = run_request(f"Discharge {name}", patient_id=pid)
    assert r["results"]["billing.clearance"]["status"] in ("success", "partial")
    ap = next(a for a in r["approvals"] if a[1] == "discharge_patient")
    res = client.post(f"/api/approvals/{ap[0]}/decide", headers=doctor, json={"approve": True}).json()
    assert res["status"] == "executed" and res["execution_result"]["invoice"].startswith("INV-")
    assert "claim_id" in res["execution_result"]  # PM-JAY claim filed automatically at discharge


# ------------------------------------------------------------------ ambulance pre-arrival coordination
def test_ambulance_call_prealert_and_arrival(client, nurse, doctor):
    r = client.post("/api/ambulance/calls", headers=nurse, json={"locality": "Sitabuldi", "complaint": "Elderly man collapsed with chest pain",
                                                                 "vitals": {"hr": 126, "rr": 25, "spo2": 90, "sbp": 90, "temp": 36.9}}).json()
    out = _wait_request(r["request_id"])
    assert out["status"] == "completed"  # time-critical dispatch executes without an approval hold
    fleet = client.get("/api/ambulance/fleet", headers=nurse).json()
    d = next(x for x in fleet["dispatches"] if x["locality"] == "Sitabuldi")
    assert d["status"] == "to_scene" and d["selection"] and d["severity"] <= 2
    assert client.post(f"/api/ambulance/dispatches/{d['id']}/advance", headers=nurse).json()["status"] == "on_scene"
    moving = client.post(f"/api/ambulance/dispatches/{d['id']}/advance", headers=nurse).json()
    assert moving["status"] == "to_hospital" and moving["request_id"] and moving["emergency_case_id"]
    pre = _wait_request(moving["request_id"])
    assign = next(a for a in pre["approvals"] if a[1] == "assign_emergency")
    assert client.post(f"/api/approvals/{assign[0]}/decide", headers=doctor, json={"approve": True}).json()["status"] == "executed"
    db = SessionLocal()
    try:
        case = db.get(EmergencyCase, moving["emergency_case_id"])
        assert case.status == "incoming" and db.get(Bed, case.assigned_bed_id).status == "reserved"  # bay held before arrival
    finally:
        db.close()
    assert client.post(f"/api/ambulance/dispatches/{d['id']}/advance", headers=nurse).json()["status"] == "arrived"
    db = SessionLocal()
    try:
        case = db.get(EmergencyCase, moving["emergency_case_id"])
        assert case.status == "in_treatment" and db.get(Bed, case.assigned_bed_id).status == "occupied"
    finally:
        db.close()


# ------------------------------------------------------------------ digital twin
def test_digital_twin_surge_is_worse_and_reproducible(client, admin):
    body = {"surge_pct": 90, "horizon_hours": 48, "replications": 8, "recommendations": False}
    a = client.post("/api/twin/simulate", headers=admin, json=body).json()
    b = client.post("/api/twin/simulate", headers=admin, json=body).json()
    assert len(a["timeline"]) == 49
    kb, ks = a["kpis"]["baseline"], a["kpis"]["scenario"]
    assert ks["ed_arrivals"]["mean"] > kb["ed_arrivals"]["mean"]
    assert ks["boarding_patient_hours"]["mean"] >= kb["boarding_patient_hours"]["mean"]
    assert a["kpis"] == b["kpis"]  # common random numbers → deterministic comparison


def test_what_if_through_agents():
    r = run_request("What if ER arrivals increase by 60% over the next 3 days?", username="admin")
    res = r["results"]["optimization.what_if"]
    assert res["status"] == "success" and res["data"]["scenario"]["surge_pct"] == 60


# ------------------------------------------------------------------ copilot & Hinglish
def test_hinglish_normalisation():
    n = normalize("ICU mein kitne bed khali hain?")
    assert "how many icu beds are available" in n["text"].lower() and n["hinglish"]
    assert classify(n["text"])[0]["name"] == "bed_query"
    assert normalize("Usko kal cardiology mein book karo")["has_pronoun"]
    assert "chest pain" in normalize("60 saal ka aadmi, seene mein dard")["text"]


def test_orchestrator_understands_hinglish():
    r = run_request("ICU mein kitne bed khali hain?")
    assert r["intents"][0] == "bed_query"


def _wait_copilot(client, h, rid, cid):
    for _ in range(60):
        s = client.get(f"/api/copilot/requests/{rid}?conversation_id={cid}", headers=h).json()
        if s["done"]:
            return s
        time.sleep(0.3)
    raise AssertionError("copilot request did not finish")


def test_copilot_remembers_patient_and_asks_to_clarify(client, doctor):
    r1 = client.post("/api/copilot/chat", headers=doctor, json={"message": "Where is Rohan Mehta in his care journey?"}).json()
    assert r1["type"] == "request"
    _wait_copilot(client, doctor, r1["request_id"], r1["conversation_id"])
    r2 = client.post("/api/copilot/chat", headers=doctor, json={"message": "Usko kal subah 11 baje cardiology mein book karo",
                                                                "conversation_id": r1["conversation_id"]}).json()
    assert "Rohan Mehta" in (r2["understood_as"] or "")
    s2 = _wait_copilot(client, doctor, r2["request_id"], r1["conversation_id"])
    assert "appointment" in [i["name"] for i in s2["intents"]]
    r3 = client.post("/api/copilot/chat", headers=doctor, json={"message": "Discharge the patient"}).json()
    assert r3["type"] == "clarify" and r3["options"]


# ------------------------------------------------------------------ readmission risk
def test_readmission_model_and_risk():
    card = readmission_card()
    assert card["metrics"]["auc"] > 0.65 and card["metrics"]["auc"] >= card["metrics"]["lace_only_auc"] - 0.02
    db = SessionLocal()
    try:
        a = db.query(Admission).filter(Admission.status == "active").first()
        rr = readmission_risk(db, a.patient, a)
        assert 0 <= rr["probability"] <= 1 and set(rr["lace"]["components"]) == {"L", "A", "C", "E"}
        assert rr["follow_up_days"] in (5, 10, 14)
    finally:
        db.close()


# ------------------------------------------------------------------ security
def test_login_lockout_and_security_headers(client):
    codes = [client.post("/api/auth/login", json={"username": "lab", "password": f"wrong{i}"}).status_code for i in range(5)]
    assert codes[:4] == [401] * 4 and codes[4] == 429
    assert client.post("/api/auth/login", json={"username": "lab", "password": "lab123"}).status_code == 429  # locked even with the right password
    h = client.get("/api/health")
    assert h.headers["X-Content-Type-Options"] == "nosniff" and h.headers["X-Frame-Options"] == "DENY" and h.headers.get("X-Request-ID")


def test_public_display_and_kiosk(client):
    q = client.get("/api/public/queue")
    assert q.status_code == 200 and all("patient" not in row for row in q.json()["rows"])  # tokens only, no names
    assert client.post("/api/public/kiosk/checkin", json={"mrn": "MRN-1001", "phone_last4": "0000"}).status_code == 404
    ok = client.post("/api/public/kiosk/checkin", json={"mrn": "1001", "phone_last4": "1234"}).json()
    assert ok["token"].startswith("CAR-") and ok["position"] >= 1 and ok["greeting"] == "Welcome, Rohan"


# ------------------------------------------------------------------ documentation, governance, access transparency
def test_soap_draft_note_and_sbar_handover(client, doctor, nurse):
    pid, _ = _admitted("self")
    draft = client.post(f"/api/patients/{pid}/notes/draft", headers=doctor).json()
    assert draft["ai_drafted"] and draft["status"] == "draft" and draft["objective"]
    saved = client.post(f"/api/patients/{pid}/notes", headers=doctor, json={**{k: draft[k] for k in ("subjective", "objective", "assessment", "plan")},
                                                                            "ai_drafted": True, "status": "signed"}).json()
    assert saved["status"] == "signed" and saved["ai_drafted"]
    assert any(n["id"] == saved["id"] for n in client.get(f"/api/patients/{pid}/notes", headers=nurse).json())
    ho = client.get("/api/handover", headers=nurse).json()
    assert ho["patients"] and {"situation", "background", "assessment", "recommendation"} <= set(ho["patients"][0])


def test_governance_and_record_access_log(client, admin, patient_user):
    assert client.get("/api/patients/1", headers=admin).status_code == 200
    log = client.get("/api/portal/access-log", headers=patient_user).json()
    assert any(e["action"] == "Viewed your record" for e in log)
    g = client.get("/api/governance", headers=admin).json()
    assert g["hitl"]["totals"]["total"] > 0 and g["hitl"]["auto_executed"] > 0
    nlp = g["models"]["intent_classifier"]
    assert nlp["cv_accuracy"] > 0.7 and nlp["held_out_accuracy"] >= 0.9  # leakage-free CV; held-out includes Hinglish
    assert client.get("/api/governance", headers=patient_user).status_code == 403


# ------------------------------------------------------------------ ICU telemetry
def test_smart_alarm_needs_persistence():
    hub = TelemetryHub()
    st = {"streak": {k: 0 for k in LIMITS}, "alarm": {}}
    normal = {"hr": 88, "spo2": 97, "rr": 16, "sbp": 120, "temp": 37.0}
    for _ in range(PERSISTENCE - 1):  # transient artefact
        assert hub._alarms(1, st, normal | {"spo2": 84}) == []
    hub._alarms(1, st, normal)
    assert hub.stats["suppressed"] == 1 and hub.stats["alarms"] == 0
    for i in range(PERSISTENCE):
        alarms = hub._alarms(1, st, normal | {"spo2": 84})
    assert alarms and alarms[0]["param"] == "spo2" and alarms[0]["level"] == "critical"


def test_telemetry_stream(client, nurse):
    t = client.get("/api/telemetry", headers=nurse).json()
    assert t["beds"] and {"hr", "spo2", "news2", "alarms"} <= set(t["beds"][0])
