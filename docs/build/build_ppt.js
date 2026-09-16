// Generates the MedOrchestra presentation (.pptx) with pptxgenjs.
const fs = require('fs')
const path = require('path')
const pptxgen = require('pptxgenjs')

const OUT = process.argv[2] || path.join(__dirname, 'MedOrchestra_Presentation.pptx')
const M = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'metrics.json'), 'utf8'))
const F = (n) => path.join(__dirname, `fig_${n}.png`)
const S = (n) => path.join(__dirname, 'shots', `${n}.png`)
const ICON = 'D:\\codin\\idea lab\\frontend\\public\\icon-512.png'
const V2 = M.v2, TW = M.v2.twin, BIL = M.v2.billing, CARD = M.v2.nlp_card
const inr = (v) => '\u20B9' + Math.round(v).toLocaleString('en-IN')

// palette: clinical teal dominant, seafoam support, coral accent for alerts
const C = { dark: '0B1F24', teal: '0F5C54', sea: '14B8A6', mint: 'CCFBF1', coral: 'F97360', ink: '0F172A', mute: '64748B', line: 'E2E8F0', bg: 'F6FAF9', white: 'FFFFFF' }
const HEAD = 'Cambria', BODY = 'Calibri'

const pres = new pptxgen()
pres.layout = 'LAYOUT_WIDE' // 13.33 x 7.5
pres.author = 'MedOrchestra project team'
pres.title = 'Multi-Agent AI Systems for Hospital Management'

function size(file) { const b = fs.readFileSync(file); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) } }
function fit(file, x, y, w, h) { // contain inside box, centred
  const s = size(file); const r = s.w / s.h
  let iw = w, ih = w / r
  if (ih > h) { ih = h; iw = h * r }
  return { x: x + (w - iw) / 2, y: y + (h - ih) / 2, w: iw, h: ih }
}
const shadow = () => ({ type: 'outer', color: '000000', opacity: 0.14, blur: 8, offset: 2, angle: 90 })
function T(slide, text, o) { slide.addText(text, { fontFace: BODY, color: C.ink, isTextBox: true, margin: 0, valign: 'top', ...o }) }
function title(slide, text, sub) {
  T(slide, text, { x: 0.6, y: 0.4, w: 12.1, h: 0.7, fontFace: HEAD, fontSize: 32, bold: true, color: C.teal, valign: 'middle' })
  if (sub) T(slide, sub, { x: 0.6, y: 1.1, w: 12.1, h: 0.4, fontSize: 15, color: C.mute, italic: true })
}
function card(slide, x, y, w, h, fill = C.white) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: C.line, width: 0.75 }, shadow: shadow() })
}
function shot(slide, file, x, y, w, h) { // screenshot on a rounded card
  const b = fit(file, x + 0.08, y + 0.08, w - 0.16, h - 0.16)
  card(slide, b.x - 0.08, b.y - 0.08, b.w + 0.16, b.h + 0.16)
  slide.addImage({ path: file, ...b })
}
function dot(slide, x, y, label, fill = C.teal, d = 0.5) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill } })
  T(slide, String(label), { x, y, w: d, h: d, fontSize: d > 0.45 ? 16 : 12, bold: true, color: C.white, align: 'center', valign: 'middle' })
}
function bulletList(slide, items, o) {
  slide.addText(items.map((t, i) => ({ text: t, options: { bullet: { indent: 18 }, breakLine: i < items.length - 1, paraSpaceAfter: 6 } })),
    { fontFace: BODY, fontSize: 16, color: C.ink, isTextBox: true, margin: 0, valign: 'top', ...o })
}
function page(slide, n) { T(slide, String(n), { x: 12.45, y: 7.0, w: 0.4, h: 0.3, fontSize: 10, color: C.mute, align: 'right' }) }
let n = 0

// 1 ─ title ------------------------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.dark }
  s.addImage({ path: ICON, x: 0.7, y: 0.7, w: 0.9, h: 0.9 })
  T(s, 'MedOrchestra', { x: 1.8, y: 0.8, w: 5, h: 0.4, fontSize: 18, bold: true, color: C.mint })
  T(s, 'Multi-Agent Hospital Intelligence Platform', { x: 1.8, y: 1.2, w: 5, h: 0.35, fontSize: 13, color: '9FB7B3' })
  T(s, 'Multi-Agent AI Systems for Hospital Resource Optimization, Clinical Workflow Automation and Patient Care Coordination',
    { x: 0.7, y: 2.2, w: 6.2, h: 2.4, fontFace: HEAD, fontSize: 30, bold: true, color: C.white, valign: 'middle' })
  T(s, 'Project presentation', { x: 0.7, y: 4.8, w: 6, h: 0.4, fontSize: 16, color: C.sea, italic: true })
  T(s, 'Submitted by: ______________________   Roll No.: ________\nGuide: ______________________\nDepartment of ______________________ · 2026–27',
    { x: 0.7, y: 5.4, w: 6.2, h: 1.3, fontSize: 13, color: 'C9D6D4', paraSpaceAfter: 4 })
  const b = fit(S('dashboard'), 7.3, 0.9, 5.4, 5.7)
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: b.x - 0.1, y: b.y - 0.1, w: b.w + 0.2, h: b.h + 0.2, rectRadius: 0.08, fill: { color: '17343A' }, line: { color: '2A5058' } })
  s.addImage({ path: S('dashboard'), ...b })
  s.addNotes('Introduce the project: a working multi-agent AI platform for hospital operations built from our synopsis. Nine specialised agents coordinated by an orchestrator, with humans approving every critical action.')
}

// 2 ─ problem ----------------------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.bg }
  title(s, 'The problem', 'Hospital operations run on disconnected systems, phone calls and spreadsheets')
  const probs = [
    ['Fragmented information', 'Beds, staff, labs, pharmacy and appointments live in separate systems'],
    ['Manual allocation', 'Beds, ICU, theatres and staff assigned by hand — conflicts and idle capacity'],
    ['Long waiting times', 'Consultations, diagnostics and departments are not coordinated'],
    ['Communication gaps', 'Updates between departments are delayed or missed'],
    ['Emergency coordination', 'Critical cases need beds, teams and tests simultaneously'],
    ['Late escalation', 'Deteriorating ward patients are noticed too late'],
    ['No predictive planning', 'Historical data is not used to anticipate demand'],
    ['Administrative overload', 'Clinicians spend time chasing instead of treating'],
  ]
  probs.forEach(([h, d], i) => {
    const col = i % 4, row = Math.floor(i / 4)
    const x = 0.6 + col * 3.07, y = 1.85 + row * 2.45
    card(s, x, y, 2.85, 2.2)
    dot(s, x + 0.25, y + 0.25, i + 1, i === 4 || i === 5 ? C.coral : C.teal)
    T(s, h, { x: x + 0.25, y: y + 0.9, w: 2.4, h: 0.45, fontSize: 16, bold: true, color: C.ink })
    T(s, d, { x: x + 0.25, y: y + 1.35, w: 2.4, h: 0.8, fontSize: 12.5, color: C.mute })
  })
  page(s, n)
  s.addNotes('These are the problems listed in our synopsis. The core need: an intelligent, coordinated system that optimises resources and automates workflows while keeping clinicians in control.')
}

// 3 ─ solution overview: agents around orchestrator --------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.white }
  title(s, 'Our solution: eleven specialised agents, one orchestrator', 'Each agent owns one domain and uses the right algorithm; the orchestrator composes them per request')
  const cx = 3.9, cy = 4.35
  const agents = ['Bed Mgmt', 'Appointment & Queue', 'Staff Scheduling', 'Diagnostics', 'Pharmacy', 'Patient Care', 'Emergency', 'Resource Optimizer', 'Billing & Insurance', 'Ambulance Dispatch', 'Notification']
  const pos = agents.map((a, i) => {
    const ang = -Math.PI / 2 + (i * 2 * Math.PI) / agents.length
    return { a, x: cx + 2.55 * Math.cos(ang), y: cy + 2.05 * Math.sin(ang) }
  })
  // connectors first so the hub and the agent boxes sit on top of them
  pos.forEach(({ x, y }) => {
    s.addShape(pres.shapes.LINE, { x: Math.min(cx, x), y: Math.min(cy, y), w: Math.max(Math.abs(x - cx), 0.01), h: Math.max(Math.abs(y - cy), 0.01),
      line: { color: 'A7C9C3', width: 1.25 }, flipV: (x < cx) !== (y < cy) })
  })
  s.addShape(pres.shapes.OVAL, { x: cx - 1.05, y: cy - 1.05, w: 2.1, h: 2.1, fill: { color: C.teal }, line: { color: C.white, width: 3 } })
  T(s, 'AI\nOrchestrator', { x: cx - 1.05, y: cy - 1.05, w: 2.1, h: 2.1, fontSize: 17, bold: true, color: C.white, align: 'center', valign: 'middle' })
  pos.forEach(({ a, x, y }) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x - 0.8, y: y - 0.3, w: 1.6, h: 0.6, rectRadius: 0.12, fill: { color: a === 'Emergency' ? 'FDE8E3' : C.mint }, line: { color: a === 'Emergency' ? C.coral : C.sea } })
    T(s, a, { x: x - 0.8, y: y - 0.3, w: 1.6, h: 0.6, fontSize: 11.5, bold: true, color: C.ink, align: 'center', valign: 'middle' })
  })
  const feats = [
    ['Natural language in', 'Staff describe a need; NLP finds intents and entities'],
    ['Plan & coordinate', 'Dependency-ordered plan, shared blackboard, FIPA-ACL messages'],
    ['Optimise & explain', 'CP-SAT, NEWS2, queueing, forecasting, ML — with factor breakdowns'],
    ['Humans decide', 'Critical actions wait for approval; approve, modify or reject'],
  ]
  feats.forEach(([h, d], i) => {
    const y = 1.85 + i * 1.28
    dot(s, 7.6, y, i + 1)
    T(s, h, { x: 8.3, y: y - 0.02, w: 4.4, h: 0.4, fontSize: 17, bold: true })
    T(s, d, { x: 8.3, y: y + 0.4, w: 4.4, h: 0.7, fontSize: 13.5, color: C.mute })
  })
  page(s, n)
  s.addNotes('Instead of one big AI model we use eleven agents: the eight from the synopsis plus Notification, Billing & Insurance and Ambulance Dispatch. The orchestrator plans which agents are needed, they share findings on a blackboard and talk using FIPA performatives like PROPOSE and REFUSE.')
}

// 4 ─ architecture -----------------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.white }
  title(s, 'System architecture', 'Layered design from the synopsis — requests flow down, live events flow back up over WebSockets')
  const b = fit(F('arch'), 0.6, 1.6, 7.4, 5.6)
  s.addImage({ path: F('arch'), ...b })
  const layers = [
    ['Client', 'React + TypeScript PWA: role dashboards, agent console, patient portal'],
    ['Application', 'FastAPI gateway · JWT · role-based access · WebSocket bus'],
    ['Orchestration', 'NLP → planner (DAG) → blackboard → conflicts → HITL gate'],
    ['Agents', '11 domain agents proposing explainable actions'],
    ['Services', 'OR-Tools CP-SAT · NEWS2 · M/M/c · Holt-Winters · Gradient Boosting'],
    ['Data', 'SQLAlchemy → SQLite (dev) / PostgreSQL (Docker)'],
  ]
  layers.forEach(([h, d], i) => {
    const y = 1.75 + i * 0.9
    card(s, 8.4, y, 4.35, 0.78, i === 2 ? C.mint : C.white)
    T(s, h, { x: 8.6, y: y + 0.08, w: 4, h: 0.3, fontSize: 13.5, bold: true, color: C.teal })
    T(s, d, { x: 8.6, y: y + 0.38, w: 4, h: 0.35, fontSize: 11.5, color: C.mute })
  })
  page(s, n)
  s.addNotes('Walk through the layers. The key layer is AI orchestration, which is where natural language becomes a plan and where the human-in-the-loop gate sits.')
}

// 5 ─ pipeline ---------------------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.bg }
  title(s, 'How a request is handled — the 10-step agent pipeline', 'Exactly the pipeline (i)–(x) proposed in the synopsis, implemented in the orchestrator')
  const b = fit(F('pipeline'), 0.6, 1.75, 12.1, 1.5)
  card(s, 0.5, b.y - 0.2, 12.3, b.h + 0.4)
  s.addImage({ path: F('pipeline'), ...b })
  const cols = [
    ['Understand', 'TF-IDF + logistic regression (offline) or Claude with a strict JSON schema; entities grounded against the database (patients, medicines, vitals, beds, tests, procedures).'],
    ['Plan & execute', 'Intent templates merged into a dependency DAG; agents run level by level, posting to a shared blackboard and exchanging INFORM / REQUEST / PROPOSE / REFUSE messages.'],
    ['Resolve & gate', 'Conflict resolver handles contention, staff overload, missing capacity and safety refusals; the autonomy policy decides what runs automatically and what needs approval.'],
  ]
  cols.forEach(([h, d], i) => {
    const x = 0.6 + i * 4.1
    card(s, x, 4.0, 3.85, 2.9)
    dot(s, x + 0.25, 4.25, i + 1)
    T(s, h, { x: x + 0.95, y: 4.3, w: 2.7, h: 0.4, fontSize: 18, bold: true })
    T(s, d, { x: x + 0.25, y: 5.0, w: 3.4, h: 1.8, fontSize: 13, color: C.mute })
  })
  page(s, n)
  s.addNotes('Every request, whether typed by a doctor, registered at the ER desk, raised by the early-warning service or booked by a patient, goes through these ten steps and leaves a complete trace.')
}

// 6 ─ demo: agent console -----------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.white }
  title(s, 'Live demo: the synopsis ICU-admission example', '“Patient needs admission and requires ICU monitoring” — running in the AI Agent Console')
  shot(s, S('agents_icu_top'), 0.5, 1.55, 7.6, 5.75)
  const steps = [
    ['Understood', 'Intent admission (99%), ICU bed, ventilator + monitor'],
    ['Patient', 'No name given → provisional registration so care is not delayed'],
    ['Beds & staff', 'Ventilator ICU bed ranked; Critical Care doctor and ICU nurse chosen'],
    ['Optimised', 'CP-SAT checks other waiting patients; ML predicts length of stay'],
    ['Human decides', 'Bed held automatically; admission waits for a doctor'],
  ]
  steps.forEach(([h, d], i) => {
    const y = 1.7 + i * 1.1
    dot(s, 8.45, y, i + 1, i === 4 ? C.coral : C.teal, 0.45)
    T(s, h, { x: 9.1, y: y - 0.02, w: 3.7, h: 0.35, fontSize: 15, bold: true })
    T(s, d, { x: 9.1, y: y + 0.33, w: 3.7, h: 0.65, fontSize: 12.5, color: C.mute })
  })
  page(s, n)
  s.addNotes('Demo: click the ICU admission scenario. Watch agents light up in the network, the trace stream in, then open Explain on the bed and staff cards to show the factor breakdown. Finally approve the admission as a doctor.')
}

// 7 ─ human in the loop -------------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.bg }
  title(s, 'Humans stay in control', 'Agents propose — authorised people approve, modify or reject; everything is audited')
  const b = fit(F('hitl'), 0.6, 1.6, 3.6, 5.6)
  card(s, b.x - 0.12, b.y - 0.12, b.w + 0.24, b.h + 0.24)
  s.addImage({ path: F('hitl'), ...b })
  const modes = [
    ['Supervised', 'Every action waits for approval', 'E2E8F0'],
    ['Balanced (default)', 'Low-risk reversible actions run automatically; clinical and risky actions need approval', C.mint],
    ['Autonomous', 'Low/medium operational actions run automatically; high-risk, prescribing, discharge and staffing still need approval', 'E2E8F0'],
  ]
  modes.forEach(([h, d, f], i) => {
    const x = 4.7 + i * 2.75
    card(s, x, 1.75, 2.55, 2.4, f)
    T(s, h, { x: x + 0.2, y: 1.95, w: 2.2, h: 0.4, fontSize: 15, bold: true, color: C.teal })
    T(s, d, { x: x + 0.2, y: 2.45, w: 2.2, h: 1.6, fontSize: 12, color: C.ink })
  })
  shot(s, S('approvals'), 4.6, 4.4, 8.3, 2.9)
  page(s, n)
  s.addNotes('Safety is the key design choice. Admissions, emergency assignments, AI-suggested tests, contraindicated prescriptions, surgeries, discharges and rosters all require an authorised approver. The approver can change the bed or doctor before approving. The administrator can switch the autonomy mode.')
}

// 8 ─ algorithms --------------------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.white }
  title(s, 'Real algorithms inside the agents', 'Transparent, validated methods — not a black box')
  const algos = [
    ['OR-Tools CP-SAT', 'Bed allocation, weekly rosters and theatre scheduling with hard constraints and weighted objectives'],
    ['NEWS2 (RCP 2017)', 'Early-warning score for ER triage and ward deterioration with the official response policy'],
    ['M/M/c queueing', 'Erlang-C waiting-time prediction; dynamic priority queue with ageing'],
    ['Holt-Winters', 'Weekly-seasonal demand forecasting with 95% prediction intervals'],
    ['Gradient Boosting', 'Length-of-stay prediction with 80% quantile intervals for discharge planning'],
    ['NLP', `TF-IDF + logistic regression over ${V2.intents} intents, Hinglish normalisation; optional Claude with JSON-schema output`],
  ]
  algos.forEach(([h, d], i) => {
    const col = i % 3, row = Math.floor(i / 3)
    const x = 0.6 + col * 4.1, y = 1.75 + row * 2.75
    card(s, x, y, 3.85, 2.5, row === 0 && col === 0 ? C.mint : C.white)
    dot(s, x + 0.25, y + 0.25, i + 1)
    T(s, h, { x: x + 0.95, y: y + 0.3, w: 2.8, h: 0.45, fontSize: 18, bold: true })
    T(s, d, { x: x + 0.25, y: y + 1.0, w: 3.35, h: 1.4, fontSize: 13.5, color: C.mute })
  })
  page(s, n)
  s.addNotes('Explain one or two formulations if asked: CP-SAT maximises priority-weighted placements minus an explainable cost; the theatre model uses optional intervals and NoOverlap per theatre and per surgeon.')
}

// 9 ─ emergency & early warning ----------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.bg }
  title(s, 'Emergency and ward early warning', 'NEWS2 on every assessment — escalation reaches the right people and the agents automatically')
  shot(s, S('emergency'), 0.5, 1.6, 6.9, 4.6)
  const b = fit(F('escalation'), 7.7, 1.7, 5.1, 2.3)
  card(s, b.x - 0.12, b.y - 0.12, b.w + 0.24, b.h + 0.24)
  s.addImage({ path: F('escalation'), ...b })
  bulletList(s, [
    'Live NEWS2 preview while vitals are entered',
    'Level-1 cases get a resuscitation bay, ED team and specialist consult',
    'Ward NEWS2 ≥ 7 → emergency alert + automatic ICU-transfer proposal',
    'Rejecting an assignment releases the held bed',
  ], { x: 7.8, y: 4.35, w: 5.0, h: 2.6, fontSize: 15 })
  page(s, n)
  s.addNotes('Demo the chest-pain preset on the Emergency page, then record NEWS2 ≥ 7 observations for a ward patient to show the automatic ICU-transfer proposal.')
}

// 10 ─ theatres & resources ---------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.white }
  title(s, 'Operation theatres and resources', 'CP-SAT re-plans a day’s theatre list without overlaps or overtime')
  shot(s, S('theatres'), 0.5, 1.6, 8.1, 5.1)
  const stats = [
    [`${M.ot.before.overtime_minutes}→${M.ot.after.overtime_minutes}`, 'minutes of overtime'],
    [`${M.ot.before.conflicts}→${M.ot.after.conflicts}`, 'theatre overlaps'],
    [`${M.ot.before.makespan}→${M.ot.after.makespan}`, 'last case finishes'],
    [`${Math.round(M.ot.wall_ms)} ms`, 'CP-SAT solve time'],
  ]
  stats.forEach(([v, l], i) => {
    const y = 1.65 + i * 1.3
    card(s, 8.95, y, 3.85, 1.12, i === 0 ? C.mint : C.white)
    T(s, v, { x: 9.15, y: y + 0.1, w: 3.5, h: 0.6, fontFace: HEAD, fontSize: 28, bold: true, color: C.teal })
    T(s, l, { x: 9.15, y: y + 0.7, w: 3.5, h: 0.3, fontSize: 12.5, color: C.mute })
  })
  page(s, n)
  s.addNotes('Tomorrow’s list was deliberately inefficient in the demo data. One click on Optimise day moves cases earlier and into free theatres, removing overlaps and overtime. Surgeries can also be booked by just asking the agents.')
}


// 11 ─ pre-hospital: ambulance ------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.bg }
  title(s, 'Care starts before the hospital', '108 dispatch → live tracking → ED pre-alert: the bay and the team are ready when the patient arrives')
  shot(s, S('ambulance'), 0.5, 1.6, 7.9, 5.6)
  const steps = [
    ['Pre-triage the call', 'NEWS2 + red flags from the caller description and paramedic vitals'],
    ['Nearest capable unit', 'ETA + penalty for a BLS unit on a critical call; dispatched without an approval hold'],
    ['Live tracking', 'Positions stream to every screen over WebSockets'],
    ['Pre-arrival alert', 'Incoming ED case created in transit; agents hold a bay and a team'],
    ['Arrival', 'Straight into the reserved bay — no search, no waiting'],
  ]
  steps.forEach(([h, d], i) => {
    const y = 1.75 + i * 1.12
    dot(s, 8.75, y, i + 1, i === 3 ? C.coral : C.teal, 0.45)
    T(s, h, { x: 9.4, y: y - 0.02, w: 3.4, h: 0.35, fontSize: 15, bold: true })
    T(s, d, { x: 9.4, y: y + 0.33, w: 3.4, h: 0.7, fontSize: 12, color: C.mute })
  })
  page(s, n)
  s.addNotes('Demo: click Random call on the Ambulance page. Show the unit moving, then the toast when the crew leaves the scene, then approve the bay before the patient arrives.')
}

// 12 ─ digital twin -------------------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.white }
  title(s, 'Hospital digital twin: decisions before the pressure arrives', 'Monte-Carlo simulation starting from the live hospital state — and it recommends what to do')
  shot(s, S('twin'), 0.5, 1.55, 7.6, 5.7)
  const rows = [
    ['ED boarding', `${TW.baseline.boarding_patient_hours.toFixed(0)} → ${TW.surge.boarding_patient_hours.toFixed(0)} patient-hours`],
    ['ED saturated', `${TW.baseline.ed_saturated_hours.toFixed(0)} → ${TW.surge.ed_saturated_hours.toFixed(0)} hours`],
    ['Electives cancelled', `${TW.baseline.electives_cancelled.toFixed(0)} → ${TW.surge.electives_cancelled.toFixed(0)}`],
    ['Best single lever', `${TW.recommendations[0].title} (−${Math.round(TW.recommendations[0].impact * 100)}% pressure)`],
  ]
  T(s, 'Baseline vs +50% ED arrivals (72 h)', { x: 8.35, y: 1.7, w: 4.5, h: 0.4, fontSize: 15, bold: true, color: C.teal })
  rows.forEach(([h, d], i) => {
    const y = 2.2 + i * 1.15
    card(s, 8.35, y, 4.45, 1.0, i === 3 ? C.mint : C.white)
    T(s, h, { x: 8.55, y: y + 0.12, w: 4.1, h: 0.3, fontSize: 12.5, color: C.mute })
    T(s, d, { x: 8.55, y: y + 0.44, w: 4.1, h: 0.45, fontSize: 15, bold: true, color: C.ink })
  })
  bulletList(s, ['Same random streams for both runs → the difference is the scenario, not noise',
    `${TW.replications} replications in ${(TW.wall_ms / 1000).toFixed(1)} s — interactive`], { x: 8.35, y: 6.85, w: 4.5, h: 0.6, fontSize: 11.5 })
  page(s, n)
  s.addNotes('Presets: dengue surge, mass-casualty incident, nursing absence, ICU closure. Each recommendation can be applied in the twin and re-run, so the panel answers "what should we do", not just "what will happen".')
}

// 13 ─ billing & insurance ------------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.bg }
  title(s, 'Closing the financial loop', 'Charges captured from clinical activity · PM-JAY and insurer packages · claims and clearance at discharge')
  shot(s, S('billing'), 0.5, 1.6, 8.0, 5.6)
  const big = [
    [inr(BIL.gross_billed), `billed across ${BIL.invoices} open episodes`],
    [inr(BIL.outstanding), 'patient share still to collect'],
    [inr(BIL.pmjay_adjustments), 'PM-JAY package adjustment'],
    [`${BIL.payer_mix.pmjay} / ${BIL.payer_mix.private} / ${BIL.payer_mix.self}`, 'PM-JAY / insured / self-pay patients'],
  ]
  big.forEach(([v, l], i) => {
    const y = 1.7 + i * 1.4
    card(s, 8.85, y, 3.95, 1.22, i === 2 ? C.mint : C.white)
    T(s, v, { x: 9.05, y: y + 0.12, w: 3.6, h: 0.6, fontFace: HEAD, fontSize: 24, bold: true, color: C.teal })
    T(s, l, { x: 9.05, y: y + 0.74, w: 3.6, h: 0.4, fontSize: 12, color: C.mute })
  })
  page(s, n)
  s.addNotes('Charges carry a stable reference, so re-syncing updates bed-days without duplicating lines. Cost estimates use the P10/P50/P90 stay from the LOS model. On discharge the invoice is finalised and the PM-JAY claim filed automatically.')
}

// 14 ─ copilot, monitor, documentation -------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.white }
  title(s, 'Built for the ward, not just the dashboard', 'Hinglish copilot · ICU central monitor with smart alarms · AI-drafted notes and SBAR handover')
  shot(s, S('copilot'), 0.5, 1.55, 6.1, 3.0)
  shot(s, S('monitor'), 6.8, 1.55, 6.0, 3.0)
  const cards = [
    ['Copilot', '“ICU mein kitne bed khali hain?” — Hinglish understood, the patient under discussion remembered, and it asks *which patient* when unsure'],
    ['Smart alarms', 'A breach must persist for 3 readings before it alarms — transient artefacts are suppressed and counted'],
    ['Documentation', 'SOAP note drafted from the chart (clinician edits and signs) and SBAR handover for every bed in the ward'],
  ]
  cards.forEach(([h, d], i) => {
    const x = 0.5 + i * 4.16
    card(s, x, 4.8, 3.95, 2.35)
    dot(s, x + 0.25, 5.02, i + 1)
    T(s, h, { x: x + 0.95, y: 5.05, w: 2.8, h: 0.4, fontSize: 17, bold: true })
    T(s, d, { x: x + 0.25, y: 5.68, w: 3.5, h: 1.35, fontSize: 12.5, color: C.mute })
  })
  page(s, n)
  s.addNotes('These are the features clinicians actually touch during a shift. Mention that the copilot is available on every page and that approvals can be decided inside the chat.')
}

// 15 ─ governance ---------------------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.bg }
  title(s, 'Governance: how do we know the AI is supervised?', 'Oversight metrics and honest model cards, visible inside the product')
  shot(s, S('governance'), 0.5, 1.6, 7.7, 5.6)
  const items = [
    ['Human oversight', 'Approval, modification and rejection rates, median decision time, autonomy ratio, and which fields humans changed'],
    ['Model cards', `Intent classifier ${(CARD.cv_accuracy * 100).toFixed(0)}% leakage-free cross-validation and ${(CARD.held_out_accuracy * 100).toFixed(0)}% held-out (incl. Hinglish); LOS MAE ${M.los.mae_days} d vs ${M.los.baseline_mae_days} d naïve; readmission AUC ${V2.readmission.auc} with a fairness check`],
    ['Safety & privacy', 'Contraindicated prescriptions blocked; record-access log visible to patients; login lock-out and security headers'],
  ]
  items.forEach(([h, d], i) => {
    const y = 1.7 + i * 1.85
    card(s, 8.45, y, 4.35, 1.65, i === 1 ? C.mint : C.white)
    T(s, h, { x: 8.65, y: y + 0.12, w: 4, h: 0.35, fontSize: 15, bold: true, color: C.teal })
    T(s, d, { x: 8.65, y: y + 0.5, w: 4, h: 1.05, fontSize: 11.5, color: C.ink })
  })
  page(s, n)
  s.addNotes('This slide usually answers the examiner question about trust: we report leakage-free validation, not training accuracy, and we show how often a human disagreed with the system.')
}

// 16 ─ results: big numbers -----------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.white }
  title(s, 'Results', 'Measured on the synthetic 108-bed hospital')
  const big = [
    [`${(M.nlp.accuracy * 100).toFixed(1)}%`, `intent accuracy on held-out requests (${(CARD.cv_accuracy * 100).toFixed(0)}% cross-validated)`],
    [`${M.forecast.metrics.bed_occupancy.mape}%`, `bed-occupancy forecast MAPE (naive: ${M.forecast.metrics.bed_occupancy.naive_seasonal_mape}%)`],
    [`−${Math.round((1 - M.los.mae_days / M.los.baseline_mae_days) * 100)}%`, `length-of-stay error vs baseline (MAE ${M.los.mae_days} d)`],
    [`${(M.roster.wall_ms / 1000).toFixed(1)} s`, `optimal 7-day roster for ${M.roster.staff} staff`],
    [`${V2.tests} / ${V2.tests}`, 'automated tests passing'],
    [`${(TW.wall_ms / 1000).toFixed(1)} s`, `digital twin: ${TW.replications} replications × 2 scenarios`],
  ]
  big.forEach(([v, l], i) => {
    const col = i % 3, row = Math.floor(i / 3)
    const x = 0.6 + col * 4.1, y = 1.75 + row * 2.7
    card(s, x, y, 3.85, 2.45, i === 0 ? C.mint : C.white)
    T(s, v, { x: x + 0.3, y: y + 0.35, w: 3.3, h: 1.0, fontFace: HEAD, fontSize: 44, bold: true, color: i === 2 ? C.coral : C.teal })
    T(s, l, { x: x + 0.3, y: y + 1.45, w: 3.3, h: 0.8, fontSize: 14, color: C.mute })
  })
  page(s, n)
  s.addNotes('All numbers are produced by our evaluation script on the synthetic data. They demonstrate correctness and feasibility; clinical effectiveness would need a real hospital study.')
}

// 12 ─ chart: forecast accuracy --------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.bg }
  title(s, 'Forecasting accuracy', 'Holt-Winters vs. seasonal-naive baseline — 14-day hold-out MAPE, reported as measured (lower is better)')
  const keys = ['admissions', 'er_visits', 'opd_visits', 'bed_occupancy', 'icu_occupancy']
  const labels = ['Admissions', 'ER visits', 'OPD visits', 'Bed occupancy', 'ICU occupancy']
  card(s, 0.5, 1.6, 8.2, 5.6)
  s.addChart(pres.charts.BAR, [
    { name: 'Holt-Winters', labels, values: keys.map((k) => M.forecast.metrics[k].mape) },
    { name: 'Seasonal naive', labels, values: keys.map((k) => M.forecast.metrics[k].naive_seasonal_mape) },
  ], {
    x: 0.7, y: 1.8, w: 7.8, h: 5.2, barDir: 'col', barGrouping: 'clustered', chartColors: [C.teal, 'B6C6C3'],
    showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 11, dataLabelColor: C.ink, dataLabelFormatCode: '0.0"%"',
    showLegend: true, legendPos: 'b', legendFontSize: 12, catAxisLabelColor: C.ink, catAxisLabelFontSize: 12, valAxisLabelColor: C.mute,
    valAxisLabelFormatCode: '0"%"', valGridLine: { color: 'E5E7EB', size: 0.5 }, catGridLine: { style: 'none' },
    showTitle: true, title: 'MAPE by metric', titleFontSize: 14, titleColor: C.ink,
  })
  bulletList(s, [
    `Better than the seasonal-naive baseline on 4 of 5 series (admissions, the noisiest, is the exception)`,
    'Weekly pattern (Monday peak, Sunday low) captured automatically',
    `Length-of-stay model: MAE ${M.los.mae_days} d vs ${M.los.baseline_mae_days} d baseline, R² ${M.los.r2}`,
    `80% interval coverage ${(M.los.interval_coverage * 100).toFixed(0)}% — honest uncertainty`,
  ], { x: 9.1, y: 1.9, w: 3.8, h: 5, fontSize: 15 })
  page(s, n)
  s.addNotes('Forecasts feed the Resource Optimization Agent: peak days and ICU occupancy above 90% trigger recommendations such as pre-emptive discharges. Be upfront that the naive baseline is slightly better on daily admissions — the noisiest series — and that we report it as measured.')
}

// 13 ─ screens gallery -----------------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.white }
  title(s, 'One platform, every role', `${V2.screens} screens — role dashboards, clinical workflows, pre-hospital, finance, analytics, public screens and a patient app`)
  const g = [['g_inpatients', 'Inpatients & early warning'], ['handover', 'SBAR shift handover'], ['g_analytics', 'Forecasts & ML model'], ['portal', 'Patient portal: bill & access log']]
  g.forEach(([f, l], i) => {
    const col = i % 2, row = Math.floor(i / 2)
    const x = 0.6 + col * 6.2, y = 1.55 + row * 2.9
    shot(s, S(f), x, y, 5.9, 2.5)
    T(s, l, { x, y: y + 2.52, w: 5.9, h: 0.32, fontSize: 13, bold: true, color: C.teal, align: 'center' })
  })
  page(s, n)
  s.addNotes('Mention Ctrl+K global search, voice input in the console, printable discharge summaries and the installable PWA.')
}

// 14 ─ tech & testing -------------------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.bg }
  title(s, 'Technology and quality', 'Open-source stack, reproducible deployment, automated tests')
  const stack = [['Frontend', 'React 19 · TypeScript · Vite · Tailwind · Recharts · PWA'], ['Backend', 'Python 3.11 · FastAPI · Pydantic · WebSockets'],
    ['AI / optimisation', 'scikit-learn · OR-Tools CP-SAT · NumPy · optional Claude'], ['Data', 'SQLAlchemy · SQLite · PostgreSQL'],
    ['Security', 'JWT · PBKDF2 · RBAC · lock-out · security headers · audit log'], ['Deployment', 'Docker Compose · Nginx · GitHub Actions CI · one-click start.bat']]
  stack.forEach(([h, d], i) => {
    const y = 1.7 + i * 0.88
    card(s, 0.6, y, 6.6, 0.74)
    T(s, h, { x: 0.85, y: y + 0.2, w: 1.9, h: 0.35, fontSize: 14, bold: true, color: C.teal })
    T(s, d, { x: 2.8, y: y + 0.2, w: 4.3, h: 0.35, fontSize: 13, color: C.ink })
  })
  card(s, 7.6, 1.7, 5.2, 5.2, C.white)
  T(s, `${V2.tests} / ${V2.tests}`, { x: 7.9, y: 1.95, w: 4.6, h: 1.0, fontFace: HEAD, fontSize: 48, bold: true, color: C.teal })
  T(s, 'automated tests passing', { x: 7.9, y: 2.95, w: 4.6, h: 0.4, fontSize: 15, color: C.mute })
  bulletList(s, ['Unit tests: NEWS2, triage, NLP, optimisers, queueing, forecasting, readmission, smart alarms',
    'Integration tests: agent workflows, approvals and rollbacks, billing and claims, ambulance pre-arrival, digital twin, copilot, security',
    'GitHub Actions CI: tests + TypeScript type-check + production build on every push',
    'End-to-end scenarios verified in the browser'], { x: 7.9, y: 3.6, w: 4.7, h: 3.2, fontSize: 13 })
  page(s, n)
  s.addNotes('Tests run in about 15 seconds with a fresh database. Integration tests cover the complete human-in-the-loop flow including rollback on rejection.')
}

// 15 ─ conclusion & future ---------------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.white }
  title(s, 'Conclusion and future scope')
  card(s, 0.6, 1.4, 6.0, 4.1, C.mint)
  T(s, 'What we achieved', { x: 0.9, y: 1.6, w: 5.4, h: 0.45, fontSize: 19, bold: true, color: C.teal })
  bulletList(s, [
    'All 12 synopsis modules working end-to-end',
    'Eleven cooperating agents with explainable recommendations',
    'Safe by design: risk-tiered human approval, full audit, governance dashboard',
    'Beyond the synopsis: 108 pre-hospital coordination, billing & PM-JAY claims, digital twin, ICU monitor, copilot, public screens',
    'Runs offline; one-click start; Docker-ready; CI on every push',
  ], { x: 0.9, y: 2.2, w: 5.5, h: 3.2, fontSize: 15 })
  card(s, 6.9, 1.4, 5.9, 4.1)
  T(s, 'Next steps', { x: 7.2, y: 1.6, w: 5.3, h: 0.45, fontSize: 19, bold: true, color: C.teal })
  bulletList(s, [
    'HL7 FHIR / ABDM integration and real PM-JAY claim submission',
    'IoT smart beds and monitors feeding early warning',
    'Retrain and recalibrate the models on real hospital data',
    'Multi-hospital referral coordination',
    'Full Hindi and regional-language interface (copilot already understands Hinglish)',
  ], { x: 7.2, y: 2.2, w: 5.4, h: 3.2, fontSize: 15 })
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 5.85, w: 12.2, h: 1.0, rectRadius: 0.08, fill: { color: C.dark }, line: { color: C.dark } })
  T(s, 'AI coordinates, optimises and explains — qualified clinicians make the decisions.', { x: 0.9, y: 5.85, w: 11.6, h: 1.0, fontFace: HEAD, fontSize: 22, italic: true, color: C.white, align: 'center', valign: 'middle' })
  page(s, n)
  s.addNotes('Close with the limitation: data is synthetic and integrations are simulated; clinical validation is the next step.')
}

// 16 ─ thank you -------------------------------------------------------------------
{
  const s = pres.addSlide(); n++
  s.background = { color: C.dark }
  s.addImage({ path: ICON, x: 6.17, y: 1.5, w: 1.0, h: 1.0 })
  T(s, 'Thank you', { x: 1, y: 2.8, w: 11.33, h: 1.0, fontFace: HEAD, fontSize: 48, bold: true, color: C.white, align: 'center' })
  T(s, 'Questions & live demo', { x: 1, y: 3.9, w: 11.33, h: 0.5, fontSize: 20, color: C.sea, align: 'center', italic: true })
  T(s, 'Demo login: admin / admin123  ·  doctor / doctor123  ·  nurse / nurse123  ·  patient / patient123', { x: 1, y: 5.2, w: 11.33, h: 0.4, fontSize: 14, color: 'C9D6D4', align: 'center' })
  s.addNotes('Keep the app running before the viva: start.bat, then log in as admin.')
}

pres.writeFile({ fileName: OUT }).then(() => console.log('written', OUT, n, 'slides'))
