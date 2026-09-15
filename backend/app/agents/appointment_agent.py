"""Appointment & Queue Agent — slot finding, queue prioritisation and wait-time prediction (M/M/c)."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from ..models import Appointment, Department, Staff
from ..services.clinical import match_department
from ..services.queueing import mmc_expected_wait, peak_hourly_rate
from .base import AgentContext, AgentResult, BaseAgent, ProposedAction, Recommendation

OPD_START, OPD_END = 9, 17


def next_free_slot(db, doctor: Staff, desired: datetime, minutes: int) -> datetime:
    day_start = desired.replace(hour=OPD_START, minute=0, second=0, microsecond=0)
    t = max(desired.replace(second=0, microsecond=0), day_start)
    t = t.replace(minute=(t.minute // minutes) * minutes) if t.minute % minutes else t
    taken = {a.scheduled_at.replace(second=0, microsecond=0) for a in db.scalars(
        select(Appointment).where(Appointment.doctor_id == doctor.id, Appointment.status.not_in(["cancelled", "no_show"]),
                                  Appointment.scheduled_at >= day_start, Appointment.scheduled_at < day_start + timedelta(days=3))).all()}
    for _ in range(200):
        if t.hour >= OPD_END:
            t = (t + timedelta(days=1)).replace(hour=OPD_START, minute=0)
        if t not in taken and t >= datetime.now() - timedelta(minutes=1):
            return t
        t += timedelta(minutes=minutes)
    return t


class AppointmentQueueAgent(BaseAgent):
    key = "appointment"
    name = "Appointment & Queue Agent"
    description = "Books OPD appointments, prioritises queues and predicts waiting time using queueing theory."
    capabilities = ["slot search", "doctor matching", "queue prioritisation", "M/M/c wait prediction", "follow-up scheduling"]
    icon = "calendar-clock"
    color = "indigo"

    def act_find_slot(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        dept_name = ctx.entities.get("department") or match_department(ctx.request.text) or "General Medicine"
        dept = db.scalar(select(Department).where(Department.name == dept_name)) or db.scalar(select(Department).where(Department.name == "General Medicine"))
        desired = datetime.fromisoformat(ctx.entities["datetime"]) if ctx.entities.get("datetime") else datetime.now() + timedelta(minutes=15)
        doctors = db.scalars(select(Staff).where(Staff.role == "doctor", Staff.department_id == dept.id)).all()
        if not doctors:
            return AgentResult(agent=self.key, status="failed", summary=f"No doctors configured for {dept.name}.")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        options = []
        for d in doctors:
            slot = next_free_slot(db, d, desired, dept.avg_consult_minutes)
            queue = db.query(Appointment).filter(Appointment.doctor_id == d.id, Appointment.scheduled_at >= today,
                                                 Appointment.scheduled_at < today + timedelta(days=1),
                                                 Appointment.status.in_(["scheduled", "checked_in", "in_progress"])).count()
            delay = (slot - desired).total_seconds() / 60
            factors = [{"factor": "minutes after requested time", "cost": round(max(delay, 0) / 10, 1)},
                       {"factor": f"today's queue ({queue})", "cost": queue * 1.5},
                       {"factor": "on duty" if d.on_duty else "not on duty now", "cost": 0 if d.on_duty else 5}]
            options.append({"doctor_id": d.id, "doctor": d.name, "specialization": d.specialization, "slot": slot.isoformat(),
                            "queue": queue, "cost": round(sum(f["cost"] for f in factors), 1), "factors": factors})
        options.sort(key=lambda o: o["cost"])
        best = options[0]
        # Department-level expected wait (M/M/c): arrivals ~ today's bookings over OPD hours
        day_start = desired.replace(hour=0, minute=0, second=0, microsecond=0)
        booked = db.scalars(select(Appointment.scheduled_at).where(Appointment.department_id == dept.id, Appointment.scheduled_at >= day_start,
                                                                   Appointment.scheduled_at < day_start + timedelta(days=1))).all()
        on_duty = max(1, sum(1 for d in doctors if d.on_duty))
        mmc = mmc_expected_wait(on_duty, peak_hourly_rate(list(booked)), dept.avg_consult_minutes)
        ctx.post(self.key, "appointment", best | {"department": dept.name})
        p = ctx.patient
        urgency = ctx.entities.get("urgency")
        action = ProposedAction(
            action_type="book_appointment",
            title=f"Book {p.name if p else 'patient'} with {best['doctor']} at {datetime.fromisoformat(best['slot']):%d %b %H:%M}",
            payload={"patient_id": p.id if p else None, "doctor_id": best["doctor_id"], "department_id": dept.id,
                     "scheduled_at": best["slot"], "priority": 2 if urgency else 3, "reason": ctx.request.text[:200]},
            risk="low", category="operations", requires_approval=False,
            rationale=[f"Lowest combined delay + queue cost ({best['cost']})", f"Dept utilisation ρ={mmc['utilization']}"],
        )
        recs = [Recommendation(f"{o['doctor']} — {datetime.fromisoformat(o['slot']):%a %H:%M}", f"queue {o['queue']}", o["cost"], o["factors"]) for o in options[:3]]
        return AgentResult(agent=self.key, actions=[action], recommendations=recs, data={"options": options[:5], "department": dept.name, "queueing": mmc},
                           summary=f"Best slot in {dept.name}: {best['doctor']} at {datetime.fromisoformat(best['slot']):%d %b %H:%M} "
                                   f"(queue {best['queue']}). Predicted department wait (M/M/{on_duty}): "
                                   f"{mmc['wq_minutes'] if mmc['wq_minutes'] is not None else 'unstable — over capacity'} min.")

    def act_follow_up(self, ctx: AgentContext, days: int = 7) -> AgentResult:
        p = ctx.patient
        if not p:
            return AgentResult(agent=self.key, status="skipped", summary="No patient")
        doctor = p.primary_doctor or ctx.db.scalar(select(Staff).where(Staff.role == "doctor"))
        dept = doctor.department if doctor else None
        slot = next_free_slot(ctx.db, doctor, (datetime.now() + timedelta(days=days)).replace(hour=10, minute=0), dept.avg_consult_minutes if dept else 15)
        ctx.post(self.key, "follow_up", {"doctor_id": doctor.id, "slot": slot.isoformat()})
        return AgentResult(agent=self.key, summary=f"Follow-up proposed with {doctor.name} on {slot:%d %b at %H:%M} ({days} days post-discharge).",
                           data={"doctor": doctor.name, "slot": slot.isoformat(), "department_id": dept.id if dept else None})

    def act_queue_status(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        rows = []
        for dept in db.scalars(select(Department)).all():
            waiting = db.query(Appointment).filter(Appointment.department_id == dept.id, Appointment.status == "checked_in",
                                                   Appointment.scheduled_at >= today).count()
            times = db.scalars(select(Appointment.scheduled_at).where(Appointment.department_id == dept.id, Appointment.scheduled_at >= today,
                                                                     Appointment.scheduled_at < today + timedelta(days=1))).all()
            booked = len(times)
            docs = db.query(Staff).filter(Staff.department_id == dept.id, Staff.role == "doctor", Staff.on_duty.is_(True)).count()
            if booked == 0 and docs == 0:
                continue
            mmc = mmc_expected_wait(max(docs, 1), peak_hourly_rate(list(times)), dept.avg_consult_minutes)
            rows.append({"department": dept.name, "waiting": waiting, "booked": booked, "doctors": docs, **mmc})
        rows.sort(key=lambda r: -(r["utilization"]))
        recs = [Recommendation(f"{r['department']} utilisation {r['utilization']:.0%}", f"{r['waiting']} waiting, {r['doctors']} doctor(s) — add a doctor or reschedule routine visits")
                for r in rows if r["utilization"] >= 0.85]
        return AgentResult(agent=self.key, recommendations=recs, data={"departments": rows},
                           summary=f"{sum(r['waiting'] for r in rows)} patient(s) waiting across {len(rows)} OPD queues; "
                                   f"{len(recs)} department(s) above 85% utilisation.")
