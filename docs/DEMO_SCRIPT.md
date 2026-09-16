# Demo script (≈ 15 minutes) & viva notes

Start the system with `start.bat` (or see README), open http://localhost:5173. Demo data is anchored to *today*.

## 1. Command Center — *admin / admin123* (1 min)
- KPIs: bed occupancy, ICU/ventilator beds, emergency load, OPD waits, staff on duty, approvals.
- Ward occupancy, ED board sorted by triage, patient-flow chart, **bottlenecks detected by the Resource Optimization Agent**.
- Top bar: **Live** (WebSocket), NLP engine (Local NLP or Claude), HITL mode, **Simulate** toggle. Bottom-right: **Copilot**.

## 2. Synopsis example — ICU admission (2 min)
AI Agent Console → **“ICU admission (synopsis example)”**.
- Live agent network (11 agents), understanding panel, DAG execution plan, *Explain* factor breakdowns.
- New in v2: the **Billing & Insurance Agent** adds a **cost estimate** from the predicted stay (and PM-JAY / insurance cover).
- HITL: bed held automatically; admission waits for a doctor → approve (optionally *Modify bed*).

## 3. 🚑 Ambulance pre-arrival coordination (2 min) — the v2 headline
Ambulance & 108 → click **Random call** (or pick a locality + complaint → *Dispatch*).
- The Ambulance Dispatch Agent pre-triages severity, ranks units by ETA (explainable), dispatches automatically (time-critical actions never wait).
- Watch the unit move on the live map. When the crew leaves the scene the ED receives a **pre-alert** (toast), an *incoming* case appears on the ED board, and the agents propose a bay + team → **approve**: the bay is *held* before arrival.
- Use *Advance stage* to fast-forward. On arrival the patient goes straight to the held bay (door-to-bay time saved).

## 4. 🧪 Digital twin — what-if (1.5 min)
Digital Twin → preset **Mass-casualty incident** or **30% nursing absence**.
- Baseline vs scenario with P10–P90 bands (Monte-Carlo, common random numbers), ED boarding curve, KPI table.
- **Prescriptive recommendations** — click *Apply in twin & re-run* on the top lever and show boarding dropping.
- Also via agents: console → *“What if ER arrivals increase by 50% for the next 3 days?”*

## 5. 💳 Billing & insurance (1.5 min)
Billing & Insurance → KPIs, revenue by category, payer mix (PM-JAY / TPA / self).
- Open an invoice: itemised charges were **captured automatically** from bed-days, tests, medicines, procedures. Record a UPI payment; submit a PM-JAY claim; as admin settle it in *Insurance claims*.
- *Cost estimator*: ICU, 70 years, emergency, PM-JAY → P10 / expected / P90 cost from the LOS model.
- Console → *“What is the bill for Rohan Mehta?”*; discharge a PM-JAY patient → the final bill is closed and the claim filed automatically.

## 6. 💬 Copilot (1 min)
Open **Copilot** → *“ICU mein kitne bed khali hain?”* (Hinglish is normalised: *understood as …*).
Then *“Where is Rohan Mehta in his care journey?”* → *“Usko kal subah 11 baje cardiology mein book karo”* — the copilot remembers the patient.
*“Discharge the patient”* in a new chat → it asks **which patient** instead of failing. Approvals can be decided inside the chat.

## 7. Emergency & safety (1.5 min)
Emergency → preset **Chest pain** → live NEWS2 preview → *Register & triage* (L1, resus bay, code alert). Rejecting the assignment releases the bay.
Console → **Prescription safety** (amoxicillin for penicillin-allergic Rohan) → Pharmacy Agent REFUSES → held as critical approval.

## 8. Ward care (1.5 min)
- **ICU Central Monitor** (nurse/doctor): live ECG/pleth, smart alarms with *Ack*, "transients suppressed" counter.
- Inpatients → record observations with HR 130, RR 27, SpO₂ 89, BP 88/55 → NEWS2 ≥ 7 → automatic ICU-transfer proposal.
- **Shift Handover (SBAR)** — generated per ward, printable.
- Patient record → **Clinical notes** → *AI-draft SOAP note* → edit → *sign*. **Readmission risk** card (LACE) drives the follow-up interval.

## 9. Optimisation (1 min)
Operation Theatres → tomorrow → **Optimise day (CP-SAT)**. Console → **Optimise roster** / **Global bed optimisation**. OPD & Queue → M/M/c.

## 10. Governance, patient side & public screens (1.5 min)
- **AI Governance**: approval / modification / rejection rates, median decision time, autonomy ratio, model cards (leakage-free CV, held-out incl. Hinglish, LOS MAE vs naïve, readmission AUC + fairness by gender), medication safety, record-access log.
- Patient portal (*patient / patient123*): AI booking, **My bill** with demo UPI payment, **Who accessed my record**.
- Sidebar → **TV display** (tokens only, voice announcements EN + HI) and **Kiosk** (MRN **1001**, phone **1234**).
- System & Policy → switch autonomy to *Supervised* and show that even bookings wait (ambulance dispatch still does not).

---

## Likely viva questions

**Why multi-agent instead of one AI model?** Each agent owns one domain, its data and its algorithm (CP-SAT, NEWS2, queueing, billing rules, dispatch scoring…), so it can be developed, tested and replaced independently; the orchestrator composes them per request and conflicts become explicit.

**How do agents communicate?** Through a per-request blackboard and FIPA-ACL style messages (INFORM / REQUEST / PROPOSE / REFUSE) shown in the live trace; execution order comes from a dependency DAG.

**How is safety ensured?** Risk-tiered actions and RBAC-checked approvals; modify / reject with rollback; pharmacy refusals cannot auto-execute; AI-drafted notes stay drafts until a clinician signs; everything audited. Only life-critical dispatch bypasses holds — by explicit policy, visible on the Governance page.

**How do you know the ML is any good?** Model cards with honest validation: intent classifier ~74 % leakage-free cross-validation and ~96 % on held-out phrasings incl. Hinglish; LOS MAE vs a naïve baseline and interval coverage; readmission AUC vs LACE alone and a fairness check by gender. All models are trained on synthetic data and must be retrained/recalibrated on local data before real use.

**What is a digital twin here?** A stochastic simulation initialised from the live database state (beds, discharges, ED), used to test scenarios before they happen. Common random numbers make baseline-vs-scenario differences meaningful; the lever search makes it prescriptive.

**How does pre-arrival coordination save time?** The ED is alerted when the crew leaves the scene (ETA known), so triage, bay allocation and team assembly happen during transport; on arrival the patient goes straight to a held bay.

**How is billing kept correct?** Charges are derived from clinical events with stable references, so syncing is idempotent; PM-JAY coverage uses package rules; payments cannot exceed the balance; claims cannot be duplicated.

**Privacy?** RBAC, record-access logging with a patient-facing access log (DPDP Act 2023 spirit), token-only public display, kiosk verification with rate limiting, login lock-out.

**What if the LLM is wrong or unavailable?** Claude output is schema-constrained and re-grounded on the database; any failure falls back to the offline pipeline — the whole system runs without internet (map tiles excepted).

**Limitations?** Synthetic data, demo-scale knowledge base and tariffs, simulated integrations (insurer, SMS, HIS, telemetry); real deployment needs clinical validation, ABDM/FHIR integration and regulatory approval.
