"""Integration tests: auth/RBAC, core APIs and full multi-agent orchestration with human approval."""
from app.agents.orchestrator import orchestrator
from app.database import SessionLocal
from app.models import AgentRequest, User


def run_request(text, username="doctor", **kw):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=username).one()
        req = orchestrator.submit(db, text, user, **kw)
        rid = req.id
    finally:
        db.close()
    orchestrator.process(rid, delay=0)
    db = SessionLocal()
    try:
        r = db.get(AgentRequest, rid)
        return {"id": r.id, "status": r.status, "intents": [i["name"] for i in r.intents], "results": r.results,
                "approvals": [(a.id, a.action_type, a.status) for a in r.approvals], "conflicts": r.conflicts}
    finally:
        db.close()


def test_login_and_me(client, admin):
    assert client.get("/api/auth/me", headers=admin).json()["role"] == "admin"
    assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401


def test_rbac(client, nurse, patient_user):
    assert client.get("/api/audit", headers=nurse).status_code == 403
    assert client.get("/api/dashboard", headers=patient_user).status_code == 403
    assert client.get("/api/dashboard").status_code == 401


def test_dashboard_and_lists(client, admin):
    d = client.get("/api/dashboard", headers=admin).json()
    assert d["kpis"]["beds_total"] > 90
    for path in ("/api/wards", "/api/patients", "/api/queue", "/api/staff", "/api/diagnostics", "/api/medications",
                 "/api/emergency", "/api/analytics/forecast", "/api/analytics/bottlenecks", "/api/agents"):
        assert client.get(path, headers=admin).status_code == 200, path


def test_icu_admission_flow_with_approval(client, doctor):
    r = run_request("Patient needs admission and requires ICU monitoring with ventilator support.")
    assert r["status"] == "awaiting_approval"
    assert r["intents"][0] == "admission"
    admit = [a for a in r["approvals"] if a[1] == "admit_patient"]
    assert admit, r
    res = client.post(f"/api/approvals/{admit[0][0]}/decide", headers=doctor, json={"approve": True, "note": "ok"})
    assert res.status_code == 200 and res.json()["status"] == "executed"


def test_emergency_triage_and_rejection_releases_bed(client, doctor):
    r = run_request("Emergency: 60 year old male with chest pain, BP 88/60, HR 130, SpO2 91%, RR 26")
    assert r["results"]["emergency.triage"]["data"]["triage_level"] == 1
    assign = [a for a in r["approvals"] if a[1] == "assign_emergency"][0]
    bed_id = client.get("/api/approvals?status=pending", headers=doctor).json()
    bed_id = next(a for a in bed_id if a["id"] == assign[0])["payload"]["bed_id"]
    client.post(f"/api/approvals/{assign[0]}/decide", headers=doctor, json={"approve": False, "note": "handled manually"})
    bed = next(b for b in client.get("/api/beds", headers=doctor).json() if b["id"] == bed_id)
    assert bed["status"] == "available"


def test_allergy_is_blocked_for_override(client):
    r = run_request("Prescribe amoxicillin 500 mg BD for Rohan Mehta")
    assert any(c["type"] == "safety" for c in r["conflicts"])
    assert any(a[1] == "create_prescription" and a[2] == "pending" for a in r["approvals"])


def test_appointment_auto_executes(client):
    r = run_request("Book an appointment with a cardiologist tomorrow at 11 am for Rohan Mehta")
    assert r["status"] == "completed"
    assert r["results"]["_executed"][0]["action_type"] == "book_appointment"


def test_approver_role_enforced(client, nurse):
    r = run_request("Generate an optimized staff roster for next week", username="admin")
    ap = [a for a in r["approvals"] if a[1] == "apply_roster"][0]
    assert client.post(f"/api/approvals/{ap[0]}/decide", headers=nurse, json={"approve": True}).status_code == 403


def test_emergency_endpoint_and_preview(client, nurse):
    p = client.post("/api/emergency/triage-preview", headers=nurse, json={"chief_complaint": "stroke", "vitals": {"hr": 90}}).json()
    assert p["triage_level"] == 2
    r = client.post("/api/emergency", headers=nurse, json={"name": "Test Patient", "age": 50, "chief_complaint": "sprain", "auto_coordinate": False,
                                                           "vitals": {"hr": 80, "rr": 16, "spo2": 99, "sbp": 120, "temp": 36.8}})
    assert r.status_code == 200 and r.json()["case"]["triage_level"] == 4


def test_patient_portal(client, patient_user):
    me = client.get("/api/portal/me", headers=patient_user).json()
    assert me["patient"]["name"] == "Rohan Mehta"
    assert client.get("/api/patients/2", headers=patient_user).status_code == 403
