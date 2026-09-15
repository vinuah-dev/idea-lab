"""Staff Scheduling Agent — availability, workload-aware assignment and optimised rostering."""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

from sqlalchemy import select

from ..models import Department, Staff, Ward
from ..services.clinical import match_protocols
from ..services.optimizer import optimize_roster
from .base import AgentContext, AgentResult, BaseAgent, ProposedAction, Recommendation


def rank_doctors(doctors: list[Staff], dept_id: int | None, specialization: str | None, critical: bool) -> list[dict]:
    ranked = []
    for d in doctors:
        factors = []
        if dept_id and d.department_id == dept_id:
            factors.append({"factor": "same department", "points": 40})
        if specialization and specialization.lower() in (d.specialization or "").lower():
            factors.append({"factor": f"specialisation: {d.specialization}", "points": 10})
        factors.append({"factor": "on duty" if d.on_duty else "off duty / on call", "points": 20 if d.on_duty else 0})
        spare = 1 - d.current_load / max(d.max_patients, 1)
        factors.append({"factor": f"workload {d.current_load}/{d.max_patients}", "points": round(30 * spare, 1)})
        if critical and d.seniority in ("consultant", "senior"):
            factors.append({"factor": f"{d.seniority} for critical case", "points": 10})
        ranked.append({"id": d.id, "name": d.name, "specialization": d.specialization, "department_id": d.department_id,
                       "load": d.current_load, "max": d.max_patients, "on_duty": d.on_duty,
                       "score": round(sum(f["points"] for f in factors), 1), "factors": factors})
    ranked.sort(key=lambda r: -r["score"])
    return ranked


def rank_nurses(nurses: list[Staff], dept_id: int | None, ward_type: str | None) -> list[dict]:
    ranked = []
    for n in nurses:
        factors = []
        if dept_id and n.department_id == dept_id:
            factors.append({"factor": "assigned to receiving ward's department", "points": 30})
        spare = 1 - n.current_load / max(n.max_patients, 1)
        factors.append({"factor": f"workload {n.current_load}/{n.max_patients}", "points": round(40 * spare, 1)})
        skills = [s.lower() for s in (n.skills or [])]
        if ward_type in ("icu", "hdu", "cardiac") and "critical care" in skills:
            factors.append({"factor": "critical-care certified", "points": 20})
        if ward_type == "pediatric" and "pediatric" in skills:
            factors.append({"factor": "paediatric skills", "points": 20})
        if ward_type == "emergency" and "triage" in skills:
            factors.append({"factor": "emergency triage skills", "points": 15})
        ranked.append({"id": n.id, "name": n.name, "department_id": n.department_id, "load": n.current_load,
                       "max": n.max_patients, "skills": n.skills, "score": round(sum(f["points"] for f in factors), 1),
                       "factors": factors})
    ranked.sort(key=lambda r: -r["score"])
    return ranked


class StaffSchedulingAgent(BaseAgent):
    key = "staff"
    name = "Staff Scheduling Agent"
    description = "Matches doctors and nurses to patients by specialty, skills and workload; builds optimised rosters."
    capabilities = ["availability lookup", "workload balancing", "skill matching", "CP-SAT roster optimisation", "reassignment"]
    icon = "users"
    color = "violet"

    def _target_department(self, ctx: AgentContext) -> Department | None:
        name = ctx.entities.get("department")
        triage = ctx.blackboard.get("triage")
        if triage and "admission" not in ctx.intents:
            name = "Emergency"  # ED team leads; the specialty is called as a consult
        if not name:
            bt = ctx.entities.get("bed_type") or ((ctx.blackboard.get("bed_need") or {}).get("types") or [None])[0]
            name = {"icu": "Critical Care", "hdu": "Critical Care", "cardiac": "Cardiology", "pediatric": "Pediatrics",
                    "maternity": "Obstetrics & Gynecology", "emergency": "Emergency"}.get(bt)
        if not name:
            protos = match_protocols(ctx.request.text)
            name = protos[0]["department"] if protos else None
        return ctx.db.scalar(select(Department).where(Department.name == name)) if name else None

    def act_find_staff(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        dept = self._target_department(ctx)
        triage = ctx.blackboard.get("triage")
        need = ctx.blackboard.get("bed_need") or {}
        critical = bool(triage and triage["triage_level"] <= 2) or (need.get("types", [""])[0] in ("icu", "cardiac"))
        doctors = db.scalars(select(Staff).where(Staff.role == "doctor", Staff.current_load < Staff.max_patients)).all()
        on_duty = [d for d in doctors if d.on_duty] or doctors
        ranked_docs = rank_doctors(on_duty, dept.id if dept else None, dept.name if dept else None, critical)
        # nurses: prefer the department of the best-ranked bed's ward
        cands = ctx.blackboard.get("bed_candidates") or []
        ward_dept = ward_type = None
        if cands:
            ward = db.scalar(select(Ward).where(Ward.name == cands[0]["ward"]))
            ward_dept, ward_type = (ward.department_id, ward.ward_type) if ward else (None, None)
        nurses = db.scalars(select(Staff).where(Staff.role == "nurse", Staff.on_duty.is_(True),
                                                Staff.current_load < Staff.max_patients)).all()
        ranked_nurses = rank_nurses(nurses, ward_dept or (dept.id if dept else None), ward_type)
        ctx.post(self.key, "doctor_candidates", ranked_docs[:5])
        ctx.post(self.key, "nurse_candidates", ranked_nurses[:5])
        if not ranked_docs:
            return AgentResult(agent=self.key, status="partial", summary="No doctor with spare capacity is on duty — escalate to on-call roster.")
        d0 = ranked_docs[0]
        n0 = ranked_nurses[0] if ranked_nurses else None
        ctx.send(self.key, "optimization", "PROPOSE",
                 f"Doctor {d0['name']} (score {d0['score']})" + (f", nurse {n0['name']} (score {n0['score']})" if n0 else ""))
        recs = [Recommendation(f"Dr. {d['name'].replace('Dr. ', '')} — {d['specialization']}", f"load {d['load']}/{d['max']}", d["score"], d["factors"]) for d in ranked_docs[:2]]
        if n0:
            recs.append(Recommendation(f"Nurse {n0['name']}", f"load {n0['load']}/{n0['max']}", n0["score"], n0["factors"]))
        specialty = ctx.entities.get("department")
        specialist = None
        if triage and specialty and dept and specialty != dept.name:
            sdept = db.scalar(select(Department).where(Department.name == specialty))
            pool = [d for d in on_duty if sdept and d.department_id == sdept.id]
            if pool:
                sp = rank_doctors(pool, sdept.id, specialty, True)[0]
                specialist = {"id": sp["id"], "name": sp["name"], "department": specialty}
                recs.append(Recommendation(f"Specialist consult: {sp['name']} ({specialty})", "Auto-paged as on-call consultant", sp["score"], sp["factors"]))
                ctx.send(self.key, "notification", "REQUEST", f"Page {sp['name']} for {specialty} consult")
        return AgentResult(agent=self.key, recommendations=recs,
                           data={"department": dept.name if dept else None, "doctors": ranked_docs[:5], "nurses": ranked_nurses[:5],
                                 "critical": critical, "specialist": specialist},
                           summary=f"{len(on_duty)} doctor(s) and {len(nurses)} nurse(s) have capacity"
                                   + (f" (target department: {dept.name})" if dept else "")
                                   + f". Best doctor: {d0['name']}" + (f"; best nurse: {n0['name']}." if n0 else "."))

    def act_availability(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        dept = self._target_department(ctx)
        role = ctx.entities.get("staff_role")
        q = select(Staff).where(Staff.on_duty.is_(True))
        if role:
            q = q.where(Staff.role == role)
        if dept:
            q = q.where(Staff.department_id == dept.id)
        staff = db.scalars(q).all()
        overloaded = [s for s in staff if s.current_load >= s.max_patients]
        free = sorted([s for s in staff if s.current_load < s.max_patients], key=lambda s: s.current_load / max(s.max_patients, 1))
        recs = [Recommendation(f"{s.name} ({s.role}, {s.specialization})", f"load {s.current_load}/{s.max_patients}") for s in free[:5]]
        if overloaded:
            recs.append(Recommendation(f"{len(overloaded)} staff at or above capacity",
                                       ", ".join(s.name for s in overloaded[:5]) + " — consider redistributing patients"))
        scope = f"{role or 'staff'}s" + (f" in {dept.name}" if dept else "")
        return AgentResult(agent=self.key, recommendations=recs,
                           summary=f"{len(staff)} {scope} on duty; {len(free)} with spare capacity, {len(overloaded)} at capacity.",
                           data={"on_duty": len(staff), "available": [{"id": s.id, "name": s.name, "role": s.role,
                                                                       "load": s.current_load, "max": s.max_patients} for s in free[:10]],
                                 "overloaded": [s.name for s in overloaded]})

    def act_reassign(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        dept = self._target_department(ctx) or db.scalar(select(Department).where(Department.name == "Critical Care"))
        role = ctx.entities.get("staff_role") or "nurse"
        count = int(ctx.entities.get("staff_count") or 1)
        pool = db.scalars(select(Staff).where(Staff.role == role, Staff.on_duty.is_(True), Staff.department_id != dept.id)).all()
        by_dept: dict[int, list[Staff]] = {}
        for s in pool:
            by_dept.setdefault(s.department_id, []).append(s)
        # take from departments with the most spare capacity, never leaving a department with < 2
        candidates = []
        for dept_id, members in by_dept.items():
            spare = sorted(members, key=lambda s: s.current_load / max(s.max_patients, 1))
            candidates += spare[: max(0, len(members) - 2)]
        candidates.sort(key=lambda s: s.current_load / max(s.max_patients, 1))
        chosen = candidates[:count]
        if not chosen:
            return AgentResult(agent=self.key, status="partial", summary=f"No {role}s can be released without breaching minimum cover elsewhere.")
        action = ProposedAction(
            action_type="reassign_staff", title=f"Reassign {len(chosen)} {role}(s) to {dept.name}",
            payload={"staff_ids": [s.id for s in chosen], "department_id": dept.id},
            risk="medium", category="staffing", requires_approval=True,
            rationale=[f"{s.name}: load {s.current_load}/{s.max_patients} in {s.department.name if s.department else '-'}" for s in chosen]
                      + ["Each source department keeps at least 2 on-duty staff"],
            description="Temporary redeployment for the current shift.",
        )
        return AgentResult(agent=self.key, actions=[action],
                           summary=f"Proposed redeploying {', '.join(s.name for s in chosen)} to {dept.name} (lowest workload, cover preserved).",
                           data={"chosen": [s.name for s in chosen]})

    def act_generate_roster(self, ctx: AgentContext, days: int = 7) -> AgentResult:
        db = ctx.db
        staff = db.scalars(select(Staff).where(Staff.role.in_(["doctor", "nurse"]))).all()
        start = date.today() + timedelta(days=1)
        day_list = [start + timedelta(days=i) for i in range(days)]
        groups: dict[tuple, int] = {}
        for s in staff:
            groups[(s.department_id, s.role)] = groups.get((s.department_id, s.role), 0) + 1
        coverage = {}
        for (dept_id, role), n in groups.items():
            coverage[(dept_id, role, "morning")] = max(1, math.floor(n * 0.30))
            coverage[(dept_id, role, "evening")] = max(1, math.floor(n * 0.22)) if n >= 2 else 0
            coverage[(dept_id, role, "night")] = max(1, math.floor(n * 0.16)) if n >= 3 else 0
        coverage = {k: v for k, v in coverage.items() if v > 0}
        rng = random.Random(42)
        unavailable = {(s.id, rng.randrange(days)) for s in staff if rng.random() < 0.25}  # leave requests
        result = optimize_roster([{"id": s.id, "role": s.role, "department_id": s.department_id} for s in staff],
                                 day_list, coverage, unavailable, max_shifts=5, time_limit=8)
        ctx.log(self.key, f"{result['solver']} solved roster: {result['status']} in {result['wall_ms']} ms")
        action = ProposedAction(
            action_type="apply_roster", title=f"Publish optimised roster {day_list[0]:%d %b} – {day_list[-1]:%d %b}",
            payload={"start": day_list[0].isoformat(), "end": day_list[-1].isoformat(), "assignments": result["assignments"]},
            risk="medium", category="staffing", requires_approval=True,
            rationale=[f"Coverage {result['coverage_pct']}% of {result['required_slots']} required shift-slots",
                       f"Night shifts per person between {result.get('min_nights', 0)} and {result.get('max_nights', 0)} (fairness)",
                       "Max 5 shifts/week, no night→morning turnarounds, leave requests honoured",
                       f"Solver: {result['solver']} ({result['status']}, {result['wall_ms']} ms)"],
        )
        return AgentResult(agent=self.key, actions=[action],
                           summary=f"Generated a {days}-day roster for {len(staff)} staff: {len(result['assignments'])} shifts, "
                                   f"{result['coverage_pct']}% coverage, solver {result['status']}.",
                           data={k: v for k, v in result.items() if k != "assignments"} | {"shifts": len(result["assignments"])})
