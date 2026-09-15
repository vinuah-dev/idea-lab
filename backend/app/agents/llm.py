"""Optional Claude integration for natural-language understanding and coordination briefs.

If ANTHROPIC_API_KEY is not configured (or a call fails) every caller falls back to the
local NLP pipeline, so the platform always works offline.
"""
from __future__ import annotations

import json
import logging

from ..config import settings
from ..services.ot_scheduler import PROCEDURES
from .nlp import INTENTS

log = logging.getLogger("medorchestra.llm")

try:  # pragma: no cover - import guard
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None

TEST_CODES = ["CBC", "LFT", "KFT", "TROP", "LIPID", "HBA1C", "ABG", "CRP", "BCUL", "COAG", "NS1", "URINE",
              "CXR", "CTH", "CTA", "MRIB", "USG", "ECG", "ECHO"]

UNDERSTANDING_SCHEMA = {
    "type": "object",
    "properties": {
        "intents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": list(INTENTS)},
                    "confidence": {"type": "number"},
                },
                "required": ["name", "confidence"],
                "additionalProperties": False,
            },
        },
        "patient_name": {"type": "string"},
        "age": {"type": "integer"},
        "gender": {"type": "string", "enum": ["", "Male", "Female", "Other"]},
        "bed_type": {"type": "string", "enum": ["", "icu", "hdu", "cardiac", "general", "isolation", "pediatric", "maternity", "emergency"]},
        "bed_features": {"type": "array", "items": {"type": "string", "enum": ["ventilator", "cardiac_monitor", "oxygen", "monitor"]}},
        "department": {"type": "string"},
        "tests": {"type": "array", "items": {"type": "string", "enum": TEST_CODES}},
        "medications": {"type": "array", "items": {"type": "string"}},
        "urgency": {"type": "string", "enum": ["", "routine", "urgent", "stat"]},
        "chief_complaint": {"type": "string"},
        "vitals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string", "enum": ["hr", "rr", "spo2", "sbp", "dbp", "temp"]}, "value": {"type": "number"}},
                "required": ["name", "value"],
                "additionalProperties": False,
            },
        },
        "staff_role": {"type": "string", "enum": ["", "doctor", "nurse", "technician"]},
        "staff_count": {"type": "integer"},
        "procedure": {"type": "string", "enum": [""] + list(PROCEDURES)},
        "rationale": {"type": "string"},
    },
    "required": ["intents", "patient_name", "age", "gender", "bed_type", "bed_features", "department", "tests",
                 "medications", "urgency", "chief_complaint", "vitals", "staff_role", "staff_count", "procedure", "rationale"],
    "additionalProperties": False,
}

UNDERSTANDING_SYSTEM = f"""You are the request-understanding component of a hospital operations multi-agent system.
Classify a staff member's request into one or more operational intents and extract structured entities.

Intents:
{chr(10).join(f"- {k}: {v}" for k, v in INTENTS.items())}

Rules:
- A request can carry several intents (e.g. admission + diagnostics). Order by relevance, confidence 0..1.
- Use "" for unknown strings, 0 for unknown integers and [] for unknown lists. Never invent values.
- tests: map mentioned investigations to the catalogue codes (CXR = chest x-ray, CTH = CT head, MRIB = MRI brain,
  TROP = troponin, BCUL = blood culture, COAG = PT/INR, USG = ultrasound, NS1 = dengue antigen).
- vitals: temperature in Celsius, spo2 in percent, sbp/dbp from "BP 90/60".
- procedure: the catalogue key of a surgical procedure if one is mentioned (e.g. "cholecystectomy", "tkr", "csection").
- This is operational decision support: do not give diagnoses or treatment advice. Keep rationale to one sentence."""

SUMMARY_SYSTEM = """You write concise coordination briefs for hospital staff after a multi-agent workflow has run.
Summarise what each agent found and what is awaiting human approval, in 3-6 short bullet points followed by
one "Next steps" line. Use plain text with "- " bullets. Do not provide diagnoses or treatment decisions — those
remain with the clinicians; you may restate the suggested workup as "for clinician review"."""


class LLMClient:
    def __init__(self) -> None:
        self.client = None
        self.last_error: str | None = None
        if settings.llm_available and anthropic is not None:
            self.client = anthropic.Anthropic(
                api_key=settings.anthropic_api_key, timeout=settings.llm_timeout_seconds, max_retries=1
            )

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def _call(self, system: str, user: str, max_tokens: int, output_format: dict | None = None) -> str | None:
        output_config: dict = {"effort": "low"}
        if output_format:
            output_config["format"] = output_format
        try:
            response = self.client.beta.messages.create(
                model=settings.llm_model,
                max_tokens=max_tokens,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config=output_config,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.AuthenticationError:
            self.last_error = "authentication failed — check ANTHROPIC_API_KEY"
        except anthropic.RateLimitError:
            self.last_error = "rate limited"
        except anthropic.APIStatusError as e:
            self.last_error = f"API error {e.status_code}"
        except anthropic.APIConnectionError:
            self.last_error = "network error"
        else:
            if response.stop_reason == "refusal":
                self.last_error = "request declined by model"
                return None
            self.last_error = None
            return next((b.text for b in response.content if b.type == "text"), None)
        log.warning("LLM call failed: %s", self.last_error)
        return None

    def understand(self, text: str) -> dict | None:
        if not self.enabled:
            return None
        raw = self._call(UNDERSTANDING_SYSTEM, text, 4096, {"type": "json_schema", "schema": UNDERSTANDING_SCHEMA})
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self.last_error = "invalid JSON from model"
            return None
        ent: dict = {}
        for key in ("patient_name", "department", "chief_complaint", "bed_type", "urgency", "gender", "staff_role", "procedure"):
            if data.get(key):
                ent[key] = data[key]
        for key in ("age", "staff_count"):
            if data.get(key):
                ent[key] = data[key]
        for key in ("bed_features", "tests"):
            if data.get(key):
                ent[key] = data[key]
        if data.get("medications"):
            ent["medication_names"] = data["medications"]
        if data.get("vitals"):
            ent["vitals"] = {v["name"]: v["value"] for v in data["vitals"]}
        intents = [i for i in data.get("intents", []) if i.get("name") in INTENTS]
        if not intents:
            return None
        return {
            "engine": f"Claude ({settings.llm_model})",
            "intents": intents,
            "confidence": intents[0]["confidence"],
            "entities": ent,
            "rationale": data.get("rationale", ""),
        }

    def summarize(self, request_text: str, findings: dict) -> str | None:
        if not self.enabled:
            return None
        payload = json.dumps(findings, default=str)[:12000]
        return self._call(SUMMARY_SYSTEM, f"Request: {request_text}\n\nAgent findings (JSON):\n{payload}", 2048)


llm = LLMClient()
