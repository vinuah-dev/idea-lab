# MedOrchestra — Multi-Agent AI System for Hospital Management

**Hospital resource optimisation, clinical workflow automation, patient-care coordination, pre-hospital care and hospital finance through eleven specialised AI agents with human-in-the-loop control.**

MedOrchestra started from the project synopsis *"Multi-Agent AI Systems for Hospital Resource Optimization, Clinical Workflow Automation, and Patient Care Coordination"* and grew into a full hospital platform (v2):

**Core (synopsis)**
- **11 specialised AI agents** coordinated by a **central orchestrator** (planner → shared blackboard → FIPA-ACL messages → conflict resolution → HITL gate)
- **Natural-language requests** in English *or Hinglish* → intent classification & entity extraction (Claude when an API key is configured, otherwise a fully offline TF-IDF + logistic-regression pipeline with rule-based Hinglish normalisation)
- **Real optimisation & clinical algorithms**: OR-Tools CP-SAT (beds, rosters, theatres), NEWS2 early warning, M/M/c queueing, Holt-Winters forecasting, drug-safety screening
- **Human-in-the-loop** approval with approve / reject / *approve-with-modification*, and a configurable **autonomy policy** (supervised / balanced / autonomous)

**Beyond the synopsis (v2)**
- 🚑 **Ambulance & 108 pre-hospital coordination** — severity pre-triage, nearest-capable-unit dispatch (explainable ETA scoring), live fleet map, and a **pre-arrival ED alert** that holds the resuscitation bay and team *before* the patient arrives
- 🧪 **Hospital digital twin** — Monte-Carlo discrete-event simulation that starts from the *live* hospital state; what-if surges, mass-casualty events, bed closures and staff absence, with **prescriptive recommendations** (each lever tested in the twin)
- 💳 **Billing & insurance** — automatic, idempotent charge capture from clinical activity, **LOS-aware cost estimates**, **PM-JAY (Ayushman Bharat)** package mapping, TPA claims, payments, printable invoices, and billing clearance in the discharge workflow
- 📈 **ICU central monitor** — streaming bedside telemetry with ECG/pleth traces and **smart alarms** (persistence filter that measurably suppresses transient artefacts)
- 💬 **Conversational copilot** — floating chat on every page, Hinglish-aware, remembers the patient being discussed ("usko kal book karo"), asks *"Which patient?"* instead of failing, voice input (en-IN / hi-IN)
- 🔁 **30-day readmission risk** — LACE index + logistic regression; sets the follow-up interval the agents book at discharge
- 📝 **Clinical documentation** — AI-drafted SOAP notes (clinician must review & sign) and auto-generated **SBAR shift handover**
- 🛡️ **AI governance** — HITL approval / modification / rejection rates, decision times, autonomy ratio, **model cards with leakage-free validation**, medication-safety events and record-access oversight
- 🖥️ **OPD token TV display** (voice announcements in English + Hindi) and a **self check-in kiosk** — privacy by design (tokens only, MRN + phone verification, rate-limited)
- 🔐 **Security hardening** — login lock-out after repeated failures, password policy, security headers, request IDs, record-access logging with a **"who viewed my record"** view for patients (DPDP Act 2023 spirit)
- Role-based dashboards, patient portal (bill + UPI demo payment + access log), installable **PWA**, live WebSocket updates, simulator, audit log, **55 automated tests** and **GitHub Actions CI**

> Decision support only — diagnosis, treatment and other critical clinical decisions remain with qualified healthcare professionals. Tariffs, package rates and geography are illustrative demo data.

---

## 1. Quick start (Windows)

Prerequisites: **Python 3.10+** and **Node.js 18+**.

```bat
setup.bat      :: one time — creates the Python venv, installs backend + frontend dependencies
start.bat      :: starts the API (port 8000) and the web app (port 5173) and opens the browser
```

Open **http://localhost:5173** and click any demo account. Public screens: **/display** (waiting-room TV) and **/kiosk** (self check-in).

### Manual start (any OS)

```bash
# backend
cd backend
python -m venv .venv
.venv/Scripts/activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev
```

The database (SQLite, `backend/hospital.db`) is created and seeded automatically. Demo data is anchored to *today* and rebuilt automatically when it is stale or when the schema changes; an administrator can also reset it from **System → Reset demo data**.

### Single-server / production build

```bash
cd frontend && npm run build        # produces frontend/dist
cd ../backend && uvicorn app.main:app --port 8000   # now serves the web app too at http://localhost:8000
```

### Docker (PostgreSQL)

```bash
docker compose up --build           # web app on http://localhost:8080, API on :8000, PostgreSQL 16
```

### Enable Claude (optional)

Copy `backend/.env.example` to `backend/.env` and set `ANTHROPIC_API_KEY`. The orchestrator then uses **Claude (`claude-opus-5`) with structured JSON outputs** for request understanding and writes a *coordination brief* after each workflow. Local, DB-grounded extractors still resolve patients, medicines and vitals. Without a key everything works offline.

---

## 2. Demo accounts

| Role | Username | Password | What to try |
|---|---|---|---|
| Administrator | `admin` | `admin123` | Everything; simulation; digital twin; governance; claims |
| Doctor (Cardiology) | `doctor` | `doctor123` | Approve admissions / orders / prescriptions; AI-drafted notes |
| ER Doctor | `er.doctor` | `doctor123` | Emergency & ambulance pre-arrival coordination |
| ICU Nurse | `nurse` | `nurse123` | ICU monitor, SBAR handover, bed operations, 108 calls |
| Reception | `reception` | `reception123` | Registration, OPD queue, billing desk, claim submission |
| Lab technician | `lab` | `lab123` | Diagnostics board, result entry |
| Pharmacist | `pharmacist` | `pharma123` | Prescription verification, inventory |
| Patient | `patient` | `patient123` | Portal: AI booking, bill + demo UPI payment, record-access log |

Kiosk demo: MRN **1001**, phone digits **1234** (Rohan Mehta has an appointment later today).
A step-by-step viva/demo walkthrough is in **[docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)**.

### Submission deliverables (in `docs/`)

| File | Contents |
|---|---|
| `MedOrchestra_Project_Report.docx` / `.pdf` | Full project report (front matter, 8 chapters, references, appendices). Fill in the `____` placeholders. |
| `MedOrchestra_Presentation.pptx`, `MedOrchestra_Presentation_RBU.pptx` | Viva presentations (generic and institute template) |
| `figures/diagrams/`, `figures/screenshots/` | Architecture/UML diagrams and application screenshots |
| `ARCHITECTURE.md`, `DEMO_SCRIPT.md` | Technical design notes and the live-demo script with likely viva questions |

---

## 3. Modules

| Module | Implementation |
|---|---|
| Authentication & RBAC | JWT + PBKDF2, 7 roles, per-endpoint guards, approver-role policy, lock-out, password policy |
| Patient management | Registration, unified record, cross-module timeline, vitals trend, SOAP notes, readmission risk, discharge summary |
| Beds & resources | 108 beds / 10 wards, ORs, ventilators, imaging; predictive maintenance |
| Inpatient monitoring | Census, NEWS2 observations, escalation → ICU-transfer proposal, LOS prediction, **ICU central monitor**, **SBAR handover** |
| Operation theatres | Timeline, slot finder, WHO-checklist surgical pathway, CP-SAT day optimisation |
| Appointments & queue | Slot search, dynamic priority queue, M/M/c wait prediction, **TV token display**, **self check-in kiosk** |
| Staff scheduling | Workload-aware assignment, redeployment, CP-SAT weekly roster |
| Diagnostics & pharmacy | Protocol workups, modality scheduling, TAT tracking; allergy / interaction / dose checks, stock & reorder |
| Emergency & pre-hospital | NEWS2 + red flags → 5-level triage, code alerts; **108 dispatch, live fleet, pre-arrival bay hold** |
| Billing & insurance | **Charge capture, cost estimator, PM-JAY / TPA claims, payments, invoices, discharge billing clearance** |
| AI optimisation & planning | Global CP-SAT bed assignment, joint allocation, bottlenecks, forecasting, **digital-twin what-if** |
| Notifications | Role/user routing, in-app + simulated SMS/e-mail, live toasts |
| Analytics & governance | Occupancy, waits, utilisation, forecasts; **HITL oversight metrics, model cards, access logs** |

The agent pipeline (intake → NLP → planning → coordinated execution → conflict resolution → HITL → notify & audit) is in [`backend/app/agents/orchestrator.py`](backend/app/agents/orchestrator.py).

---

## 4. Architecture

```
Client ─ React/TS PWA: role dashboards · agent console · copilot · patient portal · TV display · kiosk
   │  REST + WebSocket (agent traces, fleet positions, telemetry, alerts)
Application ─ FastAPI gateway · JWT auth · RBAC · security middleware · event bus
   │
AI orchestration ─ Hinglish normaliser → NLP understanding → planner (DAG) → blackboard → conflict resolution → HITL gate
   │
Specialised agents ─ Bed · Appointment & Queue · Staff · Diagnostics · Pharmacy · Patient Care · Emergency · Optimizer
                     · Billing & Insurance · Ambulance Dispatch · Notification
   │
Services ─ OR-Tools CP-SAT · NEWS2 · M/M/c · Holt-Winters · LOS (GBM) · readmission (LACE + LR) · digital twin (DES)
           · billing engine · dispatch & fleet tracker · telemetry hub · clinical knowledge base · audit
   │
Data ─ SQLAlchemy → SQLite (dev) / PostgreSQL (Docker)
```

Detailed diagrams: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## 5. Project structure

```
backend/
  app/
    agents/            orchestrator, 11 agents, NLP (+ model card), Claude client, action executor (HITL)
    services/          optimizer & OT scheduler (OR-Tools), triage & early warning, LOS & readmission models,
                       digital twin, billing, dispatch & fleet tracker, telemetry, Hinglish normaliser,
                       queueing, forecasting, maintenance, clinical KB, settings (HITL policy), activity
    routers/           REST API (auth, patients, ward, resources, surgery, clinical, agents, billing, ambulance,
                       twin, copilot, governance, public display & kiosk, clinical docs, telemetry, insights)
    models.py          ORM data model        seed.py   synthetic hospital        simulation.py  live simulator
    main.py            FastAPI app, security middleware, WebSocket, background trackers, SPA hosting
  tests/               55 unit + integration tests (pytest)
frontend/
  src/pages/           29 screens (command center, agent console, ambulance map, digital twin, ICU monitor,
                       billing, governance, handover, TV display, kiosk, …)
  src/components/      layout, copilot, agent network graph, approval card, invoice view, UI kit
.github/workflows/     CI: backend tests + frontend typecheck/build
docs/                  report, presentations, architecture, demo script
docker-compose.yml     PostgreSQL + API + Nginx
```

---

## 6. Testing & quality

```bash
cd backend
.venv/Scripts/python -m pytest -q      # 55 passed
cd ../frontend && npx tsc --noEmit     # type-check
```

Tests cover the full orchestrations (ICU admission → approval → execution; emergency → rejection releases the bed; allergy block; auto-booked appointment; approver-role enforcement), theatre optimisation, NEWS2 escalation, autonomy modes, and the v2 modules: idempotent charge capture and payments, PM-JAY cashless coverage and claim settlement, LOS-aware estimates, billing agent + discharge finalising the bill, **ambulance call → pre-arrival bay hold → arrival**, digital-twin reproducibility (common random numbers), what-if via agents, Hinglish normalisation and copilot memory/clarification, readmission model quality, login lock-out and security headers, kiosk privacy, SOAP drafts and SBAR handover, governance metrics and the smart-alarm persistence filter.

Measured model quality (shown live on the **AI Governance** page): intent classifier 74 % leakage-free cross-validated accuracy and 96 % on a held-out set that includes Hinglish; LOS model MAE ≈ 2.1 d vs 2.8 d naïve; readmission model AUC ≈ 0.72.

API documentation (Swagger UI): **http://localhost:8000/docs**.

---

## 7. Limitations & future scope

Synthetic data; demo-scale clinical knowledge base and illustrative tariffs; SMS/e-mail, insurer (TPA/NHA) and HIS/LIS integrations are simulated; telemetry and ambulance movement are simulated. Future work: HL7 FHIR / ABDM (ABHA) integration, real device telemetry over MQTT, models trained and calibrated on local data, multi-hospital referral network, full Hindi / regional-language UI.
