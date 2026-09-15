"""Runtime policy settings, including the human-in-the-loop autonomy mode."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Setting

DEFAULTS: dict = {
    "autonomy_mode": "balanced",
    "news2_review_threshold": 5,
    "news2_escalation_threshold": 7,
    "auto_icu_transfer_proposal": True,
}

AUTONOMY_MODES = {
    "supervised": "Every agent action waits for human approval (nothing executes automatically).",
    "balanced": "Low-risk, reversible actions run automatically; clinical and risky actions need approval (default).",
    "autonomous": "Low and medium-risk operational actions run automatically; high/critical-risk actions, prescribing, "
                  "discharge, staffing changes and AI-suggested workups still need approval.",
}

# actions a human must always sign off unless the mode is 'balanced' and the agent itself marked them auto
ALWAYS_REVIEW = {"create_prescription", "discharge_patient", "apply_roster", "reassign_staff"}


def get_setting(db: Session, key: str):
    row = db.get(Setting, key)
    if row is not None and isinstance(row.value, dict) and "v" in row.value:
        return row.value["v"]
    return DEFAULTS.get(key)


def all_settings(db: Session) -> dict:
    return {k: get_setting(db, k) for k in DEFAULTS}


def set_setting(db: Session, key: str, value) -> None:
    if key not in DEFAULTS:
        raise KeyError(key)
    if key == "autonomy_mode" and value not in AUTONOMY_MODES:
        raise ValueError(f"autonomy_mode must be one of {', '.join(AUTONOMY_MODES)}")
    row = db.get(Setting, key) or Setting(key=key)
    row.value = {"v": value}
    db.add(row)


def needs_approval(mode: str, action) -> bool:
    """Apply the configured autonomy policy to an agent's proposed action."""
    if mode == "supervised":
        return True
    if mode == "autonomous":
        ai_suggested = any("ai-suggested" in r.lower() for r in action.rationale)
        return action.requires_approval and (action.risk in ("high", "critical") or action.action_type in ALWAYS_REVIEW or ai_suggested)
    return action.requires_approval
