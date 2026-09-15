# MedOrchestra — Multi-Agent AI System for Hospital Management

**Hospital resource optimisation, clinical workflow automation and patient-care coordination through specialised AI agents with human-in-the-loop control.**

MedOrchestra implements the project synopsis *"Multi-Agent AI Systems for Hospital Resource Optimization, Clinical Workflow Automation, and Patient Care Coordination"* as a full-stack, working platform:

- **9 specialised AI agents** (the synopsis' 8 plus a Notification Agent) coordinated by a **central orchestrator**
- **Natural-language requests** → intent classification & entity extraction (Claude when an API key is configured, otherwise a fully offline TF-IDF + Logistic Regression pipeline)
- **Real optimisation & clinical algorithms**: Google OR-Tools CP-SAT (bed matching, staff rostering), NEWS2 early-warning triage, M/M/c queueing theory, Holt-Winters demand forecasting, drug-safety screening
- **Human-in-the-loop (HITL)** approval gate for every safety-critical action, with approve / reject / *approve-with-modification*, and a configurable **autonomy policy** (supervised / balanced / autonomous)
- **Ward early-warning monitoring**: bedside observations are NEWS2-scored; deterioration automatically alerts staff and makes the agents propose an **ICU transfer**
- **Operation-theatre scheduling**: explainable slot finder (turnover + surgeon availability) and **CP-SAT day re-optimisation** that removes overlaps and overtime
- **Machine learning**: Gradient-Boosting **length-of-stay prediction** with 80 % prediction intervals, used when agents plan admissions
- **Explainable AI**: every recommendation carries a factor-by-factor score breakdown
- **Role-based dashboards** ("My work" per role) for administrators, doctors, nurses, reception, lab, pharmacy and a **patient portal** — installable as a **PWA app**
- Printable **discharge summaries**, **predictive equipment maintenance**, **Ctrl+K global search**, **voice input** in the agent console, user & access management
- **Live updates** over WebSockets, a **live hospital simulator**, a complete **audit log** and **38 automated tests**

> Decision support only — diagnosis, treatment and other critical clinical decisions remain with qualified healthcare professionals.

---

## 1. Quick start (Windows)

Prerequisites: **Python 3.10+** and **Node.js 18+**.

```bat
setup.bat      :: one time — creates the Python venv, installs backend + frontend dependencies
start.bat      :: starts the API (port 8000) and the web app (port 5173) and opens the browser
```

Open **http://localhost:5173** and click any demo account.

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

The database (SQLite, `backend/hospital.db`) is created and seeded automatically on first start. Demo data is anchored to *today*, so it is refreshed automatically when it becomes stale; an administrator can also reset it from **System → Reset demo data**.

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

Copy `backend/.env.example` to `backend/.env` and set `ANTHROPIC_API_KEY`. The orchestrator then uses **Claude (`claude-opus-5`) with structured JSON outputs** for request understanding and writes a natural-language *coordination brief* after each workflow. Local, DB-grounded extractors still resolve patients, medicines and vitals. Without a key everything works offline.

---

## 2. Demo accounts

| Role | Username | Password | What to try |
|---|---|---|---|
| Administrator | `admin` | `admin123` | Everything; simulation; audit log; roster approval |
| Doctor (Cardiology) | `doctor` | `doctor123` | Approve admissions / orders / prescriptions |
| ER Doctor | `er.doctor` | `doctor123` | Emergency coordination |
| ICU Nurse | `nurse` | `nurse123` | Bed operations, ER registration, nursing approvals |
| Reception | `reception` | `reception123` | Registration, OPD queue |
| Lab technician | `lab` | `lab123` | Diagnostics board, result entry |
| Pharmacist | `pharmacist` | `pharma123` | Prescription verification, inventory |
| Patient | `patient` | `patient123` | Patient portal, AI appointment booking |

A step-by-step viva/demo walkthrough is in **[docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)**.

### Submission deliverables (in `docs/`)

| File | Contents |
|---|---|
| `MedOrchestra_Project_Report.docx` / `.pdf` | Full project report — front matter (certificate, declaration, acknowledgement, abstract, TOC), 8 chapters (introduction, literature survey, analysis & requirements, design with UML/DFD/ER diagrams, implementation & algorithms, screenshots, testing & evaluation with measured results, conclusion), references and appendices. Fill in the `____` placeholders (names, roll numbers, guide, institute). |
| `MedOrchestra_Presentation.pptx` | 16-slide presentation with speaker notes for the viva |
| `figures/diagrams/`, `figures/screenshots/` | All architecture/UML diagrams and application screenshots as PNG |
| `ARCHITECTURE.md`, `DEMO_SCRIPT.md` | Technical design notes and the live-demo script with likely viva questions |

---

## 3. How it maps to the synopsis

| Synopsis module (§5) | Implementation |
|---|---|
| Authentication & RBAC | JWT + PBKDF2 password hashing, 7 roles, per-endpoint role guards, approver-role policy, user management, password change |
| Patient Management | Registration, search, unified record, cross-module timeline, vitals trend, quick agent actions, discharge summary |
| Bed & Resource Management | 108 beds / 10 wards, ORs, ventilators, imaging; live status + transitions; predictive maintenance |
| *(added)* Inpatient monitoring | Census, NEWS2 bedside observations, observation schedules, escalation → ICU-transfer proposal, LOS prediction |
| *(added)* Operation theatres | Theatre timeline, slot finder, surgical care pathway (WHO checklist), CP-SAT day optimisation, `surgery` agent intent |
| Appointment & Queue | Slot search, dynamic priority queue with ageing, per-patient ETA, M/M/c wait prediction |
| Staff Scheduling | Workload-aware assignment, redeployment proposals, CP-SAT weekly roster |
| Diagnostic Coordination | Test catalogue, protocol-based workup, least-loaded modality scheduling, TAT tracking |
| Pharmacy Coordination | Allergy cross-reactivity, drug–drug interactions, dose limits, stock, reorder planning |
| Patient Care Coordination | Care pathways (admission / emergency / OPD / discharge), journey status, discharge readiness |
| Emergency Support | NEWS2 + red flags → 5-level triage, resus-bay preference, code alerts, surge monitoring |
| AI Resource Optimisation | Global CP-SAT bed assignment, joint bed-doctor-nurse allocation, bottleneck detection |
| Notification & Alerts | Role/user routing, in-app + simulated SMS/e-mail, live toasts |
| Analytics Dashboard | Occupancy, waits, utilisation, forecasts with prediction intervals, agent performance |

Agent pipeline (synopsis §4.2 i–x) is implemented step for step in [`backend/app/agents/orchestrator.py`](backend/app/agents/orchestrator.py).

---

## 4. Architecture

```
Client ─ React/TS PWA: role dashboards · agent console · patient portal
   │  REST + WebSocket
Application ─ FastAPI gateway · JWT auth · RBAC · event bus
   │
AI orchestration ─ NLP understanding → planner (DAG) → blackboard context → conflict resolution → HITL gate
   │
Specialised agents ─ Bed · Appointment & Queue · Staff · Diagnostics · Pharmacy · Patient Care · Emergency · Optimizer · Notification
   │
Services ─ OR-Tools CP-SAT · NEWS2 · M/M/c · Holt-Winters · clinical knowledge base · audit
   │
Data ─ SQLAlchemy → SQLite (dev) / PostgreSQL (Docker)
```

Detailed diagrams (architecture, orchestration sequence, ER diagram, DFDs, use cases, algorithms): **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## 5. Project structure

```
backend/
  app/
    agents/            orchestrator, 9 agents, NLP, Claude client, action executor (HITL)
    services/          optimizer & OT scheduler (OR-Tools), triage & early warning (NEWS2), LOS model (ML),
                       queueing, forecasting, maintenance, clinical KB, settings (HITL policy), activity
    routers/           REST API (auth, dashboard, patients, resources, appointments, staff, clinical, agents, insights)
    models.py          ORM data model (patients / resources / workflows / AI orchestration / audit)
    seed.py            synthetic hospital generator      simulation.py   live event simulator
    main.py            FastAPI app, WebSocket, SPA hosting
  tests/               38 unit + integration tests (pytest)
frontend/
  src/pages/           20 screens (command center, agent console, approvals, emergency, inpatients, theatres, …)
  src/components/      layout, agent network graph, approval card, UI kit
docs/                  architecture, demo script
docker-compose.yml     PostgreSQL + API + Nginx
```

---

## 6. Testing

```bash
cd backend
.venv/Scripts/python -m pytest -q      # 38 passed
cd ../frontend && npx tsc --noEmit     # type-check
```

Tests cover theatre optimisation (no overlaps, less overtime), surgery booking through the agents, NEWS2 escalation → ICU-transfer proposal, autonomy modes, user management, the LOS model versus a naive baseline, search and discharge summaries, plus NEWS2 scoring, triage escalation, intent classification (incl. multi-intent and false-positive suppression), entity extraction, drug safety, CP-SAT hard constraints and priority handling, roster constraints, Erlang-C, Holt-Winters, RBAC, and full orchestrations (ICU admission → approval → execution, emergency → rejection releases the held bed, allergy block, auto-booked appointment, approver-role enforcement, patient portal isolation).

API documentation (Swagger UI) is available at **http://localhost:8000/docs** (or `/docs` through the dev server).

---

## 7. Limitations & future scope

Limitations follow the synopsis (§9): recommendations depend on data quality; the clinical knowledge base is a small demo subset; SMS/e-mail and HIS/LIS integrations are simulated; the demo data is synthetic. Future work: HL7 FHIR integration, IoT/MQTT bed & device telemetry, ML length-of-stay models trained on real data, multi-hospital referral coordination, voice / regional-language interfaces.
