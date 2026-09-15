# Demo script (≈ 10 minutes) & viva notes

Start the system with `start.bat` (or see README), open http://localhost:5173.

## 1. Command Center — *admin / admin123* (1 min)
- KPIs: bed occupancy, ICU/ventilator beds, emergency load, OPD waits, staff on duty, approvals.
- Ward occupancy bars, ED board sorted by triage, 30-day patient-flow chart, **bottlenecks detected by the Resource Optimization Agent**.
- Top bar: **Live** (WebSocket), NLP engine (Local NLP or Claude), **Simulate** toggle.

## 2. Synopsis example — ICU admission (2 min)
AI Agent Console → click **“ICU admission (synopsis example)”**
(*“Patient needs admission and requires ICU monitoring with ventilator support.”*)
- Watch the **live agent network**: the orchestrator dispatches Patient Care → Bed → Staff → Diagnostics → Optimizer → Notification; inter-agent **PROPOSE/INFORM** messages animate.
- **Understanding** panel: intent *admission*, entities *bed_type=icu, features=[ventilator, monitor]*.
- **Execution plan**: dependency levels (DAG).
- **Findings**: open *Explain* on the bed / staff / optimizer cards to show the **factor breakdown** (explainable AI).
- **HITL**: the bed is *held* automatically (reversible), the admission waits for a doctor. No name was given, so a *provisional registration* is created — reception completes identity later.
- Approve it (optionally pick another bed from the *Modify bed* dropdown) → the admission executes, beds page updates live.

## 3. Emergency (2 min)
Emergency → preset **Chest pain** → watch the **live NEWS2 preview** (score, component points, triage level, target time) → *Register & triage*.
- You land on the agent trace: triage L1, **resuscitation bay with ventilator preferred**, ER doctor chosen, Cardiology consult paged, ACS workup suggested (needs clinician approval), code alert pushed to doctors & nurses (toast).
- Show that **rejecting** the assignment releases the held bay.

## 4. Safety — prescription (1 min)
Console → **Prescription safety** (*Prescribe amoxicillin for Rohan Mehta* — he is penicillin-allergic).
- Pharmacy Agent REFUSES → conflict logged → held as **critical** approval for doctor override. Pharmacy → Safety checker shows the same for any patient/drug pair (e.g. warfarin + aspirin).

## 5. Optimisation (1.5 min)
- Console → **Optimise roster**: OR-Tools CP-SAT schedules ~77 staff for 7 days (coverage %, fairness of night shifts, rest rules) → admin approves → Staff → *Weekly roster* shows the generated roster.
- Console → **Global bed optimisation**: places all waiting ER patients optimally + bottlenecks + forecast.
- OPD & Queue: dynamic priority (click *score* → factor breakdown), ETA per patient, **M/M/c** utilisation ρ, P(wait), Wq.

## 6. Analytics & forecasting (1 min)
Analytics: Holt-Winters forecast with 95 % interval and hold-out MAPE; switch metric to ICU occupancy; observed vs M/M/c waits; equipment & staff utilisation; agent performance.

## 6b. Ward early warning → automatic ICU transfer proposal (1 min)
Inpatients & Early Warning → pick a general-ward patient → **Obs** → enter HR 130, RR 27, SpO₂ 89, BP 88/55, Temp 39.4 → the live NEWS2
jumps to ≥ 7 → *Save*. Doctors and nurses get a critical alert and the agents start an **ICU transfer** request (link in the dialog);
the approval shows the ICU bed, the team and the **ML-predicted length of stay**.

## 6c. Operation theatres (1 min)
Operation Theatres → switch the date to **tomorrow** (the list is deliberately inefficient: cases finish after 20:00) → **Optimise day
(CP-SAT)** → overtime and last-case time drop, no overlaps → *Apply*. Or ask the console *"Schedule a laparoscopic cholecystectomy for
Rohan Mehta tomorrow"* → ranked theatre slots with explanations → doctor approves → surgical pathway with the WHO checklist is created.

## 6d. Autonomy policy (0.5 min)
System & Policy → switch HITL mode to **Supervised** → run *Book OPD appointment* again: now even the booking waits for approval. Switch back to **Balanced**.

## 7. Patient portal (0.5 min)
Log out → *patient / patient123* → book a Cardiology visit → the Appointment Agent picks the best doctor/slot and confirms (simulated SMS shown to reception).

## 8. Live simulation & audit (0.5 min)
Admin → **Simulate**: walk-ins, lab results, bed cleaning, deterioration alerts (NEWS2), ER arrivals routed through the full agent pipeline. Audit Log shows every human decision and agent action.

---

## Likely viva questions

**Why multi-agent instead of one AI model?** Separation of concerns: each agent owns one domain, its data and its algorithm (CP-SAT, NEWS2, queueing…), so it can be developed, tested and improved independently. The orchestrator composes them per request, and conflicts become explicit and resolvable.

**How do agents communicate?** Through a shared *blackboard* (per-request context) and FIPA-ACL style messages (INFORM/REQUEST/PROPOSE/REFUSE) that are logged in the trace. Execution order comes from a dependency DAG built by the planner.

**Where exactly is AI used?** (1) NLP — intent classification & entity extraction (ML classifier or Claude); (2) decision support — constraint optimisation, early-warning scoring, forecasting, queue prediction; (3) automation — generating plans, actions and briefs. Clinical decisions stay with humans.

**How is safety ensured?** Risk-tiered actions: only reversible / low-risk actions auto-execute; everything else needs an authorised role (RBAC-checked server-side). Approvers can modify or reject; rejection rolls back holds. Pharmacy refusals cannot be auto-executed. Everything is audited.

**What if the LLM is wrong or unavailable?** Structured-output schema constrains Claude; entities are re-grounded against the database; any failure falls back to the local classifier. The system runs fully offline.

**How does the optimiser handle two patients wanting the same bed?** Beds held by pending approvals are excluded; the CP-SAT model maximises priority-weighted placements across all waiting patients, so the higher-acuity patient keeps the bed and the other receives the next-best one (recorded as a conflict).

**How is waiting time predicted?** M/M/c queueing (Erlang-C) per department + per-patient ETA from the dynamic priority queue.

**How accurate is forecasting?** Holt-Winters fitted by grid search; hold-out MAPE is shown on the Analytics page (typically ~8–10 % on the demo data).

**Scalability / deployment?** Stateless FastAPI + PostgreSQL in Docker; agents are plain Python classes (could be split into services / message queue); WebSocket bus for live updates.

**Limitations?** Synthetic data, demo-scale knowledge base, simulated integrations; real deployment needs clinical validation, HL7/FHIR integration and regulatory compliance.
