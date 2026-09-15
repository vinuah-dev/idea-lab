"""Clinical/operational knowledge base used by the agents (test catalogue, protocols, drug safety).

This is decision-support reference data for the demo — not a substitute for clinical judgement.
"""
from __future__ import annotations

import re

# code: (name, category, modality resource_type or None for lab analyser, turnaround minutes, keywords)
TEST_CATALOG: dict[str, dict] = {
    "CBC": {"name": "Complete Blood Count", "category": "lab", "modality": "lab_analyzer", "tat": 60,
            "keywords": ["cbc", "complete blood count", "blood count", "hemogram", "haemogram"]},
    "LFT": {"name": "Liver Function Test", "category": "lab", "modality": "lab_analyzer", "tat": 120,
            "keywords": ["lft", "liver function"]},
    "KFT": {"name": "Kidney Function Test", "category": "lab", "modality": "lab_analyzer", "tat": 120,
            "keywords": ["kft", "rft", "kidney function", "renal function", "creatinine"]},
    "TROP": {"name": "Troponin I", "category": "lab", "modality": "lab_analyzer", "tat": 45,
             "keywords": ["troponin", "trop"]},
    "LIPID": {"name": "Lipid Profile", "category": "lab", "modality": "lab_analyzer", "tat": 180,
              "keywords": ["lipid", "cholesterol"]},
    "HBA1C": {"name": "HbA1c", "category": "lab", "modality": "lab_analyzer", "tat": 240,
              "keywords": ["hba1c", "glycated", "sugar test", "blood sugar", "glucose"]},
    "ABG": {"name": "Arterial Blood Gas", "category": "lab", "modality": "lab_analyzer", "tat": 20,
            "keywords": ["abg", "blood gas", "arterial blood gas"]},
    "CRP": {"name": "C-Reactive Protein", "category": "lab", "modality": "lab_analyzer", "tat": 90,
            "keywords": ["crp", "c-reactive"]},
    "BCUL": {"name": "Blood Culture", "category": "lab", "modality": "lab_analyzer", "tat": 2880,
             "keywords": ["blood culture", "culture"]},
    "COAG": {"name": "PT / INR (Coagulation)", "category": "lab", "modality": "lab_analyzer", "tat": 60,
             "keywords": ["pt inr", "inr", "coagulation", "pt/inr"]},
    "NS1": {"name": "Dengue NS1 Antigen", "category": "lab", "modality": "lab_analyzer", "tat": 120,
            "keywords": ["dengue", "ns1"]},
    "URINE": {"name": "Urine Routine", "category": "lab", "modality": "lab_analyzer", "tat": 60,
              "keywords": ["urine"]},
    "CXR": {"name": "Chest X-Ray", "category": "imaging", "modality": "xray", "tat": 30,
            "keywords": ["chest x-ray", "chest xray", "cxr", "x-ray", "xray", "x ray"]},
    "CTH": {"name": "CT Head (non-contrast)", "category": "imaging", "modality": "ct", "tat": 45,
            "keywords": ["ct head", "ct brain", "ct scan", "ct"]},
    "CTA": {"name": "CT Abdomen", "category": "imaging", "modality": "ct", "tat": 60,
            "keywords": ["ct abdomen"]},
    "MRIB": {"name": "MRI Brain", "category": "imaging", "modality": "mri", "tat": 90,
             "keywords": ["mri", "mri brain"]},
    "USG": {"name": "Ultrasound Abdomen", "category": "imaging", "modality": "ultrasound", "tat": 40,
            "keywords": ["ultrasound", "usg", "sonography"]},
    "ECG": {"name": "12-lead ECG", "category": "cardiac", "modality": "ecg", "tat": 15,
            "keywords": ["ecg", "ekg", "electrocardiogram"]},
    "ECHO": {"name": "2D Echocardiography", "category": "cardiac", "modality": "ultrasound", "tat": 60,
             "keywords": ["echo", "2d echo", "echocardiogram", "echocardiography"]},
}

# Condition keyword -> suggested workup (for clinician review), preferred bed and department
PROTOCOLS: list[dict] = [
    {"name": "Acute Coronary Syndrome pathway", "keywords": ["chest pain", "heart attack", "mi", "cardiac", "angina"],
     "tests": ["ECG", "TROP", "CXR", "COAG"], "bed": ["cardiac", "icu", "hdu"], "department": "Cardiology"},
    {"name": "Acute Stroke pathway", "keywords": ["stroke", "facial droop", "slurred speech", "paralysis", "weakness one side"],
     "tests": ["CTH", "CBC", "COAG", "HBA1C"], "bed": ["icu", "hdu", "general"], "department": "Neurology"},
    {"name": "Sepsis bundle", "keywords": ["sepsis", "septic", "high fever", "infection"],
     "tests": ["CBC", "BCUL", "CRP", "ABG", "KFT"], "bed": ["hdu", "icu", "isolation"], "department": "General Medicine"},
    {"name": "Respiratory distress workup", "keywords": ["breathing", "breathlessness", "shortness of breath", "pneumonia", "respiratory", "asthma", "copd"],
     "tests": ["ABG", "CXR", "CBC", "CRP"], "bed": ["hdu", "icu", "general"], "department": "General Medicine"},
    {"name": "Trauma primary survey", "keywords": ["accident", "trauma", "fall", "injury", "fracture"],
     "tests": ["CTH", "CXR", "CBC", "COAG"], "bed": ["general", "hdu", "icu"], "department": "Orthopedics"},
    {"name": "Dengue fever monitoring", "keywords": ["dengue", "platelet"],
     "tests": ["NS1", "CBC", "LFT"], "bed": ["general", "isolation"], "department": "General Medicine"},
    {"name": "Diabetic emergency", "keywords": ["dka", "diabetic", "sugar", "hyperglycemia", "hypoglycemia"],
     "tests": ["HBA1C", "ABG", "KFT", "URINE"], "bed": ["hdu", "general"], "department": "General Medicine"},
    {"name": "Acute abdomen workup", "keywords": ["abdominal pain", "appendicitis", "stomach pain", "vomiting"],
     "tests": ["USG", "CBC", "LFT", "KFT"], "bed": ["general"], "department": "General Surgery"},
    {"name": "Obstetric assessment", "keywords": ["pregnant", "pregnancy", "labour", "delivery"],
     "tests": ["USG", "CBC", "URINE"], "bed": ["maternity"], "department": "Obstetrics & Gynecology"},
    {"name": "Pediatric fever workup", "keywords": ["child", "baby", "infant"],
     "tests": ["CBC", "CRP", "URINE"], "bed": ["pediatric"], "department": "Pediatrics"},
]

DEPARTMENT_KEYWORDS: dict[str, list[str]] = {
    "Cardiology": ["cardiology", "cardiologist", "heart", "cardiac", "chest pain", "palpitation", "bp"],
    "Neurology": ["neurology", "neurologist", "neuro", "brain", "stroke", "seizure", "migraine", "headache"],
    "Orthopedics": ["orthopedic", "orthopaedic", "ortho", "bone", "fracture", "knee", "joint", "back pain", "spine"],
    "Pediatrics": ["pediatric", "paediatric", "pediatrician", "child", "baby", "infant", "kid"],
    "Obstetrics & Gynecology": ["gynec", "gynaec", "obstetric", "pregnan", "labour", "maternity"],
    "Oncology": ["oncology", "oncologist", "cancer", "tumor", "tumour", "chemo"],
    "General Surgery": ["surgery", "surgeon", "surgical", "appendicitis", "hernia", "operation"],
    "Emergency": ["emergency", "casualty", "er "],
    "General Medicine": ["general medicine", "physician", "fever", "diabetes", "general", "medicine", "cough", "cold"],
    "Pulmonology": ["pulmonology", "pulmonologist", "lung", "asthma", "copd", "chest physician"],
}

# (generic A, generic B): (severity, message)
DRUG_INTERACTIONS: dict[frozenset, tuple[str, str]] = {
    frozenset({"warfarin", "aspirin"}): ("major", "Additive anticoagulant/antiplatelet effect — high bleeding risk"),
    frozenset({"warfarin", "ibuprofen"}): ("major", "NSAID increases bleeding risk with warfarin"),
    frozenset({"warfarin", "ciprofloxacin"}): ("moderate", "Ciprofloxacin may raise INR — monitor closely"),
    frozenset({"clopidogrel", "omeprazole"}): ("moderate", "Omeprazole reduces clopidogrel activation — prefer pantoprazole"),
    frozenset({"sildenafil", "nitroglycerin"}): ("contraindicated", "Severe hypotension risk — do not co-administer"),
    frozenset({"sildenafil", "isosorbide mononitrate"}): ("contraindicated", "Severe hypotension risk — do not co-administer"),
    frozenset({"enalapril", "spironolactone"}): ("major", "Risk of hyperkalaemia — monitor potassium"),
    frozenset({"enalapril", "potassium chloride"}): ("major", "Risk of hyperkalaemia — monitor potassium"),
    frozenset({"simvastatin", "clarithromycin"}): ("major", "Raised statin levels — myopathy / rhabdomyolysis risk"),
    frozenset({"digoxin", "amiodarone"}): ("major", "Amiodarone raises digoxin levels — reduce digoxin dose"),
    frozenset({"tramadol", "sertraline"}): ("major", "Serotonin syndrome and seizure risk"),
    frozenset({"ondansetron", "azithromycin"}): ("moderate", "Additive QT prolongation — ECG monitoring advised"),
    frozenset({"metformin", "iohexol contrast"}): ("moderate", "Hold metformin around iodinated contrast (lactic acidosis risk)"),
    frozenset({"aspirin", "ibuprofen"}): ("moderate", "Ibuprofen may blunt aspirin's cardioprotection; GI bleed risk"),
    frozenset({"heparin", "aspirin"}): ("major", "Additive bleeding risk"),
}

# allergy keyword -> generics/classes it contraindicates
ALLERGY_CROSS: dict[str, list[str]] = {
    "penicillin": ["amoxicillin", "ampicillin", "piperacillin", "penicillin", "amoxicillin-clavulanate"],
    "sulfa": ["cotrimoxazole", "sulfamethoxazole", "furosemide"],
    "nsaid": ["ibuprofen", "diclofenac", "aspirin", "naproxen"],
    "aspirin": ["aspirin"],
    "cephalosporin": ["ceftriaxone", "cefuroxime", "cefixime"],
    "iodine": ["iohexol contrast"],
    "morphine": ["morphine"],
}


def match_tests(text: str) -> list[str]:
    """Return catalogue codes mentioned in free text (longest keyword wins)."""
    t = re.sub(r"[^a-z0-9/\- ]", " ", f" {text.lower()} ")
    hits: list[tuple[int, int, str]] = []  # (start, end, code)
    for code, meta in TEST_CATALOG.items():
        for kw in meta["keywords"]:
            for m in re.finditer(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", t):
                hits.append((m.start(), m.end(), code))
    # longest match wins, so "ct head" beats "ct" and "chest x-ray" beats "x-ray"
    found: list[str] = []
    taken: list[tuple[int, int]] = []
    for start, end, code in sorted(hits, key=lambda h: h[0] - h[1]):
        if any(start < e and end > s for s, e in taken):
            continue
        taken.append((start, end))
        if code not in found:
            found.append(code)
    return found


def match_protocols(text: str) -> list[dict]:
    t = text.lower()
    return [p for p in PROTOCOLS if any(re.search(rf"\b{re.escape(k)}\b", t) for k in p["keywords"])]


def match_department(text: str) -> str | None:
    t = f" {text.lower()} "
    best, best_len = None, 0
    for dept, kws in DEPARTMENT_KEYWORDS.items():
        for kw in kws:
            if kw in t and len(kw) > best_len:
                best, best_len = dept, len(kw)
    return best


def check_interactions(new_generic: str, current_generics: list[str]) -> list[dict]:
    alerts = []
    for g in current_generics:
        hit = DRUG_INTERACTIONS.get(frozenset({new_generic.lower(), g.lower()}))
        if hit:
            alerts.append({"type": "interaction", "severity": hit[0], "with": g, "message": hit[1]})
    return alerts


def check_allergies(generic: str, allergies: list[str]) -> list[dict]:
    alerts = []
    g = generic.lower()
    for allergy in allergies or []:
        a = allergy.lower()
        contraindicated = ALLERGY_CROSS.get(a, [a])
        if g in contraindicated or a in g:
            alerts.append({"type": "allergy", "severity": "contraindicated", "with": allergy,
                           "message": f"Patient allergic to {allergy} — {generic} contraindicated"})
    return alerts
