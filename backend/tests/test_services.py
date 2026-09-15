"""Unit tests for the decision-support algorithms."""
from datetime import date, timedelta

from app.agents.nlp import detect_intents, extract_entities, extract_vitals
from app.services.clinical import check_allergies, check_interactions, match_protocols, match_tests
from app.services.forecasting import holt_winters_forecast
from app.services.optimizer import BedOption, PatientNeed, optimize_bed_assignment, optimize_roster, rank_beds
from app.services.queueing import erlang_c, mmc_expected_wait, priority_score
from app.services.triage import compute_news2, triage


# ---------------------------------------------------------------- NEWS2 / triage
def test_news2_normal_vitals_score_zero():
    score, comps = compute_news2({"hr": 75, "rr": 16, "spo2": 98, "sbp": 125, "temp": 37.0})
    assert score == 0 and all(v == 0 for v in comps.values())


def test_news2_high_risk():
    # RR 26 (3) + SpO2 90 (3) + SBP 88 (3) + HR 135 (3) + temp 39.5 (2) = 14
    score, _ = compute_news2({"rr": 26, "spo2": 90, "sbp": 88, "hr": 135, "temp": 39.5})
    assert score == 14


def test_triage_levels():
    assert triage({"hr": 80, "rr": 16, "spo2": 99, "sbp": 120, "temp": 36.8}, "cardiac arrest").triage_level == 1
    assert triage({"hr": 80, "rr": 16, "spo2": 99, "sbp": 120, "temp": 36.8}, "chest pain").triage_level == 2
    assert triage({"hr": 80, "rr": 16, "spo2": 99, "sbp": 120, "temp": 36.8}, "ankle sprain").triage_level == 4
    assert triage({"consciousness": "U"}, "found collapsed").triage_level == 1


def test_elderly_escalation():
    young = triage({"hr": 95, "rr": 18, "spo2": 97, "sbp": 130, "temp": 37.0}, "abdominal pain", age=30)
    old = triage({"hr": 95, "rr": 18, "spo2": 97, "sbp": 130, "temp": 37.0}, "abdominal pain", age=82)
    assert old.triage_level == young.triage_level - 1


# ---------------------------------------------------------------- NLP
def test_intent_classification():
    assert detect_intents("Patient needs admission and requires ICU monitoring")[0][0]["name"] == "admission"
    assert detect_intents("book an appointment with a cardiologist tomorrow")[0][0]["name"] == "appointment"
    assert detect_intents("how many ICU beds are free")[0][0]["name"] == "bed_query"
    assert detect_intents("forecast admissions for next week")[0][0]["name"] == "analytics"


def test_multi_intent():
    names = {i["name"] for i in detect_intents("Admit the patient to ICU and order CBC and chest x-ray")[0]}
    assert {"admission", "diagnostics"} <= names


def test_analytics_does_not_spawn_admission():
    names = {i["name"] for i in detect_intents("Forecast admissions and ICU demand for the next 14 days")[0]}
    assert "admission" not in names


def test_entity_extraction():
    e = extract_entities("65 year old male, BP 90/60, HR 120, SpO2 91%, needs ICU bed with ventilator, order troponin stat")
    assert e["age"] == 65 and e["gender"] == "Male"
    assert e["bed_type"] == "icu" and "ventilator" in e["bed_features"]
    assert e["vitals"]["sbp"] == 90 and e["vitals"]["spo2"] == 91
    assert "TROP" in e["tests"] and e["urgency"] == "stat"


def test_fahrenheit_conversion():
    assert extract_vitals("temp 102")["temp"] == 38.9


# ---------------------------------------------------------------- clinical knowledge
def test_test_matching_prefers_longest():
    assert match_tests("order chest x-ray and ct head") == ["CXR", "CTH"] or set(match_tests("order chest x-ray and ct head")) == {"CXR", "CTH"}


def test_protocol_word_boundaries():
    assert not match_protocols("patient needs admission")  # 'mi' inside 'admission' must not match ACS
    assert match_protocols("severe chest pain")[0]["name"].startswith("Acute Coronary")


def test_drug_safety():
    assert check_allergies("amoxicillin", ["penicillin"])[0]["severity"] == "contraindicated"
    assert check_interactions("aspirin", ["warfarin"])[0]["severity"] == "major"
    assert check_interactions("paracetamol", ["warfarin"]) == []


# ---------------------------------------------------------------- optimisation
def _beds():
    return [
        BedOption(1, "ICU-01", "ICU", "icu", ["monitor", "ventilator"], 3, 2, 0.8),
        BedOption(2, "ICU-02", "ICU", "icu", ["monitor"], 3, 2, 0.8),
        BedOption(3, "GW-01", "General", "general", [], 1, 1, 0.5),
    ]


def test_bed_ranking_respects_hard_constraints():
    ranked = rank_beds(PatientNeed("p", "p", ["icu"], ["ventilator"]), _beds())
    assert [r["code"] for r in ranked] == ["ICU-01"]


def test_premium_equipment_is_reserved():
    ranked = rank_beds(PatientNeed("p", "p", ["icu"]), _beds())
    assert ranked[0]["code"] == "ICU-02"  # keep the ventilator bed for someone who needs it


def test_global_assignment_prioritises_urgent_patient():
    needs = [PatientNeed("routine", "r", ["icu"], priority=4), PatientNeed("critical", "c", ["icu"], ["ventilator"], priority=1)]
    res = optimize_bed_assignment(needs, _beds()[:1])
    assert res["assignments"][0]["need"] == "critical"
    assert res["unassigned"] == ["routine"]


def test_roster_constraints():
    staff = [{"id": i, "role": "nurse", "department_id": 1} for i in range(6)]
    days = [date.today() + timedelta(days=i) for i in range(7)]
    cov = {(1, "nurse", "morning"): 2, (1, "nurse", "evening"): 1, (1, "nurse", "night"): 1}
    res = optimize_roster(staff, days, cov, max_shifts=5, time_limit=5)
    per_day = {}
    for a in res["assignments"]:
        per_day.setdefault((a["staff_id"], a["date"]), 0)
        per_day[(a["staff_id"], a["date"])] += 1
    assert max(per_day.values()) == 1  # at most one shift per day
    counts = {}
    for a in res["assignments"]:
        counts[a["staff_id"]] = counts.get(a["staff_id"], 0) + 1
    assert max(counts.values()) <= 5
    assert res["coverage_pct"] == 100.0


# ---------------------------------------------------------------- queueing & forecasting
def test_erlang_c_bounds():
    assert 0 <= erlang_c(3, 10, 4) <= 1
    assert mmc_expected_wait(1, 10, 10)["stable"] is False  # λ ≥ cμ → unstable
    assert mmc_expected_wait(3, 8, 10)["wq_minutes"] >= 0


def test_priority_ageing():
    fresh, _ = priority_score(4, 0, 40)
    waited, _ = priority_score(4, 120, 40)
    assert waited > fresh


def test_holt_winters_captures_weekly_pattern():
    series = [20 + (8 if d % 7 == 0 else 0) for d in range(84)]
    fc = holt_winters_forecast(series, horizon=7)
    assert len(fc.forecast) == 7 and fc.mape is not None and fc.mape < 10
    assert max(fc.forecast) - min(fc.forecast) > 4
