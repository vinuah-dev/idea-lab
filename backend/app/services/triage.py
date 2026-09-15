"""Emergency triage: NEWS2 early-warning score + complaint red-flags -> 5-level triage.

NEWS2 (National Early Warning Score 2, Royal College of Physicians, 2017) is a validated
bedside score built from six physiological parameters. Triage levels follow the
Manchester Triage System colour bands and target times.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

TRIAGE_LEVELS = {
    1: {"label": "Resuscitation", "color": "red", "target_minutes": 0},
    2: {"label": "Emergent", "color": "orange", "target_minutes": 10},
    3: {"label": "Urgent", "color": "yellow", "target_minutes": 60},
    4: {"label": "Less urgent", "color": "green", "target_minutes": 120},
    5: {"label": "Non-urgent", "color": "blue", "target_minutes": 240},
}

CRITICAL_FLAGS = [
    "cardiac arrest", "not breathing", "unconscious", "unresponsive", "no pulse", "massive bleeding",
    "severe bleeding", "choking", "anaphylaxis", "gunshot", "polytrauma",
]
EMERGENT_FLAGS = [
    "chest pain", "heart attack", "stroke", "facial droop", "slurred speech", "seizure", "fits",
    "difficulty breathing", "breathlessness", "shortness of breath", "severe breathing", "head injury",
    "road accident", "accident", "trauma", "sepsis", "overdose", "poisoning", "burns", "labour pain",
    "suicidal", "stab", "fracture with bleeding", "dka",
]
URGENT_FLAGS = [
    "abdominal pain", "fracture", "high fever", "vomiting", "dehydration", "asthma", "fall",
    "back pain", "dengue", "pneumonia", "bleeding", "fever", "dizziness", "fainting", "pregnant",
]
MINOR_FLAGS = ["sprain", "cut", "wound", "mild fever", "cough", "cold", "rash", "ear pain", "sore throat"]


@dataclass
class TriageResult:
    news2: int
    news2_components: dict[str, int]
    clinical_risk: str
    triage_level: int
    triage_label: str
    color: str
    target_minutes: int
    red_flags: list[str] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)
    recommended_area: str = "general"

    def to_dict(self) -> dict:
        return asdict(self)


def _score_rr(rr: float | None) -> int:
    if rr is None:
        return 0
    if rr <= 8:
        return 3
    if rr <= 11:
        return 1
    if rr <= 20:
        return 0
    if rr <= 24:
        return 2
    return 3


def _score_spo2(spo2: float | None) -> int:
    if spo2 is None:
        return 0
    if spo2 <= 91:
        return 3
    if spo2 <= 93:
        return 2
    if spo2 <= 95:
        return 1
    return 0


def _score_sbp(sbp: float | None) -> int:
    if sbp is None:
        return 0
    if sbp <= 90:
        return 3
    if sbp <= 100:
        return 2
    if sbp <= 110:
        return 1
    if sbp <= 219:
        return 0
    return 3


def _score_hr(hr: float | None) -> int:
    if hr is None:
        return 0
    if hr <= 40:
        return 3
    if hr <= 50:
        return 1
    if hr <= 90:
        return 0
    if hr <= 110:
        return 1
    if hr <= 130:
        return 2
    return 3


def _score_temp(t: float | None) -> int:
    if t is None:
        return 0
    if t <= 35.0:
        return 3
    if t <= 36.0:
        return 1
    if t <= 38.0:
        return 0
    if t <= 39.0:
        return 1
    return 2


def compute_news2(vitals: dict) -> tuple[int, dict[str, int]]:
    consciousness = str(vitals.get("consciousness", "A") or "A").upper()[:1]
    components = {
        "respiration_rate": _score_rr(vitals.get("rr")),
        "spo2": _score_spo2(vitals.get("spo2")),
        "supplemental_o2": 2 if vitals.get("on_oxygen") else 0,
        "systolic_bp": _score_sbp(vitals.get("sbp")),
        "pulse": _score_hr(vitals.get("hr")),
        "consciousness": 0 if consciousness == "A" else 3,
        "temperature": _score_temp(vitals.get("temp")),
    }
    return sum(components.values()), components


def clinical_risk(score: int, components: dict[str, int]) -> str:
    if score >= 7:
        return "high"
    if score >= 5:
        return "medium"
    if any(v == 3 for v in components.values()):
        return "low-medium"
    return "low"


def triage(vitals: dict | None, complaint: str = "", age: int | None = None) -> TriageResult:
    vitals = vitals or {}
    score, comps = compute_news2(vitals)
    risk = clinical_risk(score, comps)
    text = (complaint or "").lower()
    rationale: list[str] = [f"NEWS2 aggregate score {score} → {risk} clinical risk"]
    for name, pts in comps.items():
        if pts >= 2:
            rationale.append(f"{name.replace('_', ' ')} contributes {pts} points")

    flags_critical = [f for f in CRITICAL_FLAGS if f in text]
    flags_emergent = [f for f in EMERGENT_FLAGS if f in text]
    flags_urgent = [f for f in URGENT_FLAGS if f in text]
    flags_minor = [f for f in MINOR_FLAGS if f in text]

    if score >= 7 or flags_critical or comps["consciousness"] == 3:
        level = 1
    elif score >= 5 or flags_emergent or any(v == 3 for v in comps.values()):
        level = 2
    elif score >= 1 or flags_urgent:
        level = 3
    elif flags_minor:
        level = 4
    else:
        level = 4 if vitals else 5

    if age is not None and (age >= 75 or age <= 1) and level > 2:
        level -= 1
        rationale.append(f"Age {age} is a vulnerability factor → escalated one level")

    red_flags = flags_critical + flags_emergent
    if red_flags:
        rationale.append("Red-flag complaint keywords: " + ", ".join(red_flags))

    area = "resuscitation" if level == 1 else "icu" if (level == 2 and score >= 5) else "emergency"
    meta = TRIAGE_LEVELS[level]
    return TriageResult(
        news2=score,
        news2_components=comps,
        clinical_risk=risk,
        triage_level=level,
        triage_label=meta["label"],
        color=meta["color"],
        target_minutes=meta["target_minutes"],
        red_flags=red_flags,
        rationale=rationale,
        recommended_area=area,
    )
