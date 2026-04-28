# MetaForge

> AI Evidence-Based Medicine Research Platform — 6 AI Agents collaborate to compress meta-analysis from 45-90 days to 1 hour

[![Python](https://img.shields.io/badge/python-3.9+-green.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-blue.svg)]()
[![Tests](https://img.shields.io/badge/tests-155%20passed-brightgreen.svg)]()
[![License](https://img.shields.io/badge/license-MIT-orange.svg)]()

## One-Line Definition

**MetaForge doesn't sell literature analysis tools — it sells meta-analysis results.** Input a research question, get a structured meta-analysis report with forest plots, funnel plots, and GRADE evidence ratings.

---

## Core Capabilities

### Complete Closed Loop — Input Data, Get Results

```
Input research data → Statistical analysis → Forest/Funnel/PRISMA → Subgroup/Sensitivity/Bias → CSV/JSON/LaTeX export
```

### Statistical Engine (Real Calculations)

| Feature | Method | Description |
|---------|--------|-------------|
| **Fixed Effect Model** | Mantel-Haenszel | Classic fixed effect meta-analysis |
| **Random Effects Model** | DerSimonian-Laird | Accounts for between-study heterogeneity |
| **Heterogeneity Test** | I², Q, τ² | Cochran's Q test |
| **Egger's Test** | Regression | Publication bias detection |
| **Begg's Test** | Rank correlation | Publication bias detection |
| **Trim-and-Fill** | Duval & Tweedie | Estimate missing studies and adjust effect |
| **Subgroup Analysis** | By study characteristics | Between-group difference test |
| **Sensitivity Analysis** | Leave-one-out | Impact of excluding each study |
| **Cumulative Meta-Analysis** | Progressive addition | Observe effect size evolution |
| **Meta-Regression** | Weighted least squares | Effect size vs covariate |
| **Dose-Response** | Linear + RCS spline | Non-linear dose-response modeling |
| **Network Meta-Analysis** | Graph-theoretical | Multi-treatment comparison with SUCRA ranking |
| **Continuous Data** | SMD (Hedges' g) / WMD | Mean difference analysis |
| **Forest Plot** | SVG generation | Publication-quality |
| **Funnel Plot** | SVG generation | Publication bias visualization |
| **Galbraith Plot** | Radial plot | Heterogeneity visualization |
| **L'Abbe Plot** | Treatment vs control | Event rate comparison |
| **PRISMA Flow Diagram** | SVG generation | PRISMA 2020 compliant |
| **Network Diagram** | SVG generation | NMA treatment network |
| **League Table** | SVG generation | All pairwise NMA comparisons |

### 34 API Endpoints

```
GET  /api/health              Health check
POST /api/analyze             Complete meta-analysis
POST /api/demo                Run demo dataset
POST /api/bias                Publication bias tests (Egger+Begg+TrimFill)
POST /api/cumulative          Cumulative meta-analysis
POST /api/prisma              PRISMA flow diagram
POST /api/forest              Forest plot
POST /api/funnel              Funnel plot
POST /api/galbraith           Galbraith (radial) plot
POST /api/labbe               L'Abbe plot
GET  /api/models              Statistical model list
POST /api/export/csv          CSV export
POST /api/export/json         JSON export
POST /api/upload/csv          CSV upload analysis
POST /api/meta_regression     Meta-regression
POST /api/dose_response       Dose-response analysis
POST /api/report/pdf          Printable HTML report
POST /api/nma/analyze         Network Meta-Analysis
POST /api/nma/network         NMA network diagram
POST /api/nma/league          NMA league table
GET  /api/nma/demo            NMA demo (oncology)
POST /api/ai/search           AI literature search
POST /api/ai/screen           AI screening
POST /api/ai/extract          AI data extraction
POST /api/register            User registration
POST /api/login               User login
POST /api/projects/save       Save project
GET  /api/projects/list       List projects
GET  /api/projects/{id}       Get project
POST /api/share               Create share link
GET  /api/shared/{token}      Access shared project
GET  /api/docs                Interactive API docs
```

### Web Workbench

- Interactive data input table
- 3 quick datasets (NSCLC PD-1 / Statins / Antihypertensives)
- CSV data import
- Real-time parameter switching (model/effect measure)
- Publication bias test panel
- Cumulative analysis charts
- Subgroup + sensitivity analysis
- CSV/JSON result export
- Ctrl+Enter shortcut
- Toast notifications

---

## Quick Start

```bash
git clone https://github.com/MoKangMedical/metaforge.git
cd metaforge
pip install -r requirements.txt
python3 -m uvicorn app.main:app --port 8000
```

Open:
- `http://localhost:8000` → Landing Page
- `http://localhost:8000/app` → Web Workbench
- `http://localhost:8000/api/docs` → API Documentation

---

## Running Tests

```bash
pip install pytest httpx
python3 -m pytest tests/ -v
```

155 tests covering:
- Statistical engine (dichotomous + continuous data)
- All bias tests (Egger, Begg, Trim-and-Fill)
- Meta-regression and dose-response
- Network Meta-Analysis
- All API endpoints

---

## Technical Architecture

```
metaforge/
├── app/
│   ├── main.py              # FastAPI backend (34 endpoints + full engines)
│   ├── templates/
│   │   └── app.html         # Web workbench (interactive UI)
│   ├── agents/              # AI Agent system (Seeker, Filter, Extractor)
│   ├── engines/             # Cochrane-compliant engines
│   ├── stats/               # Statistical modules
│   └── assessment/          # ROB2 bias assessment
├── tests/
│   ├── test_engine.py       # 113 unit tests for MetaAnalysisEngine
│   ├── test_nma.py          # 24 unit tests for NMAEngine
│   └── test_api.py          # 18 integration tests for API
├── docs/                    # GitHub Pages documentation
│   ├── index.html           # Landing page
│   ├── features.html        # Feature breakdown
│   ├── pricing.html         # Pricing plans
│   ├── api.html             # API documentation
│   └── about.html           # About page
├── assets/figures/          # Publication-quality charts
├── css/style.css            # Design system
├── requirements.txt         # Dependencies
└── README.md
```

---

## GitHub Pages

Documentation: [mokangmedical.github.io/metaforge](https://mokangmedical.github.io/metaforge/)

---

## License

MIT License
