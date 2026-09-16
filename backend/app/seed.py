"""Synthetic but realistic demo data for a ~110-bed multispeciality hospital.

Run:  python -m app.seed --reset
"""
from __future__ import annotations

import argparse
import math
import random
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import (Admission, Ambulance, Appointment, AuditLog, Bed, CareTask, ClinicalNote, DailyStat, Department, DiagnosticOrder,
                     EmergencyCase, InsuranceClaim, Medication, Notification, Patient, Prescription, Resource, Shift, Staff, Surgery,
                     User, VitalSign, Ward)
from .security import hash_password
from .services import billing
from .services.clinical import TEST_CATALOG
from .services.dispatch import FLEET, HOSPITAL, LOCALITIES
from .services.ot_scheduler import PROCEDURES, TURNOVER
from .services.triage import clinical_risk, compute_news2, triage

RNG = random.Random(7)
AUX = random.Random(99)  # separate stream for v2 data so the core demo data stays identical

DEPARTMENTS = [  # name, code, floor, avg consult minutes
    ("Emergency", "ER", 0, 10), ("Critical Care", "ICU", 3, 20), ("Cardiology", "CAR", 2, 15), ("Neurology", "NEU", 2, 18),
    ("Orthopedics", "ORT", 1, 12), ("General Medicine", "GM", 1, 10), ("General Surgery", "GS", 4, 15), ("Pediatrics", "PED", 1, 12),
    ("Obstetrics & Gynecology", "OBG", 4, 15), ("Oncology", "ONC", 5, 20), ("Pulmonology", "PUL", 2, 14),
    ("Radiology", "RAD", 0, 20), ("Pathology", "PATH", 0, 10), ("Pharmacy", "PHA", 0, 5),
]

WARDS = [  # name, type, dept, floor, beds, prefix, nurse ratio, occupancy target
    ("Emergency Bays", "emergency", "ER", 0, 10, "ER", 0.5, 0.0),
    ("Medical ICU", "icu", "ICU", 3, 10, "ICU", 0.5, 0.8),
    ("Cardiac Care Unit", "cardiac", "CAR", 2, 8, "CCU", 0.5, 0.75),
    ("High Dependency Unit", "hdu", "ICU", 3, 8, "HDU", 0.33, 0.62),
    ("General Ward A (Medicine)", "general", "GM", 1, 20, "GWA", 0.17, 0.75),
    ("General Ward B (Surgery)", "general", "GS", 4, 16, "GWB", 0.17, 0.7),
    ("Orthopedic Ward", "general", "ORT", 1, 10, "ORW", 0.17, 0.7),
    ("Pediatric Ward", "pediatric", "PED", 1, 10, "PED", 0.25, 0.6),
    ("Maternity Ward", "maternity", "OBG", 4, 10, "MAT", 0.25, 0.6),
    ("Isolation Ward", "isolation", "GM", 1, 6, "ISO", 0.33, 0.5),
]

REASONS = {
    "ICU": ["Septic shock", "Acute respiratory failure", "Post-cardiac arrest care", "Severe pneumonia on ventilator",
            "Diabetic ketoacidosis", "Post-op monitoring after laparotomy", "Traumatic brain injury"],
    "CCU": ["Acute MI (STEMI) post-PCI", "Unstable angina", "Heart failure exacerbation", "Atrial fibrillation with RVR", "Complete heart block"],
    "HDU": ["COPD exacerbation", "Upper GI bleed", "Acute pancreatitis", "Stroke — step-down care", "Severe dengue with low platelets"],
    "GWA": ["Community-acquired pneumonia", "Uncontrolled diabetes", "Dengue fever", "Typhoid fever", "Acute gastroenteritis",
            "UTI with fever", "Anaemia workup", "Cellulitis of leg"],
    "GWB": ["Appendectomy post-op", "Hernia repair post-op", "Cholecystectomy post-op", "Intestinal obstruction", "Abscess drainage"],
    "ORW": ["Hip fracture fixation", "Total knee replacement", "Tibia fracture", "Spine surgery post-op"],
    "PED": ["Bronchiolitis", "Paediatric pneumonia", "Febrile seizure", "Dehydration with gastroenteritis"],
    "MAT": ["Normal delivery — postpartum", "C-section post-op", "Pre-eclampsia monitoring", "Preterm labour"],
    "ISO": ["Pulmonary tuberculosis", "H1N1 influenza", "Chickenpox", "MDR organism infection"],
}

FIRST_M = ["Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Rahul", "Amit", "Suresh", "Ramesh", "Vikram", "Karan", "Sanjay",
           "Manoj", "Deepak", "Anil", "Rajiv", "Imran", "Farhan", "Harpreet", "Joseph", "Thomas", "Ravi", "Kiran", "Prakash",
           "Nitin", "Siddharth", "Yash", "Ishaan", "Kabir", "Mohan", "Gopal", "Abdul"]
FIRST_F = ["Aadhya", "Ananya", "Diya", "Priya", "Pooja", "Sneha", "Kavya", "Meera", "Lakshmi", "Sunita", "Anjali", "Neha",
           "Ritu", "Fatima", "Ayesha", "Simran", "Mary", "Divya", "Shreya", "Isha", "Nisha", "Rekha", "Geeta", "Asha", "Zoya",
           "Tanvi", "Radhika", "Swati", "Nandini", "Pallavi", "Farida", "Bhavna"]
LAST = ["Sharma", "Verma", "Gupta", "Singh", "Kumar", "Patel", "Shah", "Mehta", "Iyer", "Nair", "Reddy", "Rao", "Joshi",
        "Kulkarni", "Deshpande", "Chatterjee", "Banerjee", "Das", "Khan", "Sheikh", "Fernandes", "D'Souza", "Pillai", "Menon",
        "Agarwal", "Jain", "Malhotra", "Kapoor", "Chopra", "Bose", "Mishra", "Pandey", "Yadav", "Thakur", "Gill"]

CONDITIONS = ["Type 2 diabetes", "Hypertension", "Asthma", "Coronary artery disease", "CKD stage 3", "COPD", "Hypothyroidism",
              "Atrial fibrillation", "Heart failure", "Epilepsy"]

DOCTORS = [  # dept, count, specialisation
    ("ER", 4, "Emergency Medicine"), ("ICU", 3, "Critical Care"), ("CAR", 3, "Cardiology"), ("NEU", 2, "Neurology"),
    ("ORT", 3, "Orthopedics"), ("GM", 5, "Internal Medicine"), ("GS", 3, "General Surgery"), ("PED", 2, "Pediatrics"),
    ("OBG", 2, "Obstetrics & Gynecology"), ("ONC", 2, "Medical Oncology"), ("PUL", 1, "Pulmonology"),
]
NURSES = [("ER", 6), ("ICU", 10), ("CAR", 5), ("GM", 9), ("GS", 5), ("ORT", 3), ("PED", 4), ("OBG", 4), ("NEU", 1)]

MEDICATIONS = [  # name, generic, class, form, strength, stock, reorder, daily usage, unit price (INR)
    ("Paracetamol", "paracetamol", "Analgesic", "tablet", "500 mg", 2400, 500, 180, 1.2),
    ("Ibuprofen", "ibuprofen", "NSAID", "tablet", "400 mg", 900, 300, 60, 2.0),
    ("Diclofenac", "diclofenac", "NSAID", "injection", "75 mg", 140, 100, 20, 18),
    ("Aspirin", "aspirin", "Antiplatelet", "tablet", "75 mg", 1500, 300, 70, 0.8),
    ("Clopidogrel", "clopidogrel", "Antiplatelet", "tablet", "75 mg", 620, 200, 40, 4.5),
    ("Warfarin", "warfarin", "Anticoagulant", "tablet", "5 mg", 260, 100, 12, 3.1),
    ("Heparin", "heparin", "Anticoagulant", "injection", "5000 IU", 85, 120, 25, 95),
    ("Enoxaparin", "enoxaparin", "Anticoagulant", "injection", "40 mg", 150, 80, 18, 320),
    ("Atorvastatin", "atorvastatin", "Statin", "tablet", "20 mg", 1100, 300, 55, 3.2),
    ("Simvastatin", "simvastatin", "Statin", "tablet", "20 mg", 300, 100, 10, 2.4),
    ("Metformin", "metformin", "Antidiabetic", "tablet", "500 mg", 1800, 400, 90, 1.5),
    ("Insulin Regular", "insulin regular", "Insulin", "injection", "100 IU/ml", 60, 80, 15, 210),
    ("Insulin Glargine", "insulin glargine", "Insulin", "injection", "100 IU/ml", 45, 40, 6, 780),
    ("Amlodipine", "amlodipine", "Antihypertensive", "tablet", "5 mg", 1300, 300, 60, 1.4),
    ("Enalapril", "enalapril", "ACE inhibitor", "tablet", "5 mg", 700, 200, 30, 1.8),
    ("Spironolactone", "spironolactone", "Diuretic", "tablet", "25 mg", 380, 100, 14, 2.6),
    ("Furosemide", "furosemide", "Diuretic", "injection", "20 mg", 240, 100, 35, 12),
    ("Potassium Chloride", "potassium chloride", "Electrolyte", "syrup", "15 ml", 120, 60, 10, 45),
    ("Amoxicillin", "amoxicillin", "Penicillin antibiotic", "capsule", "500 mg", 900, 250, 50, 4.0),
    ("Amoxicillin-Clavulanate", "amoxicillin-clavulanate", "Penicillin antibiotic", "tablet", "625 mg", 420, 200, 40, 14),
    ("Piperacillin-Tazobactam", "piperacillin", "Penicillin antibiotic", "injection", "4.5 g", 38, 60, 14, 540),
    ("Ceftriaxone", "ceftriaxone", "Cephalosporin antibiotic", "injection", "1 g", 310, 150, 45, 65),
    ("Azithromycin", "azithromycin", "Macrolide antibiotic", "tablet", "500 mg", 520, 150, 25, 12),
    ("Clarithromycin", "clarithromycin", "Macrolide antibiotic", "tablet", "500 mg", 160, 60, 6, 24),
    ("Ciprofloxacin", "ciprofloxacin", "Fluoroquinolone antibiotic", "tablet", "500 mg", 480, 150, 20, 5),
    ("Meropenem", "meropenem", "Carbapenem antibiotic", "injection", "1 g", 22, 40, 8, 1450),
    ("Cotrimoxazole", "cotrimoxazole", "Sulfonamide antibiotic", "tablet", "960 mg", 260, 80, 8, 3),
    ("Metronidazole", "metronidazole", "Antibiotic", "injection", "500 mg", 200, 100, 22, 28),
    ("Omeprazole", "omeprazole", "PPI", "capsule", "20 mg", 1400, 300, 70, 1.9),
    ("Pantoprazole", "pantoprazole", "PPI", "injection", "40 mg", 340, 150, 40, 48),
    ("Ondansetron", "ondansetron", "Antiemetic", "injection", "4 mg", 280, 120, 35, 15),
    ("Salbutamol", "salbutamol", "Bronchodilator", "inhaler", "100 mcg", 140, 60, 9, 160),
    ("Budesonide", "budesonide", "Corticosteroid", "nebule", "0.5 mg", 96, 80, 12, 38),
    ("Hydrocortisone", "hydrocortisone", "Corticosteroid", "injection", "100 mg", 130, 60, 10, 60),
    ("Tramadol", "tramadol", "Opioid analgesic", "injection", "50 mg", 180, 80, 16, 22),
    ("Morphine", "morphine", "Opioid analgesic", "injection", "10 mg", 70, 50, 6, 55),
    ("Sertraline", "sertraline", "SSRI", "tablet", "50 mg", 300, 80, 5, 6),
    ("Digoxin", "digoxin", "Cardiac glycoside", "tablet", "0.25 mg", 200, 60, 4, 2),
    ("Amiodarone", "amiodarone", "Antiarrhythmic", "tablet", "200 mg", 180, 60, 5, 9),
    ("Nitroglycerin", "nitroglycerin", "Nitrate", "spray", "0.4 mg", 75, 40, 4, 240),
    ("Sildenafil", "sildenafil", "PDE5 inhibitor", "tablet", "50 mg", 60, 20, 1, 25),
    ("Normal Saline", "sodium chloride", "IV fluid", "infusion", "500 ml", 820, 400, 160, 32),
    ("Ringer Lactate", "ringer lactate", "IV fluid", "infusion", "500 ml", 310, 300, 90, 38),
    ("Adrenaline", "adrenaline", "Vasopressor", "injection", "1 mg", 90, 50, 5, 30),
    ("Noradrenaline", "noradrenaline", "Vasopressor", "injection", "4 mg", 28, 30, 6, 120),
]

RESOURCES = [  # type, count, name prefix, location
    ("operating_room", 4, "OT", "Surgical Block, Floor 4"), ("ventilator", 8, "Ventilator", "Critical Care"),
    ("mri", 1, "MRI 3T", "Radiology"), ("ct", 2, "CT Scanner", "Radiology"), ("xray", 3, "Digital X-Ray", "Radiology"),
    ("ultrasound", 3, "Ultrasound", "Radiology"), ("ecg", 4, "ECG Machine", "Cardiology"), ("dialysis", 3, "Dialysis Unit", "Nephrology Bay"),
    ("defibrillator", 5, "Defibrillator", "Emergency / ICU"), ("infusion_pump", 12, "Infusion Pump", "Wards"),
    ("lab_analyzer", 3, "Lab Analyzer", "Pathology"),
]

RESULT_TEMPLATES = {
    "CBC": [("Hb 13.1 g/dL, WBC 7,800/µL, Platelets 2.4 lakh/µL — within normal limits", False),
            ("Hb 10.2 g/dL (L), WBC 16,400/µL (H), Platelets 1.1 lakh/µL (L)", True)],
    "TROP": [("Troponin I 0.01 ng/mL — negative", False), ("Troponin I 2.8 ng/mL (H) — suggestive of myocardial injury", True)],
    "CXR": [("No active lung parenchymal lesion. Heart size normal.", False), ("Right lower zone consolidation — suggestive of pneumonia", True)],
    "ECG": [("Normal sinus rhythm, rate 78/min", False), ("ST elevation in II, III, aVF", True)],
    "LFT": [("Bilirubin 0.8 mg/dL, SGPT 32 U/L — normal", False), ("SGPT 186 U/L (H), SGOT 142 U/L (H)", True)],
    "KFT": [("Creatinine 0.9 mg/dL, Urea 28 mg/dL — normal", False), ("Creatinine 2.4 mg/dL (H), Urea 88 mg/dL (H)", True)],
    "CRP": [("CRP 3 mg/L — normal", False), ("CRP 96 mg/L (H)", True)],
    "NS1": [("Dengue NS1 antigen — negative", False), ("Dengue NS1 antigen — POSITIVE", True)],
}

DEMO_USERS = [  # username, password, role, full name, link
    ("admin", "admin123", "admin", "Anita Desai (Administrator)", None),
    ("doctor", "doctor123", "doctor", None, ("doctor", "CAR")),
    ("er.doctor", "doctor123", "doctor", None, ("doctor", "ER")),
    ("nurse", "nurse123", "nurse", None, ("nurse", "ICU")),
    ("reception", "reception123", "receptionist", "Kavita Rao (Front Desk)", None),
    ("lab", "lab123", "lab", None, ("technician", "PATH")),
    ("pharmacist", "pharma123", "pharmacist", None, ("pharmacist", "PHA")),
    ("patient", "patient123", "patient", None, None),
]


def _name(gender: str) -> str:
    return f"{RNG.choice(FIRST_M if gender == 'Male' else FIRST_F)} {RNG.choice(LAST)}"


def _new_patient(db: Session, n: int, age: int | None = None, gender: str | None = None, name: str | None = None) -> Patient:
    gender = gender or RNG.choice(["Male", "Female"])
    age = age if age is not None else max(1, min(92, int(RNG.gauss(48, 20))))
    conds = RNG.sample(CONDITIONS, k=RNG.choice([0, 0, 1, 1, 2])) if age > 30 else []
    allergies = []
    r = RNG.random()
    if r < 0.10:
        allergies.append("penicillin")
    elif r < 0.15:
        allergies.append("sulfa")
    elif r < 0.19:
        allergies.append("nsaid")
    p = Patient(mrn=f"MRN-{1001 + n}", name=name or _name(gender), age=age, gender=gender,
                phone=f"+91 9{RNG.randint(100000000, 999999999)}", blood_group=RNG.choice(["A+", "B+", "O+", "AB+", "A-", "O-", "B-"]),
                allergies=allergies, conditions=conds, status="registered",
                created_at=datetime.now() - timedelta(days=RNG.randint(0, 400)))
    db.add(p)
    return p


def seed(db: Session) -> None:
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    depts = {}
    for name, code, floor, consult in DEPARTMENTS:
        d = Department(name=name, code=code, floor=floor, avg_consult_minutes=consult)
        db.add(d)
        depts[code] = d
    db.flush()

    # ---------------------------------------------------------------- staff
    used_names = set()

    def staff_name(prefix=""):
        while True:
            g = RNG.choice(["Male", "Female"])
            n = _name(g)
            if n not in used_names:
                used_names.add(n)
                return prefix + n

    doctors: list[Staff] = []
    for code, count, spec in DOCTORS:
        for i in range(count):
            s = Staff(name="Dr. Rajesh Sharma" if (code == "CAR" and i == 0) else staff_name("Dr. "), role="doctor", specialization=spec,
                      department_id=depts[code].id, seniority=RNG.choice(["consultant", "senior", "senior", "mid", "junior"]) if i else "consultant",
                      skills=RNG.sample(["ACLS", "ventilator management", "ultrasound", "echo", "procedural sedation", "trauma care"], k=2),
                      max_patients=14, current_load=0, on_duty=(i < max(1, math.ceil(count * 0.7))) or RNG.random() < 0.3,
                      phone=f"+91 98{RNG.randint(10000000, 99999999)}")
            db.add(s)
            doctors.append(s)
    nurses: list[Staff] = []
    for code, count in NURSES:
        for i in range(count):
            skills = ["iv therapy", "wound care"]
            if code in ("ICU", "CAR"):
                skills += ["critical care", "ventilator"]
            if code == "ER":
                skills += ["triage", "critical care"] if i % 2 == 0 else ["triage"]
            if code == "PED":
                skills.append("pediatric")
            s = Staff(name="Priya Nair" if (code == "ICU" and i == 0) else staff_name(), role="nurse", specialization="Nursing",
                      department_id=depts[code].id, seniority=RNG.choice(["senior", "mid", "mid", "junior"]), skills=skills,
                      max_patients=3 if code in ("ICU", "CAR") else 6, current_load=0,
                      on_duty=i < math.ceil(count * 0.75), phone=f"+91 97{RNG.randint(10000000, 99999999)}")
            db.add(s)
            nurses.append(s)
    techs = []
    for code, count in (("RAD", 3), ("PATH", 3)):
        for _ in range(count):
            s = Staff(name=staff_name(), role="technician", specialization="Radiology" if code == "RAD" else "Laboratory",
                      department_id=depts[code].id, skills=[], max_patients=20, on_duty=True)
            db.add(s)
            techs.append(s)
    pharmacists = []
    for _ in range(3):
        s = Staff(name=staff_name(), role="pharmacist", specialization="Clinical Pharmacy", department_id=depts["PHA"].id,
                  skills=[], max_patients=40, on_duty=True)
        db.add(s)
        pharmacists.append(s)
    db.flush()

    # ---------------------------------------------------------------- wards / beds
    wards = {}
    for name, wtype, code, floor, nbeds, prefix, ratio, _ in WARDS:
        w = Ward(name=name, ward_type=wtype, department_id=depts[code].id, floor=floor, nurse_ratio=ratio)
        db.add(w)
        db.flush()
        wards[prefix] = w
        for i in range(1, nbeds + 1):
            feats = {
                "ER": ["monitor", "oxygen"] + (["ventilator"] if i <= 2 else []),
                "ICU": ["monitor", "oxygen"] + (["ventilator"] if i <= 6 else []),
                "CCU": ["cardiac_monitor", "monitor", "oxygen"],
                "HDU": ["monitor", "oxygen"],
                "ISO": ["isolation", "oxygen"] + (["monitor"] if i <= 3 else []),
            }.get(prefix, ["oxygen"] if i % 2 == 0 else [])
            db.add(Bed(code=f"{prefix}-{i:02d}", ward_id=w.id, bed_type=wtype, features=feats, status="available"))
    db.flush()

    # ---------------------------------------------------------------- resources
    for rtype, count, prefix, loc in RESOURCES:
        for i in range(1, count + 1):
            status = "available"
            if rtype == "ventilator" and i <= 5:
                status = "in_use"
            if (rtype, i) in {("ct", 2), ("infusion_pump", 12), ("xray", 3)}:
                status = "maintenance" if rtype != "ct" else "in_use"
            db.add(Resource(name=f"{prefix}-{i}" if count > 1 else prefix, resource_type=rtype, status=status, location=loc,
                            usage_hours=round(RNG.uniform(200, 5200), 1),
                            last_maintenance=date.today() - timedelta(days=RNG.randint(5, 200)),
                            next_free_at=now + timedelta(minutes=RNG.randint(10, 50)) if status == "in_use" else None))
    db.flush()

    # ---------------------------------------------------------------- 108 ambulance fleet (pre-hospital coordination)
    for code, vtype, base in FLEET:
        lat, lng = (HOSPITAL["lat"], HOSPITAL["lng"]) if base == "Hospital base" else LOCALITIES[base]
        crew = [f"{AUX.choice(FIRST_M + FIRST_F)} {AUX.choice(LAST)} (EMT)", f"{AUX.choice(FIRST_M)} {AUX.choice(LAST)} (driver)"]
        if vtype == "ALS":
            crew.insert(0, f"{AUX.choice(FIRST_M + FIRST_F)} {AUX.choice(LAST)} (paramedic)")
        db.add(Ambulance(code=code, vehicle_type=vtype, base=base, base_lat=lat, base_lng=lng, lat=lat, lng=lng, crew=crew,
                         status="maintenance" if code == "AMB-08" else "available"))
    db.flush()

    # ---------------------------------------------------------------- patients
    patients: list[Patient] = []
    demo_patient = _new_patient(db, 0, age=34, gender="Male", name="Rohan Mehta")
    demo_patient.conditions, demo_patient.allergies = ["Hypertension"], ["penicillin"]
    patients.append(demo_patient)
    for n in range(1, 320):
        patients.append(_new_patient(db, n))
    for p in patients[1:]:  # payer mix: ~35% PM-JAY beneficiaries, ~15% private insurance
        r = AUX.random()
        if r < 0.35:
            p.insurance_scheme, p.insurance_id = "pmjay", f"PMJAY-{AUX.randint(10**8, 10**9 - 1)}"
        elif r < 0.5:
            p.insurance_scheme, p.insurance_id = "private", f"PVT-{AUX.randint(10**4, 10**5 - 1)}"
    demo_patient.phone, demo_patient.insurance_scheme, demo_patient.insurance_id = "+91 98220 41234", "private", "PVT-44821"
    db.flush()
    free_pool = [p for p in patients[1:]]
    RNG.shuffle(free_pool)

    def take_patient(min_age=0, max_age=120, gender=None):
        for i, p in enumerate(free_pool):
            if min_age <= p.age <= max_age and (gender is None or p.gender == gender):
                return free_pool.pop(i)
        return free_pool.pop()

    # ---------------------------------------------------------------- admissions
    docs_by_dept = {}
    for d in doctors:
        docs_by_dept.setdefault(d.department_id, []).append(d)
    nurses_by_dept = {}
    for n in nurses:
        nurses_by_dept.setdefault(n.department_id, []).append(n)

    def pick_least(pool):
        pool = [s for s in pool if s.current_load < s.max_patients] or pool
        return min(pool, key=lambda s: (not s.on_duty, s.current_load / s.max_patients))

    care_templates = ["Registration & consent verified", "Bed allocated and prepared", "Admission assessment by doctor",
                      "Nursing admission, baseline vitals & NEWS2", "Diagnostic workup completed", "Treatment plan documented",
                      "Daily clinical review", "Discharge planning initiated"]
    step_types = ["registration", "bed", "assessment", "nursing", "diagnostics", "treatment", "review", "discharge"]
    roles = ["receptionist", "nurse", "doctor", "nurse", "lab", "doctor", "doctor", "nurse"]
    admitted: list[tuple[Patient, Admission]] = []
    for name, wtype, code, floor, nbeds, prefix, ratio, occ in WARDS:
        if prefix == "ER":
            continue
        w = wards[prefix]
        beds = sorted(w.beds, key=lambda b: b.code)
        RNG.shuffle(beds)
        if prefix == "ICU":  # keep one ventilator-equipped ICU bed free (synopsis ICU-admission demo)
            beds.sort(key=lambda b: b.code == "ICU-02")
        n_occ = round(nbeds * occ)
        for b in beds[:n_occ]:
            if prefix == "PED":
                p = take_patient(1, 13)
            elif prefix == "MAT":
                p = take_patient(20, 40, "Female")
            else:
                p = take_patient(16, 95)
            dept_id = w.department_id
            doc = pick_least(docs_by_dept.get(dept_id) or docs_by_dept[depts["GM"].id])
            nurse = pick_least(nurses_by_dept.get(dept_id) or nurses_by_dept[depts["GM"].id])
            admitted_at = now - timedelta(hours=RNG.randint(6, 144))
            r = RNG.random()
            remaining_h = RNG.uniform(-6, -1) if r < 0.04 else RNG.uniform(1, 12) if r < 0.2 else RNG.uniform(14, 120)
            adm = Admission(patient_id=p.id, bed_id=b.id, doctor_id=doc.id, nurse_id=nurse.id, reason=RNG.choice(REASONS[prefix]),
                            acuity={"icu": "critical", "cardiac": "high", "hdu": "high"}.get(wtype, RNG.choice(["low", "moderate"])),
                            admitted_at=admitted_at, expected_discharge=now + timedelta(hours=remaining_h))
            db.add(adm)
            b.status, b.patient_id = "occupied", p.id
            p.status = "icu" if wtype == "icu" else "admitted"
            p.primary_doctor_id = doc.id
            doc.current_load += 1
            nurse.current_load += 1
            admitted.append((p, adm))
            hours = (now - admitted_at).total_seconds() / 3600
            done_upto = min(7, 3 + int(hours // 24))
            for i, title in enumerate(care_templates):
                status = "done" if i < done_upto else ("in_progress" if i == done_upto else "pending")
                db.add(CareTask(patient_id=p.id, pathway="admission", title=title, step_type=step_types[i], sequence=i, status=status,
                                assigned_role=roles[i], created_by="Patient Care Coordinator Agent",
                                due_at=admitted_at + timedelta(hours=2 + i * 8),
                                completed_at=admitted_at + timedelta(hours=1 + i * 6) if status == "done" else None,
                                created_at=admitted_at))
        for b in beds[n_occ:]:
            r = RNG.random()
            if r < 0.12:
                b.status = "cleaning"
                b.updated_at = now - timedelta(minutes=RNG.randint(10, 100))
            elif r < 0.15:
                b.status = "maintenance"
    db.flush()

    # ---------------------------------------------------------------- bedside observations (NEWS2 early warning)
    deteriorating = set(RNG.sample(range(len(admitted)), k=min(5, len(admitted))))
    for idx, (p, adm) in enumerate(admitted):
        wtype = db.get(Bed, adm.bed_id).ward.ward_type
        sick = wtype in ("icu", "hdu", "cardiac")
        nurse_name = db.get(Staff, adm.nurse_id).name if adm.nurse_id else "Ward nurse"
        score = 0
        for k in range(6):
            t = now - timedelta(hours=20 - k * 4) if k < 5 else now - timedelta(minutes=RNG.randint(15, 200))
            drift = (k / 5) if idx in deteriorating else 0.0
            vit = {"hr": round(RNG.gauss(102 if sick else 82, 7) + drift * 30), "rr": round(RNG.gauss(20 if sick else 16, 1.5) + drift * 7),
                   "spo2": round(min(100, RNG.gauss(94.5 if sick else 97.5, 1.0) - drift * 4)),
                   "sbp": round(RNG.gauss(114 if sick else 126, 9) - drift * 20), "dbp": round(RNG.gauss(72, 6)),
                   "temp": round(RNG.gauss(37.3 if sick else 36.9, 0.3) + drift * 1.1, 1)}
            on_o2 = sick and idx % 3 != 0
            score, comps = compute_news2(vit | {"on_oxygen": on_o2})
            db.add(VitalSign(patient_id=p.id, recorded_at=t, consciousness="A", on_oxygen=on_o2, news2=score,
                             risk=clinical_risk(score, comps), recorded_by=nurse_name, **vit))
        p.risk_score = round(min(1.0, score / 12), 2)
    db.flush()

    # ---------------------------------------------------------------- operating theatres (today + an unoptimised tomorrow)
    theatres = sorted(db.scalars(select(Resource).where(Resource.resource_type == "operating_room")).all(), key=lambda r: r.name)
    surg_docs = {c: docs_by_dept[depts[c].id] for c in ("GS", "ORT", "OBG", "NEU", "ONC")}
    lists_today = [
        [("GS", "appendectomy", 0), ("GS", "cholecystectomy", 1), ("GS", "hernia", 0), ("GS", "debridement", 1)],
        [("ORT", "tkr", 0), ("ORT", "hip", 1), ("ORT", "orif", 2)],
        [("OBG", "csection", 0), ("OBG", "hysterectomy", 1), ("ONC", "mastectomy", 0)],
        [("NEU", "craniotomy", 0), ("GS", "laparotomy", 2)],
    ]

    def book(theatre, day_base, start_min, code, key, doc_idx, priority="elective"):
        meta = PROCEDURES[key]
        start = day_base + timedelta(minutes=start_min)
        end = start + timedelta(minutes=meta["duration"])
        status = "completed" if end <= now else "in_progress" if start <= now else "scheduled"
        pt = take_patient(20, 40, "Female") if code == "OBG" else take_patient(18, 85)
        docs = surg_docs[code]
        s = Surgery(patient_id=pt.id, surgeon_id=docs[doc_idx % len(docs)].id, ot_id=theatre.id, procedure=meta["name"],
                    specialty=meta["specialty"], priority=priority, scheduled_start=start, duration_minutes=meta["duration"],
                    anaesthesia=meta["anaesthesia"], status=status, created_by="Theatre coordinator",
                    started_at=start if status != "scheduled" else None, completed_at=end if status == "completed" else None)
        db.add(s)
        if status == "in_progress":
            theatre.status = "in_use"
        return meta["duration"]

    for theatre, plan in zip(theatres, lists_today):
        cursor = 8 * 60
        for code, key, di in plan:
            pr = "urgent" if key in ("laparotomy", "csection") else "elective"
            cursor += book(theatre, today, cursor, code, key, di, pr) + TURNOVER + RNG.choice([0, 15, 30])
    tomorrow = today + timedelta(days=1)
    for theatre, items in zip(theatres, [[(14 * 60, "GS", "cholecystectomy", 0), (16 * 60 + 30, "GS", "hernia", 1)],
                                         [(15 * 60, "ORT", "tkr", 0), (17 * 60 + 45, "ORT", "spine", 1)],
                                         [(18 * 60, "OBG", "hysterectomy", 1)], []]):
        for start_min, code, key, di in items:
            book(theatre, tomorrow, start_min, code, key, di)
    db.flush()

    # ---------------------------------------------------------------- emergency department
    er_doctors = docs_by_dept[depts["ER"].id]
    er_beds = sorted(wards["ER"].beds, key=lambda b: b.code)
    er_cases = [
        ("Chest pain radiating to left arm, sweating", {"hr": 112, "rr": 22, "spo2": 95, "sbp": 104, "temp": 37.1}, "ambulance", "in_treatment", 55),
        ("Road accident — right leg injury, conscious", {"hr": 104, "rr": 20, "spo2": 97, "sbp": 118, "temp": 36.8}, "ambulance", "in_treatment", 80),
        ("High fever with chills for 3 days", {"hr": 108, "rr": 21, "spo2": 96, "sbp": 112, "temp": 39.4}, "walk-in", "in_treatment", 40),
        ("Acute asthma attack, wheezing", {"hr": 118, "rr": 26, "spo2": 92, "sbp": 124, "temp": 37.0, "on_oxygen": True}, "walk-in", "in_treatment", 30),
        ("Breathlessness since morning", {"hr": 116, "rr": 25, "spo2": 91, "sbp": 108, "temp": 37.6}, "walk-in", "awaiting_bed", 26),
        ("Severe abdominal pain with vomiting", {"hr": 98, "rr": 19, "spo2": 98, "sbp": 126, "temp": 37.9}, "walk-in", "awaiting_bed", 18),
        ("Fall at home — wrist pain and swelling", {"hr": 84, "rr": 16, "spo2": 99, "sbp": 132, "temp": 36.7}, "walk-in", "triage", 6),
    ]
    for i, (complaint, vitals, mode, status, mins) in enumerate(er_cases):
        p = take_patient(18, 85)
        res = triage(vitals, complaint, p.age)
        case = EmergencyCase(patient_id=p.id, arrival_mode=mode, chief_complaint=complaint, vitals=vitals, news2_score=res.news2,
                             triage_level=res.triage_level, status=status, created_at=now - timedelta(minutes=mins))
        if status == "in_treatment":
            bed = er_beds[i + 2]
            bed.status, bed.patient_id = "occupied", p.id
            doc = er_doctors[i % len(er_doctors)]
            case.assigned_bed_id, case.assigned_doctor_id = bed.id, doc.id
            case.seen_at = case.created_at + timedelta(minutes=min(res.target_minutes, 8))
            doc.current_load += 1
        db.add(case)
        p.status = "emergency"
        p.risk_score = round(min(1.0, res.news2 / 12), 2)
    er_beds[-1].status = "cleaning"
    er_beds[-1].updated_at = now - timedelta(minutes=25)
    db.flush()

    # ---------------------------------------------------------------- OPD appointments (today + upcoming)
    opd_depts = ["CAR", "NEU", "ORT", "GM", "GS", "PED", "OBG", "ONC", "PUL"]
    reasons = {"CAR": ["Chest discomfort on exertion", "BP follow-up", "Palpitations"], "NEU": ["Recurrent headache", "Numbness in hands", "Seizure follow-up"],
               "ORT": ["Knee pain", "Lower back pain", "Shoulder stiffness"], "GM": ["Fever and cough", "Diabetes review", "Fatigue", "Stomach ache"],
               "GS": ["Hernia consultation", "Post-op review"], "PED": ["Child with fever", "Vaccination visit"], "OBG": ["Antenatal check-up", "Irregular periods"],
               "ONC": ["Chemotherapy review"], "PUL": ["Chronic cough", "Asthma review"]}
    queue_counter: dict[int, int] = {}
    for _ in range(190):
        code = RNG.choice(opd_depts + ["GM", "GM", "GM", "CAR", "CAR", "ORT"])
        dept = depts[code]
        doc = RNG.choice(docs_by_dept[dept.id])
        slot_min = RNG.randrange(0, (17 - 9) * 60, dept.avg_consult_minutes)
        when = today + timedelta(hours=9, minutes=slot_min)
        p = take_patient(1 if code == "PED" else 16, 13 if code == "PED" else 90) if free_pool else RNG.choice(patients)
        if when < now - timedelta(minutes=50):
            status = RNG.choices(["completed", "no_show"], [0.93, 0.07])[0]
        elif when < now - timedelta(minutes=15):
            status = RNG.choices(["completed", "in_progress", "checked_in"], [0.5, 0.2, 0.3])[0]
        elif when < now + timedelta(minutes=40):
            status = RNG.choices(["checked_in", "scheduled"], [0.7, 0.3])[0]
        else:
            status = "scheduled"
        queue_counter[doc.id] = queue_counter.get(doc.id, 0) + 1
        appt = Appointment(patient_id=p.id, doctor_id=doc.id, department_id=dept.id, scheduled_at=when, status=status,
                           priority=RNG.choices([2, 3, 4], [0.15, 0.7, 0.15])[0], reason=RNG.choice(reasons[code]),
                           queue_number=queue_counter[doc.id], booked_by=RNG.choice(["reception", "patient portal", "phone"]))
        if status in ("checked_in", "in_progress", "completed"):
            appt.checked_in_at = min(when, now) - timedelta(minutes=RNG.randint(5, 40))
        if status in ("in_progress", "completed"):
            appt.started_at = appt.checked_in_at + timedelta(minutes=RNG.randint(8, 35))
            if appt.started_at > now:
                appt.started_at = now - timedelta(minutes=2)
        if status == "completed":
            appt.completed_at = min(appt.started_at + timedelta(minutes=dept.avg_consult_minutes + RNG.randint(-3, 6)), now)
        if status in ("checked_in", "in_progress"):
            p.status = "waiting" if status == "checked_in" else "in_consultation"
        db.add(appt)
    # demo patient: upcoming cardiology visit tomorrow
    cardio_doc = next(d for d in doctors if d.name == "Dr. Rajesh Sharma")
    db.add(Appointment(patient_id=demo_patient.id, doctor_id=cardio_doc.id, department_id=depts["CAR"].id,
                       scheduled_at=today + timedelta(days=1, hours=11), status="scheduled", priority=3,
                       reason="BP follow-up and lipid review", queue_number=4, booked_by="patient portal"))
    db.add(Appointment(patient_id=demo_patient.id, doctor_id=cardio_doc.id, department_id=depts["CAR"].id,
                       scheduled_at=today - timedelta(days=12, hours=-10), status="completed", priority=3,
                       reason="Hypertension review", queue_number=2, booked_by="reception",
                       checked_in_at=today - timedelta(days=12, hours=-10), started_at=today - timedelta(days=12, hours=-10, minutes=-12),
                       completed_at=today - timedelta(days=12, hours=-10, minutes=-27)))
    # demo patient: an appointment later today, used to demonstrate the self check-in kiosk (MRN-1001 + phone 1234)
    db.add(Appointment(patient_id=demo_patient.id, doctor_id=cardio_doc.id, department_id=depts["CAR"].id,
                       scheduled_at=(now + timedelta(minutes=90)).replace(second=0, microsecond=0), status="scheduled", priority=3,
                       reason="ECG and BP check", queue_number=queue_counter.get(cardio_doc.id, 0) + 1, booked_by="patient portal"))
    db.flush()

    # ---------------------------------------------------------------- diagnostics
    analyzers = db.scalars(select(Resource).where(Resource.resource_type == "lab_analyzer")).all()
    modality = {}
    for r in db.scalars(select(Resource)).all():
        modality.setdefault(r.resource_type, []).append(r)
    codes = ["CBC", "CBC", "KFT", "LFT", "CRP", "CXR", "ECG", "TROP", "USG", "CTH", "NS1", "ABG", "LIPID", "HBA1C", "URINE", "MRIB", "ECHO"]
    for _ in range(46):
        p, adm = RNG.choice(admitted)
        code = RNG.choice(codes)
        meta = TEST_CATALOG[code]
        created = now - timedelta(minutes=RNG.randint(20, 900))
        status = RNG.choices(["completed", "in_progress", "scheduled", "ordered"], [0.55, 0.15, 0.18, 0.12])[0]
        res_pool = modality.get(meta["modality"]) or analyzers
        order = DiagnosticOrder(patient_id=p.id, ordered_by_id=adm.doctor_id, test_code=code, test_name=meta["name"],
                                category=meta["category"], priority=RNG.choices(["routine", "urgent", "stat"], [0.65, 0.25, 0.1])[0],
                                status=status, resource_id=RNG.choice(res_pool).id, created_at=created,
                                scheduled_at=created + timedelta(minutes=RNG.randint(10, 90)) if status != "ordered" else None)
        if status == "completed":
            text, abnormal = RNG.choice(RESULT_TEMPLATES.get(code, [("Report within normal limits", False), ("Abnormal findings — see report", True)]))
            order.result, order.abnormal = text, abnormal
            order.completed_at = min(created + timedelta(minutes=meta["tat"] * RNG.uniform(0.6, 1.3)), now)
        db.add(order)
    db.add(DiagnosticOrder(patient_id=demo_patient.id, ordered_by_id=cardio_doc.id, test_code="LIPID", test_name="Lipid Profile",
                           category="lab", priority="routine", status="completed", resource_id=analyzers[0].id,
                           created_at=today - timedelta(days=12), completed_at=today - timedelta(days=11),
                           result="Total cholesterol 228 mg/dL (H), LDL 152 mg/dL (H), HDL 41 mg/dL", abnormal=True))
    db.flush()

    # ---------------------------------------------------------------- pharmacy
    meds = {}
    for name, generic, cls, form, strength, stock, reorder, usage, price in MEDICATIONS:
        m = Medication(name=name, generic=generic, drug_class=cls, form=form, strength=strength, stock=stock, reorder_level=reorder,
                       daily_usage=usage, unit_price=price, expiry=date.today() + timedelta(days=RNG.randint(120, 720)))
        db.add(m)
        meds[generic] = m
    meds["morphine"].expiry = date.today() + timedelta(days=35)
    meds["budesonide"].expiry = date.today() + timedelta(days=48)
    db.flush()
    common = ["paracetamol", "pantoprazole", "ceftriaxone", "ondansetron", "metformin", "amlodipine", "atorvastatin", "aspirin",
              "enoxaparin", "furosemide", "azithromycin", "insulin regular", "tramadol", "salbutamol"]
    for p, adm in RNG.sample(admitted, k=min(34, len(admitted))):
        for generic in RNG.sample(common, k=RNG.choice([1, 2])):
            m = meds[generic]
            db.add(Prescription(patient_id=p.id, doctor_id=adm.doctor_id, medication_id=m.id, dose=m.strength,
                                frequency=RNG.choice(["OD", "BD", "TDS"]), duration_days=RNG.choice([3, 5, 7]), quantity=10,
                                status=RNG.choices(["dispensed", "verified", "pending"], [0.6, 0.2, 0.2])[0],
                                created_at=adm.admitted_at + timedelta(hours=2)))
    # a warfarin patient (sets up an interaction demo) and a flagged pending prescription
    wp, wadm = admitted[3]
    wp.conditions = list(set((wp.conditions or []) + ["Atrial fibrillation"]))
    db.add(Prescription(patient_id=wp.id, doctor_id=wadm.doctor_id, medication_id=meds["warfarin"].id, dose="5 mg", frequency="OD",
                        duration_days=30, quantity=30, status="dispensed", created_at=wadm.admitted_at + timedelta(hours=3)))
    db.add(Prescription(patient_id=demo_patient.id, doctor_id=cardio_doc.id, medication_id=meds["amlodipine"].id, dose="5 mg",
                        frequency="OD", duration_days=30, quantity=30, status="dispensed", created_at=today - timedelta(days=12)))
    db.add(Prescription(patient_id=demo_patient.id, doctor_id=cardio_doc.id, medication_id=meds["atorvastatin"].id, dose="20 mg",
                        frequency="HS", duration_days=30, quantity=30, status="dispensed", created_at=today - timedelta(days=12)))
    db.flush()

    # ---------------------------------------------------------------- shifts (current week, simple rotation)
    for s in doctors + nurses:
        for d in range(7):
            if (s.id + d) % 7 in (0, 3):
                continue
            db.add(Shift(staff_id=s.id, date=date.today() + timedelta(days=d), shift_type=["morning", "evening", "night"][(s.id + d // 2) % 3],
                         department_id=s.department_id, generated_by="seed"))

    # ---------------------------------------------------------------- historical daily statistics (for analytics & forecasting)
    for i in range(180, 0, -1):
        day = date.today() - timedelta(days=i)
        dow = day.weekday()
        weekly = [1.18, 1.08, 1.02, 1.0, 1.04, 0.86, 0.72][dow]
        monsoon = 1.18 if day.month in (7, 8, 9) else 1.0
        trend = 1 + (180 - i) * 0.0008
        adm = max(8, round(22 * weekly * monsoon * trend + RNG.gauss(0, 2.2)))
        er = max(15, round(46 * (0.9 + 0.2 * (dow >= 5)) * monsoon * trend + RNG.gauss(0, 4)))
        opd = max(80, round(330 * weekly * trend + RNG.gauss(0, 18)))
        occ = min(0.97, max(0.55, 0.74 * monsoon * (0.96 + 0.06 * weekly) + RNG.gauss(0, 0.025)))
        icu = min(0.99, max(0.6, occ + 0.07 + RNG.gauss(0, 0.03)))
        db.add(DailyStat(day=day, admissions=adm, discharges=max(6, adm + RNG.randint(-3, 3)), er_visits=er, opd_visits=opd,
                         surgeries=max(2, round(9 * weekly + RNG.gauss(0, 1.5))), bed_occupancy=round(occ, 3),
                         icu_occupancy=round(icu, 3), avg_wait_minutes=round(max(12, 18 + 22 * occ * weekly + RNG.gauss(0, 4)), 1)))

    db.flush()

    # ---------------------------------------------------------------- billing: auto-captured charges, deposits, pre-auth claims
    for p, adm in admitted:
        inv = billing.sync_patient(db, p, force=True)
        if not inv:
            continue
        s = billing.summarize(inv)
        if inv.payer == "self" and s["balance"] > 5000 and AUX.random() < 0.6:
            deposit = min(round(s["balance"] * 0.6, -2), AUX.choice([10000, 15000, 20000, 25000]))
            billing.record_payment(db, inv, deposit, AUX.choice(["upi", "card", "cash"]), f"DEP-{AUX.randint(10**6, 10**7 - 1)}", "Kavita Rao (Front Desk)")
        elif inv.payer == "private" and AUX.random() < 0.6:
            billing.submit_claim(db, inv)  # cashless pre-authorisation already sent to the TPA
    first_private = db.scalar(select(InsuranceClaim).where(InsuranceClaim.scheme == "private").order_by(InsuranceClaim.id))
    if first_private:
        billing.decide_claim(db, first_private, True, round(first_private.claimed_amount * 0.9, -2), "Approved with 10% non-payables deduction")

    # ---------------------------------------------------------------- clinical notes (signed progress notes)
    for p, adm in admitted[:10]:
        doc = db.get(Staff, adm.doctor_id)
        db.add(ClinicalNote(patient_id=p.id, note_type="progress", status="signed", author=f"{doc.name} (doctor)",
                            subjective="Feels better than yesterday; tolerating oral diet. No new complaints overnight.",
                            objective="Afebrile on the ward round; haemodynamically stable. Chest clear, abdomen soft.",
                            assessment=f"{adm.reason} — clinically improving.",
                            plan="- Continue current treatment\n- Review investigations on the evening round\n- Mobilise with physiotherapy",
                            created_at=adm.admitted_at + timedelta(hours=18)))

    # ---------------------------------------------------------------- users
    staff_by_role_dept = {}
    for s in doctors + nurses + techs + pharmacists:
        staff_by_role_dept.setdefault((s.role, s.department_id), []).append(s)
    for username, pw, role, full, link in DEMO_USERS:
        staff_id = patient_id = None
        if link:
            srole, code = link
            pool = staff_by_role_dept[(srole, depts[code].id)]
            s = next((x for x in pool if x.name in ("Dr. Rajesh Sharma", "Priya Nair")), pool[0])
            s.on_duty = True
            staff_id, full = s.id, s.name
        if role == "patient":
            patient_id, full = demo_patient.id, demo_patient.name
        db.add(User(username=username, full_name=full, role=role, password_hash=hash_password(pw),
                    email=f"{username.replace('.', '_')}@citycare.example", staff_id=staff_id, patient_id=patient_id,
                    department_id=db.get(Staff, staff_id).department_id if staff_id else None))

    # ---------------------------------------------------------------- initial alerts
    db.add(Notification(role="pharmacist", title="Low stock: 6 medicines", message="Heparin, Insulin Regular, Piperacillin-Tazobactam, Meropenem, Noradrenaline at/below reorder level.",
                        level="warning", category="pharmacy", link="/pharmacy", created_at=now - timedelta(minutes=50)))
    db.add(Notification(role="admin", title="ICU occupancy 80%", message="Medical ICU is at 80% occupancy; 2 beds free (1 with ventilator).",
                        level="warning", category="capacity", link="/beds", created_at=now - timedelta(minutes=35)))
    db.add(Notification(role="nurse", title="ED patient past target time", message="Breathlessness case waiting 26 min (L2 target 10 min).",
                        level="critical", category="emergency", link="/emergency", created_at=now - timedelta(minutes=16)))
    db.add(AuditLog(actor="system", actor_type="system", action="seed", entity="database", details={"patients": len(patients)}))
    db.commit()


def reset_and_seed() -> None:
    from .services.telemetry import hub
    billing._recent_sync.clear()
    hub.state.clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


def needs_seed() -> bool:
    db = SessionLocal()
    try:
        return db.scalar(select(User).limit(1)) is None
    finally:
        db.close()


def schema_outdated() -> bool:
    """True when the database predates the current models (missing table or column) → rebuild the demo data."""
    from sqlalchemy import inspect

    insp = inspect(engine)
    existing = set(insp.get_table_names())
    if not existing:
        return False
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            return True
        cols = {c["name"] for c in insp.get_columns(table.name)}
        if any(c.name not in cols for c in table.columns):
            return True
    return False


def is_stale() -> bool:
    """Demo data is anchored to 'today'; older data (e.g. seeded yesterday) is refreshed on start-up."""
    db = SessionLocal()
    try:
        last = db.scalar(select(DailyStat.day).order_by(DailyStat.day.desc()).limit(1))
        return last is not None and last < date.today() - timedelta(days=1)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables")
    args = parser.parse_args()
    if args.reset or needs_seed():
        reset_and_seed()
        print("Database seeded.")
    else:
        print("Database already contains data (use --reset to recreate).")
