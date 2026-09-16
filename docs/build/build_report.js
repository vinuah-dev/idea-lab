// Generates the MedOrchestra project report (.docx) with docx-js.
const fs = require('fs')
const path = require('path')
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell, WidthType, ShadingType,
  ImageRun, TableOfContents, Footer, Header, PageNumber, NumberFormat, LevelFormat, BorderStyle, VerticalAlign,
} = require('docx')

const M = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'metrics.json'), 'utf8'))
const OUT = process.argv[2] || path.join(__dirname, 'MedOrchestra_Project_Report.docx')
const FONT = 'Times New Roman'
const TEAL = '0F5C54'
const CONTENT_W = 9026 // A4 width 11906 − 2×1440 margins (DXA)

let chapter = 0, section = 0, figN = 0, tabN = 0

// ------------------------------------------------------------------ helpers
function runs(text, base = {}) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map((s) => {
    if (s.startsWith('**')) return new TextRun({ text: s.slice(2, -2), bold: true, ...base })
    if (s.startsWith('`')) return new TextRun({ text: s.slice(1, -1), font: 'Consolas', size: 20, ...base })
    return new TextRun({ text: s, ...base })
  })
}
const P = (t, opts = {}) => new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { after: 120, line: 360 }, ...opts, children: runs(t) })
const C = (t, size = 24, bold = false, after = 120) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after }, children: [new TextRun({ text: t, size, bold })] })
const blank = (n = 1) => Array.from({ length: n }, () => new Paragraph({ children: [] }))

function H1(title) {
  chapter += 1; section = 0; figN = 0; tabN = 0
  return new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun(`Chapter ${chapter}: ${title}`)] })
}
function H1u(title) { // unnumbered chapter-level heading (references, appendices, front matter)
  return new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun(title)] })
}
function H2(title) {
  section += 1
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(`${chapter}.${section} ${title}`)] })
}
const H3 = (title) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(title)] })

const bullets = (items, ref = 'bul') => items.map((t) => new Paragraph({ numbering: { reference: ref, level: 0 }, alignment: AlignmentType.JUSTIFIED, spacing: { after: 60, line: 320 }, children: runs(t) }))
const numbered = (items) => bullets(items, 'num')

function code(lines) {
  return lines.map((l, i) => new Paragraph({
    spacing: { after: 0, line: 240 }, shading: { type: ShadingType.CLEAR, fill: 'F1F5F9', color: 'auto' },
    border: i === 0 ? { top: { style: BorderStyle.SINGLE, size: 4, color: 'CBD5E1' } } : i === lines.length - 1 ? { bottom: { style: BorderStyle.SINGLE, size: 4, color: 'CBD5E1' } } : {},
    children: [new TextRun({ text: l || ' ', font: 'Consolas', size: 18 })],
  }))
}
const eq = (t) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 120 }, children: [new TextRun({ text: t, italics: true, font: 'Cambria Math', size: 22 })] })

function cell(text, width, { header = false, fill, align = AlignmentType.LEFT } = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER,
    shading: header ? { type: ShadingType.CLEAR, fill: TEAL, color: 'auto' } : fill ? { type: ShadingType.CLEAR, fill, color: 'auto' } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: String(text).split('\n').map((line) => new Paragraph({ alignment: align, spacing: { after: 0, line: 260 },
      children: runs(line, { size: 20, ...(header ? { bold: true, color: 'FFFFFF' } : {}) }) })),
  })
}
function table(headers, rows, rel, caption) {
  tabN += 1
  const total = rel.reduce((a, b) => a + b, 0)
  const widths = rel.map((r) => Math.floor((r / total) * CONTENT_W))
  widths[widths.length - 1] += CONTENT_W - widths.reduce((a, b) => a + b, 0)
  const cap = new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 160, after: 80 }, keepNext: true,
    children: [new TextRun({ text: `Table ${chapter}.${tabN}: ${caption}`, bold: true, size: 20 })] })
  const t = new Table({
    width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, widths[i], { header: true })) }),
      ...rows.map((r, ri) => new TableRow({ children: r.map((v, i) => cell(v, widths[i], { fill: ri % 2 ? 'F4F8F7' : undefined })) })),
    ],
  })
  return [cap, t, new Paragraph({ spacing: { after: 120 }, children: [] })]
}

function pngSize(file) {
  const b = fs.readFileSync(file)
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20), data: b }
}
function fig(file, caption, maxW = 600, maxH = 790) {
  figN += 1
  const { w, h, data } = pngSize(file)
  let dw = maxW, dh = (h / w) * maxW
  if (dh > maxH) { dh = maxH; dw = (w / h) * maxH }
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 }, keepNext: true,
      children: [new ImageRun({ type: 'png', data, transformation: { width: Math.round(dw), height: Math.round(dh) },
        altText: { title: caption, description: caption, name: path.basename(file) } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [new TextRun({ text: `Figure ${chapter}.${figN}: ${caption}`, italics: true, size: 20 })] }),
  ]
}
const F = (n) => path.join(__dirname, `fig_${n}.png`)
const S = (n) => path.join(__dirname, 'shots', `${n}.png`)

// ------------------------------------------------------------------ metrics
const nlp = M.nlp, fc = M.forecast.metrics, los = M.los, ro = M.roster, bd = M.beds, ot = M.ot, cnt = M.counts
const v2 = M.v2, tw = M.v2.twin, bil = M.v2.billing, card = M.v2.nlp_card, rdm = M.v2.readmission
const pct = (v) => `${(v * 100).toFixed(1)}%`

// ------------------------------------------------------------------ front matter
const titlePage = [
  ...blank(2),
  C('A PROJECT REPORT', 28, true, 200),
  C('on', 24, false, 200),
  C('MULTI-AGENT AI SYSTEMS FOR HOSPITAL RESOURCE OPTIMIZATION,', 30, true, 60),
  C('CLINICAL WORKFLOW AUTOMATION, AND PATIENT CARE COORDINATION', 30, true, 240),
  C('(MedOrchestra — Multi-Agent Hospital Intelligence Platform)', 24, false, 480),
  C('Submitted in partial fulfilment of the requirements for the award of the degree of', 22, false, 80),
  C('_______________________________________________', 24, true, 480),
  C('Submitted by', 22, false, 60),
  C('Name: ______________________    Roll No.: ____________', 24, true, 60),
  C('Name: ______________________    Roll No.: ____________', 24, true, 360),
  C('Under the guidance of', 22, false, 60),
  C('_____________________________', 24, true, 480),
  C('Department of ____________________________', 24, false, 60),
  C('_______________________________ (Institute)', 24, false, 60),
  C('Academic Year 2026 – 2027', 24, false, 60),
]

const certificate = [
  H1u('Certificate'),
  P('This is to certify that the project report entitled **“Multi-Agent AI Systems for Hospital Resource Optimization, Clinical Workflow Automation, and Patient Care Coordination”** is a bonafide record of the work carried out by ______________________ (Roll No. __________) and ______________________ (Roll No. __________) under my supervision and guidance, in partial fulfilment of the requirements for the award of the degree of ________________________ of ________________________ during the academic year 2026–2027.'),
  P('The work embodied in this report has not been submitted elsewhere for the award of any other degree or diploma.'),
  ...blank(4),
  new Paragraph({ children: [new TextRun({ text: '__________________________\t\t\t\t__________________________' })] }),
  new Paragraph({ children: [new TextRun({ text: 'Project Guide\t\t\t\t\t\tHead of the Department' })] }),
  ...blank(3),
  new Paragraph({ children: [new TextRun({ text: 'External Examiner: __________________________        Date: ____________' })] }),
]

const declaration = [
  H1u('Declaration'),
  P('We hereby declare that the project work entitled **“Multi-Agent AI Systems for Hospital Resource Optimization, Clinical Workflow Automation, and Patient Care Coordination”** submitted to ________________________ is a record of original work done by us under the guidance of ______________________. The results embodied in this report have not been submitted to any other university or institute for the award of any degree or diploma. Wherever we have used the work of others, it has been duly acknowledged and referenced.'),
  ...blank(3),
  new Paragraph({ children: [new TextRun('Place: ______________')] }),
  new Paragraph({ children: [new TextRun('Date: ______________\t\t\t\t\tSignature(s) of the student(s)')] }),
]

const acknowledgement = [
  H1u('Acknowledgement'),
  P('We express our sincere gratitude to our project guide, ______________________, for the constant guidance, encouragement and valuable feedback throughout this project. We are thankful to the Head of the Department, ______________________, and to all faculty members of the Department of ______________________ for providing the facilities and support needed to complete this work.'),
  P('We also thank the doctors and nursing staff whose descriptions of everyday hospital workflows — admissions, triage, bed turnover, theatre lists and ward rounds — helped us understand the real problems this system tries to address. Finally, we thank our families and friends for their continuous support and motivation.'),
]

const abstract = [
  H1u('Abstract'),
  P('Hospitals coordinate beds, intensive-care units, operating theatres, doctors, nurses, diagnostics and pharmacy through disconnected systems, telephone calls and spreadsheets. The result is poor resource utilisation, long waiting times, scheduling conflicts and delayed escalation of deteriorating patients. This project designs and implements **MedOrchestra**, a multi-agent artificial-intelligence platform for hospital resource optimisation, clinical workflow automation and patient-care coordination.'),
  P(`Instead of a single AI model, ${v2.agents} specialised agents — Bed Management, Appointment & Queue, Staff Scheduling, Diagnostic Coordination, Pharmacy, Patient Care Coordinator, Emergency Support, Resource Optimization, Billing & Insurance, Ambulance Dispatch and Notification — are coordinated by a central orchestrator. A natural-language request, in English or in Romanised Hindi (Hinglish), is classified into one or more of ${nlp.intents} operational intents, converted into a dependency-ordered plan, and executed by agents that share a blackboard and exchange FIPA-ACL-style messages. Decisions are powered by established techniques: Google OR-Tools CP-SAT constraint optimisation for bed allocation, staff rostering and theatre scheduling; the National Early Warning Score 2 (NEWS2) for triage and ward deterioration; M/M/c queueing theory for waiting-time prediction; Holt-Winters exponential smoothing for demand forecasting; a Gradient-Boosting model with quantile intervals for length-of-stay prediction, the LACE index with logistic regression for 30-day readmission risk, and a Monte-Carlo discrete-event **digital twin** of the hospital for capacity what-if analysis.`),
  P('The platform goes beyond the ward walls: a pre-hospital module dispatches the nearest capable ambulance and alerts the emergency department while the patient is still in transit, so that a bay and a team are ready on arrival; a billing module captures charges automatically from clinical activity and maps each stay to an Ayushman Bharat (PM-JAY) or insurer package; and a governance dashboard reports how often humans approved, modified or rejected the AI’s proposals together with honest model cards.'),
  P('Every recommendation carries an explainable factor breakdown. Low-risk, reversible actions execute automatically, while safety-critical actions (admissions, emergency assignments, AI-suggested investigations, contraindicated prescriptions, discharges, surgeries, rosters) are routed to authorised clinicians for approval, modification or rejection under a configurable autonomy policy, keeping humans in control of clinical decisions.'),
  P(`The system is implemented with FastAPI (Python), SQLAlchemy (SQLite/PostgreSQL), React with TypeScript as an installable progressive web app, and WebSockets for live updates; Claude can optionally be used for language understanding. Evaluation on a synthetic ${cnt.beds}-bed hospital shows ${pct(nlp.accuracy)} intent accuracy on held-out requests, a bed-occupancy forecast MAPE of ${fc.bed_occupancy.mape}% (versus ${fc.bed_occupancy.naive_seasonal_mape}% for a seasonal-naive baseline; Holt-Winters is the more accurate of the two on four of the five forecast series), a length-of-stay MAE ${((1 - los.mae_days / los.baseline_mae_days) * 100).toFixed(0)}% lower than a median baseline, a 7-day roster for ${ro.staff} staff solved optimally in ${(ro.wall_ms / 1000).toFixed(1)} s, and theatre re-optimisation that removed all overlaps and ${ot.before.overtime_minutes} minutes of overtime. All ${v2.tests} automated tests pass.`),
  P('**Keywords:** multi-agent systems, hospital management, resource optimisation, constraint programming, NEWS2, human-in-the-loop, explainable AI, clinical workflow automation.'),
]

const abbreviations = [
  H1u('List of Abbreviations'),
  ...table(['Abbreviation', 'Meaning'], [
    ['ACL', 'Agent Communication Language (FIPA)'], ['ACVPU', 'Alert, new Confusion, Voice, Pain, Unresponsive'], ['API', 'Application Programming Interface'],
    ['CP-SAT', 'Constraint Programming – Satisfiability solver (Google OR-Tools)'], ['DAG', 'Directed Acyclic Graph'], ['ED / ER', 'Emergency Department / Emergency Room'],
    ['EHR / HIS', 'Electronic Health Record / Hospital Information System'], ['HDU', 'High Dependency Unit'], ['HITL', 'Human-in-the-Loop'], ['ICU', 'Intensive Care Unit'],
    ['JWT', 'JSON Web Token'], ['LLM', 'Large Language Model'], ['LOS', 'Length of Stay'], ['MAE / MAPE', 'Mean Absolute Error / Mean Absolute Percentage Error'],
    ['NEWS2', 'National Early Warning Score 2'], ['NLP', 'Natural Language Processing'], ['OPD', 'Out-Patient Department'], ['OT', 'Operation Theatre'],
    ['PWA', 'Progressive Web App'], ['RBAC', 'Role-Based Access Control'], ['TAT', 'Turnaround Time'], ['TF-IDF', 'Term Frequency – Inverse Document Frequency'],
  ], [1, 4], 'Abbreviations used in this report'),
]

// ------------------------------------------------------------------ chapter 1
const ch1 = [
  H1('Introduction'),
  H2('Background'),
  P('A hospital is a complex socio-technical system. Patients move between registration, consultation, diagnostics, admission, surgery, intensive care and discharge, while a limited pool of resources — beds, ICU units, operating theatres, ventilators, imaging machines, doctors, nurses and medicines — must be shared among them. In many hospitals these resources and workflows are managed through separate departmental systems, manual communication, spreadsheets and telephone calls. Information about a free ICU bed, an available surgeon or a pending laboratory result often reaches the right person late, or not at all.'),
  P('Artificial intelligence can help, but a single monolithic model is a poor fit for hospital operations: the sub-problems are very different in nature (triage is a clinical scoring problem, rostering is a combinatorial optimisation problem, appointment booking is a search problem, stock management is an inventory problem), and they interact through shared resources. This project therefore adopts a **multi-agent architecture**, in which specialised AI agents each own one operational domain and a central orchestration layer coordinates them toward a common goal.'),
  H2('Motivation'),
  ...bullets([
    'Delays in bed allocation and emergency coordination directly affect patient outcomes; early escalation of deteriorating ward patients saves lives.',
    'Clinicians spend a significant share of their time on coordination work (finding beds, calling departments, chasing results) instead of patient care.',
    'Resources such as ICU beds and theatres are expensive; small improvements in utilisation and scheduling produce large operational gains.',
    'AI systems in healthcare must be explainable, auditable and supervised by qualified professionals — a design requirement rather than an afterthought.',
  ]),
  H2('Problem Statement'),
  P('Hospital operations involve continuous coordination between patients, doctors, nurses, laboratories, pharmacies, administrative staff and infrastructure. When these activities are handled through disconnected systems or manual communication, the following problems arise:'),
  ...bullets([
    '**Fragmented information** — patient data, appointments, bed availability, diagnostics, staff schedules and pharmacy information live in different systems.',
    '**Manual resource allocation** — beds, ICU units, theatres, equipment and staff are allocated by hand, causing inefficiency and conflicts.',
    '**Long patient waiting times** — consultations, diagnostics and departmental workflows are not coordinated.',
    '**Communication gaps** — updates between reception, clinicians, laboratory, pharmacy and billing are delayed or missed.',
    '**Emergency coordination** — high-acuity cases require rapid, simultaneous mobilisation of beds, teams and diagnostics.',
    '**Administrative workload** — scheduling, notifications, status updates and follow-ups are repetitive.',
    '**Lack of predictive planning** — historical data is not used to anticipate demand, staffing needs or bottlenecks.',
  ]),
  P('**Core problem:** there is a need for an intelligent, coordinated system that optimises hospital resources, automates routine workflows and facilitates patient-care coordination through multiple specialised AI agents, while retaining human oversight for critical decisions.'),
  H2('Objectives'),
  ...numbered([
    'Develop a centralised hospital-management platform based on a multi-agent AI architecture.',
    'Create specialised agents for resource management, clinical workflow automation and patient-care coordination.',
    'Optimise allocation of beds, ICU units, doctors, nurses, equipment, diagnostic facilities and operating theatres.',
    'Automate routine workflows such as appointment scheduling, queue management, notifications and follow-ups.',
    'Reduce patient waiting time through cross-department coordination and queue prioritisation.',
    'Provide intelligent support for emergency prioritisation and resource mobilisation.',
    'Analyse historical and real-time data to forecast demand and identify bottlenecks.',
    'Provide role-based dashboards for administrators, doctors, nurses and other personnel, and a patient portal.',
    'Maintain a human-in-the-loop approach so that critical medical decisions remain with qualified professionals.',
    'Provide an extensible architecture that can integrate with existing hospital information systems.',
  ]),
  H2('Scope of the Project'),
  P(`The project delivers a working, end-to-end prototype for a simulated ${cnt.beds}-bed multispeciality hospital (${cnt.patients} patients, ${cnt.staff} staff, ${cnt.resources} items of equipment and 180 days of operational history). It covers the twelve modules proposed in the synopsis — authentication and RBAC, patient management, bed and resource management, appointments and queues, staff scheduling, diagnostics, pharmacy, patient-care coordination, emergency support, AI resource optimisation, notifications and analytics — and extends them with ward early-warning monitoring, operating-theatre scheduling, machine-learning length-of-stay prediction, predictive equipment maintenance, a configurable autonomy policy and, in the second iteration, pre-hospital ambulance coordination, hospital billing with PM-JAY and insurance claims, a Monte-Carlo digital twin for capacity planning, an ICU central monitor, readmission-risk prediction, AI-drafted clinical documentation, public waiting-room screens and an AI-governance dashboard. Integration with real hospital information systems, SMS gateways and IoT devices is represented by interfaces and simulation, and all patient data is synthetic.`),
  H2('Organisation of the Report'),
  P('Chapter 2 reviews the literature on multi-agent systems and AI for hospital operations. Chapter 3 analyses the requirements and feasibility. Chapter 4 presents the system design, including architecture, agent interaction, human-in-the-loop design and database design. Chapter 5 describes the implementation and the algorithms used by each agent. Chapter 6 describes the extended modules — pre-hospital coordination, billing and insurance, the digital twin, monitoring, documentation and governance. Chapter 7 presents the results through screenshots of the working system. Chapter 8 covers testing and quantitative evaluation. Chapter 9 concludes the report and outlines future work.'),
]

// ------------------------------------------------------------------ chapter 2
const ch2 = [
  H1('Literature Survey'),
  H2('Multi-Agent Systems'),
  P('An agent is a computer system situated in an environment that is capable of autonomous action to meet its design objectives; intelligent agents are additionally reactive, proactive and social [1]. A multi-agent system (MAS) consists of several interacting agents, each with incomplete information or capability, whose combined behaviour solves problems beyond any individual agent. MAS research provides two ideas used directly in this project: the **blackboard architecture**, in which independent knowledge sources cooperate by reading and writing a shared data structure under the control of a coordinator [3], and **agent communication languages** such as FIPA-ACL, in which messages carry a performative (inform, request, propose, agree, refuse) that makes the intent of each interaction explicit [2].'),
  H2('AI and Optimisation in Hospital Operations'),
  P('Operational research has a long history in healthcare. Operating-room planning and scheduling alone has a large literature covering case-mix planning, surgeon assignment and daily sequencing under uncertainty [7]. Bed management is usually treated as an assignment problem with hard constraints (bed type, isolation, equipment) and soft preferences (ward speciality, distance, workload). Modern constraint-programming solvers such as Google OR-Tools CP-SAT make it practical to solve realistic instances of these problems in seconds [13], which is why constraint optimisation, rather than a learned model, is used for allocation decisions in this project.'),
  H2('Early Warning and Triage'),
  P('The National Early Warning Score 2 (NEWS2), published by the Royal College of Physicians in 2017, standardises the assessment of acute-illness severity using six physiological parameters plus supplemental oxygen, and prescribes a graded clinical response [4]. NEWS has been shown to discriminate patients at risk of cardiac arrest, unanticipated ICU admission and death within 24 hours [5]. Emergency departments additionally use five-level triage systems such as the Manchester Triage System, which assigns target times to treatment for each priority band [6]. The Emergency Support Agent and the ward early-warning service implement these published rules transparently rather than replacing them with an opaque model.'),
  H2('Queueing Theory in Healthcare'),
  P('Queueing models describe the relationship between arrivals, service capacity and waiting time. The Erlang-C formula for the M/M/c queue, originally derived for telephone exchanges [21], is widely used to size clinics and emergency departments [8], [15]. It shows the strongly non-linear growth of waiting time as utilisation approaches one, which motivates capacity alerts at around 85 % utilisation.'),
  H2('Demand Forecasting'),
  P('Hospital demand (admissions, emergency visits, occupancy) exhibits trend and strong weekly seasonality. Holt-Winters triple exponential smoothing models level, trend and seasonality with three smoothing constants [9], [10]. It is interpretable, needs little data and forecasts reliably over short horizons, making it suitable for operational planning.'),
  H2('Length-of-Stay Prediction'),
  P('Predicting length of stay supports discharge planning and bed-capacity forecasting. A recent systematic review reports that machine-learning methods — particularly tree ensembles — are among the most frequently used and best-performing approaches, while highlighting the need for well-defined evaluation against baselines [12]. Gradient boosting builds an additive ensemble of shallow trees by functional gradient descent [11]; with quantile loss it also yields prediction intervals, which communicate uncertainty to planners.'),
  H2('Large Language Models and Human Oversight'),
  P('Large language models can map free-text requests to structured representations, making systems usable through natural language. However, WHO guidance on AI for health emphasises human autonomy, transparency, accountability and safety [16]. This project therefore uses language models only for understanding and summarisation, constrains their output with a JSON schema, grounds extracted entities against the hospital database, and never lets a model execute safety-critical actions without human approval.'),
  H2('Research Gap'),
  ...table(['Existing approach', 'Limitation', 'How MedOrchestra addresses it'], [
    ['Departmental HIS modules', 'Siloed data; no cross-department coordination', 'Unified data model and an orchestrator that spans departments'],
    ['Stand-alone optimisation tools', 'Solve one problem (e.g. rostering) in isolation', 'Specialised agents share a blackboard; the optimizer reasons about beds, staff and waiting patients jointly'],
    ['Single end-to-end AI model', 'Opaque, hard to validate, mixes unrelated tasks', 'Domain agents using transparent, validated methods; factor-level explanations'],
    ['Fully automated decision systems', 'Unsafe for clinical decisions; poor accountability', 'Risk-tiered human-in-the-loop gate, configurable autonomy, full audit trail'],
    ['Paper-based early warning', 'Late escalation, no link to bed/ICU capacity', 'NEWS2 scoring on every observation with automatic ICU-transfer proposals'],
  ], [2, 2.5, 3.2], 'Gap analysis'),
]

// ------------------------------------------------------------------ chapter 3
const ch3 = [
  H1('System Analysis and Requirements'),
  H2('Existing System'),
  P('In a typical hospital the admitting doctor telephones bed managers to find a free bed, nurses record observations on paper charts, the operation-theatre list is maintained on a whiteboard or spreadsheet, OPD queues are managed by token number only, and pharmacy stock is checked manually. Information is duplicated across departments, there is no single view of hospital capacity, escalation depends on individual vigilance, and decisions are rarely recorded with their rationale.'),
  H2('Proposed System'),
  P('MedOrchestra replaces this with a single platform in which every patient, resource and workflow is linked. Staff interact through role-specific dashboards or simply describe a need in natural language; the orchestrator plans the workflow, the specialised agents evaluate options with appropriate algorithms, explainable recommendations are presented, low-risk actions are executed immediately and critical actions wait for approval by an authorised person. The key features are:'),
  ...bullets([
    'Natural-language AI Agent Console with a live visualisation of agents and a step-by-step trace.',
    'Human-in-the-loop approval queue with approve, reject and approve-with-modification, and three autonomy modes.',
    'Command centre with live KPIs, ward occupancy, emergency board, bottlenecks and role-specific work lists.',
    'Emergency department board with live NEWS2 triage preview and automatic multi-agent coordination.',
    'Inpatient census with bedside observations, NEWS2 trends, observation schedules and automatic ICU-transfer proposals.',
    'Bed, equipment and operation-theatre management, including CP-SAT theatre optimisation and predictive maintenance.',
    'OPD appointments with dynamic priority queues and M/M/c wait prediction; staff rostering with CP-SAT.',
    'Diagnostics and pharmacy workflows with turnaround tracking and drug-safety screening.',
    'Analytics with demand forecasting, length-of-stay model card and agent performance; audit log; patient portal PWA.',
  ]),
  H2('Feasibility Study'),
  H3('Technical feasibility'),
  P('The system uses mature open-source technologies (Python, FastAPI, SQLAlchemy, scikit-learn, OR-Tools, React). All algorithms run on commodity hardware: the largest optimisation problem in the prototype (a 7-day roster for 77 staff) solves in about two seconds on a laptop.'),
  H3('Economic feasibility'),
  P('All core components are free and open source. The optional language-model service is pay-per-use and can be disabled, in which case the local NLP pipeline is used at no cost. Deployment requires a single server or a small container cluster with PostgreSQL.'),
  H3('Operational feasibility'),
  P('The system supports rather than replaces staff. Adoption can start with low-risk workflows (appointments, bed status, notifications) in supervised mode and gradually extend to optimisation and early warning as trust grows. Role-based dashboards keep each user focused on relevant information.'),
  H3('Data and integration feasibility'),
  P('The data model mirrors standard HIS entities, and REST APIs allow integration with existing EHR, laboratory and pharmacy systems. The quality of recommendations depends on timely and accurate data, which is why every recommendation shows the facts it is based on.'),
  H2('Users and Roles'),
  ...table(['Role', 'Main tasks in the system'], [
    ['Administrator', 'Monitor operations, approve rosters and redeployments, set autonomy policy, manage users, review audit log, run simulation'],
    ['Doctor', 'Ask agents, approve admissions, investigations, prescriptions overrides, surgeries and discharges, review patients'],
    ['Nurse', 'Record observations, register emergency cases, update bed status, approve bed placements'],
    ['Receptionist', 'Register patients, manage OPD appointments and queues'],
    ['Lab technician', 'Progress diagnostic orders and report results'],
    ['Pharmacist', 'Verify and dispense prescriptions, manage stock, approve purchase orders'],
    ['Patient', 'View own record, reports and medicines; book appointments through the Appointment Agent'],
  ], [1.2, 5], 'User roles'),
  H2('Functional Requirements'),
  ...table(['ID', 'Requirement'], [
    ['FR-01', 'Users shall authenticate with username and password; access shall be restricted by role.'],
    ['FR-02', 'Staff shall submit operational requests in natural language; the system shall identify intents and entities.'],
    ['FR-03', 'The orchestrator shall select agents, build a dependency-ordered plan and execute it with a live trace.'],
    ['FR-04', 'The system shall recommend beds, staff and equipment with explainable scores and optimise allocation globally.'],
    ['FR-05', 'Safety-critical actions shall require approval by an authorised role; approvers may modify or reject them.'],
    ['FR-06', 'Emergency cases shall be triaged with NEWS2 and red-flag detection and coordinated automatically.'],
    ['FR-07', 'Bedside observations shall be NEWS2-scored and escalated according to the NEWS2 response policy.'],
    ['FR-08', 'The system shall manage OPD appointments, prioritise queues and predict waiting time.'],
    ['FR-09', 'The system shall generate optimised staff rosters and propose redeployments.'],
    ['FR-10', 'The system shall schedule diagnostic tests on appropriate modalities and track turnaround.'],
    ['FR-11', 'The system shall screen prescriptions for allergies, interactions, dose and stock, and plan reorders.'],
    ['FR-12', 'The system shall schedule surgeries in operating theatres without overlap and re-optimise the day.'],
    ['FR-13', 'The system shall track each patient’s care pathway and produce discharge summaries.'],
    ['FR-14', 'The system shall send role-based notifications in real time.'],
    ['FR-15', 'The system shall forecast demand, predict length of stay and detect bottlenecks.'],
    ['FR-16', 'All user decisions and agent actions shall be recorded in an audit log.'],
    ['FR-17', 'Patients shall view their record and book appointments through a portal.'],
    ['FR-18', 'Administrators shall manage users and the autonomy policy.'],
  ], [0.8, 6], 'Functional requirements'),
  H2('Non-Functional Requirements'),
  ...table(['Category', 'Requirement'], [
    ['Security', 'JWT authentication, PBKDF2-SHA256 password hashing, server-side RBAC on every endpoint, audit logging'],
    ['Safety', 'No safety-critical action without human approval (except under an explicitly configured policy); rejections roll back holds'],
    ['Performance', 'Interactive API responses under 1 s; typical multi-agent orchestration completes in a few seconds'],
    ['Usability', 'Role-specific dashboards, natural-language input, explanations, global search, responsive/PWA interface'],
    ['Reliability', 'Agent failures are isolated; LLM failures fall back to local NLP; allocation transactions are serialised'],
    ['Maintainability', 'Modular agents and services, typed API, automated tests'],
    ['Portability', 'Runs on Windows/Linux/macOS; SQLite for development, PostgreSQL in Docker for production'],
  ], [1.3, 5], 'Non-functional requirements'),
  H2('Hardware and Software Requirements'),
  ...table(['Item', 'Minimum specification'], [
    ['Processor / RAM', 'Dual-core 2 GHz / 4 GB (8 GB recommended)'], ['Storage', '1 GB free disk space'],
    ['Operating system', 'Windows 10/11, Linux or macOS'], ['Runtime', 'Python 3.10+ and Node.js 18+'],
    ['Database', 'SQLite (bundled) or PostgreSQL 16'], ['Browser', 'Any modern browser (Chrome, Edge, Firefox, Safari)'],
    ['Optional', 'Docker Desktop; Anthropic API key for Claude-based understanding'],
  ], [1.5, 4], 'Hardware and software requirements'),
]

// ------------------------------------------------------------------ chapter 4
const ch4 = [
  H1('System Design'),
  H2('System Architecture'),
  P('The system follows the layered architecture proposed in the synopsis (Figure 4.1). Requests flow from the client layer through the application layer to the AI orchestration layer, which coordinates the specialised agents; agents use shared hospital services and algorithms and persist state in the data layer. Events flow back to all connected clients over a WebSocket bus.'),
  ...fig(F('arch'), 'Layered system architecture', 560, 560),
  ...bullets([
    '**Client layer** — a React/TypeScript single-page application with role-based dashboards, the AI Agent Console and the patient portal, installable as a PWA.',
    '**Application layer** — FastAPI REST gateway with JWT authentication, role-based access control and a WebSocket event bus.',
    '**AI orchestration layer** — NLP understanding, planning, blackboard-based execution, conflict resolution and the human-in-the-loop gate.',
    '**Specialised agents** — nine domain agents that evaluate options and propose actions.',
    '**Services & algorithms** — optimisation, triage, queueing, forecasting, machine learning, clinical knowledge base, audit and notifications.',
    '**Integration & data layers** — adapters for external systems and a relational database.',
  ]),
  H2('Multi-Agent Orchestration Pipeline'),
  P('Every request passes through the ten-step pipeline defined in the synopsis (Figure 4.2, Table 4.1).'),
  ...fig(F('pipeline'), 'Orchestration pipeline (synopsis steps i–x)', 600, 200),
  ...table(['Step', 'Synopsis stage', 'Implementation'], [
    ['i', 'Request intake', 'AgentRequest record; sources: console, emergency desk, patient portal, early-warning service, simulator'],
    ['ii', 'NLP and classification', 'TF-IDF + logistic regression (or Claude with JSON schema) → intents; regex and database-grounded entity extraction'],
    ['iii', 'Workflow identification', 'Each intent maps to a workflow template of agent steps'],
    ['iv', 'Agent selection', 'Templates are merged, de-duplicated and ordered topologically into dependency levels'],
    ['v', 'Coordination', 'Agents run level by level, post findings to the blackboard and exchange FIPA-ACL messages'],
    ['vi', 'Constraint analysis', 'CP-SAT allocation, exclusion of held resources, conflict detection and resolution'],
    ['vii', 'Recommendations', 'Recommendation and ProposedAction objects with factor-level explanations'],
    ['viii', 'Human approval', 'Autonomy policy decides which actions need approval; approvals routed to authorised roles'],
    ['ix', 'Execution', 'Executor applies approved or low-risk actions transactionally'],
    ['x', 'Logging & monitoring', 'Trace, audit log, notifications, live WebSocket updates and a coordination brief'],
  ], [0.5, 1.5, 5], 'Pipeline steps and their implementation'),
  H2('Agent Catalogue'),
  ...table(['Agent', 'Responsibility', 'Key techniques', 'Typical actions'], [
    ['Bed Management', 'Real-time bed tracking and matching', 'Hard/soft constraint scoring, held-bed exclusion, portable-equipment pairing', 'Reserve bed'],
    ['Appointment & Queue', 'Slots, queues, waiting time', 'Slot search, ageing priority, M/M/c Erlang-C', 'Book appointment'],
    ['Staff Scheduling', 'Doctor/nurse matching, rosters', 'Skill/workload scoring, CP-SAT rostering', 'Publish roster, redeploy staff'],
    ['Diagnostic Coordination', 'Tests and modalities', 'Protocol workups, least-loaded modality scheduling, TAT tracking', 'Create diagnostic orders'],
    ['Pharmacy', 'Medication safety and stock', 'Allergy cross-reactivity, interaction and dose rules, reorder quantity', 'Create prescription, purchase order'],
    ['Patient Care Coordinator', 'Patient identity and journey', 'Care pathways, readiness scoring', 'Create pathway, discharge'],
    ['Emergency Support', 'Triage and mobilisation', 'NEWS2, red-flag detection, surge detection', 'Assign ER bay and team'],
    ['Resource Optimization', 'Global allocation and planning', 'CP-SAT bed & theatre optimisation, Holt-Winters, GBM LOS', 'Admit/transfer, book surgery, apply schedules'],
    ['Notification', 'Communication', 'Role/user routing, channel selection', 'Alerts, approval requests, patient SMS'],
  ], [1.4, 1.6, 2.4, 1.6], 'Specialised agents'),
  H2('Agent Interaction'),
  P('Figure 4.3 shows the interaction for the synopsis example “Patient needs admission and requires ICU monitoring”. The orchestrator identifies the admission intent and the ICU/ventilator requirement, the Patient Care Agent resolves (or provisionally registers) the patient, the Bed and Staff agents propose candidates to the Resource Optimizer, which solves the joint allocation while considering patients already waiting, and the Notification Agent requests approval from a doctor.'),
  ...fig(F('sequence'), 'Sequence diagram for an ICU admission request', 560, 560),
  H2('Human-in-the-Loop Design'),
  P('Agents only propose actions. The orchestrator applies the configured autonomy policy to every proposal (Figure 4.4). Reversible, low-risk actions such as holding a bed or booking an appointment execute immediately in the default balanced mode; actions that affect clinical care require approval from the roles listed in Table 4.4. Approvers can modify the AI’s choice (bed, doctor, time, dose) before approving; rejecting releases held resources and cancels pending tasks.'),
  ...fig(F('hitl'), 'Human-in-the-loop decision gate', 300, 560),
  ...table(['Action', 'Risk', 'Balanced mode', 'Approver roles'], [
    ['Hold a bed', 'Low', 'Automatic', '—'], ['Book OPD appointment', 'Low', 'Automatic', '—'],
    ['Admit / transfer patient', 'Medium–High', 'Approval', 'Doctor, Admin'], ['Assign ER bay and team', 'High–Critical', 'Approval', 'Doctor, Admin'],
    ['Investigations requested by a prescriber', 'Low', 'Automatic', '—'], ['AI-suggested protocol workup', 'Medium', 'Approval', 'Doctor, Admin'],
    ['Prescription with major/contraindicated alert', 'High–Critical', 'Approval (override)', 'Doctor, Admin'], ['Purchase order', 'Low', 'Approval', 'Pharmacist, Doctor, Admin'],
    ['Book surgery / apply theatre schedule', 'Medium–High', 'Approval', 'Doctor, Admin'], ['Discharge', 'Medium–High', 'Approval', 'Doctor, Admin'],
    ['Roster publication / staff redeployment', 'Medium', 'Approval', 'Admin'], ['Global bed placement', 'Medium', 'Approval', 'Admin, Nurse, Receptionist'],
  ], [2.6, 1.2, 1.4, 1.8], 'Human-in-the-loop policy (balanced mode)'),
  ...table(['Autonomy mode', 'Behaviour'], [
    ['Supervised', 'Every agent action waits for human approval.'],
    ['Balanced (default)', 'Low-risk reversible actions execute automatically; clinical and risky actions need approval.'],
    ['Autonomous', 'Low and medium-risk operational actions execute automatically; high/critical-risk actions, prescribing, discharge, staffing changes and AI-suggested workups still need approval.'],
  ], [1.4, 5], 'Configurable autonomy modes'),
  H2('Ward Early-Warning Escalation'),
  P('Each observation set is scored with NEWS2 and the response prescribed by the Royal College of Physicians is applied (Figure 4.5). A score of seven or more triggers an emergency alert and — for patients outside intensive care — an automatic orchestrator request to transfer the patient to the ICU, which is then planned by the agents and approved by a doctor.'),
  ...fig(F('escalation'), 'NEWS2 escalation workflow', 600, 260),
  H2('Data Flow Diagrams'),
  ...fig(F('dfd0'), 'Context-level (Level 0) data flow diagram', 520, 200),
  ...fig(F('dfd1'), 'Level 1 data flow diagram', 600, 260),
  H2('Use Case Diagram'),
  ...fig(F('usecase'), 'Use cases by actor', 600, 420),
  H2('Database Design'),
  P('The data model links every operational event to a patient, a resource and a workflow (Figure 4.9). Table 4.6 summarises the main tables.'),
  ...fig(F('er'), 'Entity-relationship diagram (main entities)', 600, 400),
  ...table(['Table', 'Purpose'], [
    ['users, departments, staff, shifts', 'Accounts and roles; departments; clinicians with skills, workload and duty status; roster shifts'],
    ['patients', 'Demographics, allergies, conditions, status and clinical risk score'],
    ['wards, beds, resources', 'Wards and beds with type, features and status; theatres and equipment with usage and maintenance data'],
    ['admissions, emergency_cases', 'Inpatient episodes with bed, team, acuity and expected discharge; ED cases with vitals, NEWS2 and triage level'],
    ['appointments, diagnostic_orders, prescriptions, medications', 'OPD bookings and queues; lab/imaging orders and results; prescriptions with safety alerts; formulary and stock'],
    ['vital_signs, surgeries, care_tasks', 'Bedside observations with NEWS2; theatre bookings; care-pathway steps'],
    ['agent_requests, approvals', 'Orchestrated requests with intents, plan, trace, results and conflicts; human-in-the-loop decisions'],
    ['notifications, audit_logs, settings, daily_stats', 'Alerts; audit trail; autonomy policy; historical metrics for analytics and forecasting'],
  ], [2.2, 4.5], 'Database tables'),
  H2('API Design'),
  ...table(['Endpoint group', 'Examples'], [
    ['Authentication & users', 'POST /api/auth/login · GET /api/auth/me · POST /api/auth/change-password · /api/users'],
    ['AI agents & approvals', 'POST /api/agents/requests · GET /api/agents/requests/{id} · GET /api/approvals · POST /api/approvals/{id}/decide'],
    ['Patients & ward', 'GET /api/patients · GET /api/patients/{id} · POST /api/patients/{id}/vitals · GET /api/admissions · GET /api/admissions/{id}/summary'],
    ['Resources & theatres', 'GET /api/wards · PATCH /api/beds/{id} · GET /api/surgeries · GET /api/ot/slots · POST /api/ot/optimize'],
    ['Clinical workflows', '/api/appointments · /api/queue · /api/diagnostics · /api/prescriptions · /api/emergency · /api/emergency/triage-preview'],
    ['Insights & system', '/api/dashboard · /api/dashboard/mywork · /api/analytics/* · /api/search · /api/settings · /api/audit · /api/simulation/*'],
    ['Real time', 'WebSocket /ws?token=… (agent traces, notifications, approvals, refresh events)'],
  ], [1.6, 5], 'REST API overview (interactive documentation at /docs)'),
]

// ------------------------------------------------------------------ chapter 5
const ch5 = [
  H1('Implementation'),
  H2('Technology Stack'),
  ...table(['Layer', 'Technology', 'Purpose'], [
    ['Frontend', 'React 19, TypeScript, Vite, Tailwind CSS v4, Recharts, lucide icons', 'Role-based single-page application and charts'],
    ['Mobile', 'Progressive Web App (manifest, service worker, installable)', 'Access from phones and tablets'],
    ['Backend', 'Python 3.11, FastAPI, Pydantic v2, Uvicorn', 'REST API, validation, WebSockets'],
    ['Database', 'SQLAlchemy 2 ORM — SQLite (development), PostgreSQL 16 (Docker)', 'Persistent storage'],
    ['AI / NLP', 'scikit-learn TF-IDF + logistic regression; optional Claude (claude-opus-5) with structured outputs', 'Intent and entity understanding, coordination briefs'],
    ['Optimisation', 'Google OR-Tools CP-SAT; SciPy (Hungarian fallback)', 'Bed allocation, rostering, theatre scheduling'],
    ['Analytics / ML', 'NumPy Holt-Winters; scikit-learn Gradient Boosting', 'Forecasting and length-of-stay prediction'],
    ['Security', 'PyJWT (HS256), PBKDF2-SHA256, RBAC', 'Authentication and authorisation'],
    ['Deployment & testing', 'Docker Compose (PostgreSQL, API, Nginx); pytest; TypeScript compiler', 'Reproducible deployment and quality assurance'],
  ], [1.1, 3, 2.2], 'Technology stack'),
  H2('Project Structure'),
  ...code([
    'backend/app/',
    '  agents/     orchestrator.py, base.py (blackboard, messages), nlp.py, llm.py, executor.py (HITL)',
    '              bed_, appointment_, staff_, diagnostic_, pharmacy_, care_, emergency_,',
    '              optimization_, billing_, ambulance_, notification_agent.py',
    '  services/   optimizer.py, ot_scheduler.py (OR-Tools) · triage.py, early_warning.py (NEWS2)',
    '              los_model.py, readmission.py (ML) · digital_twin.py (Monte-Carlo simulation)',
    '              billing.py · dispatch.py (fleet) · telemetry.py · hinglish.py',
    '              forecasting.py · queueing.py · maintenance.py · clinical.py',
    '              settings_store.py (autonomy policy) · activity.py (audit, notifications)',
    '  routers/    auth, users, dashboard, patients, ward, resources, surgery, appointments, staff,',
    '              clinical, agents, insights, billing, ambulance, twin, copilot, governance,',
    '              docs (notes & handover), monitor (telemetry), public (display & kiosk)',
    '  models.py · serializers.py · seed.py · simulation.py · main.py',
    'backend/tests/   test_services.py · test_api.py · test_extended.py · test_v2.py (55 tests)',
    'frontend/src/    pages/ (29 screens) · components/ (layout, copilot, agent network, invoice view, UI kit)',
    'docs/            ARCHITECTURE.md · DEMO_SCRIPT.md    .github/workflows/ci.yml   docker-compose.yml',
  ]),
  H2('Orchestrator'),
  P('The orchestrator (`agents/orchestrator.py`) processes each request in a worker thread. After understanding, it builds a plan from intent templates: each step is an `agent.action` pair with dependencies, steps shared by several intents are merged, and a topological level is computed so that independent steps are dispatched together. An `AgentContext` object acts as the blackboard: agents post findings such as `bed_candidates`, `doctor_candidates`, `triage` or `allocation`, and read those of other agents. Agents communicate with FIPA-ACL performatives (for example the Bed Agent PROPOSEs candidates to the Optimizer, the Emergency Agent REQUESTs a team from the Staff Agent, the Pharmacy Agent REFUSEs a contraindicated drug). Every event is appended to a trace and broadcast over WebSockets.'),
  P('After all agents have run, the conflict resolver checks the proposed actions for resource contention with higher-priority patients, staff overload, missing resuscitation capacity, safety refusals and duplicate effects, and applies priority rules. The human-in-the-loop gate then applies the autonomy policy, executes permitted actions and creates approval records for the rest. Allocation transactions are serialised with a lock, preventing two concurrent requests from double-booking a bed.'),
  H2('Natural-Language Understanding'),
  P(`The local pipeline trains, at start-up, a logistic-regression classifier over a union of word (1–2-gram) and character (3–5-gram) TF-IDF features using ${nlp.intents} intents and about 220 template sentences. Multi-intent requests are handled by classifying each clause and by word-bounded keyword rules; suppression rules prevent hospital-level questions (e.g. “forecast admissions”) from triggering patient workflows. Entities are extracted with regular expressions and grounded against the database: patient names and MRNs, medicines, vital signs (with °F→°C conversion), bed types and features, tests, surgical procedures, departments, dates, times and staff counts. When an Anthropic API key is configured, Claude is called with a strict JSON schema at low effort and its output is merged with the database-grounded entities; any failure falls back to the local pipeline. Requests written in Hinglish (Romanised Hindi mixed with English, for example "ICU mein kitne bed khali hain?") are normalised by a rule set before classification, and the patient name is masked out so that it can never influence the predicted intent.`),
  H2('Specialised Agents'),
  H3('Patient Care Coordinator Agent'),
  P('Resolves the patient from an explicit reference, MRN or name; when an admission or emergency concerns an unidentified patient it creates a provisional registration so that care is not delayed. It creates care pathways (admission, emergency, diagnostic, OPD, discharge, surgical), reports journey status with overdue tasks and turnaround breaches, and scores discharge readiness.'),
  H3('Bed Management Agent'),
  P('Derives bed requirements from the request, triage level, clinical protocol and patient age; ranks free beds by hard constraints (type, features) and soft costs; excludes beds held by other pending approvals; and, when no ventilator-equipped bed is free, pairs a monitored bed with a portable ventilator. It also predicts beds that will free up from planned discharges.'),
  H3('Staff Scheduling Agent'),
  P('Ranks doctors by department, specialisation, duty status, workload and seniority, and nurses by department, workload and skills (critical care, paediatrics, triage). It pages specialist consultants for emergencies, proposes redeployments that keep minimum cover elsewhere, and generates weekly rosters with CP-SAT.'),
  H3('Diagnostic Coordination Agent'),
  P('Maps requested tests to catalogue codes and modalities, suggests protocol-based workups (e.g. acute coronary syndrome, stroke, sepsis) for clinician review, schedules each test on the least-loaded available machine according to priority, and tracks turnaround time.'),
  H3('Pharmacy Agent'),
  P('Screens medicines for allergy cross-reactivity, drug–drug interactions against active prescriptions, maximum single dose and stock; proposes alternatives from the same drug class; and computes purchase-order quantities as 30-day demand plus safety stock minus current stock.'),
  H3('Emergency Support Agent'),
  P('Computes NEWS2 and detects red-flag complaints to assign one of five triage levels with target times, creates the emergency case, requests capacity and a team, and monitors ED load for surge conditions and target-time breaches.'),
  H3('Appointment & Queue Agent'),
  P('Searches free slots for every doctor in the department, ranks options by delay and queue length, predicts department waiting time with an M/M/c model at peak-hour load, and schedules post-discharge follow-ups.'),
  H3('Resource Optimization Agent'),
  P('Performs the joint allocation of bed, doctor and nurse using CP-SAT against all waiting patients, predicts length of stay, books surgeries and re-optimises theatre days, forecasts demand and detects bottlenecks across the hospital.'),
  H3('Billing & Insurance Agent'),
  P('Estimates the cost of a proposed admission or surgery from the predicted length of stay, captures charges automatically from clinical events, maps the episode to an Ayushman Bharat (PM-JAY) or insurer package, prepares claims for front-office verification and reports billing clearance during discharge planning.'),
  H3('Ambulance Dispatch Agent'),
  P('Pre-triages a 108 call from the caller’s description and any paramedic vitals, ranks free ambulances by estimated time to scene with capability and coverage penalties, dispatches the best unit immediately (life-critical actions are exempt from approval holds) and raises the emergency-department pre-arrival alert when the crew leaves the scene.'),
  H3('Notification Agent'),
  P('Routes critical emergency alerts, approval requests, receiving-nurse notices, patient SMS confirmations and capacity alerts to the right roles and users over in-app, SMS and e-mail channels (the latter two simulated).'),
  H2('Algorithms'),
  H3('NEWS2 and triage'),
  ...table(['Parameter', '3', '2', '1', '0', '1', '2', '3'], [
    ['Respiration rate (/min)', '≤8', '', '9–11', '12–20', '', '21–24', '≥25'],
    ['SpO₂ scale 1 (%)', '≤91', '92–93', '94–95', '≥96', '', '', ''],
    ['Supplemental O₂', '', 'Yes', '', 'No', '', '', ''],
    ['Systolic BP (mmHg)', '≤90', '91–100', '101–110', '111–219', '', '', '≥220'],
    ['Pulse (/min)', '≤40', '', '41–50', '51–90', '91–110', '111–130', '≥131'],
    ['Consciousness', '', '', '', 'Alert', '', '', 'C/V/P/U'],
    ['Temperature (°C)', '≤35.0', '', '35.1–36.0', '36.1–38.0', '38.1–39.0', '≥39.1', ''],
  ], [2.2, 0.7, 0.8, 0.9, 0.9, 0.9, 0.8, 0.8], 'NEWS2 scoring (Royal College of Physicians, 2017)'),
  P('The aggregate score maps to low (0–4), low-medium (any single parameter scoring 3), medium (5–6) and high (≥7) clinical risk. Triage level 1 is assigned for NEWS2 ≥ 7, unresponsiveness or critical red flags; level 2 for NEWS2 5–6, a single parameter scoring 3 or emergent red flags such as chest pain or stroke signs; level 3 for other abnormal scores or urgent complaints; levels 4–5 for minor presentations. Age ≥ 75 years or ≤ 1 year escalates one level.'),
  H3('Bed allocation with CP-SAT'),
  P('For patients i and beds j, a Boolean variable x[i,j] exists only for feasible pairs (allowed bed type and all required features). The model is:'),
  eq('maximise  Σ x[i,j] · (1000 · (6 − priorityᵢ) − 10 · cost[i,j])'),
  eq('subject to  Σⱼ x[i,j] ≤ 1  ∀ i,    Σᵢ x[i,j] ≤ 1  ∀ j'),
  eq('cost = 12·type rank + 8·[other department] + 2·|Δfloor| + 15·ward occupancy + 20·(1 − nurse coverage) + 6·missing preferred + 4·wasted premium equipment'),
  P('The dominant priority term guarantees that the most urgent patients are placed first; the cost terms produce an explainable, load-balanced choice that also keeps scarce equipment for patients who need it.'),
  H3('Staff rostering with CP-SAT'),
  P('Variables x[s,d,t] indicate that staff member s works shift t (morning, evening, night) on day d. Constraints: at most one shift per day; no night shift followed by a morning shift; at most five shifts per week; approved leave; and coverage Σₛ x[s,d,t] + shortfall ≥ requirement per department, role and shift. The objective minimises 1000·Σ shortfall + 25·(night-shift spread) + 25·(total-shift spread) + Σ x, i.e. coverage first, then fairness, then no over-staffing.'),
  H3('Operating-theatre scheduling'),
  P('The slot finder evaluates, for each theatre, the requested earliest start and the end of every busy block; a start is feasible if the interval [start, end + 30 min turnover) overlaps no booking in that theatre, the surgeon is free and an elective case ends by 20:00. The day optimiser uses CP-SAT interval scheduling: for each not-yet-started case s and theatre o an optional interval with presence p[s,o], exactly one presence per case, NoOverlap constraints per theatre (including cases already running) and per surgeon, and the objective'),
  eq('min  Σ w_priority · startₛ + 40 · Σ overtimeₛ + 3 · makespan + 20 · Σ theatre changes'),
  P('with weights 30, 6 and 1 for emergency, urgent and elective cases.'),
  H3('Waiting-time prediction (M/M/c)'),
  P('With arrival rate λ (peak-hour arrivals), service rate μ = 60 / consultation minutes and c doctors on duty, the offered load is a = λ/μ and utilisation ρ = a/c. The probability of waiting and the mean queueing delay are:'),
  eq('P(wait) = [aᶜ / (c! (1 − ρ))] / [ Σₖ₌₀^{c−1} aᵏ/k! + aᶜ / (c! (1 − ρ)) ],     Wq = P(wait) / (cμ − λ)'),
  P('Within the queue, patients are ordered by a dynamic priority score 20·(6 − priority) + 0.4·min(waited, 180) + bonuses for seniors, young children and lateness; the waiting-time term (ageing) prevents starvation of low-priority patients.'),
  H3('Demand forecasting (Holt-Winters)'),
  eq('ℓₜ = α(yₜ − sₜ₋ₘ) + (1 − α)(ℓₜ₋₁ + bₜ₋₁),   bₜ = β(ℓₜ − ℓₜ₋₁) + (1 − β)bₜ₋₁,   sₜ = γ(yₜ − ℓₜ) + (1 − γ)sₜ₋ₘ'),
  eq('ŷₜ₊ₕ = ℓₜ + h·bₜ + sₜ₊ₕ₋ₘ,   m = 7'),
  P('The smoothing constants are selected by grid search on one-step-ahead squared error; a 95 % prediction interval is derived from the residual standard deviation and widens with the horizon.'),
  H3('Length-of-stay prediction'),
  P('A GradientBoostingRegressor (180 trees, depth 3, learning rate 0.06) is trained on age, acuity, number of comorbidities, emergency admission and ward type. Two additional models with quantile loss (α = 0.1 and 0.9) provide an 80 % prediction interval. The Resource Optimization Agent uses the prediction to set the expected discharge date and states it, with the interval, in the approval rationale.'),
  H3('Predictive maintenance and drug safety'),
  P('Equipment maintenance risk combines calendar age since the last service and usage-hour progress through the manufacturer service interval (risk = 0.65·days/interval + 0.35·hour progress), flagging high-risk devices as a bottleneck. Drug safety uses a curated knowledge base of allergy classes (e.g. penicillins, sulphonamides, NSAIDs), fifteen clinically significant interactions and maximum single doses.'),
  H2('Security, Audit and Real-Time Updates'),
  P('Passwords are stored as salted PBKDF2-SHA256 hashes; users receive a signed JWT; every endpoint declares the roles allowed to call it; approvals are additionally checked against the required approver roles. Every login, data change, approval decision and agent action is written to the audit log with actor, action, entity and details. A WebSocket event bus pushes agent traces, notifications, approvals and refresh events so that all dashboards update live.'),
  H2('Frontend and Progressive Web App'),
  P('The frontend has twenty screens including the command centre with role-specific work lists, the AI Agent Console (with an animated agent network, pipeline progress, live trace, understanding and plan panels, explainable findings and inline approvals), approvals, emergency board, inpatient census, patient record with vitals trend, beds and equipment, operation-theatre timeline, OPD queues, staff rosters, diagnostics, pharmacy, analytics, audit log, users, system and policy, printable discharge summaries and the patient portal. A global command palette (Ctrl + K) searches patients, staff, beds and medicines, and the agent console accepts voice input. The application is installable as a PWA.'),
  H2('Synthetic Data and Live Simulation'),
  P(`A deterministic generator creates a ${cnt.beds}-bed hospital with ten wards, fourteen departments, ${cnt.staff} staff, ${cnt.patients} patients, ${cnt.active_admissions} active admissions with ${cnt.vitals} bedside observations, emergency cases, 190 OPD appointments for the current day, diagnostic orders, prescriptions, ${cnt.surgeries} theatre cases and 180 days of historical statistics with weekly and monsoon seasonality. A live simulator generates walk-ins, consultations, laboratory results, bed turnover, theatre progress, routine observations, deterioration events (which trigger ICU-transfer proposals) and emergency arrivals routed through the full agent pipeline.`),
]


// ------------------------------------------------------------------ chapter 6 (extended modules)
const inr = (v) => '₹' + Math.round(v).toLocaleString('en-IN')
const ch6v2 = [
  H1('Extended Modules: Pre-hospital, Finance, Simulation and Governance'),
  P('The modules described in this chapter were added after the core platform was working end to end. They address four gaps that became visible once the hospital could actually be operated: care starts before the patient reaches the hospital; every clinical action has a financial consequence; capacity decisions are taken under uncertainty; and a system that proposes clinical actions must be able to show how it is supervised.'),
  H2('Pre-hospital Coordination (108 Ambulance)'),
  P('A 108-style call can be registered from the ambulance console, the agent console or the copilot. The Ambulance Dispatch Agent pre-triages the call using the same NEWS2 and red-flag logic as the emergency department, then ranks every free unit by cost:'),
  eq('cost(u) = ETA(u) + 6 · [level ≤ 2 and u is a Basic Life Support unit] + 4 · [u is the hospital ALS unit and level ≥ 3]'),
  P('The estimated time to scene is derived from the haversine distance multiplied by a road-network factor of 1.35 and divided by a time-of-day speed (slower in peak traffic, faster at night). The two penalties encode policy rather than geometry: an advanced-life-support unit is preferred for critical calls, and the hospital’s own ALS unit is kept free for them. The lowest-cost unit is dispatched automatically — dispatch is the one action that never waits in an approval queue, in any autonomy mode.'),
  ...table(['Locality (Nagpur demo geography)', 'Road distance', 'Estimated time to scene'],
    v2.dispatch.sample_etas.map((r) => [r.locality, r.km + ' km', r.eta_min + ' min']), [3, 1.4, 1.6],
    'Sample dispatch estimates from the hospital base'),
  P('While the unit is moving its position is streamed to every connected client. When the crew leaves the scene the hospital receives a **pre-arrival alert**: an incoming emergency case is created with the paramedic vitals, and the full multi-agent pipeline runs during transport — triage, bed search, team assembly and optimisation — so that a doctor approves a bay and a team before the patient arrives. The approved bay is **reserved** rather than occupied; on arrival it becomes occupied and the emergency clock starts. This turns the usual sequence (arrive, triage, then search for a bay) into a parallel one, which is where pre-hospital notification saves time in practice.'),
  H2('Billing, Insurance and PM-JAY Packages'),
  P('Charges are never typed in by hand. Each billable event — a bed-day, a nursing day, a consultant visit, an investigation, a dispensed medicine, a procedure, ventilator use or an emergency attendance — is written as a charge line carrying a stable reference such as `dx:412` or `room:57`. Re-synchronising an invoice therefore updates quantities (bed-days grow with the stay) without ever duplicating a line, which is the property that makes automatic capture safe.'),
  ...table(['Payer', 'Rule implemented', 'What the patient pays'], [
    ['Self-pay', 'Full tariff', 'The whole net amount'],
    ['PM-JAY (Ayushman Bharat)', 'Surgical package when a procedure was performed, otherwise the per-day medical package for the highest level of care (routine ward / HDU / ICU / ICU with ventilator), capped by the family cover', 'Nothing — cashless; the difference between tariff and package is recorded as a hospital package adjustment'],
    ['Private insurance (TPA)', '90 % of the net amount, up to the sum insured', '10 % co-payment plus anything above the sum insured'],
  ], [1.4, 4.2, 2.4], 'Coverage rules implemented by the Billing & Insurance Agent'),
  P('On the demo hospital this produces ' + bil.invoices + ' open invoices worth ' + inr(bil.gross_billed) + ', of which ' + inr(bil.outstanding) + ' is the patient share still to be collected and ' + inr(bil.pmjay_adjustments) + ' is the PM-JAY package adjustment absorbed by the hospital — a figure administrators normally discover only at the end of the month.'),
  P('Cost estimation reuses the length-of-stay model: the 10th, 50th and 90th percentile stay lengths are priced to give an honest range instead of a single figure. For a 68-year-old emergency ICU admission with ventilator support the estimate is ' + inr(bil.estimate_icu.expected) + ' (range ' + inr(bil.estimate_icu.low) + '–' + inr(bil.estimate_icu.high) + '), of which a PM-JAY beneficiary pays nothing.'),
  P('Discharge is where the clinical and financial workflows meet: the Patient Care Agent reports discharge readiness while the Billing Agent reports billing clearance, and on execution the invoice is finalised and — for PM-JAY beneficiaries — the claim is filed automatically.'),
  H2('Hospital Digital Twin'),
  P('Capacity questions ("can we absorb a 50 % surge?", "what if four ICU beds close?") cannot be answered from current occupancy alone, because the answer depends on how patients arrive and leave over the following days. The digital twin is a discrete-event simulation whose initial state is read from the live database: every occupied bed with its expected discharge time, beds being cleaned, patients in emergency work-up and patients already boarding.'),
  ...bullets([
    '**Arrivals** — emergency arrivals follow a Poisson process with an hour-of-day profile scaled by the surge factor; elective admissions arrive between 08:00 and 14:00. A mass-casualty incident can inject a batch of high-acuity patients at a chosen hour.',
    '**Flow** — after an exponential work-up each emergency patient is admitted with a probability that depends on the triage level (90 / 65 / 30 / 8 / 2 %) and needs critical care with a second level-dependent probability; a patient with no free bed **boards** in the emergency bay until one is released.',
    '**Discharge** — length of stay is log-normal (mean 4.2 days in critical care, 3.1 days in wards) and discharges occur only between 09:00 and 20:00, followed by a 45-minute bed turnaround.',
    '**Staffing** — absence beyond a 10 % float-pool buffer closes beds proportionally, which is how a nursing shortage becomes a capacity problem.',
  ]),
  P('Each scenario is run ' + tw.replications + ' times against the baseline using **common random numbers** — both runs are driven by the same random streams — so the difference is caused by the scenario and not by simulation noise. The comparison below is a 72-hour scenario with 50 % more emergency arrivals on the demo hospital.'),
  ...table(['Indicator (mean over replications)', 'Baseline', 'Surge (+50 % ED arrivals)'], [
    ['Emergency arrivals', String(Math.round(tw.baseline.ed_arrivals)), String(Math.round(tw.surge.ed_arrivals))],
    ['ED boarding (patient-hours)', tw.baseline.boarding_patient_hours.toFixed(0), tw.surge.boarding_patient_hours.toFixed(0)],
    ['Longest boarding queue (patients)', tw.baseline.max_boarding.toFixed(1), tw.surge.max_boarding.toFixed(1)],
    ['90th-percentile wait for a bed (hours)', tw.baseline.p90_boarding_hours.toFixed(1), tw.surge.p90_boarding_hours.toFixed(1)],
    ['Hours the emergency department is saturated', tw.baseline.ed_saturated_hours.toFixed(0), tw.surge.ed_saturated_hours.toFixed(0)],
    ['Elective admissions cancelled', tw.baseline.electives_cancelled.toFixed(0), tw.surge.electives_cancelled.toFixed(0)],
    ['Peak critical-care occupancy', (tw.baseline.peak_critical_occupancy * 100).toFixed(0) + ' %', (tw.surge.peak_critical_occupancy * 100).toFixed(0) + ' %'],
  ], [3.4, 1.6, 2], 'Digital-twin comparison over 72 hours (demo hospital)'),
  P('The twin is also **prescriptive**. Each intervention — surge beds, a discharge lounge, rapid bed turnaround, criteria-led discharge or deferring elective admissions — is simulated in turn and ranked by the reduction of a pressure index that combines boarding, emergency saturation and cancellations. On the scenario above the best single lever was "' + tw.recommendations[0].title.toLowerCase() + '" (' + Math.round(tw.recommendations[0].impact * 100) + ' % lower pressure index), followed by "' + tw.recommendations[1].title.toLowerCase() + '" (' + Math.round(tw.recommendations[1].impact * 100) + ' %). The same analysis can be requested in words from the agent console: "what if ER arrivals increase by 50% for the next 3 days?".'),
  H2('Readmission Risk and Transitions of Care'),
  P('Discharge planning uses the **LACE index** — length of stay, acuity of the admission, Charlson comorbidity index derived from the problem list, and emergency-department visits in the previous six months — extended with a logistic-regression model over age, critical-care stay, polypharmacy and abnormal results at discharge. The predicted probability sets the follow-up interval that the agents book (five days for high risk, ten for moderate, fourteen otherwise) and produces transition-of-care actions such as a 48-hour nurse telephone call or a pharmacist-led medication reconciliation.'),
  H2('ICU Central Monitor and Smart Alarms'),
  P('Critical-care beds stream vital signs to a central monitor with ECG and plethysmograph traces. Alarm fatigue is addressed explicitly: a limit breach must persist for three consecutive readings before it raises an alarm, so movement artefacts and probe displacements are suppressed, and the number of suppressed transients is displayed so that the benefit is measurable rather than assumed. Alarms can be acknowledged at the bedside and every acknowledgement is audited.'),
  H2('Conversational Copilot and Hinglish Understanding'),
  P('A copilot is available on every screen. It normalises Hinglish into English before classification ("ICU mein kitne bed khali hain?" becomes "how many ICU beds are available?"), remembers the patient under discussion so that pronouns resolve ("usko kal cardiology mein book karo"), and — when a patient-level request names nobody — asks **which patient** with fuzzy-matched suggestions instead of failing or guessing. Approvals raised by a request can be decided inside the chat, and the full agent trace is one click away.'),
  H2('Clinical Documentation'),
  P('Two documentation tasks are automated. A **SOAP progress note** is drafted from chart data — the latest observations and NEWS2 trend, abnormal results, active medicines, pending investigations and the predicted stay — and is stored only as a draft until a clinician edits and signs it; the note records that it was AI-drafted. A **SBAR shift handover** is generated for every inpatient of a ward (situation, background, assessment, recommendation) with flags for high NEWS2, overdue observations, allergies and imminent discharges, and is printable for the shift-change meeting.'),
  H2('Public Screens: Token Display and Self Check-in'),
  P('A waiting-room television board shows the token currently being served for each doctor together with the next tokens, and announces changes in English and Hindi; it never shows patient names. A touch kiosk lets a patient check in by entering the medical-record number and the last four digits of the registered mobile number, with repeated failures rate-limited. Both are public routes that need no login, which is what makes them usable in a waiting area.'),
  H2('Security, Privacy and AI Governance'),
  ...table(['Concern', 'Control implemented'], [
    ['Credential attacks', 'Account and client lock-out after five failed sign-ins within ten minutes; every failure is audited'],
    ['Weak passwords', 'Minimum eight characters with letters and digits, enforced on creation, reset and self-service change'],
    ['Browser-level attacks', 'Security headers on every response (content-type sniffing, framing, referrer and permissions policy) and a request identifier for tracing'],
    ['Record snooping', 'Every staff view of a patient record is logged; patients see that log in their portal ("who accessed my record")'],
    ['Public screens', 'Tokens only on the display; kiosk verification requires MRN and phone digits and is rate-limited'],
    ['Oversight of the AI', 'Governance dashboard: approval, modification and rejection rates, median decision time, autonomy ratio, model cards and medication-safety events'],
  ], [1.6, 5], 'Security and privacy controls'),
  P('The governance dashboard answers the question a clinical audit committee asks first: **how often does a human disagree with the system?** It reports how many proposals were approved, approved with changes (and which fields were changed), rejected, and how quickly, alongside model cards that quote leakage-free validation figures rather than training accuracy.'),
]

// ------------------------------------------------------------------ chapter 7 (results)
const ch6 = [
  H1('Results and Screenshots'),
  P('This chapter presents the working system. All screenshots were captured from the running application with the synthetic hospital data.'),
  H2('Login and Role-Based Access'),
  ...fig(S('login'), 'Login screen with one-click demo accounts for each role'),
  H2('Command Center'),
  P('The command centre shows role-specific work lists (here, inpatients ordered by NEWS2 and the theatre list), live KPIs, ward occupancy, the emergency board, patient-flow trends and bottlenecks detected by the Resource Optimization Agent.'),
  ...fig(S('dashboard'), 'Command center (administrator)'),
  ...fig(S('nurse_dashboard'), 'Nurse view: ward early-warning board with overdue observations'),
  H2('AI Agent Console'),
  P('For the synopsis example “Patient needs admission and requires ICU monitoring with ventilator support”, the console shows the live agent network with the agents that participated, the pipeline progress, the live trace of messages and results, the understanding panel (admission intent, ICU and ventilator requirements) and the execution plan.'),
  ...fig(S('agents_icu_top'), 'AI Agent Console — live agent network, trace, understanding and plan'),
  ...fig(S('agents_icu_bottom'), 'Agent findings with explainable recommendations and the approval request'),
  ...fig(S('agents_er'), 'Emergency request: NEWS2 triage, resuscitation bay, ED team and protocol workup'),
  H2('Human-in-the-Loop Approvals'),
  ...fig(S('approvals'), 'Approval queue with risk levels, rationale and the option to modify the AI’s choice'),
  H2('Emergency Department'),
  ...fig(S('emergency'), 'ED board sorted by triage level, with live NEWS2 preview for new arrivals'),
  H2('Inpatients and Patient Record'),
  ...fig(S('inpatients'), 'Inpatient census with NEWS2, observation schedule and ML-predicted length of stay'),
  ...fig(S('patient'), 'Patient record: care pathway, quick agent actions and NEWS2 / vital-signs trend'),
  ...fig(S('discharge'), 'Printable discharge summary generated from the record', 440, 780),
  H2('Resources'),
  ...fig(S('beds'), 'Beds and equipment with live status and predictive maintenance'),
  ...fig(S('theatres'), 'Operation-theatre timeline with turnover blocks and CP-SAT optimisation'),
  ...fig(S('staff'), 'Staff workload and duty status'),
  H2('Clinical Workflows'),
  ...fig(S('opd'), 'OPD queues with dynamic priority, ETA and M/M/c metrics'),
  ...fig(S('diagnostics'), 'Diagnostics board with turnaround tracking and result reporting'),
  ...fig(S('pharmacy'), 'Pharmacy verification queue with safety alerts'),
  H2('Pre-hospital, Finance and Planning (Extended Modules)'),
  P('The ambulance console shows the live fleet on a map together with the active call, its predicted severity and the stage of the run; the emergency department is pre-alerted while the patient is still in transit.'),
  ...fig(S('ambulance'), 'Ambulance and pre-hospital coordination with the live fleet map'),
  ...fig(S('billing'), 'Billing and insurance: automatically captured charges, payer mix and claims'),
  ...fig(S('patient_billing'), 'Itemised patient bill with PM-JAY package coverage'),
  ...fig(S('twin'), 'Hospital digital twin: baseline versus surge with prescriptive recommendations'),
  ...fig(S('monitor'), 'ICU central monitor with streaming vitals and smart alarms'),
  ...fig(S('handover'), 'SBAR shift handover generated from the chart'),
  ...fig(S('copilot'), 'Conversational copilot answering a Hinglish request'),
  ...fig(S('governance'), 'AI governance: human-in-the-loop metrics and model cards'),
  H2('Public Screens'),
  ...fig(S('display'), 'Waiting-room token display (tokens only, no patient names)', 560),
  ...fig(S('kiosk'), 'Self check-in kiosk with English and Hindi labels', 420, 640),
  H2('Analytics, Administration and Patient Portal'),
  ...fig(S('analytics_top'), 'Holt-Winters demand forecast and length-of-stay model card'),
  ...fig(S('analytics_bottom'), 'Occupancy, waiting-time, utilisation and agent-performance analytics'),
  ...fig(S('system'), 'System & policy: runtime status, simulation, autonomy policy and architecture'),
  ...fig(S('users'), 'User and access management with the permission matrix'),
  ...fig(S('portal'), 'Patient portal: AI booking, the bill with a demo UPI payment and the record-access log'),
]

// ------------------------------------------------------------------ chapter 7
const testRows = [
  ['Triage', 'NEWS2 is 0 for normal vitals; 14 for a severely abnormal set', 'Pass'],
  ['Triage', 'Five-level triage for arrest, chest pain, sprain and unresponsive patients; age escalation', 'Pass'],
  ['NLP', 'Single-intent classification (admission, appointment, bed query, analytics)', 'Pass'],
  ['NLP', 'Multi-intent detection (admission + diagnostics); no false admission from “forecast admissions”', 'Pass'],
  ['NLP', 'Entity extraction (age, sex, ICU, ventilator, BP, SpO₂, troponin, stat); °F→°C', 'Pass'],
  ['Clinical KB', 'Longest test match; word-bounded protocol match; allergy and interaction detection', 'Pass'],
  ['Optimiser', 'Hard constraints respected; premium equipment reserved; urgent patient placed first', 'Pass'],
  ['Optimiser', 'Roster: ≤ 1 shift/day, ≤ 5 shifts/week, full coverage when feasible', 'Pass'],
  ['Queueing / forecast', 'Erlang-C bounds and instability; priority ageing; weekly pattern captured (MAPE < 10 %)', 'Pass'],
  ['Auth / RBAC', 'Login, wrong password, forbidden endpoints for nurse and patient, unauthenticated access', 'Pass'],
  ['Orchestration', 'ICU admission → approval → admission executed', 'Pass'],
  ['Orchestration', 'Chest-pain emergency → L1 triage; rejection releases the held bay', 'Pass'],
  ['Safety', 'Penicillin-allergic patient: amoxicillin held as critical approval', 'Pass'],
  ['Automation', 'Appointment booked automatically (low risk)', 'Pass'],
  ['HITL', 'Nurse cannot approve an admin-only roster action', 'Pass'],
  ['Emergency API', 'Triage preview and ER registration', 'Pass'],
  ['Portal', 'Patient sees own record only', 'Pass'],
  ['ML', 'LOS model better than median baseline; interval coverage 70–90 %', 'Pass'],
  ['Theatres', 'Empty day starts at 08:00; optimiser removes overtime without overlaps', 'Pass'],
  ['Theatres', 'Surgery booked through the agents, no theatre clash', 'Pass'],
  ['Early warning', 'NEWS2 ≥ 7 triggers emergency response and ICU-transfer proposal; normal vitals do not escalate', 'Pass'],
  ['Policy', 'Supervised mode holds even an appointment; invalid mode rejected', 'Pass'],
  ['Users', 'Create user, change password, deactivate account', 'Pass'],
  ['Misc', 'Global search, role work lists, discharge summary, maintenance fields', 'Pass'],
  ['Billing', 'Charge capture is idempotent; payment reduces the balance; over-payment rejected', 'Pass'],
  ['Billing', 'PM-JAY episode is cashless; claim submitted once, settled by the insurer; nurse cannot settle a claim', 'Pass'],
  ['Billing', 'LOS-aware estimate ordered low ≤ expected ≤ high; PM-JAY share is zero', 'Pass'],
  ['Billing', 'Billing agent answers a bill query; discharge finalises the invoice and files the PM-JAY claim', 'Pass'],
  ['Pre-hospital', '108 call dispatches without an approval hold; pre-alert creates an incoming case; approved bay is reserved and becomes occupied on arrival', 'Pass'],
  ['Digital twin', 'Surge increases boarding; identical scenarios reproduce identical results (common random numbers)', 'Pass'],
  ['Digital twin', '“What if” request through the agents parses the surge percentage and returns recommendations', 'Pass'],
  ['Hinglish / copilot', 'Hinglish normalisation and classification; copilot remembers the patient; missing patient triggers a clarification', 'Pass'],
  ['ML', 'Readmission model AUC above the LACE index alone; LACE components and follow-up interval in range', 'Pass'],
  ['Security', 'Five failed sign-ins lock the account; security headers and request id present', 'Pass'],
  ['Privacy', 'Public queue shows tokens only; kiosk rejects a wrong phone number and issues a token for a correct one', 'Pass'],
  ['Documentation', 'AI SOAP draft is a draft until signed; SBAR handover contains all four sections', 'Pass'],
  ['Governance', 'Oversight metrics and model cards returned; patient sees the record-access log; patient role forbidden', 'Pass'],
  ['ICU monitor', 'Alarm only after three consecutive breaches; transient artefacts counted as suppressed', 'Pass'],
]
const ch7 = [
  H1('Testing and Evaluation'),
  H2('Testing Strategy'),
  ...bullets([
    '**Unit tests** for algorithms: NEWS2, triage, NLP, entity extraction, knowledge base, bed optimisation, rostering, queueing, forecasting and the LOS model.',
    '**Integration tests** through the REST API with a fresh database: authentication, RBAC, complete multi-agent orchestrations, approvals and rollbacks, ward escalation, theatre scheduling, autonomy policy and user management.',
    '**System tests** of end-to-end scenarios in the browser (Section 7.3), including live WebSocket updates.',
    '**Static checks**: the TypeScript compiler over the whole frontend and a production build.',
  ]),
  H2('Automated Test Results'),
  P('The backend suite contains ' + v2.tests + ' pytest tests across four modules (`test_services.py` for algorithms, `test_api.py` and `test_extended.py` for the core API and orchestrations, `test_v2.py` for the extended modules). All ' + v2.tests + ' tests pass (`' + v2.tests + ' passed` in about 28 s on a fresh database). The same suite, together with a TypeScript type-check and a production build of the frontend, runs on every push through GitHub Actions. Table 8.1 groups the tests by area.'),
  ...table(['Area', 'What is verified', 'Result'], testRows, [1.2, 5, 0.7], 'Automated test cases'),
  H2('Scenario Testing'),
  ...table(['Scenario (natural-language input)', 'Observed behaviour'], [
    ['“Patient needs admission and requires ICU monitoring with ventilator support.”', 'Provisional registration; ventilator ICU bed held; Critical Care doctor and ICU nurse selected; admission awaits doctor approval'],
    ['“Emergency: 58 year old male with chest pain … BP 92/60, HR 124, SpO₂ 93%”', 'NEWS2 8 → L1; resuscitation bay preferred; ED doctor + cardiology consult; ACS workup suggested for review; critical alerts'],
    ['“Admit Rohan Mehta to the cardiac unit and order ECG, troponin and chest x-ray stat”', 'Two intents; requested tests ordered automatically; cardiac bed held; admission awaits approval'],
    ['“Prescribe amoxicillin 500 mg BD for Rohan Mehta” (penicillin allergy)', 'Pharmacy Agent refuses; conflict logged; critical approval for doctor override'],
    ['“Book an appointment with a cardiologist tomorrow at 11 am …”', 'Best doctor and slot found; booked automatically; SMS confirmation'],
    ['“We need two more nurses in the ICU tonight”', 'Two lowest-workload nurses proposed for redeployment, keeping minimum cover'],
    ['“Generate an optimized staff roster for next week”', `CP-SAT roster for ${ro.staff} staff, ${ro.coverage_pct}% coverage, awaiting admin approval`],
    ['“Schedule a laparoscopic cholecystectomy for Rohan Mehta tomorrow”', 'Ranked theatre slots with explanations; surgeon selected; booking awaits approval; surgical pathway on execution'],
    ['“Optimize the operation theatre schedule for tomorrow to reduce overtime”', `Overtime ${ot.before.overtime_minutes} → ${ot.after.overtime_minutes} min, overlaps ${ot.before.conflicts} → ${ot.after.conflicts}`],
    ['Bedside observations with NEWS2 ≥ 7 on a general ward', 'Emergency alert to doctors and nurses; automatic ICU-transfer request prepared by the agents'],
    ['Patient portal booking', 'Appointment Agent books the best slot and confirms within seconds'],
    ['“Road accident at Wardhaman Nagar, send an ambulance”', 'Call pre-triaged; nearest capable unit dispatched immediately; ED pre-alerted on departure from the scene; bay reserved before arrival'],
    ['“ICU mein kitne bed khali hain?” (Hinglish, copilot)', 'Normalised to English, classified as a bed query, answered with ICU availability and expected discharges'],
    ['“What is the bill for Rohan Mehta?”', 'Charges re-synchronised, payer coverage applied, balance and claim status reported'],
    ['“What if ER arrivals increase by 50% for the next 3 days?”', 'Digital twin run against the baseline; boarding, saturation and cancellations compared; best intervention ranked'],
  ], [3, 4], 'End-to-end scenario tests'),
  H2('Evaluation of the AI Components'),
  H3('Intent classification'),
  P(`The local NLP pipeline was evaluated on ${nlp.n} held-out requests written independently of the training sentences. Accuracy of the primary intent is **${pct(nlp.accuracy)}**, with an average processing time of ${nlp.avg_ms} ms per request.`),
  P(`Held-out accuracy alone can flatter a classifier, so the model card shown inside the application also reports a leakage-free cross-validation: the ${card.training_sentences} training sentences are split with GroupKFold so that all paraphrase variants of a sentence stay in the same fold. That gives **${pct(card.cv_accuracy)} \u00B1 ${pct(card.cv_std)}** five-fold accuracy, and **${pct(card.held_out_accuracy)}** on a further ${card.held_out_size}-sentence set that deliberately includes Hinglish requests normalised by the rule set. The difference between the two figures is the honest measure of how much the model depends on phrasing it has already seen.`),
  ...table(['Intent', 'Correct / total'], Object.entries(nlp.per_intent).map(([k, v]) => [k.replace('_', ' '), v]), [3, 2], 'Held-out intent accuracy by intent'),
  H3('Demand forecasting'),
  P('Holt-Winters forecasts were evaluated on the last 14 days of the 180-day history and compared with a seasonal-naive baseline (the value seven days earlier).'),
  ...table(['Metric', 'Holt-Winters MAPE', 'Seasonal-naive MAPE'], Object.entries(fc).map(([k, v]) => [k.replace('_', ' '), `${v.mape}%`, `${v.naive_seasonal_mape}%`]), [2.5, 2, 2], 'Forecast accuracy (14-day hold-out)'),
  P(`Holt-Winters is the more accurate model on four of the five series, including the two that drive capacity decisions (bed occupancy ${fc.bed_occupancy.mape}% versus ${fc.bed_occupancy.naive_seasonal_mape}%, ICU occupancy ${fc.icu_occupancy.mape}% versus ${fc.icu_occupancy.naive_seasonal_mape}%). Daily admissions — the noisiest series, with the smallest counts and therefore the largest relative error — is the exception on this hold-out window, where the seasonal-naive baseline is marginally better (${fc.admissions.mape}% versus ${fc.admissions.naive_seasonal_mape}%). The figures are reported as measured rather than by selecting only the favourable series; for operational use the occupancy forecasts, which the Resource Optimization Agent actually consumes, are the relevant ones.`),
  H3('Length-of-stay model'),
  ...table(['Measure', 'Value'], [
    ['Training / test rows', `${los.train_rows} / ${los.test_rows}`], ['MAE (Gradient Boosting)', `${los.mae_days} days`],
    ['MAE (median-stay baseline)', `${los.baseline_mae_days} days`], ['R²', `${los.r2}`], ['80 % interval coverage', pct(los.interval_coverage)],
    ['Most important features', Object.entries(M.los_importances).slice(0, 4).map(([k, v]) => `${k} (${(v * 100).toFixed(0)}%)`).join(', ')],
  ], [2.5, 4], 'Length-of-stay model evaluation'),
  P('Length of stay is inherently noisy; the model reduces the error of the naive baseline by about one fifth and provides calibrated intervals, which is what planners need for discharge and capacity planning. Retraining on real discharge records would be required before clinical use.'),
  H3('Readmission-risk model'),
  ...table(['Measure', 'Value'], [
    ['Area under the ROC curve (test)', String(rdm.auc)],
    ['LACE index alone', String(rdm.lace_only_auc)],
    ['Brier score (calibration)', String(rdm.brier)],
    ['Observed readmission rate', pct(rdm.base_rate)],
    ['AUC by gender (fairness check)', 'female ' + rdm.fairness.female + ' · male ' + rdm.fairness.male],
  ], [3, 3], 'Readmission model evaluation'),
  P('The model adds a modest but consistent improvement over the LACE index on its own, and the two gender subgroups are within a few points of each other. As with the length-of-stay model, the training data is synthetic: the value here is the pipeline and the calibration/fairness reporting, not the absolute number.'),
  H3('Digital-twin behaviour'),
  P('Two properties were verified. First, **monotonicity**: increasing emergency arrivals increases boarding, emergency saturation and cancelled electives, and never decreases them. Second, **reproducibility**: running the same scenario twice returns identical key indicators, because baseline and scenario share random streams (common random numbers); this is what makes the comparison of two scenarios meaningful rather than noise. ' + tw.replications + ' replications of a 72-hour horizon complete in about ' + (tw.wall_ms / 1000).toFixed(1) + ' s, fast enough for interactive use.'),
  H3('Optimisation performance'),
  ...table(['Problem', 'Size', 'Result', 'Solve time'], [
    ['Bed allocation (CP-SAT)', `${bd.patients} patients × ${bd.free_beds} free beds (${bd.feasible_pairs} feasible pairs)`, `${bd.placed}/${bd.patients} placed, ${bd.status}`, `${bd.wall_ms} ms`],
    ['Weekly roster (CP-SAT)', `${ro.staff} staff × 7 days × 3 shifts (${ro.variables} variables)`, `${ro.status}; ${ro.coverage_pct}% of ${ro.required_slots} slots; nights ${ro.min_nights}–${ro.max_nights} per person`, `${(ro.wall_ms / 1000).toFixed(2)} s`],
    ['Theatre day (CP-SAT)', `${ot.movable} movable cases × 4 theatres`, `${ot.status}; overtime ${ot.before.overtime_minutes}→${ot.after.overtime_minutes} min; last case ${ot.before.makespan}→${ot.after.makespan}; overlaps ${ot.before.conflicts}→${ot.after.conflicts}`, `${ot.wall_ms} ms`],
  ], [1.6, 2.2, 2.8, 1], 'Optimisation results'),
  P('Roster coverage below 100 % reflects genuinely infeasible requirements in small departments under the five-shift and rest constraints; the solver minimises the shortfall and reports it instead of silently violating constraints.'),
  H3('Orchestration latency'),
  P('A complete ICU-admission orchestration (seven agent steps) finished in about 3.2 s, and a chest-pain emergency (nine steps) in about 3.5 s, including a deliberate 0.35 s visual pause per step that lets users follow the live trace; without the pause the same workflows complete in well under one second.'),
  H2('Discussion'),
  P('The results show that a multi-agent design lets each operational sub-problem be solved with the most appropriate, verifiable technique while the orchestrator composes them into coherent workflows. Explanations and the approval gate make the recommendations reviewable, and the audit log makes them accountable. The main limitation of the evaluation is the synthetic data: the absolute numbers demonstrate correctness and feasibility rather than clinical effectiveness, which would require a prospective study in a hospital.'),
]

// ------------------------------------------------------------------ chapter 8
const ch8 = [
  H1('Conclusion and Future Scope'),
  H2('Conclusion'),
  P('This project designed and implemented MedOrchestra, a multi-agent AI system for hospital resource optimisation, clinical workflow automation and patient-care coordination. ' + v2.agents + ' specialised agents, coordinated by a central orchestrator with a shared blackboard and explicit agent messages, convert natural-language requests — in English or Hinglish — into planned, explainable and auditable actions. Constraint optimisation allocates beds, rosters staff and schedules theatres; NEWS2 drives triage and ward escalation; queueing theory predicts waiting time; exponential smoothing forecasts demand; gradient boosting predicts length of stay and the LACE index predicts readmission risk.'),
  P('Beyond the synopsis, the platform now coordinates care before arrival (108 ambulance dispatch with an emergency-department pre-alert that holds a bay during transport), closes the financial loop (automatic charge capture, PM-JAY and insurer packages, claims and billing clearance at discharge), plans capacity under uncertainty (a Monte-Carlo digital twin that also recommends the most effective intervention), watches critical-care patients continuously (central monitor with persistence-filtered alarms), drafts clinical documentation for a clinician to sign, serves the waiting room through public screens, and makes its own supervision measurable through an AI-governance dashboard. A risk-tiered, configurable human-in-the-loop gate keeps clinicians in control of every safety-critical decision, and ' + v2.tests + ' automated tests plus continuous integration guard the behaviour.'),
  H2('Limitations'),
  ...bullets([
    'All data is synthetic; clinical effectiveness has not been evaluated in a real hospital.',
    'The clinical knowledge base (protocols, interactions, doses) is a demonstration subset and must be replaced by a validated drug and protocol database.',
    'Integrations with HIS/EHR, laboratory, pharmacy, SMS and IoT systems are simulated.',
    'The local NLP model is trained on template sentences; real requests would require more training data or an LLM.',
    'Real-world deployment must comply with healthcare data-protection and AI-governance regulations.',
  ]),
  H2('Future Scope'),
  ...bullets([
    '**HL7 FHIR and ABDM (ABHA) integration** with hospital information systems, laboratories and the national health stack, including real PM-JAY claim submission.',
    '**IoT and smart beds** streaming real vital signs into the early-warning service and the central monitor in place of the simulated telemetry.',
    '**Learning from real data**: retrain and recalibrate the length-of-stay, readmission and demand models on the hospital own records, with prospective monitoring of drift.',
    '**Multi-hospital coordination** for referrals and resource sharing across a network.',
    '**Full Hindi and regional-language interfaces** (the copilot already understands Hinglish; the user interface itself is still English).',
    '**Advanced explainability** (e.g. counterfactual “what would change this recommendation” explanations) and continuous monitoring of agent performance.',
    '**Mobile apps** with push notifications for on-call staff.',
  ]),
]

// ------------------------------------------------------------------ references & appendices
const refs = [
  'M. Wooldridge, An Introduction to MultiAgent Systems, 2nd ed. Chichester, UK: John Wiley & Sons, 2009.',
  'Foundation for Intelligent Physical Agents, “FIPA ACL Message Structure Specification,” Document SC00061G, 2002.',
  'H. P. Nii, “Blackboard systems,” AI Magazine, vol. 7, no. 2 and no. 3, 1986.',
  'Royal College of Physicians, National Early Warning Score (NEWS) 2: Standardising the Assessment of Acute-Illness Severity in the NHS. London: RCP, 2017.',
  'G. B. Smith, D. R. Prytherch, P. Meredith, P. E. Schmidt and P. I. Featherstone, “The ability of the National Early Warning Score (NEWS) to discriminate patients at risk of early cardiac arrest, unanticipated intensive care unit admission, and death,” Resuscitation, vol. 84, no. 4, pp. 465–470, 2013.',
  'Manchester Triage Group, Emergency Triage, 3rd ed. Chichester, UK: Wiley-Blackwell, 2014.',
  'B. Cardoen, E. Demeulemeester and J. Beliën, “Operating room planning and scheduling: A literature review,” European Journal of Operational Research, vol. 201, no. 3, pp. 921–932, 2010.',
  'L. V. Green, “Queueing analysis in healthcare,” in Patient Flow: Reducing Delay in Healthcare Delivery, R. W. Hall, Ed. New York: Springer, 2006, pp. 281–307.',
  'P. R. Winters, “Forecasting sales by exponentially weighted moving averages,” Management Science, vol. 6, no. 3, pp. 324–342, 1960.',
  'C. C. Holt, “Forecasting seasonals and trends by exponentially weighted moving averages,” International Journal of Forecasting, vol. 20, no. 1, pp. 5–10, 2004.',
  'J. H. Friedman, “Greedy function approximation: A gradient boosting machine,” The Annals of Statistics, vol. 29, no. 5, pp. 1189–1232, 2001.',
  'K. Stone, R. Zwiggelaar, P. Jones and N. Mac Parthaláin, “A systematic review of the prediction of hospital length of stay: Towards a unified framework,” PLOS Digital Health, vol. 1, no. 4, e0000017, 2022.',
  'L. Perron and V. Furnon, OR-Tools, Google. [Online]. Available: https://developers.google.com/optimization/',
  'F. Pedregosa et al., “Scikit-learn: Machine learning in Python,” Journal of Machine Learning Research, vol. 12, pp. 2825–2830, 2011.',
  'L. Kleinrock, Queueing Systems, Volume 1: Theory. New York: Wiley, 1975.',
  'World Health Organization, Ethics and Governance of Artificial Intelligence for Health: WHO Guidance. Geneva: WHO, 2021.',
  'S. Ramírez, FastAPI. [Online]. Available: https://fastapi.tiangolo.com',
  'Anthropic, Claude API documentation. [Online]. Available: https://docs.anthropic.com',
  'Meta Open Source, React. [Online]. Available: https://react.dev',
  'M. Jones, J. Bradley and N. Sakimura, “JSON Web Token (JWT),” IETF RFC 7519, 2015.',
  'A. K. Erlang, “Solution of some problems in the theory of probabilities of significance in automatic telephone exchanges,” Elektroteknikeren, vol. 13, 1917.',
]
const references = [
  H1u('References'),
  ...refs.map((r, i) => new Paragraph({ spacing: { after: 100, line: 300 }, indent: { left: 560, hanging: 560 }, alignment: AlignmentType.JUSTIFIED,
    children: [new TextRun({ text: `[${i + 1}]\t${r}`, size: 22 })] })),
]

const appendices = [
  H1u('Appendix A: Installation and Execution'),
  P('**Prerequisites:** Python 3.10+ and Node.js 18+. On Windows, run `setup.bat` once and then `start.bat`; the browser opens at http://localhost:5173.'),
  ...code([
    'cd backend',
    'python -m venv .venv  &&  .venv\\Scripts\\activate',
    'pip install -r requirements.txt',
    'uvicorn app.main:app --port 8000',
    '',
    'cd ../frontend',
    'npm install',
    'npm run dev                     # http://localhost:5173',
    '',
    'docker compose up --build       # PostgreSQL + API + web on http://localhost:8080',
    'cd backend && .venv\\Scripts\\python -m pytest -q    # 55 passed',
  ]),
  P('The database is created and seeded automatically. Setting `ANTHROPIC_API_KEY` in `backend/.env` enables Claude-based understanding; without it the system runs fully offline. API documentation is available at http://localhost:8000/docs.'),
  H1u('Appendix B: Demo Accounts and Walkthrough'),
  ...table(['Role', 'Username', 'Password'], [
    ['Administrator', 'admin', 'admin123'], ['Doctor (Cardiology)', 'doctor', 'doctor123'], ['ER doctor', 'er.doctor', 'doctor123'],
    ['ICU nurse', 'nurse', 'nurse123'], ['Reception', 'reception', 'reception123'], ['Lab technician', 'lab', 'lab123'],
    ['Pharmacist', 'pharmacist', 'pharma123'], ['Patient', 'patient', 'patient123'],
  ], [2, 2, 2], 'Demo accounts'),
  ...numbered([
    'Log in as admin; review the command center.',
    'AI Agent Console → “ICU admission (synopsis example)”; follow the agent network and trace; open the explanations; approve the admission.',
    'Emergency → “Chest pain” preset → register; observe triage and coordination; reject to see the bed released.',
    'Console → “Prescription safety”: the allergy is blocked for doctor override.',
    'Inpatients → record observations with NEWS2 ≥ 7 to trigger an ICU-transfer proposal.',
    'Operation Theatres → tomorrow → Optimise day (CP-SAT) → apply.',
    'System & Policy → switch autonomy mode to Supervised and repeat an appointment booking.',
    'Analytics → forecasts and the length-of-stay model; log in as patient to book through the portal.',
    'Ambulance & 108 → Random call → follow the unit, then approve the pre-arrival bay before it arrives.',
    'Digital Twin → pick a preset scenario, run it and apply the recommended intervention.',
    'Billing & Insurance → open an invoice, take a payment, submit and settle a PM-JAY claim.',
    'Copilot (bottom right) → ask “ICU mein kitne bed khali hain?” and then a follow-up about the same patient.',
    'AI Governance → oversight metrics and model cards; open /display and /kiosk for the public screens.',
  ]),
]

// ------------------------------------------------------------------ document
const footer = new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], size: 20 })] })] })
const header = new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: 'BFD8D4', space: 4 } },
  children: [new TextRun({ text: 'Multi-Agent AI Systems for Hospital Management — MedOrchestra', italics: true, size: 18, color: '555555' })] })] })
const margins = { top: 1440, bottom: 1440, left: 1440, right: 1440 }

const doc = new Document({
  creator: 'MedOrchestra project team', title: 'Multi-Agent AI Systems for Hospital Management — Project Report',
  styles: {
    default: { document: { run: { font: FONT, size: 24 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: 32, bold: true, color: TEAL }, paragraph: { spacing: { before: 240, after: 300 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: 28, bold: true, color: '1F2937' }, paragraph: { spacing: { before: 280, after: 140 }, outlineLevel: 1, keepNext: true } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: 24, bold: true, italics: true, color: '334155' }, paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: { config: [
    { reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    { reference: 'num', levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  ] },
  sections: [
    { properties: { page: { margin: margins } }, children: titlePage },
    { properties: { page: { margin: margins, pageNumbers: { start: 1, formatType: NumberFormat.LOWER_ROMAN } } }, footers: { default: footer },
      children: [...certificate, ...declaration, ...acknowledgement, ...abstract,
        new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun('Table of Contents')] }),
        new TableOfContents('Table of Contents', { hyperlink: true, headingStyleRange: '1-2' }), ...abbreviations] },
    { properties: { page: { margin: margins, pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } } }, headers: { default: header }, footers: { default: footer },
      children: [...ch1, ...ch2, ...ch3, ...ch4, ...ch5, ...ch6v2, ...ch6, ...ch7, ...ch8, ...references, ...appendices] },
  ],
})

Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log('written', OUT, buf.length) })
