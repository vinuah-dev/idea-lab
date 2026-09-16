# Document build scripts

These scripts regenerate the submission deliverables in `docs/` from the **running application**, so the
figures and numbers in the report and the slides always match the code.

| Script | Produces |
|---|---|
| `metrics.py` | Core evaluation metrics (NLP, forecasting, LOS, rosters, bed allocation, theatres) → `metrics.json` |
| `metrics_v2.py` | Extended metrics (model cards, digital twin, billing, dispatch, readmission) → merged into `metrics.json` |
| `shots.js` | Application screenshots → `docs/figures/screenshots/` (drives Chrome over the DevTools protocol) |
| `diagram.html` | Mermaid diagrams (architecture, pipeline, sequence, ER, DFDs, use cases, HITL, escalation) → `docs/figures/diagrams/` |
| `build_report.js` | `MedOrchestra_Project_Report.docx` (convert to PDF with Word) |
| `build_ppt.js` | `MedOrchestra_Presentation.pptx` (21 slides) |
| `build_rbu.py` | `MedOrchestra_Presentation_RBU.pptx` — fills the institute template (`template.pptx` + `c_*.png` screenshots) |

## Prerequisites

```bash
npm install docx pptxgenjs puppeteer-core     # for build_report.js / build_ppt.js / shots.js
pip install python-pptx lxml pillow pymupdf   # for build_rbu.py and PDF page checks
```

## Regenerating everything

```bash
# 1. start the app so the scripts can read live data (backend serves the built frontend on :8000)
cd frontend && npm run build && cd ../backend && uvicorn app.main:app --port 8000

# 2. metrics and screenshots
python docs/build/metrics.py
python docs/build/metrics_v2.py
node   docs/build/shots.js            # optional: node shots.js '[{"p":"/billing","f":"billing","h":1200}]'

# 3. documents
node   docs/build/build_report.js  docs/MedOrchestra_Project_Report.docx
node   docs/build/build_ppt.js     docs/MedOrchestra_Presentation.pptx
python docs/build/build_rbu.py     docs/MedOrchestra_Presentation_RBU.pptx
```

The `.docx` is converted to PDF with Word (update the table of contents first, because chapter pagination
changes with the content). `build_rbu.py` needs the institute template and its cropped screenshots, which
live next to it when the deck is regenerated.

Notes:
- The scripts read paths relative to their own folder; keep `metrics.json` beside them.
- `shots.js` uses Chrome (headless Edge does not produce screenshots on this machine); override with
  `SHOT_BROWSER=<path to chrome/edge>`.
- Numbers in the report and slides come from `metrics.json` — never hand-edit them; re-run the metric
  scripts instead so the document and the code cannot drift apart.
