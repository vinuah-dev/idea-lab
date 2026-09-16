"""Central AI Agent Orchestrator (synopsis §4.2).

Pipeline for every request:
 (i)   intake                      → AgentRequest record
 (ii)  NLP understanding           → intents + entities (Claude or local TF-IDF/LogReg, DB-grounded)
 (iii) workflow identification     → intent templates
 (iv)  agent selection & planning  → dependency DAG, topological levels
 (v)   coordinated execution       → agents share a blackboard and exchange FIPA-ACL style messages
 (vi)  constraint / conflict check → resource contention, overload, safety refusals
 (vii) recommendations & actions   → explainable factor breakdowns
 (viii) human-in-the-loop gate     → safety-critical actions become Approvals
 (ix)  execution of safe actions   → reversible / low-risk actions run automatically
 (x)   logging & notification      → trace, audit log, WebSocket push, role-based alerts
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime

from sqlalchemy import select

from ..config import settings
from ..database import SessionLocal
from ..events import bus
from ..models import AgentRequest, Approval, Medication, Patient, Staff, User
from ..security import APPROVER_ROLES
from ..services.activity import log_audit
from ..services.hinglish import normalize, resolve_pronoun
from ..services.settings_store import get_setting, needs_approval
from .ambulance_agent import AmbulanceDispatchAgent
from .appointment_agent import AppointmentQueueAgent
from .base import AgentContext, AgentResult, ProposedAction
from .bed_agent import BedManagementAgent
from .billing_agent import BillingInsuranceAgent
from .care_agent import PatientCareAgent
from .diagnostic_agent import DiagnosticCoordinationAgent
from .emergency_agent import EmergencySupportAgent
from .executor import ActionError, execute_action
from .llm import llm
from .nlp import understand_local
from .notification_agent import NotificationAgent
from .optimization_agent import ResourceOptimizationAgent
from .pharmacy_agent import PharmacyAgent
from .staff_agent import StaffSchedulingAgent

log = logging.getLogger("medorchestra.orchestrator")

AGENTS = {a.key: a for a in [
    BedManagementAgent(), AppointmentQueueAgent(), StaffSchedulingAgent(), DiagnosticCoordinationAgent(),
    PharmacyAgent(), PatientCareAgent(), EmergencySupportAgent(), ResourceOptimizationAgent(), BillingInsuranceAgent(),
    AmbulanceDispatchAgent(), NotificationAgent(),
]}

# intent -> [(step id "agent.action", params, depends_on)]
TEMPLATES: dict[str, list[tuple[str, dict, list[str]]]] = {
    "emergency": [
        ("care.resolve_patient", {"required": True, "allow_create": True}, []),
        ("emergency.triage", {}, ["care.resolve_patient"]),
        ("emergency.capacity_check", {}, []),
        ("bed.find_beds", {}, ["emergency.triage"]),
        ("staff.find_staff", {}, ["bed.find_beds"]),
        ("diagnostic.plan_tests", {}, ["emergency.triage"]),
        ("optimization.allocate", {}, ["bed.find_beds", "staff.find_staff"]),
        ("care.create_pathway", {"pathway": "emergency"}, ["optimization.allocate"]),
    ],
    "admission": [
        ("care.resolve_patient", {"required": True, "allow_create": True}, []),
        ("bed.find_beds", {}, ["care.resolve_patient"]),
        ("staff.find_staff", {}, ["bed.find_beds"]),
        ("diagnostic.plan_tests", {}, ["care.resolve_patient"]),
        ("optimization.allocate", {}, ["bed.find_beds", "staff.find_staff"]),
        ("care.create_pathway", {"pathway": "admission"}, ["optimization.allocate"]),
        ("billing.estimate", {}, ["optimization.allocate"]),
    ],
    "appointment": [
        ("care.resolve_patient", {"required": True, "allow_create": True}, []),
        ("appointment.find_slot", {}, ["care.resolve_patient"]),
    ],
    "diagnostics": [
        ("care.resolve_patient", {"required": True}, []),
        ("diagnostic.plan_tests", {}, ["care.resolve_patient"]),
    ],
    "pharmacy": [
        ("care.resolve_patient", {"required": False}, []),
        ("pharmacy.verify_prescription", {}, ["care.resolve_patient"]),
    ],
    "discharge": [
        ("care.resolve_patient", {"required": True}, []),
        ("care.discharge_readiness", {}, ["care.resolve_patient"]),
        ("pharmacy.discharge_meds", {}, ["care.discharge_readiness"]),
        ("appointment.follow_up", {}, ["care.discharge_readiness"]),
        ("bed.plan_release", {}, ["care.discharge_readiness"]),
        ("billing.clearance", {}, ["care.resolve_patient"]),
    ],
    "bed_query": [("bed.status_report", {}, [])],
    "optimization": [
        ("bed.find_waiting", {}, []),
        ("optimization.global_allocation", {}, ["bed.find_waiting"]),
        ("optimization.bottlenecks", {}, []),
    ],
    "analytics": [
        ("optimization.forecast", {}, []),
        ("optimization.bottlenecks", {}, []),
        ("appointment.queue_status", {}, []),
    ],
    "surgery": [
        ("care.resolve_patient", {"required": False}, []),
        ("optimization.schedule_surgery", {}, ["care.resolve_patient"]),
        ("billing.estimate", {}, ["optimization.schedule_surgery"]),
    ],
    "patient_status": [
        ("care.resolve_patient", {"required": True}, []),
        ("care.journey_status", {}, ["care.resolve_patient"]),
        ("diagnostic.status", {}, ["care.resolve_patient"]),
    ],
}

_lock = threading.Lock()  # serialises allocation transactions → no double-booking across concurrent requests


def _staffing_steps(text: str, entities: dict) -> list[tuple[str, dict, list[str]]]:
    t = text.lower()
    if any(k in t for k in ("roster", "schedule", "shift plan", "rota")):
        return [("staff.generate_roster", {}, [])]
    if entities.get("staff_count") or any(k in t for k in ("need", "more", "reassign", "shortage", "redeploy")):
        return [("staff.reassign", {}, []), ("staff.availability", {}, [])]
    return [("staff.availability", {}, [])]


_WHAT_IF = re.compile(r"what[- ]if|simulat|digital twin|scenario|mass casualty|surge", re.I)


def _analytics_steps(text: str) -> list[tuple[str, dict, list[str]]]:
    if _WHAT_IF.search(text):  # prescriptive "what-if" → digital-twin simulation
        return [("optimization.what_if", {}, []), ("optimization.bottlenecks", {}, [])]
    return TEMPLATES["analytics"]


def _billing_steps(text: str) -> list[tuple[str, dict, list[str]]]:
    step = "billing.estimate" if re.search(r"estimat|how much will|cost of|package|kharch", text, re.I) else "billing.bill_status"
    return [("care.resolve_patient", {"required": False}, []), (step, {}, ["care.resolve_patient"])]


def _ambulance_steps(text: str, entities: dict) -> list[tuple[str, dict, list[str]]]:
    if entities.get("locality") or entities.get("pickup") or re.search(r"send|dispatch|need|accident|collapsed|call|bhejo", text, re.I):
        return [("care.resolve_patient", {"required": False}, []), ("ambulance.dispatch", {}, ["care.resolve_patient"]),
                ("emergency.capacity_check", {}, [])]
    return [("ambulance.fleet_status", {}, [])]


def build_plan(intents: list[str], text: str, entities: dict) -> list[dict]:
    steps: dict[str, dict] = {}
    for intent in intents:
        dynamic = {"staffing": lambda: _staffing_steps(text, entities), "analytics": lambda: _analytics_steps(text),
                   "billing": lambda: _billing_steps(text), "ambulance": lambda: _ambulance_steps(text, entities)}
        template = dynamic[intent]() if intent in dynamic else TEMPLATES.get(intent, [])
        for sid, params, deps in template:
            if sid in steps:
                cur = steps[sid]
                for k, v in params.items():  # merge: most demanding requirement wins
                    cur["params"][k] = cur["params"].get(k) or v if isinstance(v, bool) else cur["params"].get(k, v)
                cur["depends_on"] = sorted(set(cur["depends_on"]) | set(deps))
            else:
                steps[sid] = {"id": sid, "agent": sid.split(".")[0], "action": sid.split(".")[1], "params": dict(params),
                              "depends_on": list(deps), "intent": intent}
    if entities.get("case_id") and "emergency.triage" in steps:
        steps["emergency.triage"]["params"]["case_id"] = entities["case_id"]
    # topological levels (deps outside the plan are ignored)
    level: dict[str, int] = {}

    def lvl(sid: str) -> int:
        if sid not in level:
            deps = [d for d in steps[sid]["depends_on"] if d in steps]
            level[sid] = 1 + max((lvl(d) for d in deps), default=0)
        return level[sid]

    for sid in steps:
        lvl(sid)
    ordered = sorted(steps.values(), key=lambda s: (level[s["id"]], list(steps).index(s["id"])))
    for s in ordered:
        s["level"] = level[s["id"]]
        s["depends_on"] = [d for d in s["depends_on"] if d in steps]
        s["agent_name"] = AGENTS[s["agent"]].name
    final_level = max((s["level"] for s in ordered), default=0) + 1
    ordered.append({"id": "notification.dispatch", "agent": "notification", "action": "dispatch", "params": {},
                    "depends_on": [], "intent": "system", "level": final_level, "agent_name": AGENTS["notification"].name})
    return ordered


def _jsonable(obj):
    return json.loads(json.dumps(obj, default=str))


class Orchestrator:
    def __init__(self) -> None:
        self.agents = AGENTS

    # ------------------------------------------------------------------ entry points
    def submit(self, db, text: str, user: User | None, source: str = "console", patient_id: int | None = None,
               forced_intents: list[str] | None = None, extra_entities: dict | None = None) -> AgentRequest:
        req = AgentRequest(text=text.strip(), source=source, submitted_by=user.id if user else None, status="received",
                           patient_id=patient_id,
                           entities={"_patient_id": patient_id, "_forced_intents": forced_intents or [], **(extra_entities or {})})
        db.add(req)
        log_audit(db, user.full_name if user else "system", "user" if user else "system", "submit_request",
                  "agent_request", None, {"text": text[:200], "source": source})
        db.commit()
        bus.publish("agent.request", {"id": req.id, "status": req.status, "text": req.text, "source": source})
        return req

    def run_in_background(self, request_id: int) -> None:
        threading.Thread(target=self.process, args=(request_id,), daemon=True, name=f"orchestrate-{request_id}").start()

    # ------------------------------------------------------------------ pipeline
    def process(self, request_id: int, delay: float | None = None) -> None:
        delay = settings.agent_step_delay if delay is None else delay
        with _lock:
            db = SessionLocal()
            try:
                self._process(db, request_id, delay)
            except Exception as exc:  # pragma: no cover - last-resort guard
                log.exception("orchestration failed")
                db.rollback()
                req = db.get(AgentRequest, request_id)
                if req:
                    req.status = "failed"
                    req.summary = f"Orchestration error: {exc}"
                    db.commit()
                    bus.publish("agent.request", {"id": req.id, "status": req.status})
            finally:
                db.close()

    def _process(self, db, request_id: int, delay: float) -> None:
        req = db.get(AgentRequest, request_id)
        user = db.get(User, req.submitted_by) if req.submitted_by else None
        t0 = time.perf_counter()
        trace: list[dict] = []

        def emit(kind: str, agent: str | None = None, title: str = "", detail: str | None = None, data=None) -> None:
            ev = {"seq": len(trace) + 1, "t_ms": round((time.perf_counter() - t0) * 1000), "kind": kind, "agent": agent,
                  "title": title, "detail": detail, "data": _jsonable(data) if data is not None else None,
                  "ts": datetime.now().isoformat()}
            trace.append(ev)
            bus.publish("agent.trace", {"request_id": req.id, "event": ev})

        def checkpoint(status: str | None = None) -> None:
            if status:
                req.status = status
            req.trace = list(trace)
            db.commit()
            bus.publish("agent.request", {"id": req.id, "status": req.status})

        meta = dict(req.entities or {})
        forced = meta.pop("_forced_intents", [])
        explicit_patient = meta.pop("_patient_id", None)

        # (ii) understanding ------------------------------------------------------
        emit("stage", "orchestrator", "Request received", req.text)
        checkpoint("understanding")
        patients = [(p.id, p.name, p.mrn) for p in db.scalars(select(Patient)).all()]
        meds = [(m.id, m.name, m.generic) for m in db.scalars(select(Medication)).all()]
        norm = normalize(req.text)
        nlp_text = resolve_pronoun(norm["text"], None) if norm["hinglish"] else req.text
        if norm["hinglish"]:
            emit("thought", "orchestrator", "Hinglish detected — normalised for the local NLP pipeline", nlp_text)
        local = understand_local(nlp_text, patients, meds)
        nlp = local
        if llm.enabled:
            emit("thought", "orchestrator", f"Querying {settings.llm_model} for intent & entity extraction")
            remote = llm.understand(req.text)
            if remote:
                ent = dict(local["entities"])
                for k, v in remote["entities"].items():
                    if k in ("vitals",) and ent.get("vitals"):
                        ent["vitals"] = {**v, **ent["vitals"]}
                    elif v and k not in ("patient_id", "mrn", "medications", "datetime"):
                        ent.setdefault(k, v)
                nlp = {"engine": remote["engine"] + " + DB grounding", "intents": remote["intents"],
                       "confidence": remote["confidence"], "entities": ent, "rationale": remote.get("rationale")}
            else:
                emit("thought", "orchestrator", f"LLM unavailable ({llm.last_error}) — using local NLP pipeline")
        entities = {**nlp["entities"], **meta}
        if explicit_patient:
            entities["patient_id"] = explicit_patient
        intents = [i for i in nlp["intents"] if i["confidence"] >= 0.25][:4] or nlp["intents"][:1]
        if forced:
            intents = [{"name": f, "confidence": 1.0} for f in forced] + [i for i in intents if i["name"] not in forced]
        if any(i["name"] == "ambulance" for i in intents):  # the ED pre-arrival flow runs when the crew leaves the scene
            intents = [i for i in intents if i["name"] not in ("emergency", "admission")]
        intent_names = [i["name"] for i in intents]
        req.intents, req.entities, req.nlp_engine, req.confidence = intents, _jsonable(entities), nlp["engine"], round(float(nlp["confidence"]), 3)
        emit("understanding", "orchestrator", "Intent classification: " + ", ".join(f"{i['name']} ({i['confidence']:.0%})" for i in intents),
             detail=nlp.get("rationale"), data={"engine": nlp["engine"], "intents": intents, "entities": entities})
        if req.confidence < 0.35 and not forced:
            emit("thought", "orchestrator", "Low classification confidence — proceeding with best match; staff can refine the request")

        # (iii)-(iv) planning -------------------------------------------------------
        checkpoint("planning")
        plan = build_plan(intent_names, req.text, entities)
        req.plan = plan
        levels = sorted({s["level"] for s in plan})
        emit("plan", "orchestrator", f"Execution plan: {len(plan)} steps across {len(levels)} dependency levels, "
                                      f"{len({s['agent'] for s in plan})} agents",
             data={"plan": [{k: s[k] for k in ('id', 'agent', 'action', 'level', 'depends_on')} for s in plan]})
        checkpoint("running")

        # (v) coordinated execution -------------------------------------------------
        ctx = AgentContext(db, req, intent_names, entities, user, emit)
        results: dict[str, AgentResult] = {}
        status_of: dict[str, str] = {}
        for lv in levels[:-1]:
            batch = [s for s in plan if s["level"] == lv]
            if len(batch) > 1:
                emit("stage", "orchestrator", f"Level {lv}: dispatching {', '.join(AGENTS[s['agent']].name for s in batch)}")
            for step in batch:
                failed_dep = next((d for d in step["depends_on"] if status_of.get(d) in ("failed",)), None)
                if failed_dep:
                    status_of[step["id"]] = "skipped"
                    results[step["id"]] = AgentResult(agent=step["agent"], status="skipped", summary=f"Skipped — prerequisite {failed_dep} failed")
                    emit("agent_skip", step["agent"], f"{AGENTS[step['agent']].name} skipped", f"prerequisite {failed_dep} failed")
                    continue
                emit("agent_start", step["agent"], f"{AGENTS[step['agent']].name} → {step['action'].replace('_', ' ')}")
                time.sleep(delay)
                res = AGENTS[step["agent"]].run(step["action"], ctx, step["params"])
                results[step["id"]] = res
                status_of[step["id"]] = res.status
                emit("agent_result", step["agent"], res.summary, data={"status": res.status, "step": step["id"],
                                                                        "recommendations": [r.__dict__ for r in res.recommendations[:4]]})
                req.results = _jsonable({k: v.to_dict() for k, v in results.items()})
                checkpoint()

        # (vi) conflict resolution ------------------------------------------------
        actions: list[ProposedAction] = [a for r in results.values() for a in r.actions]
        conflicts = self._resolve_conflicts(ctx, actions, results, emit)
        req.conflicts = _jsonable(conflicts)

        # (viii)-(ix) HITL gate and execution --------------------------------------
        approvals, executed = [], []
        follow_up = ctx.blackboard.get("follow_up")
        mode = get_setting(db, "autonomy_mode")
        if actions:
            emit("stage", "orchestrator", f"Applying human-in-the-loop policy: {mode} mode")
        for a in actions:
            requires = needs_approval(mode, a)
            if requires and not a.requires_approval:
                a.rationale = a.rationale + [f"Held for approval by the '{mode}' autonomy policy"]
            if a.action_type == "discharge_patient" and follow_up:
                a.payload["follow_up"] = follow_up | {"department_id": (results.get("appointment.follow_up").data or {}).get("department_id")}
            if a.payload.get("patient_id") is None and ctx.patient and a.action_type not in ("reorder_medication", "apply_roster", "reassign_staff", "apply_bed_allocation"):
                a.payload["patient_id"] = ctx.patient.id
            if requires:
                roles = list(APPROVER_ROLES.get(a.category, ("admin",)))
                ap = Approval(request_id=req.id, agent=AGENTS[a.agent].name if a.agent in AGENTS else a.agent,
                              action_type=a.action_type, title=a.title, description=a.description, rationale=a.rationale,
                              payload=_jsonable(a.payload), risk_level=a.risk, required_roles=roles)
                db.add(ap)
                db.flush()
                approvals.append({"id": ap.id, "title": a.title, "required_roles": roles, "risk": a.risk})
                emit("approval", a.agent, f"Awaiting human approval: {a.title}", f"risk {a.risk}; approvers: {', '.join(roles)}",
                     data={"approval_id": ap.id})
            else:
                try:
                    with db.begin_nested():
                        out = execute_action(db, a.action_type, a.payload, actor=AGENTS[a.agent].name, request_id=req.id)
                    executed.append({"action_type": a.action_type, "title": a.title, "result": out})
                    emit("action", a.agent, f"Executed automatically: {a.title}",
                         "low-risk / reversible" if not a.requires_approval else f"auto-approved by '{mode}' policy", data=out)
                except (ActionError, KeyError, ValueError) as exc:
                    emit("error", a.agent, f"Could not execute {a.title}", str(exc))
        db.flush()

        # (x) notifications, summary, logging ----------------------------------------
        emit("agent_start", "notification", "Notification Agent → dispatch")
        time.sleep(delay)
        nres = AGENTS["notification"].run("dispatch", ctx, {"approvals": approvals, "executed": executed})
        results["notification.dispatch"] = nres
        emit("agent_result", "notification", nres.summary, data={"status": nres.status})

        summary = None
        findings = {k: {"summary": v.summary, "status": v.status} for k, v in results.items()}
        findings["pending_approvals"] = [a["title"] for a in approvals]
        findings["executed"] = [e["title"] for e in executed]
        findings["conflicts"] = [c["description"] for c in conflicts]
        if llm.enabled:
            emit("thought", "orchestrator", "Generating coordination brief with Claude")
            summary = llm.summarize(req.text, findings)
        if not summary:
            summary = self._template_summary(results, approvals, executed, conflicts)
        req.summary = summary
        req.results = _jsonable({k: v.to_dict() for k, v in results.items()} | {"_executed": executed})
        req.duration_ms = round((time.perf_counter() - t0) * 1000)
        failed_all = results and all(r.status in ("failed", "skipped") for k, r in results.items() if k != "notification.dispatch")
        final = "failed" if failed_all else ("awaiting_approval" if approvals else "completed")
        if final != "awaiting_approval":
            req.completed_at = datetime.now()
        emit("done", "orchestrator", f"Orchestration {final.replace('_', ' ')} in {req.duration_ms} ms",
             data={"approvals": len(approvals), "executed": len(executed), "conflicts": len(conflicts)})
        log_audit(db, "Orchestrator", "agent", "orchestrate", "agent_request", req.id,
                  {"intents": intent_names, "approvals": len(approvals), "executed": len(executed), "status": final})
        checkpoint(final)
        if approvals:
            bus.publish("approval", {"request_id": req.id, "status": "pending", "count": len(approvals)})

    # ------------------------------------------------------------------ conflict resolution
    def _resolve_conflicts(self, ctx: AgentContext, actions: list[ProposedAction], results: dict, emit) -> list[dict]:
        conflicts: list[dict] = []
        db = ctx.db
        alloc = ctx.blackboard.get("allocation") or {}
        # 1. contention between this request and higher-priority waiting patients (from the optimiser)
        if alloc.get("contention"):
            c = alloc["contention"]
            conflicts.append({"type": "resource_contention", "agents": ["bed", "optimization"],
                              "description": f"Bed {c['bed']} is optimally assigned to {c['holder']} (higher priority)",
                              "resolution": f"Priority rule applied — allocated alternative {c['alternative']}"})
        # 2. staff overload: chosen doctor/nurse became saturated → fall back to next-best candidate
        for key, cand_key in (("doctor_id", "doctor_candidates"), ("nurse_id", "nurse_candidates")):
            for a in actions:
                sid = a.payload.get(key)
                if not sid:
                    continue
                s = db.get(Staff, sid)
                if s and s.current_load >= s.max_patients:
                    alt = next((c for c in ctx.blackboard.get(cand_key, []) if c["id"] != sid and c["load"] < c["max"]), None)
                    if alt:
                        a.payload[key] = alt["id"]
                        conflicts.append({"type": "staff_overload", "agents": ["staff", "optimization"],
                                          "description": f"{s.name} reached capacity ({s.current_load}/{s.max_patients})",
                                          "resolution": f"Reassigned to {alt['name']}"})
        # 3. triage demands resuscitation capacity but allocation is lower acuity
        tri = ctx.blackboard.get("triage")
        if tri and tri["triage_level"] == 1 and alloc and alloc.get("ward_type") not in ("emergency", "icu"):
            ctx.blackboard["capacity_alert"] = True
            conflicts.append({"type": "capacity", "agents": ["emergency", "bed"],
                              "description": "Resuscitation-level patient but no resus/ICU bed free",
                              "resolution": f"Temporary placement in {alloc.get('ward')} + capacity alert to administrators"})
        if not results.get("bed.find_beds", None) is None and results["bed.find_beds"].status == "partial":
            ctx.blackboard["capacity_alert"] = True
        # 4. safety refusals (pharmacy) → escalate to prescriber override
        for a in actions:
            if a.action_type == "create_prescription" and a.risk in ("critical", "high"):
                conflicts.append({"type": "safety", "agents": ["pharmacy", "care"],
                                  "description": f"Pharmacy Agent flagged {a.title}",
                                  "resolution": "Held for explicit doctor override (cannot auto-execute)"})
        # 5. duplicate effects on the same bed within this plan
        seen: dict[int, str] = {}
        for a in actions:
            b = a.payload.get("bed_id")
            if b and a.action_type in ("admit_patient", "assign_emergency"):
                if b in seen:
                    conflicts.append({"type": "duplicate", "agents": [a.agent], "description": f"Two actions target bed {b}",
                                      "resolution": "Kept the higher-acuity action"})
                seen[b] = a.action_type
        for c in conflicts:
            emit("conflict", "orchestrator", c["description"], c["resolution"], data=c)
        if not conflicts:
            emit("stage", "orchestrator", "Conflict check passed — no resource contention between agent proposals")
        return conflicts

    @staticmethod
    def _template_summary(results: dict, approvals: list, executed: list, conflicts: list) -> str:
        lines = []
        for sid, r in results.items():
            if r.status == "skipped" or sid == "notification.dispatch":
                continue
            lines.append(f"- {AGENTS[r.agent].name}: {r.summary}")
        if conflicts:
            lines.append(f"- Conflicts resolved: " + "; ".join(f"{c['description']} → {c['resolution']}" for c in conflicts))
        nxt = []
        if executed:
            nxt.append(f"{len(executed)} low-risk action(s) executed automatically")
        if approvals:
            roles = sorted({r for a in approvals for r in a["required_roles"]})
            nxt.append(f"{len(approvals)} action(s) awaiting approval by {'/'.join(roles)}")
        lines.append("Next steps: " + ("; ".join(nxt) if nxt else "no actions required") + ".")
        return "\n".join(lines)


orchestrator = Orchestrator()
