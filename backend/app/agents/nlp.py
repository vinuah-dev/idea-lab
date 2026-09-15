"""Local NLP pipeline: intent classification (TF-IDF + Logistic Regression) and rule-based entity extraction.

Works fully offline. When an LLM is configured the orchestrator uses Claude for understanding
and merges its output with these DB-grounded extractors ("hybrid NLP").
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from functools import lru_cache

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer

from ..services.clinical import match_department, match_tests
from ..services.ot_scheduler import match_procedure

INTENTS = {
    "admission": "Admit a patient to a ward / ICU bed",
    "emergency": "Emergency case needing triage and rapid resource coordination",
    "appointment": "Book / reschedule an OPD appointment",
    "diagnostics": "Order or schedule lab / imaging tests",
    "pharmacy": "Prescriptions, medicine stock, drug safety",
    "discharge": "Discharge planning for an admitted patient",
    "staffing": "Staff availability, allocation and rostering",
    "bed_query": "Bed / ICU availability questions",
    "optimization": "Optimise or rebalance hospital resources",
    "analytics": "Reports, forecasts, bottleneck analysis",
    "patient_status": "Track where a patient is in their care journey",
    "surgery": "Schedule surgery / operating-theatre coordination",
}

_TRAINING: dict[str, list[str]] = {
    "admission": [
        "patient needs admission and requires icu monitoring", "admit the patient to icu", "admit patient to general ward",
        "please admit ramesh kumar for observation", "patient requires hospitalization", "need to admit a 65 year old for pneumonia",
        "admit him to the cardiac unit", "shift patient to icu from ward", "transfer patient to hdu bed",
        "arrange admission for post operative patient", "we need an icu bed with ventilator for this patient",
        "patient must be admitted for dengue monitoring", "inpatient admission required", "admit to isolation ward",
        "book an icu bed and admit the patient", "patient needs a bed in maternity ward", "admit child to pediatric ward",
        "move patient to icu urgently", "hospitalize the patient for iv antibiotics", "admission for chemotherapy cycle",
        "require bed allocation for admission", "patient to be kept under observation overnight", "admit for surgery tomorrow",
    ],
    "emergency": [
        "emergency patient with chest pain", "road accident victim arriving by ambulance", "patient unconscious in casualty",
        "code blue in ward 3", "severe breathing difficulty spo2 85", "stroke patient arriving in 10 minutes",
        "trauma case with head injury", "patient collapsed in opd", "heart attack patient in emergency", "seizure patient in er",
        "ambulance bringing polytrauma patient", "critical patient bp 80/50 heart rate 140", "anaphylaxis emergency",
        "burn victim arrived", "suspected sepsis patient in casualty with high fever and low bp", "emergency triage needed",
        "patient bleeding heavily after fall", "chest pain sweating since 30 minutes", "cardiac arrest resuscitation needed",
        "poisoning case brought to emergency", "mass casualty incident three patients arriving", "urgent: child not breathing properly",
    ],
    "appointment": [
        "book an appointment with a cardiologist tomorrow", "schedule opd consultation for knee pain", "i want to see a doctor",
        "book appointment with dr sharma at 10 am", "reschedule my appointment to friday", "need a neurology consultation",
        "book a slot with orthopedic doctor", "schedule follow up visit next week", "appointment for fever and cough today",
        "can i get an appointment with gynecologist", "book pediatrician for my child", "add patient to general medicine queue",
        "consultation with oncologist", "cancel my appointment", "opd booking for diabetes checkup", "follow-up after discharge in 7 days",
        "book checkup with physician this evening", "register patient in cardiology opd",
    ],
    "diagnostics": [
        "order cbc and chest x-ray", "schedule mri brain for patient", "patient needs ct scan urgently", "order blood tests",
        "book ultrasound abdomen", "run lft and kft", "ecg required stat", "order troponin and ecg", "schedule 2d echo",
        "lab test for dengue ns1", "get abg done", "blood culture and crp", "when will the ct scan be available",
        "status of lab reports", "radiology booking for x-ray", "order lipid profile and hba1c", "urine routine test",
        "check if mri machine is free", "diagnostic workup for chest pain", "pending lab results for patient",
    ],
    "pharmacy": [
        "prescribe paracetamol 500mg", "check stock of insulin", "is amoxicillin available", "medicine stock low alert",
        "dispense prescription for patient", "check drug interaction warfarin and aspirin", "refill medication",
        "which medicines are running low", "reorder antibiotics", "verify prescription for allergies",
        "start iv ceftriaxone", "give ondansetron for vomiting", "pharmacy inventory status", "prescribe metformin twice daily",
        "add aspirin 75 mg", "medication list for patient", "expiring medicines this month",
    ],
    "discharge": [
        "discharge the patient", "plan discharge for tomorrow", "patient is fit for discharge", "prepare discharge summary",
        "discharge ramesh from ward", "release icu bed after discharge", "which patients can be discharged today",
        "discharge with follow up in one week", "patient going home today", "complete discharge checklist",
    ],
    "staffing": [
        "which doctors are available now", "need two more nurses in icu", "who is on duty tonight", "generate staff roster for next week",
        "assign a nurse to bed 12", "find an available cardiologist", "staff shortage in emergency", "doctor workload today",
        "create shift schedule", "on call neurologist", "reassign nurses to balance workload", "night shift planning",
        "how many nurses are on duty", "optimize nurse scheduling",
    ],
    "bed_query": [
        "how many icu beds are available", "bed availability", "is there any free ventilator bed", "show bed occupancy",
        "which wards have free beds", "available isolation beds", "icu occupancy right now", "free beds in general ward",
        "how many beds are occupied", "any hdu bed free", "status of beds", "check bed availability in pediatric ward",
    ],
    "optimization": [
        "optimize bed allocation", "rebalance resources across wards", "optimize resource utilization",
        "allocate beds to waiting patients optimally", "reduce bottlenecks", "improve patient flow", "optimize icu usage",
        "suggest efficient resource allocation", "balance ward load", "optimize operating room schedule",
        "assign all pending admissions to beds", "resource optimization run",
    ],
    "analytics": [
        "show hospital occupancy report", "forecast admissions for next week", "predict icu demand", "average waiting time today",
        "department workload analysis", "show trends of er visits", "generate daily report", "predict bed demand",
        "what are the bottlenecks", "resource utilization statistics", "monthly performance summary", "show kpis",
    ],
    "patient_status": [
        "where is patient ramesh", "status of patient mrn-1002", "track patient journey", "what is pending for this patient",
        "has the patient completed diagnostics", "show patient timeline", "patient current location", "care plan status",
        "is the patient admitted", "what is the next step for patient",
    ],
    "surgery": [
        "schedule appendectomy for the patient tomorrow", "book operation theatre for knee replacement", "patient needs emergency laparotomy",
        "schedule surgery for hernia repair next week", "is any operating room free now", "optimize the ot schedule for today",
        "book an ot slot for c-section", "plan cholecystectomy for tomorrow morning", "emergency caesarean needed now",
        "reschedule surgeries to reduce theatre overtime", "arrange theatre for hip fracture fixation", "show the surgery list for today",
        "book craniotomy with the neurosurgeon", "need an operating theatre for debridement", "schedule total knee replacement on friday",
        "operation theatre availability tomorrow", "plan the surgical list", "optimise theatre utilisation", "optimize operation theatre schedule",
        "rebalance the operating room schedule", "when can we operate on this patient", "book surgery slot for mastectomy",
    ],
}

_FILLERS = ["", "please ", "urgent: ", "hi, ", "can you ", "kindly "]


@lru_cache(maxsize=1)
def _model() -> Pipeline:
    X, y = [], []
    for intent, samples in _TRAINING.items():
        for s in samples:
            for f in _FILLERS[:3]:
                X.append(f + s)
                y.append(intent)
    pipe = Pipeline([
        ("features", FeatureUnion([
            ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1)),
        ])),
        ("clf", LogisticRegression(C=12, max_iter=3000)),
    ])
    pipe.fit(X, y)
    return pipe


def classify(text: str) -> list[dict]:
    model = _model()
    probs = model.predict_proba([text.lower()])[0]
    order = np.argsort(probs)[::-1]
    return [{"name": model.classes_[i], "confidence": round(float(probs[i]), 3)} for i in order]


_CLAUSE_SPLIT = re.compile(r"(?:\band also\b|\balso\b|\bthen\b|;|\. |\band then\b|,\s*and\b|\bplus\b)", re.I)

KEYWORD_INTENTS = {  # regexes (word-bounded) that add secondary intents
    "emergency": [r"emergency", r"casualty", r"ambulance", r"code blue", r"unconscious", r"collapsed", r"cardiac arrest", r"trauma"],
    "admission": [r"admit", r"admission", r"hospitali[sz]e", r"(?:transfer|shift|move) (?:him |her |patient )?to (?:the )?icu"],
    "discharge": [r"discharge"],
    "pharmacy": [r"prescribe", r"dispense", r"medicines?", r"medications?", r"drugs?", r"stock of", r"refill"],
    "appointment": [r"appointment", r"book a slot", r"consultation", r"opd", r"follow[ -]up"],
    "staffing": [r"roster", r"on duty", r"nurses", r"shift schedule", r"staff"],
    "optimization": [r"optimi[sz]e (?:the )?(?:bed|resource|allocation|icu|ward)s?", r"rebalance"],
    "analytics": [r"forecast", r"predict\w*", r"report", r"trends?", r"bottlenecks?"],
    "surgery": [r"surgery", r"operation theatre", r"operating (?:room|theatre)s?", r"theatre", r"ot (?:slot|schedule|list)"],
}
# hospital-level questions must not spawn patient-level workflows from incidental keywords
_SUPPRESS = {"analytics": {"admission", "appointment", "discharge", "pharmacy", "surgery"}, "bed_query": {"admission", "discharge", "surgery"},
             "optimization": {"admission", "appointment"}, "staffing": {"optimization", "admission", "surgery"},
             "appointment": {"surgery"}, "surgery": {"optimization", "appointment"}}


def detect_intents(text: str) -> tuple[list[dict], float]:
    """Primary intent from the classifier, plus secondary intents from clause-level classification and keywords."""
    ranked = classify(text)
    primary = ranked[0]
    chosen: dict[str, float] = {primary["name"]: primary["confidence"]}
    for clause in [c.strip() for c in _CLAUSE_SPLIT.split(text) if c and len(c.strip()) > 8]:
        top = classify(clause)[0]
        if top["confidence"] >= 0.45:
            chosen[top["name"]] = max(chosen.get(top["name"], 0), top["confidence"])
    t = text.lower()
    suppressed = _SUPPRESS.get(primary["name"], set())
    for intent, patterns in KEYWORD_INTENTS.items():
        if intent in chosen or intent in suppressed:
            continue
        if any(re.search(rf"\b{p}\b", t) for p in patterns):
            chosen[intent] = 0.5
    if match_tests(text) and "diagnostics" not in chosen and primary["name"] not in ("bed_query", "analytics"):
        chosen["diagnostics"] = 0.5
    if match_procedure(text) and "surgery" not in chosen and "surgery" not in suppressed:
        chosen["surgery"] = 0.5
    intents = sorted(({"name": k, "confidence": round(v, 3)} for k, v in chosen.items()), key=lambda d: -d["confidence"])
    return intents, primary["confidence"]


# ------------------------------------------------------------------ entity extraction
BED_WORDS = {
    "icu": ["icu", "intensive care", "critical care"], "hdu": ["hdu", "high dependency", "step down"],
    "cardiac": ["ccu", "cardiac unit", "cardiac care", "cardiac bed"], "isolation": ["isolation"],
    "pediatric": ["pediatric ward", "paediatric", "picu", "child ward"], "maternity": ["maternity", "labour ward"],
    "general": ["general ward", "normal bed", "ward bed"], "emergency": ["er bay", "emergency bay", "resus"],
}
FEATURE_WORDS = {"ventilator": ["ventilator", "ventilation", "intubat"], "cardiac_monitor": ["cardiac monitor", "telemetry"],
                 "oxygen": ["oxygen", "o2 support"], "monitor": ["monitoring", "monitor"]}


_COMMON_WORDS = {"normal", "ringer", "regular", "potassium"}


def _num(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text, re.I)
    return float(m.group(1)) if m else None


def extract_vitals(text: str) -> dict:
    v: dict = {}
    hr = _num(r"(?:hr|heart rate|pulse)\s*(?:is|of|:|=)?\s*(\d{2,3})", text)
    rr = _num(r"(?:\brr\b|resp(?:iratory)?\s*rate)\s*(?:is|of|:|=)?\s*(\d{1,2})", text)
    spo2 = _num(r"(?:spo2|sp02|spo₂|sats?|saturation|oxygen saturation)\s*(?:is|of|:|=)?\s*(\d{2,3})", text)
    temp = _num(r"(?:temp(?:erature)?|fever(?: of)?)\s*(?:is|of|:|=)?\s*(\d{2,3}(?:\.\d)?)", text)
    bp = re.search(r"(?:bp|blood pressure)\s*(?:is|of|:|=)?\s*(\d{2,3})\s*/\s*(\d{2,3})", text, re.I)
    if hr:
        v["hr"] = hr
    if rr:
        v["rr"] = rr
    if spo2 and spo2 <= 100:
        v["spo2"] = spo2
    if temp:
        v["temp"] = round((temp - 32) * 5 / 9, 1) if temp > 45 else temp
    if bp:
        v["sbp"], v["dbp"] = float(bp.group(1)), float(bp.group(2))
    t = text.lower()
    if re.search(r"unconscious|unresponsive|not responding", t):
        v["consciousness"] = "U"
    elif re.search(r"confus|drowsy|disoriented", t):
        v["consciousness"] = "C"
    if re.search(r"on oxygen|on o2|oxygen support|nasal cannula", t):
        v["on_oxygen"] = True
    return v


def extract_datetime(text: str, now: datetime | None = None) -> str | None:
    now = now or datetime.now()
    t = text.lower()
    day = None
    if "day after tomorrow" in t:
        day = now + timedelta(days=2)
    elif "tomorrow" in t:
        day = now + timedelta(days=1)
    elif "today" in t or "tonight" in t or "this evening" in t or "now" in t:
        day = now
    elif "next week" in t:
        day = now + timedelta(days=7)
    else:
        for i, wd in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]):
            if wd in t:
                delta = (i - now.weekday()) % 7 or 7
                day = now + timedelta(days=delta)
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t) or re.search(r"\bat\s+(\d{1,2}):(\d{2})\b", t)
    hour = minute = None
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if len(m.groups()) >= 3 and m.group(3) == "pm" and hour < 12:
            hour += 12
        if len(m.groups()) >= 3 and m.group(3) == "am" and hour == 12:
            hour = 0
    elif "morning" in t:
        hour, minute = 10, 0
    elif "evening" in t or "tonight" in t:
        hour, minute = 17, 0
    elif "afternoon" in t:
        hour, minute = 14, 0
    if day is None and hour is None:
        return None
    day = day or now
    if hour is None:
        return day.replace(second=0, microsecond=0).isoformat() if day.date() == now.date() else day.replace(hour=10, minute=0, second=0, microsecond=0).isoformat()
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()


def extract_entities(text: str, patient_names: list[tuple[int, str, str]] | None = None,
                     medications: list[tuple[int, str, str]] | None = None) -> dict:
    """patient_names: [(id, name, mrn)], medications: [(id, brand, generic)] for DB-grounded matching."""
    t = text.lower()
    ent: dict = {}

    mrn = re.search(r"\bmrn[-\s]?(\d{3,6})\b", t)
    if mrn:
        ent["mrn"] = f"MRN-{mrn.group(1)}"
    if patient_names:
        best = None
        for pid, name, pmrn in patient_names:
            n = name.lower()
            if n in t or (ent.get("mrn") and ent["mrn"] == pmrn):
                if not best or len(n) > len(best[1]):
                    best = (pid, n, name)
        if not best:  # first-name only match (unique)
            firsts = {}
            for pid, name, _ in patient_names:
                first = name.lower().split()[0]
                if re.search(rf"\b{re.escape(first)}\b", t) and len(first) > 3:
                    firsts.setdefault(first, []).append((pid, name))
            unique = [v[0] for v in firsts.values() if len(v) == 1]
            if len(unique) == 1:
                best = (unique[0][0], unique[0][1].lower(), unique[0][1])
        if best:
            ent["patient_id"], ent["patient_name"] = best[0], best[2]

    age = re.search(r"\b(\d{1,3})\s*(?:-|\s)?(?:years?|yrs?|y/o|yo|year-old|year old)\b", t)
    if age:
        ent["age"] = int(age.group(1))
    if re.search(r"\b(male|man|boy|gentleman|mr\.?)\b", t):
        ent["gender"] = "Male"
    if re.search(r"\b(female|woman|girl|lady|mrs\.?|ms\.?|pregnant)\b", t):
        ent["gender"] = "Female"
    name = re.search(r"(?:named|name is|patient called|new patient)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text)
    if name and "patient_id" not in ent:
        ent["new_patient_name"] = name.group(1)

    for btype, words in BED_WORDS.items():
        if any(w in t for w in words):
            ent["bed_type"] = btype
            break
    feats = [f for f, words in FEATURE_WORDS.items() if any(w in t for w in words)]
    if feats:
        ent["bed_features"] = feats
    dept = match_department(text)
    if dept:
        ent["department"] = dept
    tests = match_tests(text)
    if tests:
        ent["tests"] = tests
    procedure = match_procedure(text)
    if procedure:
        ent["procedure"] = procedure
    if medications:
        meds = []
        for mid, brand, generic in medications:
            first = brand.lower().split()[0]
            if (re.search(rf"\b{re.escape(brand.lower())}\b", t) or re.search(rf"\b{re.escape(generic.lower())}\b", t)
                    or (len(first) >= 6 and first not in _COMMON_WORDS and re.search(rf"\b{re.escape(first)}\b", t))):
                meds.append({"id": mid, "name": brand, "generic": generic})
        if meds:
            ent["medications"] = meds
    dose = re.search(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|units?)\b", t)
    if dose:
        ent["dose"] = f"{dose.group(1)} {dose.group(2)}"
    freq = re.search(r"\b(od|bd|tds|qid|once daily|twice daily|thrice daily|sos|hs)\b", t)
    if freq:
        ent["frequency"] = freq.group(1).upper() if len(freq.group(1)) <= 3 else freq.group(1)

    vitals = extract_vitals(text)
    if vitals:
        ent["vitals"] = vitals
    if re.search(r"\b(stat|immediately|asap|critical|emergency|urgent(?:ly)?)\b", t):
        ent["urgency"] = "stat" if re.search(r"\b(stat|immediately|critical)\b", t) else "urgent"
    when = extract_datetime(text)
    if when:
        ent["datetime"] = when
    cnt = re.search(r"\b(\d+|one|two|three|four|five)\s+(?:more\s+)?(nurses?|doctors?|technicians?)\b", t)
    if cnt:
        words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        ent["staff_count"] = int(words.get(cnt.group(1), cnt.group(1)))
        ent["staff_role"] = "nurse" if cnt.group(2).startswith("nurse") else "doctor" if cnt.group(2).startswith("doctor") else "technician"
    elif re.search(r"\bnurses?\b", t):
        ent["staff_role"] = "nurse"
    elif re.search(r"\b(doctors?|physician|specialist|consultant)\b", t):
        ent["staff_role"] = "doctor"
    horizon = re.search(r"next\s+(\d+)\s+days", t)
    if horizon:
        ent["horizon_days"] = int(horizon.group(1))
    elif "next week" in t or "7 days" in t:
        ent["horizon_days"] = 7
    elif "next month" in t:
        ent["horizon_days"] = 30
    if re.search(r"ambulance", t):
        ent["arrival_mode"] = "ambulance"
    return ent


def understand_local(text: str, patient_names=None, medications=None) -> dict:
    intents, conf = detect_intents(text)
    return {
        "engine": "Local NLP (TF-IDF + Logistic Regression)",
        "intents": intents,
        "confidence": conf,
        "entities": extract_entities(text, patient_names, medications),
    }
