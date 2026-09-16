"""Fill the Ramdeobaba University project-presentation template with the MedOrchestra content.

Works on a copy of the template: keeps its header/footer bars, titles, underline accents and logo;
removes the invisible placeholder glyphs/labels and the prompt bullets; adds content in the
template's navy/orange palette.
"""
import json
import sys
from pathlib import Path

from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).parent
SCRATCH = HERE.parent
TEMPLATE = HERE / "template.pptx"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "out.pptx"
M = json.loads((SCRATCH / "metrics.json").read_text())
DATE = "16 September 2026"
V2 = M["v2"]
TW, BIL, CARD = V2["twin"], V2["billing"], V2["nlp_card"]

NAVY, ORANGE = RGBColor(0x07, 0x2A, 0x52), RGBColor(0xEF, 0x60, 0x19)
INK, MUTE, WHITE = RGBColor(0x1F, 0x29, 0x37), RGBColor(0x55, 0x60, 0x70), RGBColor(0xFF, 0xFF, 0xFF)
NAVY_TINT, ORANGE_TINT, LINE = RGBColor(0xE9, 0xEF, 0xF7), RGBColor(0xFF, 0xF1, 0xE8), RGBColor(0xD5, 0xDD, 0xE8)
HEAD = "+mj-lt"  # template theme heading font

prs = Presentation(str(TEMPLATE))
TOTAL = len(prs.slides)


# ------------------------------------------------------------------ helpers
def shape_named(slide, name):
    return next((s for s in slide.shapes if s.name == name), None)


def remove(slide, *names):
    for n in names:
        s = shape_named(slide, n)
        if s is not None:
            s._element.getparent().remove(s._element)


def set_text(shape, text):
    """Replace text while keeping the first run's formatting."""
    tf = shape.text_frame
    p0 = tf.paragraphs[0]
    runs = p0.runs
    for extra in tf.paragraphs[1:]:
        extra._p.getparent().remove(extra._p)
    if runs:
        runs[0].text = text
        for r in runs[1:]:
            r._r.getparent().remove(r._r)
    else:
        p0.text = text


def no_shadow(shape):
    sp_pr = shape._element.spPr
    if sp_pr.find(qn("a:effectLst")) is None:
        etree.SubElement(sp_pr, qn("a:effectLst"))


def box(slide, x, y, w, h, fill=None, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06, line_w=0.75):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(line_w)
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    no_shadow(s)
    s.text_frame.text = ""
    return s


def _bullet(p, level_indent=0.22):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(Inches(level_indent)))
    pPr.set("indent", str(-Inches(level_indent * 0.8)))
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    bu_font = etree.SubElement(pPr, qn("a:buFont"))
    bu_font.set("typeface", "Arial")
    bu = etree.SubElement(pPr, qn("a:buChar"))
    bu.set("char", "•")


def text(slide, x, y, w, h, paras, size=14, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         font=None, bullets=False, space_after=4, line_spacing=None):
    """paras: list of strings or lists of (text, {bold, color, size, italic}) runs."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    for i, para in enumerate(paras if isinstance(paras, list) else [paras]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        if line_spacing:
            p.line_spacing = line_spacing
        if bullets:
            _bullet(p)
        runs = para if isinstance(para, list) else [(para, {})]
        for t, o in runs:
            r = p.add_run()
            r.text = t
            f = r.font
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", False)
            f.color.rgb = o.get("color", color)
            if o.get("font", font):
                f.name = o.get("font", font)
    return tb


def circle(slide, x, y, d, label, fill=NAVY, size=14):
    c = box(slide, x, y, d, d, fill=fill, shape=MSO_SHAPE.OVAL)
    tf = c.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = label
    r.font.size, r.font.bold, r.font.color.rgb = Pt(size), True, WHITE
    return c


def picture(slide, path, x, y, w, h, frame=True):
    """Contain an image inside the box, centred; optional thin navy frame."""
    iw, ih = Image.open(path).size
    r = iw / ih
    pw, ph = w, w / r
    if ph > h:
        ph, pw = h, h * r
    px, py = x + (w - pw) / 2, y + (h - ph) / 2
    if frame:
        box(slide, px - 0.05, py - 0.05, pw + 0.1, ph + 0.1, fill=WHITE, line=LINE, radius=0.02)
    slide.shapes.add_picture(str(path), Inches(px), Inches(py), Inches(pw), Inches(ph))
    return px, py, pw, ph


def label(slide, x, y, w, t, color=NAVY, size=12, align=PP_ALIGN.LEFT):
    text(slide, x, y, w, 0.3, [[(t.upper(), {"bold": True, "color": color, "size": size})]], align=align)


def fix_title(slide):
    t = shape_named(slide, "TextBox 6")
    if t is not None:
        t.left, t.top = Inches(0.78), Inches(0.30)


def footer(slide, n):
    """Date on the navy bar, slide counter on the orange bar (as on the template's slide 2).
    Never remove shapes by name here: python-pptx names new text boxes "TextBox <id-1>", so names
    of template shapes can collide with shapes we have just added."""
    text(slide, 0.17, 7.265, 3.0, 0.24, [[(DATE, {"color": WHITE, "size": 9})]], anchor=MSO_ANCHOR.MIDDLE)
    text(slide, 10.6, 7.265, 2.55, 0.24, [[(f"Slide {n} of {TOTAL}", {"color": WHITE, "size": 9, "bold": True})]],
         align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)


def notes(slide, t):
    slide.notes_slide.notes_text_frame.text = t


S = list(prs.slides)
SH = SCRATCH / "report" / "shots"
nlp, fc, los, ro, ot = M["nlp"], M["forecast"]["metrics"], M["los"], M["roster"], M["ot"]

# ================================================================== 1  title
s = S[0]
set_text(shape_named(s, "TextBox 4"), "Idea Lab")
tb = shape_named(s, "TextBox 28")
set_text(tb, "COURSE CODE")
p2 = tb.text_frame.add_paragraph()
p2.alignment = PP_ALIGN.CENTER
r2 = p2.add_run()
r2.text = "________"
r2.font.size, r2.font.color.rgb = Pt(14), NAVY
title_tb = shape_named(s, "TextBox 6")
set_text(title_tb, "Multi-Agent AI Systems for Hospital Resource Optimization, Clinical Workflow Automation and Patient Care Coordination")
title_tb.height = Inches(1.0)
for r in title_tb.text_frame.paragraphs[0].runs:
    r.font.size = Pt(19)
shape_named(s, "Rectangle 7").top = Inches(2.62)
remove(s, "TextBox 33")
text(s, 3.58, 2.78, 8.6, 0.4, [[("MedOrchestra", {"bold": True, "color": NAVY, "size": 16}),
                               ("  —  Multi-Agent Hospital Intelligence Platform", {"color": MUTE, "size": 14})]])
text(s, 3.58, 3.45, 3.9, 3.4, [
    [("Team members & roll numbers", {"bold": True, "color": NAVY})],
    "________________  (Roll No. ______)",
    "________________  (Roll No. ______)",
    [("Guide / Mentor", {"bold": True, "color": NAVY})],
    "________________________",
    [("Department / School", {"bold": True, "color": NAVY})],
    "________________________",
    [("Academic year", {"bold": True, "color": NAVY})],
    "2026 – 27",
], size=13, space_after=3)
picture(s, HERE / "c_dashboard.png", 7.75, 3.4, 5.1, 3.55)
notes(s, "Introduce the team and the project: MedOrchestra, a working multi-agent AI platform for hospital operations "
         "built from our synopsis — nine specialised agents coordinated by an orchestrator, with humans approving every critical action.")

# ================================================================== 2  problem statement
s = S[1]
remove(s, "TextBox 5", "TextBox 13", "TextBox 19", "TextBox 25", "TextBox 31", "TextBox 36", "TextBox 37", "TextBox 39")
fix_title(s)
cards = [
    ("What problem are we addressing?", "Beds, ICU units, operation theatres, staff, diagnostics and pharmacy are coordinated through "
                                        "disconnected systems, phone calls and spreadsheets — so resources sit idle while patients wait."),
    ("Who is affected?", "Patients (delays, late escalation), doctors and nurses (hours of coordination work), and administrators "
                         "(no single, real-time view of hospital capacity)."),
    ("Current challenges", "Manual bed and staff allocation · long OPD queues · slow emergency mobilisation · deteriorating ward "
                           "patients noticed late · no demand forecasting · decisions without a recorded rationale."),
    ("Why is the problem important?", "In emergencies minutes decide outcomes; ICU beds and theatres are the costliest resources; "
                                      "clinicians’ time should go to care — and any AI used must stay safe, explainable and accountable."),
]
for i, (h, d) in enumerate(cards):
    x, y = 0.8 + (i % 2) * 6.1, 1.75 + (i // 2) * 2.2
    box(s, x, y, 5.85, 1.95, fill=NAVY_TINT if i in (0, 3) else WHITE, line=LINE)
    circle(s, x + 0.2, y + 0.22, 0.5, str(i + 1), fill=ORANGE if i == 2 else NAVY)
    text(s, x + 0.85, y + 0.25, 4.8, 0.4, [[(h, {"bold": True, "color": NAVY, "size": 16, "font": HEAD})]])
    text(s, x + 0.85, y + 0.72, 4.8, 1.15, d, size=12.5, color=INK)
box(s, 0.8, 6.2, 11.95, 0.8, fill=NAVY, radius=0.1)
text(s, 1.0, 6.2, 11.55, 0.8, [[("Core problem: ", {"bold": True, "color": RGBColor(0xFF, 0xB0, 0x85)}),
                               ("an intelligent, coordinated system is needed that optimises resources and automates workflows "
                                "through specialised AI agents — while qualified professionals keep control of critical decisions.",
                                {"color": WHITE})]], size=13.5, anchor=MSO_ANCHOR.MIDDLE)
footer(s, 2)
notes(s, "These are the problems from the synopsis. Emphasise the core problem: coordination across departments, with human oversight.")

# ================================================================== 3  existing solutions / literature
s = S[2]
remove(s, "TextBox 13", "TextBox 19", "TextBox 25", "TextBox 36", "TextBox 40", "TextBox 49")
fix_title(s)
cols = [("#", 0.8, 0.45), ("Existing solutions", 1.35, 3.2), ("Limitations", 4.65, 3.75), ("Our proposed approach", 8.5, 4.25)]
rows = [
    ("Hospital information systems (HIS / EHR modules)", "Departmental silos; bed boards updated by hand; no optimisation or cross-department coordination",
     "One data model for patients, resources and workflows, coordinated by an AI orchestrator"),
    ("Stand-alone scheduling / OR-planning tools [3]", "Solve one problem (e.g. roster or theatre list) in isolation, offline",
     "Agents share a blackboard; CP-SAT optimises beds, staff and theatres against live demand"),
    ("Paper NEWS2 charts & triage protocols [2]", "Manual scoring; late escalation; not linked to bed or ICU capacity",
     "Every observation NEWS2-scored; score ≥ 7 triggers alerts and an ICU-transfer proposal"),
    ("Single AI model / chatbot assistants", "Opaque, hard to validate, unsafe to act on clinical decisions [4]",
     "Nine explainable specialised agents + human-in-the-loop approval and audit trail"),
]
top = 1.6
for title, cx, cw in cols:
    box(s, cx, top, cw - 0.08, 0.42, fill=NAVY if title != "Our proposed approach" else ORANGE, radius=0.12)
    text(s, cx, top, cw - 0.08, 0.42, [[(title.upper(), {"bold": True, "color": WHITE, "size": 11.5})]], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
for i, (a, b, c) in enumerate(rows):
    y = top + 0.55 + i * 1.05
    box(s, 0.8, y, 11.95, 0.95, fill=NAVY_TINT if i % 2 == 0 else WHITE, line=LINE, radius=0.08)
    circle(s, 0.88, y + 0.23, 0.48, str(i + 1), fill=NAVY, size=13)
    text(s, 1.45, y + 0.1, 3.05, 0.78, [[(a, {"bold": True, "color": NAVY})]], size=12, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 4.72, y + 0.1, 3.6, 0.78, b, size=11.5, color=INK, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 8.57, y + 0.1, 4.05, 0.78, [[(c, {"color": INK})]], size=11.5, anchor=MSO_ANCHOR.MIDDLE)
box(s, 0.8, 6.4, 11.95, 0.7, fill=ORANGE_TINT, line=ORANGE, radius=0.1)
text(s, 1.0, 6.4, 11.6, 0.7, [[("Research gap: ", {"bold": True, "color": ORANGE}),
                              ("no system combines multi-agent coordination, constraint optimisation, early warning and human oversight "
                               "in one explainable workflow [1].", {"color": INK})],
                             [("[1] Wooldridge 2009 · [2] RCP NEWS2 2017 · [3] Cardoen et al. 2010 · [4] WHO 2021", {"color": MUTE, "size": 9.5})]],
     size=12.5, anchor=MSO_ANCHOR.MIDDLE, space_after=1)
footer(s, 3)
notes(s, "Compare existing approaches with ours; the gap is combining coordination, optimisation, early warning and human oversight.")

# ================================================================== 4  proposed solution
s = S[3]
remove(s, "TextBox 5", "TextBox 13", "TextBox 19", "TextBox 25", "TextBox 31", "TextBox 37", "TextBox 43")
fix_title(s)
items = [
    ("Project idea", "MedOrchestra — a hospital platform where staff describe a need in plain language and AI agents coordinate the response."),
    ("Proposed approach", "A central orchestrator understands the request (English or Hinglish), plans a workflow and dispatches eleven specialised "
                          "agents that share findings and negotiate over beds, staff, theatres, tests, ambulances and billing."),
    ("Key innovation", "Explainable recommendations with factor scores, constraint optimisation (OR-Tools CP-SAT), NEWS2-driven escalation "
                       "and a configurable human-in-the-loop approval gate."),
    ("Beyond the hospital walls", "108 ambulance dispatch with an emergency pre-alert during transport, automatic billing with PM-JAY "
                                  "packages, and a digital twin that answers capacity what-ifs before they happen."),
    ("Expected outcome", "Faster emergency coordination, shorter waits, better bed/theatre utilisation, earlier escalation and "
                         "less administrative work — with every decision audited."),
]
for i, (h, d) in enumerate(items):
    y = 1.5 + i * 1.09
    circle(s, 0.85, y + 0.03, 0.48, str(i + 1), fill=ORANGE if i in (2, 3) else NAVY, size=14)
    text(s, 1.5, y, 5.4, 0.34, [[(h, {"bold": True, "color": NAVY, "size": 15, "font": HEAD})]])
    text(s, 1.5, y + 0.36, 5.4, 0.78, d, size=11.5, color=INK)
# agent hub on the right
cx, cy = 9.9, 4.55
agents = ["Bed Mgmt", "Appointments", "Staff Scheduling", "Diagnostics", "Pharmacy", "Patient Care", "Emergency",
          "Resource Optimizer", "Billing & Insurance", "Ambulance 108", "Notification"]
import math
pos = []
for i, a in enumerate(agents):
    ang = -math.pi / 2 + i * 2 * math.pi / len(agents)
    pos.append((a, cx + 2.42 * math.cos(ang), cy + 2.08 * math.sin(ang)))
for _, x, y in pos:
    ln = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(cx), Inches(cy), Inches(x), Inches(y))
    ln.line.color.rgb, ln.line.width = RGBColor(0x9F, 0xB3, 0xCC), Pt(1.25)
hub = box(s, cx - 0.95, cy - 0.95, 1.9, 1.9, fill=NAVY, line=WHITE, shape=MSO_SHAPE.OVAL, line_w=3)
text(s, cx - 0.95, cy - 0.95, 1.9, 1.9, [[("AI", {"bold": True, "color": WHITE, "size": 15})], [("Orchestrator", {"bold": True, "color": WHITE, "size": 14})]],
     align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, space_after=0)
for a, x, y in pos:
    hot = a in ("Emergency", "Ambulance 108")
    box(s, x - 0.72, y - 0.24, 1.44, 0.48, fill=ORANGE_TINT if hot else NAVY_TINT, line=ORANGE if hot else NAVY, radius=0.18)
    text(s, x - 0.72, y - 0.24, 1.44, 0.48, [[(a, {"bold": True, "color": NAVY, "size": 9.5})]], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
label(s, 7.6, 6.75, 4.6, "Innovation: eleven cooperating, explainable agents", color=ORANGE, size=11, align=PP_ALIGN.CENTER)
footer(s, 4)
notes(s, "Instead of one big model we use eleven agents (eight from the synopsis plus Notification, Billing & Insurance and Ambulance Dispatch). They post findings on a shared "
         "blackboard and message each other with FIPA performatives such as PROPOSE and REFUSE.")

# ================================================================== 5  objectives
s = S[4]
remove(s, "TextBox 5", "TextBox 37", "TextBox 42", "TextBox 45", "TextBox 48", "TextBox 51", "TextBox 58")
fix_title(s)
objs = [
    ("Multi-agent platform", "Central orchestrator + eleven specialised agents on one patient / resource / workflow / finance data model."),
    ("Optimise resources", "Allocate beds, ICU, staff, theatres and equipment with constraint optimisation and demand forecasting."),
    ("Automate & coordinate", "Appointments, queues, diagnostics, pharmacy, emergency response, notifications and care pathways."),
    ("Keep humans in control", "Explainable recommendations, role-based approval, audit trail and a governance dashboard with model cards."),
]
for i, (h, d) in enumerate(objs):
    y = 1.55 + i * 0.98
    text(s, 0.8, y, 0.7, 0.5, [[(f"0{i + 1}", {"bold": True, "color": ORANGE, "size": 22, "font": HEAD})]])
    text(s, 1.55, y + 0.02, 5.6, 0.35, [[(h, {"bold": True, "color": NAVY, "size": 15.5})]])
    text(s, 1.55, y + 0.38, 5.6, 0.55, d, size=12, color=INK)
box(s, 0.8, 5.55, 6.4, 1.5, fill=NAVY_TINT, line=LINE)
text(s, 1.0, 5.63, 6.0, 0.3, [[("EXPECTED MEASURABLE TARGETS  →  ACHIEVED", {"bold": True, "color": NAVY, "size": 11})]])
targets = [
    ("Intent accuracy ≥ 85%", f"{nlp['accuracy'] * 100:.1f}%"), ("Occupancy forecast MAPE < 5%", f"{fc['bed_occupancy']['mape']}%"),
    ("Optimal roster < 5 s", f"{ro['wall_ms'] / 1000:.1f} s"), ("Critical actions human-approved", "100%"),
]
for i, (t, v) in enumerate(targets):
    x, y = 1.0 + (i % 2) * 3.05, 6.0 + (i // 2) * 0.48
    text(s, x, y, 3.0, 0.4, [[("✓ ", {"bold": True, "color": ORANGE}), (t + ": ", {"color": INK}), (v, {"bold": True, "color": NAVY})]], size=12)
# rising staircase 01–04
steps = [("01", "Platform"), ("02", "Optimise"), ("03", "Automate"), ("04", "Human control")]
for i, (n, t) in enumerate(steps):
    x = 7.75 + i * 1.28
    h = 1.2 + i * 1.02
    y = 6.95 - h
    box(s, x, y, 1.18, h, fill=NAVY if i % 2 == 0 else ORANGE, shape=MSO_SHAPE.RECTANGLE)
    text(s, x, y + 0.12, 1.18, 0.45, [[(n, {"bold": True, "color": WHITE, "size": 20, "font": HEAD})]], align=PP_ALIGN.CENTER)
    text(s, x + 0.05, y + 0.62, 1.08, 0.5, [[(t, {"bold": True, "color": WHITE, "size": 11})]], align=PP_ALIGN.CENTER)
footer(s, 5)
notes(s, "Four objectives condensed from the ten in the synopsis, with measurable targets and what we achieved.")

# ================================================================== 6  architecture / methodology
s = S[5]
remove(s, "TextBox 5", "TextBox 62", "Rectangle 41")
fix_title(s)
picture(s, HERE / "fig_arch_rbu.png", 0.8, 1.55, 6.3, 5.5)
label(s, 7.45, 1.95, 5.3, "Input → Processing → AI / Algorithm → Output", color=NAVY, size=12)
flow = [
    ("INPUT", "Natural-language requests · ER registrations · bedside vitals · bookings · live hospital data", NAVY),
    ("PROCESSING", "NLP intents & entities (TF-IDF + LR / Claude) → planner builds a dependency DAG of agent steps", NAVY),
    ("AI / ALGORITHM", "9 agents with CP-SAT, NEWS2, M/M/c queueing, Holt-Winters, Gradient Boosting; conflict resolution", ORANGE),
    ("OUTPUT", "Explainable recommendations · safe actions auto-executed · approvals for critical ones · alerts & dashboards", NAVY),
]
for i, (h, d, c) in enumerate(flow):
    y = 2.35 + i * 1.08
    box(s, 7.45, y, 1.55, 0.82, fill=c, radius=0.1)
    text(s, 7.45, y, 1.55, 0.82, [[(h, {"bold": True, "color": WHITE, "size": 11})]], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    box(s, 9.08, y, 3.67, 0.82, fill=NAVY_TINT if c == NAVY else ORANGE_TINT, line=LINE, radius=0.1)
    text(s, 9.18, y + 0.04, 3.5, 0.74, d, size=10.5, color=INK, anchor=MSO_ANCHOR.MIDDLE)
    if i < len(flow) - 1:
        a = s.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, Inches(8.1), Inches(y + 0.84), Inches(0.25), Inches(0.22))
        a.fill.solid(); a.fill.fore_color.rgb = ORANGE; a.line.fill.background(); no_shadow(a)
text(s, 7.45, 6.72, 5.3, 0.35, [[("Components: ", {"bold": True, "color": NAVY}),
                                ("software-only — FastAPI · React PWA · SQLite / PostgreSQL · WebSockets (no special hardware)", {"color": MUTE})]], size=10.5)
footer(s, 6)
notes(s, "Left: layered architecture from the synopsis. Right: the methodology as input → processing → AI → output. "
         "Every request follows the ten-step pipeline (intake, NLP, workflow, agent selection, coordination, constraints, "
         "recommendations, human approval, execution, logging).")

# ================================================================== 7  implementation
s = S[6]
remove(s, "TextBox 5", "TextBox 42", "TextBox 68")
fix_title(s)
impl = [
    ("Technologies used", "Python 3.11 · FastAPI · SQLAlchemy · React 19 + TypeScript · Tailwind · Recharts · WebSockets"),
    ("Hardware components", "None required — runs on any laptop / server; installable PWA for phones and tablets"),
    ("Software / tools", "SQLite (dev) / PostgreSQL (Docker) · OR-Tools · scikit-learn · NumPy · pytest · Docker Compose"),
    ("Algorithms / models", "NEWS2 triage · CP-SAT bed, roster & theatre optimisation · M/M/c queueing · Holt-Winters forecasting · "
                            "Gradient-Boosting length of stay · LACE readmission risk · Monte-Carlo digital twin · "
                            "TF-IDF + logistic-regression NLP with Hinglish normalisation (optional Claude)"),
    ("Prototype development", f"{V2['screens']} screens for 7 roles + public TV display & kiosk · {V2['agents']} agents + orchestrator · "
                              f"live simulator · {V2['tests']} automated tests passing with GitHub Actions CI"),
]
for i, (h, d) in enumerate(impl):
    y = 1.55 + i * 1.08
    circle(s, 0.8, y + 0.02, 0.45, str(i + 1), fill=ORANGE if i == 3 else NAVY, size=13)
    text(s, 1.42, y, 5.45, 0.33, [[(h, {"bold": True, "color": NAVY, "size": 15})]])
    text(s, 1.42, y + 0.36, 5.45, 0.7, d, size=11.5, color=INK)
label(s, 7.3, 1.62, 5.4, "Prototype / system image", color=ORANGE, size=12)
picture(s, HERE / "c_agents.png", 7.3, 1.98, 5.45, 4.75)
text(s, 7.3, 6.8, 5.45, 0.3, [[("AI Agent Console — live agent network, trace and plan for the ICU-admission request", {"italic": True, "color": MUTE})]],
     size=10, align=PP_ALIGN.CENTER)
footer(s, 7)
notes(s, "Implementation details. The image shows the AI Agent Console running the synopsis example; mention the 38 automated tests.")

# ================================================================== 8  results / prototype
s = S[7]
remove(s, "TextBox 5", "TextBox 16", "TextBox 25")
fix_title(s)
label(s, 0.8, 1.45, 10.5, "Screenshots", color=ORANGE, size=12)
shots = [("c_dashboard.png", "Command center"), ("c_ambulance.png", "108 dispatch & pre-arrival alert"), ("c_twin.png", "Digital twin what-if")]
for i, (f, cap) in enumerate(shots):
    x = 0.8 + i * 4.02
    picture(s, HERE / f, x, 1.8, 3.85, 2.4)
    text(s, x, 4.25, 3.85, 0.3, [[(cap, {"bold": True, "color": NAVY})]], size=11.5, align=PP_ALIGN.CENTER)
results = [
    (f"{nlp['accuracy'] * 100:.1f}%", f"intent accuracy held out ({CARD['cv_accuracy'] * 100:.0f}% cross-validated)"),
    (f"{fc['bed_occupancy']['mape']}%", f"bed-occupancy forecast MAPE (baseline {fc['bed_occupancy']['naive_seasonal_mape']}%)"),
    (f"−{round((1 - los['mae_days'] / los['baseline_mae_days']) * 100)}%", "length-of-stay error vs baseline"),
    (f"{ot['before']['overtime_minutes']}→{ot['after']['overtime_minutes']}", "theatre overtime (min) after CP-SAT"),
    (f"−{round(TW['recommendations'][0]['impact'] * 100)}%", f"ED pressure from the twin's best lever ({TW['recommendations'][0]['title'].lower()})"),
    (f"{V2['tests']} / {V2['tests']}", "automated tests passing"),
]
for i, (v, l) in enumerate(results):
    x, y = 0.8 + (i % 3) * 4.02, 4.72 + (i // 3) * 1.22
    box(s, x, y, 3.85, 1.08, fill=NAVY_TINT if i != 4 else ORANGE_TINT, line=LINE, radius=0.08)
    text(s, x + 0.2, y + 0.12, 0.35, 0.4, [[("✓", {"bold": True, "color": ORANGE, "size": 16})]])
    text(s, x + 0.55, y + 0.08, 3.2, 0.5, [[(v, {"bold": True, "color": NAVY, "size": 22, "font": HEAD})]])
    text(s, x + 0.55, y + 0.6, 3.2, 0.42, l, size=11, color=INK)
footer(s, 8)
notes(s, "Results measured by our evaluation script on the synthetic 108-bed hospital. They show correctness and feasibility; "
         "clinical effectiveness would need a real hospital study.")

# ================================================================== 9  innovation, impact, deliverables, future scope
s = S[8]
remove(s, "TextBox 5", "TextBox 13", "TextBox 19", "TextBox 25")
fix_title(s)
t6 = shape_named(s, "TextBox 6")
for r in t6.text_frame.paragraphs[0].runs:
    r.font.size = Pt(28)
rows9 = [
    ("★", "Innovation", "Explainable multi-agent orchestration · pre-arrival ambulance coordination that holds a bay during transport · "
                        "Monte-Carlo digital twin that recommends the best intervention · Hinglish copilot · configurable autonomy · "
                        "CP-SAT for beds, rosters and theatres"),
    ("↗", "Impact", "Faster emergency mobilisation and door-to-bay time · shorter OPD waits · theatre overtime removed · earlier escalation · "
                    "no missed charges and cashless PM-JAY claims · capacity planned before the surge · accountable AI with a governance dashboard"),
    ("✓", "Deliverables", f"Working web app + PWA ({V2['screens']} screens, 7 roles, public display & kiosk) · FastAPI backend with {V2['agents']} agents · "
                          f"{V2['tests']} automated tests + CI · project report · architecture docs & demo script · Docker deployment"),
    ("→", "Future scope", "HL7 FHIR / ABDM integration and real PM-JAY claim submission · IoT smart beds feeding the monitor · retraining and "
                          "recalibration on real hospital data · multi-hospital referral network · full Hindi interface"),
]
for i, (g, h, d) in enumerate(rows9):
    y = 1.85 + i * 1.3
    box(s, 0.8, y, 11.95, 1.15, fill=NAVY_TINT if i % 2 == 0 else WHITE, line=LINE, radius=0.08)
    circle(s, 0.98, y + 0.28, 0.6, g, fill=ORANGE if i == 0 else NAVY, size=18)
    text(s, 1.8, y + 0.1, 2.3, 0.95, [[(h, {"bold": True, "color": NAVY, "size": 17, "font": HEAD})]], anchor=MSO_ANCHOR.MIDDLE)
    text(s, 4.05, y + 0.1, 8.55, 0.95, d, size=12, color=INK, anchor=MSO_ANCHOR.MIDDLE)
footer(s, 9)
notes(s, "Highlight the innovations and the impact; list what we are submitting and where the project can go next.")

# ================================================================== 10  conclusion & references
s = S[9]
fix_title(s)
label(s, 0.8, 1.5, 5.8, "Conclusion", color=ORANGE, size=13)
text(s, 0.8, 1.9, 6.0, 3.6, [
    f"Built MedOrchestra — all 12 synopsis modules working end-to-end with {V2['agents']} cooperating AI agents.",
    "Proven algorithms (CP-SAT, NEWS2, queueing, forecasting, ML, discrete-event simulation) make every recommendation measurable and explainable.",
    "Safe by design: risk-tiered human approval, configurable autonomy and a complete audit trail.",
    "Extended it well beyond the synopsis: 108 pre-hospital coordination, billing with PM-JAY and insurer claims, a Monte-Carlo digital twin, "
    "an ICU central monitor, a Hinglish copilot, public waiting-room screens and an AI-governance dashboard.",
    "Limitation: synthetic data and simulated integrations — clinical validation is the next step.",
], size=13, bullets=True, space_after=7)
box(s, 0.8, 5.65, 6.0, 1.35, fill=NAVY, radius=0.08)
text(s, 1.0, 5.72, 5.6, 1.2, [[("Thank you — questions & live demo", {"bold": True, "color": WHITE, "size": 17, "font": HEAD})],
                             [("Login: admin / admin123 · doctor / doctor123 · nurse / nurse123 · patient / patient123", {"color": RGBColor(0xFF, 0xC9, 0xA8), "size": 11})]],
     anchor=MSO_ANCHOR.MIDDLE, space_after=4)
label(s, 7.3, 1.5, 5.4, "References", color=ORANGE, size=13)
refs = [
    "M. Wooldridge, An Introduction to MultiAgent Systems, 2nd ed., Wiley, 2009.",
    "Royal College of Physicians, National Early Warning Score (NEWS) 2, London, 2017.",
    "B. Cardoen, E. Demeulemeester, J. Beliën, “Operating room planning and scheduling: A literature review,” EJOR, 201(3), 2010.",
    "World Health Organization, Ethics and Governance of Artificial Intelligence for Health, 2021.",
    "L. V. Green, “Queueing analysis in healthcare,” in Patient Flow, Springer, 2006.",
    "P. R. Winters, “Forecasting sales by exponentially weighted moving averages,” Management Science, 6(3), 1960.",
    "J. H. Friedman, “Greedy function approximation: A gradient boosting machine,” Annals of Statistics, 29(5), 2001.",
    "L. Perron, V. Furnon, OR-Tools, Google — developers.google.com/optimization",
]
text(s, 7.3, 1.9, 5.45, 5.1, [[(f"[{i + 1}] ", {"bold": True, "color": NAVY}), (r, {"color": INK})] for i, r in enumerate(refs)], size=11, space_after=6)
footer(s, 10)
notes(s, "Conclude, mention the limitation honestly, then move to the live demo.")

prs.save(str(OUT))
print("saved", OUT, len(prs.slides), "slides")
