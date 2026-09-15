"""Resource Optimization Agent — joint allocation (CP-SAT), demand forecasting and bottleneck detection."""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..models import (Appointment, Bed, DailyStat, Department, DiagnosticOrder, EmergencyCase, Medication, Resource, Staff)
from ..services.clinical import TEST_CATALOG
from ..services.forecasting import holt_winters_forecast
from ..services.los_model import predict_los
from ..services.maintenance import maintenance_status
from ..services.ot_scheduler import PROCEDURES, TURNOVER, day_surgeries, find_slots, match_procedure, optimize_day
from ..services.optimizer import PatientNeed, optimize_bed_assignment
from .base import AgentContext, AgentResult, BaseAgent, ProposedAction, Recommendation
from .bed_agent import FALLBACK_TYPES, bed_options, held_bed_ids

EXPECTED_LOS_DAYS = {"icu": 4, "hdu": 3, "cardiac": 4, "general": 3, "isolation": 5, "pediatric": 2, "maternity": 2, "emergency": 0.5}


class ResourceOptimizationAgent(BaseAgent):
    key = "optimization"
    name = "Resource Optimization Agent"
    description = "Solves joint bed/staff allocation with constraint optimisation, forecasts demand and detects bottlenecks."
    capabilities = ["CP-SAT joint allocation", "global bed assignment", "Holt-Winters forecasting", "bottleneck detection", "explainable scoring"]
    icon = "cpu"
    color = "teal"

    def act_allocate(self, ctx: AgentContext) -> AgentResult:
        """Choose bed + doctor + nurse for this patient, optimising globally against other waiting patients."""
        db = ctx.db
        beds = ctx.blackboard.get("bed_candidates") or []
        doctors = ctx.blackboard.get("doctor_candidates") or []
        nurses = ctx.blackboard.get("nurse_candidates") or []
        need_info = ctx.blackboard.get("bed_need") or {}
        triage = ctx.blackboard.get("triage")
        p = ctx.patient
        if not p:
            return AgentResult(agent=self.key, status="failed", summary="No patient to allocate")
        if not beds:
            return AgentResult(agent=self.key, status="partial",
                               summary="Cannot allocate — no candidate beds. Escalating capacity alert to operations.",
                               data={"capacity_alert": True})

        # Global view: include ER patients already waiting for a bed so this allocation doesn't starve them.
        this = PatientNeed(key=f"p{p.id}", label=p.name, bed_types=need_info.get("types", ["general"]),
                           features=need_info.get("features", []), department_id=need_info.get("department_id"),
                           department_floor=need_info.get("department_floor"), priority=need_info.get("priority", 3),
                           preferred=need_info.get("preferred", []))
        needs = [this]
        for e in db.scalars(select(EmergencyCase).where(EmergencyCase.status == "awaiting_bed", EmergencyCase.patient_id != p.id)).all():
            types = {1: ["emergency", "icu"], 2: ["emergency", "hdu", "icu"]}.get(e.triage_level, ["emergency", "general"])
            needs.append(PatientNeed(key=f"er{e.id}", label=f"ER #{e.id} {e.patient.name}", bed_types=types, priority=e.triage_level))
        held = held_bed_ids(db, exclude_request=ctx.request.id)
        options = bed_options(db, sorted({t for n in needs for t in n.bed_types}), exclude=set(held), include_reserved_for=p.id)
        result = optimize_bed_assignment(needs, options)
        mine = next((a for a in result["assignments"] if a["need"] == this.key), None)
        contention = None
        if mine is None:  # the global optimum gives every candidate bed to higher-priority waiting patients
            taken = {a["bed_id"]: a["label"] for a in result["assignments"]}
            alt = next((b for b in beds if b["bed_id"] not in taken), beds[0])
            contention = {"bed": beds[0]["code"], "holder": taken.get(beds[0]["bed_id"], "a higher-priority patient"),
                          "alternative": alt["code"]}
            ctx.log(self.key, f"Contention: {contention['holder']} has priority for {beds[0]['code']} — using {alt['code']}")
            mine = {"bed_id": alt["bed_id"], "bed_code": alt["code"], "ward": alt["ward"],
                    "ward_type": alt["ward_type"], "cost": alt["cost"], "factors": alt["factors"]}
        ctx.log(self.key, f"{result['solver']}: {result['status']} — {len(result['assignments'])}/{len(needs)} placed "
                          f"over {result['variables']} feasible pairs in {result['wall_ms']} ms")

        bed = db.get(Bed, mine["bed_id"])
        ward_dept = bed.ward.department_id if bed else None
        doc = doctors[0] if doctors else None
        nurse = next((n for n in nurses if n["department_id"] == ward_dept), nurses[0] if nurses else None)
        ward_type = mine["ward_type"]
        acuity = "critical" if ward_type == "icu" else "high" if ward_type in ("hdu", "cardiac") else \
            ("high" if triage and triage["triage_level"] <= 2 else "moderate")
        emergency_adm = bool(triage) or ctx.request.source in ("emergency", "early-warning", "simulation")
        try:
            los_pred = predict_los(p.age, ward_type, acuity, len(p.conditions or []), emergency_adm)
            los = los_pred["days"]
        except Exception:  # model unavailable → fall back to ward averages
            los_pred, los = None, EXPECTED_LOS_DAYS.get(ward_type, 3) + (1 if p.age >= 65 else 0)
        composite = round(0.5 * max(0, 100 - mine["cost"] * 1.5) + 0.3 * (doc["score"] if doc else 0) + 0.2 * (nurse["score"] if nurse else 0), 1)
        plan = {"bed_id": mine["bed_id"], "bed_code": mine["bed_code"], "ward": mine["ward"], "ward_type": ward_type,
                "doctor_id": doc["id"] if doc else None, "doctor": doc["name"] if doc else None,
                "nurse_id": nurse["id"] if nurse else None, "nurse": nurse["name"] if nurse else None,
                "expected_los_days": los, "composite_score": composite, "contention": contention}
        ctx.post(self.key, "allocation", plan)

        rationale = [f"Bed {mine['bed_code']} ({mine['ward']}): " + ", ".join(f"{f['factor']} +{f['cost']}" for f in mine["factors"])]
        if doc:
            rationale.append(f"Doctor {doc['name']}: " + ", ".join(f"{f['factor']}" for f in doc["factors"]))
        if nurse:
            rationale.append(f"Nurse {nurse['name']}: " + ", ".join(f"{f['factor']}" for f in nurse["factors"]))
        equipment = ctx.blackboard.get("equipment")
        if equipment:
            plan["equipment"] = equipment["name"]
            rationale.append(f"Portable {equipment['name']} allocated (no ventilator-equipped bed free)")
        if los_pred:
            plan["predicted_los"] = los_pred
            rationale.append(f"Predicted length of stay {los_pred['days']} d (80% interval {los_pred['low']}–{los_pred['high']} d, Gradient Boosting model)")
        rationale.append(f"Solver {result['solver']} ({result['status']}), {len(needs) - 1} other waiting patient(s) considered")
        actions = [ProposedAction(action_type="reserve_bed", title=f"Hold {mine['bed_code']} for {p.name}",
                                  payload={"bed_id": mine["bed_id"], "patient_id": p.id}, risk="low", category="operations",
                                  requires_approval=False, rationale=["Reversible hold while clinician approves allocation"])]
        is_emergency = triage is not None and "admission" not in ctx.intents
        if is_emergency:
            actions.append(ProposedAction(
                action_type="assign_emergency", title=f"Assign {mine['bed_code']} + {plan['doctor'] or 'ED team'} to ER case #{triage.get('case_id')}",
                payload={"case_id": triage.get("case_id"), "bed_id": mine["bed_id"], "doctor_id": plan["doctor_id"],
                         "nurse_id": plan["nurse_id"], "patient_id": p.id},
                risk="critical" if triage["triage_level"] == 1 else "high", category="clinical", requires_approval=True,
                rationale=rationale, description="Confirms emergency bay and treating team. Bed is already held."))
        else:
            active = ctx.blackboard.get("active_admission")
            title = (f"Transfer {p.name} from {active['bed']} to {mine['ward']} ({mine['bed_code']})" if active and active.get("bed")
                     else f"Admit {p.name} to {mine['ward']} ({mine['bed_code']})")
            actions.append(ProposedAction(
                action_type="admit_patient", title=title,
                payload={"patient_id": p.id, "bed_id": mine["bed_id"], "doctor_id": plan["doctor_id"], "nurse_id": plan["nurse_id"],
                         "reason": ctx.request.text[:250], "acuity": acuity, "expected_los_days": los,
                         "case_id": triage.get("case_id") if triage else None,
                         "equipment_id": equipment["resource_id"] if equipment else None},
                risk="high" if ward_type in ("icu", "cardiac") else "medium", category="clinical", requires_approval=True,
                rationale=rationale, description=f"Creates the admission, assigns care team; expected LOS {los} day(s)."))
        return AgentResult(agent=self.key, actions=actions,
                           recommendations=[Recommendation(f"Allocation plan — composite score {composite}/100",
                                                           f"{mine['bed_code']} · {plan['doctor'] or '—'} · {plan['nurse'] or '—'}", composite,
                                                           [{"factor": f["factor"], "points": -f["cost"]} for f in mine["factors"]])],
                           data={"plan": plan, "solver": {k: v for k, v in result.items() if k not in ("assignments",)}},
                           summary=f"Optimal allocation: {mine['bed_code']} in {mine['ward']}, {plan['doctor'] or 'no doctor'}"
                                   f"{', ' + plan['nurse'] if plan['nurse'] else ''} (score {composite}/100, {result['solver']}).")

    def act_global_allocation(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        waiting = ctx.blackboard.get("waiting_patients") or []
        if not waiting:
            return AgentResult(agent=self.key, summary="No patients waiting for beds — allocation already optimal.")
        needs = []
        for w in waiting:
            if w["kind"] == "emergency":
                types = {1: ["emergency", "icu"], 2: ["emergency", "hdu", "icu"]}.get(w["triage_level"], ["emergency", "general"])
                needs.append(PatientNeed(key=f"er{w['id']}", label=w["name"], bed_types=types, priority=w["triage_level"]))
            else:
                needs.append(PatientNeed(key=f"adm{w['id']}", label=w["name"], bed_types=FALLBACK_TYPES["general"], priority=3))
        options = bed_options(db, None, exclude=set(held_bed_ids(db)))
        result = optimize_bed_assignment(needs, options)
        by_key = {f"er{w['id']}" if w["kind"] == "emergency" else f"adm{w['id']}": w for w in waiting}
        payload = [{"kind": by_key[a["need"]]["kind"], "id": by_key[a["need"]]["id"], "patient_id": by_key[a["need"]]["patient_id"],
                    "bed_id": a["bed_id"], "bed_code": a["bed_code"]} for a in result["assignments"]]
        actions = []
        if payload:
            actions.append(ProposedAction(
                action_type="apply_bed_allocation", title=f"Apply optimal placement for {len(payload)} waiting patient(s)",
                payload={"assignments": payload}, risk="medium", category="operations", requires_approval=True,
                rationale=[f"{a['label']} → {a['bed_code']} ({a['ward']}), cost {a['cost']}" for a in result["assignments"]]
                          + [f"{result['solver']} {result['status']} in {result['wall_ms']} ms"]))
        return AgentResult(agent=self.key, actions=actions, data={k: v for k, v in result.items()},
                           summary=f"{result['solver']} placed {len(result['assignments'])}/{len(needs)} waiting patient(s); "
                                   f"{len(result['unassigned'])} remain unplaced.")

    def act_forecast(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        horizon = int(ctx.entities.get("horizon_days") or 7)
        stats = db.scalars(select(DailyStat).order_by(DailyStat.day)).all()
        if not stats:
            return AgentResult(agent=self.key, status="failed", summary="No historical data available")
        out = {}
        for metric in ("admissions", "er_visits", "bed_occupancy", "icu_occupancy"):
            fc = holt_winters_forecast([getattr(s, metric) for s in stats], horizon=horizon)
            out[metric] = {"forecast": fc.forecast, "lower": fc.lower, "upper": fc.upper, "mape": fc.mape, "params": fc.params}
        start = stats[-1].day + timedelta(days=1)
        days = [(start + timedelta(days=i)).isoformat() for i in range(horizon)]
        risky = [days[i] for i, v in enumerate(out["icu_occupancy"]["forecast"]) if v >= 0.9]
        peak_i = max(range(horizon), key=lambda i: out["admissions"]["forecast"][i])
        recs = [Recommendation(f"Peak admissions expected {days[peak_i]}", f"~{out['admissions']['forecast'][peak_i]:.0f} admissions — plan extra discharges the day before")]
        if risky:
            recs.append(Recommendation(f"ICU occupancy forecast ≥90% on {len(risky)} day(s)", ", ".join(risky[:4]) + " — pre-emptively schedule step-downs"))
        recs.append(Recommendation("Model accuracy", f"Holt-Winters hold-out MAPE: admissions {out['admissions']['mape']}%, ER {out['er_visits']['mape']}%"))
        total_adm = sum(out["admissions"]["forecast"])
        return AgentResult(agent=self.key, recommendations=recs, data={"days": days, "metrics": out},
                           summary=f"{horizon}-day forecast: ~{total_adm:.0f} admissions, ~{sum(out['er_visits']['forecast']):.0f} ER visits; "
                                   f"mean bed occupancy {sum(out['bed_occupancy']['forecast']) / horizon:.0%}.")

    def act_bottlenecks(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        now = datetime.now()
        items = []
        from ..services.triage import TRIAGE_LEVELS
        er = db.scalars(select(EmergencyCase).where(EmergencyCase.status.in_(["triage", "awaiting_bed"]))).all()
        er_breach = [c for c in er if (now - c.created_at).total_seconds() / 60 > TRIAGE_LEVELS[c.triage_level]["target_minutes"]]
        if er_breach:
            items.append({"area": "Emergency", "severity": "high", "issue": f"{len(er_breach)} ED patient(s) past triage target time",
                          "suggestion": "Prioritise by triage level; open overflow bay"})
        orders = db.scalars(select(DiagnosticOrder).where(DiagnosticOrder.status.not_in(["completed", "cancelled"]))).all()
        tat = [o for o in orders if (now - o.created_at).total_seconds() / 60 > TEST_CATALOG.get(o.test_code, {}).get("tat", 120)]
        if tat:
            by_mod: dict[str, int] = {}
            for o in tat:
                by_mod[o.category] = by_mod.get(o.category, 0) + 1
            items.append({"area": "Diagnostics", "severity": "medium", "issue": f"{len(tat)} investigation(s) beyond turnaround ("
                          + ", ".join(f"{k}: {v}" for k, v in by_mod.items()) + ")", "suggestion": "Add technician cover to the busiest modality"})
        cleaning = db.scalars(select(Bed).where(Bed.status == "cleaning")).all()
        stale = [b for b in cleaning if b.updated_at and (now - b.updated_at) > timedelta(hours=1)]
        if stale:
            items.append({"area": "Housekeeping", "severity": "medium", "issue": f"{len(stale)} bed(s) in cleaning > 1h",
                          "suggestion": "Escalate to housekeeping supervisor"})
        over = db.scalars(select(Staff).where(Staff.on_duty.is_(True), Staff.current_load >= Staff.max_patients)).all()
        if over:
            items.append({"area": "Staffing", "severity": "medium", "issue": f"{len(over)} staff at/over capacity",
                          "suggestion": "Rebalance patient assignments or call in on-call staff"})
        low = db.scalars(select(Medication).where(Medication.stock <= Medication.reorder_level)).all()
        if low:
            items.append({"area": "Pharmacy", "severity": "low", "issue": f"{len(low)} medicine(s) at reorder level", "suggestion": "Approve purchase order"})
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        waiting = db.scalars(select(Appointment).where(Appointment.status == "checked_in", Appointment.scheduled_at >= today)).all()
        long_wait = [a for a in waiting if a.checked_in_at and (now - a.checked_in_at) > timedelta(minutes=45)]
        if long_wait:
            items.append({"area": "OPD", "severity": "medium", "issue": f"{len(long_wait)} OPD patient(s) waiting > 45 min",
                          "suggestion": "Re-route to less busy doctors in the same department"})
        risky = [r for r in db.scalars(select(Resource).where(Resource.status != "maintenance")).all()
                 if maintenance_status(r.resource_type, r.last_maintenance, r.usage_hours)["maintenance_band"] == "high"]
        if risky:
            items.append({"area": "Equipment", "severity": "low",
                          "issue": f"{len(risky)} device(s) at high predicted maintenance risk ({', '.join(r.name for r in risky[:3])})",
                          "suggestion": "Schedule preventive maintenance during low-demand hours"})
        order = {"high": 0, "medium": 1, "low": 2}
        items.sort(key=lambda i: order[i["severity"]])
        recs = [Recommendation(f"[{i['severity'].upper()}] {i['area']}: {i['issue']}", i["suggestion"]) for i in items]
        return AgentResult(agent=self.key, recommendations=recs, data={"bottlenecks": items},
                           summary=f"Detected {len(items)} operational bottleneck(s)" + (f"; most severe: {items[0]['area']}." if items else "."))

    # ------------------------------------------------------------------ operating theatres
    def act_schedule_surgery(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        text = ctx.request.text.lower()
        key = ctx.entities.get("procedure") or match_procedure(ctx.request.text)
        key = key if key in PROCEDURES else None
        day = datetime.fromisoformat(ctx.entities["datetime"]).date() if ctx.entities.get("datetime") else date.today()
        if not key and re.search(r"optimi[sz]e|reschedul|rebalanc|overtime|utili[sz]ation", text):
            return self._optimize_ot(ctx, day)
        if not key:
            slots = find_slots(db, day, 60)
            recs = [Recommendation(f"{s['ot']} from {s['start'][11:16]}", f"wait {s['wait_minutes']} min", s["cost"], s["factors"]) for s in slots]
            return AgentResult(agent=self.key, recommendations=recs, data={"slots": slots},
                               summary=(f"{len(slots)} theatre(s) can take a 60-min case on {day:%d %b}; earliest {slots[0]['ot']} at {slots[0]['start'][11:16]}."
                                        if slots else f"No free theatre time on {day:%d %b}."))
        p = ctx.patient
        if not p:
            return AgentResult(agent=self.key, status="failed", summary="Surgery booking needs an identified patient (name or MRN).")
        meta = PROCEDURES[key]
        urgency = ctx.entities.get("urgency")
        priority = ("emergency" if re.search(r"\bemergency\b|immediately|\bnow\b", text) or urgency == "stat"
                    else "urgent" if urgency == "urgent" or "urgent" in text else "elective")
        dept = db.scalar(select(Department).where(Department.name == meta["specialty"]))
        surgeons = db.scalars(select(Staff).where(Staff.role == "doctor", Staff.department_id == dept.id)).all() if dept else []
        best = None
        for d_offset in range(0, 3 if priority == "elective" else 1):
            d = day + timedelta(days=d_offset)
            cases: dict[int | None, int] = {}
            for s in day_surgeries(db, d):
                cases[s.surgeon_id] = cases.get(s.surgeon_id, 0) + 1
            for sg in surgeons or [None]:
                opts = find_slots(db, d, meta["duration"], sg.id if sg else None, priority)
                if not opts:
                    continue
                score = opts[0]["cost"] + 2 * cases.get(sg.id if sg else None, 0) - (1 if sg and sg.seniority in ("consultant", "senior") else 0)
                if best is None or score < best[0]:
                    best = (score, sg, opts, cases.get(sg.id if sg else None, 0))
            if best:
                break
        if not best:
            return AgentResult(agent=self.key, status="partial", summary=f"No feasible theatre slot for {meta['name']} in the next days — escalate to theatre manager.")
        _, sg, opts, n_cases = best
        slot = opts[0]
        start = datetime.fromisoformat(slot["start"])
        ctx.post(self.key, "surgery_plan", {"procedure": meta["name"], "ot": slot["ot"], "start": slot["start"], "surgeon": sg.name if sg else None})
        if sg:
            ctx.send(self.key, "staff", "REQUEST", f"Confirm {sg.name} for {meta['name']} at {start:%d %b %H:%M}")
        ctx.send(self.key, "care", "INFORM", "Add surgical pathway incl. WHO safety checklist")
        recs = [Recommendation(f"{o['ot']} — {o['start'][11:16]}", f"wait {o['wait_minutes']} min", o["cost"], o["factors"]) for o in opts[:3]]
        if priority == "emergency" and slot["wait_minutes"] > 60:
            recs.append(Recommendation("Consider postponing the next elective case", "Emergency case waits > 60 min for a free theatre"))
        action = ProposedAction(
            action_type="book_surgery", title=f"Book {meta['name']} for {p.name} — {slot['ot']} at {start:%d %b %H:%M}",
            payload={"patient_id": p.id, "surgeon_id": sg.id if sg else None, "ot_id": slot["ot_id"], "procedure": meta["name"],
                     "specialty": meta["specialty"], "priority": priority, "scheduled_start": slot["start"],
                     "duration_minutes": meta["duration"], "anaesthesia": meta["anaesthesia"]},
            risk="high" if priority == "emergency" else "medium", category="theatre", requires_approval=True,
            rationale=[f"{slot['ot']}: " + ", ".join(f"{f['factor']} +{f['cost']}" for f in slot["factors"]),
                       f"Surgeon {sg.name if sg else '—'} ({n_cases} other case(s) that day)",
                       f"{meta['duration']} min + {TURNOVER} min turnover · anaesthesia: {meta['anaesthesia']} · priority: {priority}",
                       "No theatre or surgeon overlap; WHO surgical safety checklist added to the care pathway"],
            description="Creates the theatre booking and the surgical care pathway.")
        return AgentResult(agent=self.key, actions=[action], recommendations=recs,
                           data={"procedure": meta["name"], "priority": priority, "surgeon": sg.name if sg else None, "options": opts},
                           summary=f"{meta['name']} ({priority}, {meta['duration']} min): best slot {slot['ot']} at {start:%d %b %H:%M}"
                                   + (f" with {sg.name}" if sg else "") + f"; {len(opts)} theatre option(s) evaluated.")

    def _optimize_ot(self, ctx: AgentContext, day: date) -> AgentResult:
        res = optimize_day(ctx.db, day)
        if not res.get("assignments"):
            return AgentResult(agent=self.key, summary=f"No reschedulable theatre cases on {day:%d %b} ({res['status']}).", data=res)
        b, a = res["before"], res["after"]
        ctx.log(self.key, f"{res['solver']}: {res['status']} — {res['movable']} cases, {res['moved']} change(s), {res['wall_ms']} ms")
        action = ProposedAction(
            action_type="apply_ot_schedule", title=f"Apply optimised theatre schedule for {day:%d %b} ({res['moved']} change(s))",
            payload={"assignments": [{k: x[k] for k in ("surgery_id", "ot_id", "start")} for x in res["assignments"]]},
            risk="medium", category="theatre", requires_approval=True,
            rationale=[f"Overlaps {b['conflicts']} → {a['conflicts']}", f"Overtime past 20:00: {b['overtime_minutes']} → {a['overtime_minutes']} min",
                       f"Last case ends {b['makespan']} → {a['makespan']}", "Hard constraints: no theatre/surgeon overlap, 30-min turnover",
                       f"{res['solver']} ({res['status']}, {res['wall_ms']} ms)"])
        recs = [Recommendation(f"{x['procedure']} → {x['ot']} {x['start'][11:16]}", f"was {x['old_ot']} {x['old_start'][11:16]}")
                for x in res["assignments"] if x["moved"]][:6]
        return AgentResult(agent=self.key, actions=[action], recommendations=recs, data={k: v for k, v in res.items() if k != "assignments"},
                           summary=f"Re-optimised {res['movable']} theatre case(s) for {day:%d %b}: overtime {b['overtime_minutes']}→{a['overtime_minutes']} min, "
                                   f"last case {b['makespan']}→{a['makespan']}, {res['moved']} change(s).")
