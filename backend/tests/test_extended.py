"""Tests for ward monitoring, theatre scheduling, LOS prediction, autonomy policy, users and search."""
import time
from datetime import date, timedelta

from test_api import run_request

from app.database import SessionLocal
from app.models import AgentRequest, Surgery
from app.services.los_model import model_card, predict_los
from app.services.ot_scheduler import TURNOVER


def _wait_request(rid, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        db = SessionLocal()
        try:
            r = db.get(AgentRequest, rid)
            if r.status in ("completed", "awaiting_approval", "failed", "rejected"):
                return {"status": r.status, "approvals": [(a.id, a.action_type, a.title) for a in r.approvals]}
        finally:
            db.close()
        time.sleep(0.3)
    raise AssertionError("orchestration did not finish")


def test_los_model_quality():
    card = model_card()
    m = card["metrics"]
    assert m["mae_days"] < 0.8 * m["baseline_mae_days"]  # clearly better than predicting the median stay
    assert m["r2"] > 0.3 and 0.7 <= m["interval_coverage"] <= 0.9
    icu = predict_los(72, "icu", "critical", 3, True)
    ward = predict_los(30, "general", "low", 0, False)
    assert icu["days"] > ward["days"]
    assert icu["low"] <= icu["days"] <= icu["high"]


def test_ot_slot_on_empty_day_starts_at_8(client, admin):
    day = (date.today() + timedelta(days=3)).isoformat()
    slots = client.get(f"/api/ot/slots?duration=90&day={day}", headers=admin).json()
    assert slots and slots[0]["start"][11:16] == "08:00"


def test_ot_optimizer_removes_overtime_without_overlap(client, admin):
    day = (date.today() + timedelta(days=1)).isoformat()
    res = client.post(f"/api/ot/optimize?day={day}", headers=admin).json()
    assert res["status"] in ("OPTIMAL", "FEASIBLE")
    assert res["before"]["overtime_minutes"] > 0
    assert res["after"]["overtime_minutes"] < res["before"]["overtime_minutes"]
    assert res["after"]["conflicts"] == 0
    body = {"assignments": [{k: a[k] for k in ("surgery_id", "ot_id", "start")} for a in res["assignments"]]}
    assert client.post("/api/ot/optimize/apply", headers=admin, json=body).json()["updated"] == len(body["assignments"])
    rows = client.get(f"/api/surgeries?day={day}", headers=admin).json()["surgeries"]
    by_ot = {}
    for s in rows:
        by_ot.setdefault(s["ot_id"], []).append((s["scheduled_start"], s["end"]))
    for items in by_ot.values():
        items.sort()
        for (a0, a1), (b0, _) in zip(items, items[1:]):
            assert b0 >= a1  # no overlap in a theatre


def test_surgery_booked_through_agents(client, doctor):
    r = run_request("Schedule a laparoscopic cholecystectomy for Rohan Mehta tomorrow")
    assert "surgery" in r["intents"]
    ap = [a for a in r["approvals"] if a[1] == "book_surgery"]
    assert ap, r
    res = client.post(f"/api/approvals/{ap[0][0]}/decide", headers=doctor, json={"approve": True}).json()
    assert res["status"] == "executed"
    db = SessionLocal()
    try:
        s = db.get(Surgery, res["execution_result"]["surgery_id"])
        assert s.procedure.startswith("Laparoscopic cholecystectomy")
        clash = [o for o in db.query(Surgery).filter(Surgery.ot_id == s.ot_id, Surgery.id != s.id, Surgery.status != "cancelled").all()
                 if o.scheduled_start < s.scheduled_start + timedelta(minutes=s.duration_minutes + TURNOVER)
                 and s.scheduled_start < o.scheduled_start + timedelta(minutes=o.duration_minutes + TURNOVER)]
        assert not clash
    finally:
        db.close()


def test_news2_escalation_proposes_icu_transfer(client, nurse):
    census = client.get("/api/admissions?ward_type=general", headers=nurse).json()
    pid = census[0]["patient"]["id"]
    res = client.post(f"/api/patients/{pid}/vitals", headers=nurse,
                      json={"hr": 132, "rr": 27, "spo2": 89, "sbp": 88, "dbp": 55, "temp": 39.4}).json()
    assert res["news2"] >= 7 and res["escalation"] == "emergency_response" and res["request_id"]
    out = _wait_request(res["request_id"])
    assert any(a[1] == "admit_patient" and a[2].startswith("Transfer") for a in out["approvals"]), out


def test_mild_vitals_do_not_escalate(client, nurse):
    pid = client.get("/api/admissions?ward_type=general", headers=nurse).json()[-1]["patient"]["id"]
    res = client.post(f"/api/patients/{pid}/vitals", headers=nurse, json={"hr": 78, "rr": 15, "spo2": 98, "sbp": 124, "temp": 36.8}).json()
    assert res["news2"] == 0 and res["request_id"] is None


def test_supervised_mode_holds_every_action(client, admin):
    client.put("/api/settings", headers=admin, json={"values": {"autonomy_mode": "supervised"}})
    try:
        r = run_request("Book an appointment with a cardiologist tomorrow at 3 pm for Rohan Mehta")
        assert r["status"] == "awaiting_approval"
        assert any(a[1] == "book_appointment" for a in r["approvals"])
    finally:
        client.put("/api/settings", headers=admin, json={"values": {"autonomy_mode": "balanced"}})
    assert client.put("/api/settings", headers=admin, json={"values": {"autonomy_mode": "reckless"}}).status_code == 400


def test_user_management_and_password_change(client, admin):
    r = client.post("/api/users", headers=admin, json={"username": "test.nurse", "full_name": "Test Nurse", "role": "nurse", "password": "secret12"})
    assert r.status_code == 200
    uid = r.json()["id"]
    tok = client.post("/api/auth/login", json={"username": "test.nurse", "password": "secret12"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/api/auth/change-password", headers=h, json={"current_password": "wrong", "new_password": "newsecret"}).status_code == 400
    assert client.post("/api/auth/change-password", headers=h, json={"current_password": "secret12", "new_password": "newsecret"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": "test.nurse", "password": "newsecret"}).status_code == 200
    client.patch(f"/api/users/{uid}", headers=admin, json={"active": False})
    assert client.post("/api/auth/login", json={"username": "test.nurse", "password": "newsecret"}).status_code == 401
    assert client.get("/api/users", headers=h).status_code == 401


def test_search_mywork_and_discharge_summary(client, admin, doctor, nurse):
    hits = client.get("/api/search?q=Rohan", headers=admin).json()
    assert hits and hits[0]["type"] == "patient"
    mine = client.get("/api/dashboard/mywork", headers=doctor).json()
    assert "inpatients" in mine and "opd" in mine
    assert "overdue_obs" in client.get("/api/dashboard/mywork", headers=nurse).json()
    adm = client.get("/api/admissions", headers=admin).json()[0]
    s = client.get(f"/api/admissions/{adm['id']}/summary", headers=admin).json()
    assert s["narrative"] and s["patient"]["id"] == adm["patient"]["id"]
    res = client.get("/api/resources", headers=admin).json()
    assert {"maintenance_risk", "maintenance_due_in_days"} <= set(res[0])
