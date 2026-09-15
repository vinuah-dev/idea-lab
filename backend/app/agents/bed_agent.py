"""Bed Management Agent — real-time bed tracking, candidate ranking and bed-turnover planning."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from sqlalchemy import select

from ..models import Admission, Approval, Bed, EmergencyCase, Resource, Staff, Ward
from ..services.clinical import match_protocols
from ..services.optimizer import BedOption, PatientNeed, rank_beds
from .base import AgentContext, AgentResult, BaseAgent, Recommendation

FALLBACK_TYPES = {
    "icu": ["icu", "hdu"], "hdu": ["hdu", "icu", "general"], "cardiac": ["cardiac", "icu", "hdu"],
    "general": ["general", "hdu"], "isolation": ["isolation", "icu"], "pediatric": ["pediatric", "general"],
    "maternity": ["maternity", "general"], "emergency": ["emergency", "hdu"],
}


def held_bed_ids(db, exclude_request: int | None = None) -> dict[int, int]:
    """Beds held by pending approvals of other requests: {bed_id: request_id}."""
    held = {}
    for a in db.scalars(select(Approval).where(Approval.status == "pending")).all():
        bed_id = (a.payload or {}).get("bed_id")
        if bed_id and a.request_id != exclude_request:
            held[int(bed_id)] = a.request_id
    return held


def bed_options(db, types: list[str] | None = None, exclude: set[int] | None = None,
                include_reserved_for: int | None = None) -> list[BedOption]:
    wards = db.scalars(select(Ward)).all()
    nurses_on_duty: dict[int | None, int] = {}
    for s in db.scalars(select(Staff).where(Staff.role == "nurse", Staff.on_duty.is_(True))).all():
        nurses_on_duty[s.department_id] = nurses_on_duty.get(s.department_id, 0) + 1
    opts = []
    for w in wards:
        if types and w.ward_type not in types:
            continue
        occ = sum(1 for b in w.beds if b.status == "occupied") / max(len(w.beds), 1)
        required = max(1, math.ceil(sum(1 for b in w.beds if b.status == "occupied") * w.nurse_ratio))
        coverage = min(1.0, nurses_on_duty.get(w.department_id, 0) / required)
        for b in w.beds:
            free = b.status == "available" or (include_reserved_for and b.status == "reserved" and b.patient_id == include_reserved_for)
            if not free or (exclude and b.id in exclude):
                continue
            opts.append(BedOption(bed_id=b.id, code=b.code, ward_name=w.name, ward_type=w.ward_type,
                                  features=b.features or [], floor=w.floor, department_id=w.department_id,
                                  ward_occupancy=occ, nurse_coverage=coverage))
    return opts


class BedManagementAgent(BaseAgent):
    key = "bed"
    name = "Bed Management Agent"
    description = "Tracks every bed in real time, ranks suitable beds for each patient and plans bed turnover."
    capabilities = ["real-time bed tracking", "bed matching", "reservation", "turnover planning", "discharge-driven capacity prediction"]
    icon = "bed-double"
    color = "sky"

    def _derive_need(self, ctx: AgentContext) -> tuple[PatientNeed, list[str]]:
        ent = ctx.entities
        reasons = []
        triage = ctx.blackboard.get("triage")
        protocols = match_protocols(ctx.request.text + " " + " ".join(ctx.patient.conditions if ctx.patient else []))
        if ent.get("bed_type"):
            types = FALLBACK_TYPES.get(ent["bed_type"], [ent["bed_type"]])
            reasons.append(f"Requested bed type: {ent['bed_type'].upper()}")
        elif triage and "admission" not in ctx.intents:
            lvl = triage["triage_level"]
            types = {1: ["emergency", "icu"], 2: ["emergency", "hdu", "icu"], 3: ["emergency", "general"]}.get(lvl, ["emergency", "general"])
            reasons.append(f"Triage level {lvl} ({triage['triage_label']}) → {types[0]} area")
        elif protocols:
            types = protocols[0]["bed"]
            reasons.append(f"{protocols[0]['name']} suggests {types[0]} bed")
        elif ctx.patient and ctx.patient.age < 14:
            types = ["pediatric", "general"]
            reasons.append("Paediatric patient")
        else:
            types = ["general", "hdu"]
            reasons.append("Default general ward admission")
        if ctx.patient and ctx.patient.age < 14 and "pediatric" not in types and types[0] == "general":
            types = ["pediatric"] + types
        features = list(ent.get("bed_features", []))
        if "ventilator" in features:
            reasons.append("Ventilator capability required")
        dept_name = ent.get("department") or (protocols[0]["department"] if protocols else None)
        dept_id = dept_floor = None
        if dept_name:
            from ..models import Department
            d = ctx.db.scalar(select(Department).where(Department.name == dept_name))
            if d:
                dept_id, dept_floor = d.id, d.floor
        priority = triage["triage_level"] if triage else (2 if types[0] in ("icu", "cardiac") else 3)
        preferred = []
        if triage and triage["triage_level"] == 1:
            preferred = ["ventilator"]
            reasons.append("Resuscitation-capable bay preferred (ventilator + monitor)")
        need = PatientNeed(key=str(ctx.patient.id if ctx.patient else "request"),
                           label=ctx.patient.name if ctx.patient else "patient", bed_types=types,
                           features=features, department_id=dept_id, department_floor=dept_floor, priority=priority,
                           preferred=preferred)
        return need, reasons

    def act_find_beds(self, ctx: AgentContext) -> AgentResult:
        need, reasons = self._derive_need(ctx)
        held = held_bed_ids(ctx.db, exclude_request=ctx.request.id)
        options = bed_options(ctx.db, need.bed_types, exclude=set(held),
                              include_reserved_for=ctx.patient.id if ctx.patient else None)
        ranked = rank_beds(need, options, top=5)
        expanded = False
        if not ranked and "ventilator" in need.features:
            # no ventilator-equipped bed free → pair a monitored bed with a portable ventilator (equipment coordination)
            vent = ctx.db.scalar(select(Resource).where(Resource.resource_type == "ventilator", Resource.status == "available"))
            if vent:
                need.features = [f for f in need.features if f != "ventilator"]
                ranked = rank_beds(need, options, top=5)
                if ranked:
                    ctx.post(self.key, "equipment", {"resource_id": vent.id, "name": vent.name, "type": "ventilator"})
                    reasons.append(f"No ventilator-equipped bed free — portable {vent.name} will be attached")
                    ctx.send(self.key, "optimization", "PROPOSE", f"Pair {ranked[0]['code']} with portable {vent.name}")
                else:
                    need.features.append("ventilator")
        if not ranked:
            wider = sorted({t for t in need.bed_types for t in FALLBACK_TYPES.get(t, [t])} | {"hdu", "general"})
            need.bed_types = need.bed_types + [t for t in wider if t not in need.bed_types]
            ranked = rank_beds(need, bed_options(ctx.db, need.bed_types, exclude=set(held)), top=5)
            expanded = True
            ctx.send(self.key, "optimization", "INFORM", "No bed in preferred category — widened search to step-down options")
        # beds expected to free up soon (predicted from planned discharges)
        soon = []
        horizon = datetime.now() + timedelta(hours=12)
        for adm in ctx.db.scalars(select(Admission).where(Admission.status == "active", Admission.expected_discharge <= horizon)).all():
            if adm.bed and adm.bed.ward.ward_type in need.bed_types:
                soon.append({"bed": adm.bed.code, "ward": adm.bed.ward.name, "expected": adm.expected_discharge.isoformat()})
        ctx.post(self.key, "bed_need", {"types": need.bed_types, "features": need.features, "priority": need.priority,
                                        "department_id": need.department_id, "department_floor": need.department_floor,
                                        "preferred": need.preferred})
        ctx.post(self.key, "bed_candidates", ranked)
        if held:
            ctx.log(self.key, f"Excluded {len(held)} bed(s) already held by other pending requests")
        recs = [Recommendation(f"{r['code']} — {r['ward']}", f"fit score {r['fit_score']}/100", r["fit_score"], r["factors"]) for r in ranked[:3]]
        if not ranked:
            ctx.send(self.key, "notification", "REQUEST", "Capacity alert: no suitable bed available")
            return AgentResult(agent=self.key, status="partial", recommendations=recs,
                               summary=f"No suitable bed available in {', '.join(need.bed_types)}. "
                                       f"{len(soon)} bed(s) expected to free within 12h.",
                               data={"candidates": [], "reasons": reasons, "soon_free": soon, "held": len(held)})
        top = ranked[0]
        ctx.send(self.key, "optimization", "PROPOSE", f"{len(ranked)} candidate beds; best {top['code']} (fit {top['fit_score']})")
        return AgentResult(agent=self.key, recommendations=recs, data={"candidates": ranked, "reasons": reasons,
                                                                       "soon_free": soon, "expanded_search": expanded},
                           summary=f"Found {len(options)} free bed(s) matching {'/'.join(need.bed_types)}; "
                                   f"best match {top['code']} in {top['ward']} (fit {top['fit_score']}/100)."
                                   + (" Search widened to step-down beds." if expanded else ""))

    def act_status_report(self, ctx: AgentContext) -> AgentResult:
        wards = ctx.db.scalars(select(Ward)).all()
        want = ctx.entities.get("bed_type")
        by_type: dict[str, dict] = {}
        for w in wards:
            d = by_type.setdefault(w.ward_type, {"total": 0, "occupied": 0, "available": 0, "reserved": 0, "cleaning": 0, "maintenance": 0, "ventilator_free": 0})
            for b in w.beds:
                d["total"] += 1
                d[b.status] = d.get(b.status, 0) + 1
                if b.status == "available" and "ventilator" in (b.features or []):
                    d["ventilator_free"] += 1
        for d in by_type.values():
            d["occupancy"] = round(d["occupied"] / d["total"], 3) if d["total"] else 0
        total = sum(d["total"] for d in by_type.values())
        occupied = sum(d["occupied"] for d in by_type.values())
        horizon = datetime.now() + timedelta(hours=24)
        soon = ctx.db.scalars(select(Admission).where(Admission.status == "active", Admission.expected_discharge <= horizon)).all()
        waiting = ctx.db.scalars(select(EmergencyCase).where(EmergencyCase.status == "awaiting_bed")).all()
        focus = by_type.get(want) if want else None
        if focus:
            summary = (f"{want.upper()}: {focus['available']} of {focus['total']} beds available "
                       f"({focus['occupancy']:.0%} occupied, {focus['ventilator_free']} free with ventilator, {focus['cleaning']} being cleaned).")
        else:
            summary = f"Hospital occupancy {occupied}/{total} beds ({occupied / max(total, 1):.0%})."
        summary += f" {len(soon)} discharge(s) expected in 24h; {len(waiting)} ER patient(s) awaiting a bed."
        recs = []
        for t, d in by_type.items():
            if d["occupancy"] >= 0.9:
                recs.append(Recommendation(f"{t.upper()} near capacity ({d['occupancy']:.0%})",
                                           "Consider expediting planned discharges or step-down transfers"))
            if d["cleaning"] >= 2:
                recs.append(Recommendation(f"{d['cleaning']} {t} beds awaiting cleaning", "Prioritise housekeeping turnaround"))
        return AgentResult(agent=self.key, summary=summary, recommendations=recs,
                           data={"by_type": by_type, "total": total, "occupied": occupied,
                                 "expected_discharges_24h": len(soon), "awaiting_bed": len(waiting)})

    def act_plan_release(self, ctx: AgentContext) -> AgentResult:
        info = ctx.blackboard.get("discharge")
        if not info or not info.get("bed_id"):
            return AgentResult(agent=self.key, status="skipped", summary="No bed to release")
        bed = ctx.db.get(Bed, info["bed_id"])
        waiting = ctx.db.scalars(select(EmergencyCase).where(EmergencyCase.status == "awaiting_bed")
                                 .order_by(EmergencyCase.triage_level, EmergencyCase.created_at)).all()
        nxt = waiting[0] if waiting else None
        summary = f"On discharge, {bed.code} goes to cleaning (~45 min turnaround) and becomes available."
        if nxt:
            summary += f" Next in line: ER case #{nxt.id} ({nxt.patient.name}, triage L{nxt.triage_level})."
            ctx.send(self.key, "emergency", "INFORM", f"{bed.code} will be free soon for case #{nxt.id}")
        return AgentResult(agent=self.key, summary=summary, data={"bed": bed.code, "turnaround_minutes": 45,
                                                                  "next_patient": nxt.patient.name if nxt else None})

    def act_find_waiting(self, ctx: AgentContext) -> AgentResult:
        waiting = ctx.db.scalars(select(EmergencyCase).where(EmergencyCase.status == "awaiting_bed")).all()
        pending_adm = ctx.db.scalars(select(Admission).where(Admission.status == "active", Admission.bed_id.is_(None))).all()
        items = [{"kind": "emergency", "id": e.id, "patient_id": e.patient_id, "name": e.patient.name,
                  "triage_level": e.triage_level, "news2": e.news2_score} for e in waiting]
        items += [{"kind": "admission", "id": a.id, "patient_id": a.patient_id, "name": a.patient.name,
                   "acuity": a.acuity} for a in pending_adm]
        ctx.post(self.key, "waiting_patients", items)
        return AgentResult(agent=self.key, summary=f"{len(items)} patient(s) currently waiting for a bed.", data={"waiting": items})
