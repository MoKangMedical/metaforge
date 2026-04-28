# Changelog

All notable changes to MetaForge are documented here.

## [4.0.0] — 2026-04-28

### Added
- **Network Meta-Analysis (NMA) engine** — graph-theoretical approach with Bucher indirect comparison, SUCRA ranking, consistency assessment, network diagram SVG, and league table SVG
- **Continuous data support** — SMD (Hedges' g) and WMD (Weighted Mean Difference) for mean/SD data
- **Galbraith (radial) plot** — heterogeneity visualization
- **L'Abbe plot** — treatment vs control event rate comparison
- **Comprehensive test suite** — 155 tests (113 engine + 24 NMA + 18 API)
- **AI Agent endpoints** — /api/ai/search, /api/ai/screen, /api/ai/extract
- **User system** — registration, login, session management
- **Project management** — save, list, get projects
- **Collaboration** — share links with access tracking
- **4 new NMA API endpoints** — /api/nma/analyze, /api/nma/network, /api/nma/league, /api/nma/demo
- **2 new visualization endpoints** — /api/galbraith, /api/labbe
- **GitHub Pages docs** — 5 professional pages (index, features, pricing, api, about)

### Changed
- API version bumped to v4.0.0
- Total API endpoints: 12 → 34
- Total codebase: 10,354 → 14,403 lines
- README completely rewritten with full feature table and API reference

## [3.0.0] — 2026-04-15

### Added
- Meta-regression analysis
- Dose-response analysis (linear + restricted cubic spline)
- Trim-and-fill publication bias adjustment
- Cumulative meta-analysis
- Printable HTML report generation
- Interactive API documentation page

## [2.0.0] — 2026-04-01

### Added
- Egger's regression test for publication bias
- Begg's rank correlation test
- Subgroup analysis
- Sensitivity analysis (leave-one-out)
- CSV upload endpoint
- Web workbench with 3 quick datasets

## [1.0.0] — 2026-03-15

### Added
- Initial release
- Fixed effect (Mantel-Haenszel) and random effects (DerSimonian-Laird) models
- Forest plot SVG generation
- Funnel plot SVG generation
- PRISMA 2020 flow diagram
- Landing page with dark sci-fi theme
- CSV/JSON export
