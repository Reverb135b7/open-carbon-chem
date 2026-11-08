# OpenCarbonChem — System Requirements, Architecture and Implementation Roadmap

Status: Milestone 1 deliverable (plan of record).
Source of requirements: `OpenCarbonChem Guide from Chatgpt.txt` (master project handover).

This document defines what OpenCarbonChem must do, how the system is structured,
how data is persisted, what each module specifies, and the milestone roadmap.
Implementation follows this plan incrementally; no feature is claimed until it
is tested.

---

## 1. System requirements

### 1.1 Functional requirements

| ID | Requirement |
|----|-------------|
| F1 | Manage activity data (fuel, energy, materials, transport, waste) with explicit units, periods, geography and primary/secondary data flag. |
| F2 | Maintain an emission-factor (EF) database where every record carries full provenance: ID, category, substance, value, unit, gas coverage, geography, reporting year, source organisation, source reference, version, uncertainty and notes. |
| F3 | Convert units dimensionally; never silently apply an incompatible conversion. |
| F4 | Compute gas-specific emissions `E = Activity Data × Emission Factor` and CO2e via `E_CO2e = Σ E_g × GWP_g` using a selected, documented GWP set. |
| F5 | Corporate GHG inventory: Scope 1 (stationary, mobile, fugitive, process), Scope 2 (purchased electricity/steam/heat/cooling, location- and market-based), Scope 3 (all 15 GHG Protocol categories). |
| F6 | Product carbon footprint: product definition, functional unit, system boundary (cradle-to-gate / cradle-to-grave), life-cycle inventory, allocation, PCF = attributable emissions / functional unit output. |
| F7 | Prevent double counting between corporate inventory and PCF; record which emissions are reported where. |
| F8 | Allocation methods (mass, economic, physical causality) with transparent, selectable bases. |
| F9 | Hotspot analysis: emissions by material, process, energy source, scope; product intensity. |
| F10 | Sensitivity analysis on key parameters (EF, sourcing, yield, transport, fuel, packaging). |
| F11 | Monte Carlo uncertainty: configurable distributions, reproducible seed, mean/median/std/percentiles, contribution analysis. |
| F12 | Decarbonisation scenarios: renewable electricity, efficiency, fuel switching, material substitution, waste, process and transport optimisation; baseline vs scenario comparison with absolute and % reduction. |
| F13 | Streamlit dashboard with 11 pages (Overview → Report Generation), interactive charts, downloadable results. |
| F14 | PDF and Excel report generation that reconciles with calculation records. |
| F15 | Synthetic sample datasets for demonstration, clearly labelled as synthetic. |

### 1.2 Non-functional requirements

| ID | Requirement |
|----|-------------|
| N1 | Scientific correctness: values traceable to published sources (IPCC, national grid factors, government datasets); no invented factors presented as official. |
| N2 | Fail-safe behaviour: incomplete or invalid data raises a typed exception from the `OpenCarbonChemError` hierarchy; never silently emit a number. |
| N3 | Calculation engine independent of UI; UI and CLI are thin clients. |
| N4 | Reproducibility: fixed seeds for stochastic methods; results carry the factor ID, GWP set and version used. |
| N5 | Auditable: every result row references the activity record and factor record that produced it. |
| N6 | Modular package under `src/opencarbonchem/`; no single-file application. |
| N7 | Automated tests for calculations, units, GWP, scope classification, PCF, allocation, uncertainty, scenarios and report reconciliation. |

### 1.3 Standards and frameworks referenced

- GHG Protocol Corporate Standard (Scopes 1/2/3, location vs market-based Scope 2).
- GHG Protocol Scope 3 Technical Guidance (15 categories).
- GHG Protocol Product Standard / ISO 14067 (PCF).
- ISO 14064-1 (organisational inventory), ISO 14044 (allocation, LCA principles).
- IPCC assessment reports for GWP values (AR6 default, AR5 legacy, AR6 2025 errata).

Conformity/certification is **not** claimed; the software implements calculation
methodologies consistent with these frameworks.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Presentation layer                                              │
│   app/pages/* (Streamlit, milestone 9)   cli.py (thin CLI)      │
├─────────────────────────────────────────────────────────────────┤
│ Application services                                            │
│   accounting/  (scope1, scope2, scope3)                         │
│   pcf/         (product definition, inventory, allocation)      │
│   analytics/   (hotspots, sensitivity, Monte Carlo)             │
│   scenarios/   (baseline vs decarbonisation levers)             │
│   reporting/   (PDF, Excel, reconciliation)                     │
├─────────────────────────────────────────────────────────────────┤
│ Core engine (UI-free)                                           │
│   core/units.py     dimensional unit registry & Quantity         │
│   core/gwp.py       GWP sets (AR6 / AR6-errata / AR5)           │
│   core/activity.py  ActivityRecord model                        │
│   core/calc.py      E = AD × EF, CO2e assembly, EmissionResult  │
│   factors/          EmissionFactor model + FactorRegistry       │
├─────────────────────────────────────────────────────────────────┤
│ Persistence                                                     │
│   database/schema.sql   SQLite DDL (activities, factors,        │
│                         results, periods, scenarios, PCF)       │
│   database/store.py     typed CRUD over SQLite                  │
│   factors/data/*.csv    packaged factor seeds (provenanced)     │
└─────────────────────────────────────────────────────────────────┘
```

Dependency rule: arrows point downward only. `core/` imports nothing from
`accounting/`, `pcf/`, `analytics/`, `scenarios/`, `reporting/` or `app/`.

### 2.1 Calculation contracts

```
E_g      = AD × EF_g                       (dimensionally validated)
E_CO2e   = Σ_g (E_g × GWP_g)               (selected GWP set, explicit CH4 basis)
PCF      = Σ attributable life-cycle CO2e / functional-unit output
Reduction      = Baseline − Scenario
Reduction (%)   = Reduction / Baseline × 100
```

Before multiplication, `dimension(AD) × dimension(EF)` must equal mass; otherwise
`IncompatibleUnitError` is raised. Results are stored in kg and presented in t/kt.

### 2.2 No-double-counting rule

Each emission record carries `scope`, `category` and (for PCF) `stage`. A PCF
calculation declares which corporate categories its stages map to; the
reconciliation check raises `DoubleCountingError` if the same contribution is
reported in both an included corporate total and a PCF total without an explicit
`excluded_from_corporate` flag.

---

## 3. Database schema (SQLite)

```
organizations ─┬─< facilities
               └─< reporting_periods ─┬─< activity_data ─< calculation_results >─ emission_factors
                                       └─< calculation_runs ─< scenario_results >─ scenarios
 emission_factors (canonical copy, provenance columns)
 gwp_values       (gas, basis, gwp_set, value, reference)
 pcf_definitions ─< pcf_inventory ─< allocation_rules
```

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `organizations` | Reporting entity, boundary method | id, name, boundary_method, consolidation |
| `facilities` | Sites within boundary | id, org_id, name, geography, industry |
| `reporting_periods` | Reporting year/window | id, org_id, label, start_date, end_date |
| `activity_data` | Primary/secondary activity records | id, period_id, scope, category, substance, quantity, unit, gas, methane_basis, geography, data_type, notes |
| `emission_factors` | Full provenance per §6 of the handover guide | factor_id, activity_category, substance, value, unit, gas, geography, reporting_year, source_org, source_reference, version, uncertainty_pct, review_status, notes |
| `gwp_values` | GWP sets with references | gwp_set, gas, methane_basis, value, reference |
| `calculation_runs` | One engine execution (audit header) | id, period_id, gwp_set, created_at |
| `calculation_results` | Row-level audit trail | id, run_id, activity_id, factor_id, scope, category, gas, emissions_kg, gwp, co2e_kg |
| `scenarios` / `scenario_results` | Decarbonisation scenarios | id, name, lever, delta params; results per run |
| `pcf_definitions` / `pcf_inventory` / `allocation_rules` | Product carbon footprint | functional unit, boundary, stages, allocation method |

DDL: `src/opencarbonchem/database/schema.sql` (idempotent `IF NOT EXISTS`).

---

## 4. Module specifications

### 4.1 `core/units.py` (implemented)
- `Dimension`, `Unit`, `UnitRegistry`, `Quantity`, `parse_unit`, `convert`.
- Conversion only between identical dimensions; crossing dimensions requires an
  explicitly registered factor else `IncompatibleUnitError`.
- Ambiguous symbols (`ton`) are rejected; non-USD currency requires an
  explicitly configured exchange rate (`CurrencyError` otherwise).

### 4.2 `core/gwp.py` (implemented)
- `GWPSet` (name, source, reference, values), `gwp(gas, gwp_set=, methane_basis=)`,
  `to_co2e(...)`, `get_gwp_set(name)`.
- Sets: `AR6` (default; IPCC AR6 WGI 2021 Table 7.15/7.SM.7, includes
  carbon-cycle response; CH4 split 29.8 fossil / 27.0 non-fossil),
  `AR6-ERRATA-2025` (IPCC errata 7 Oct 2025), `AR5` (AR5 WGI Table 8.7 without
  feedbacks: CH4 28, N2O 265 — legacy frameworks).
- CH4 lookup requires an explicit `methane_basis` when the selected set splits
  the origin; otherwise `MissingGWPError`. No silent default.

### 4.3 `core/activity.py` (implemented)
- `ActivityRecord`: id, description, scope (1|2|3), category, substance,
  quantity, unit, gas, methane_basis, geography, data_type (primary|secondary),
  period_start/period_end, notes. Validated by Pydantic; invalid data fails at
  construction.

### 4.4 `core/calc.py` (implemented)
- `compute_emissions(activity, factor, gwp_set=) -> EmissionResult`.
- Validates category/substance agreement (`FactorScopeError`) and dimensional
  closure to mass (`IncompatibleUnitError`).
- `EmissionResult` records activity value/unit, factor value/unit, factor ID,
  emissions_kg, GWP, gwp_set, co2e_kg — a complete audit row.

### 4.5 `factors/` (implemented)
- `EmissionFactor` (Pydantic): all provenance fields of handover §6;
  `review_status ∈ {illustrative, published, verified}`; `value > 0`.
- `FactorRegistry`: in-memory index with deterministic resolution:
  category + substance match → gas constraint (explicit gas, or unambiguous if
  omitted) → geography (exact beats `GLOBAL`) → year (nearest at-or-before
  reporting year). Failures raise `MissingFactorError` / `AmbiguousFactorError`.
- Seed CSV `factors/data/illustrative_factors.csv`: every row labelled
  `review_status=illustrative`, `source_org=SYNTHETIC`, for software testing
  only — not to be presented as official factors.

### 4.6 `accounting/` (scope 1/2/3 implemented; reconciliation pending)
- `scope1.py`: subcategories stationary/mobile/fugitive/process; validates scope
  and category (`BoundaryError`), aggregates by category and gas.
- `scope2.py`: purchased electricity/steam/heat/cooling; location-based always,
  market-based only when explicit contract/residual-mix factors are supplied
  (never falls back silently to grid average).
- `scope3.py`: full 15-category catalogue (number, name, direction,
  applicability, typical data) + generic calculation keyed `s3_cat01..s3_cat15`.
- `ScopeResult`: row-level results plus `total_kg`, `total_t`, `by_category`,
  `by_gas`.

### 4.7 Pending modules (specified, not yet implemented)
- `pcf/`: product definition, functional unit, boundary, inventory assembly,
  allocation (mass/economic/physical), cradle-to-gate & cradle-to-grave.
- `analytics/`: hotspots, one-at-a-time sensitivity, Monte Carlo (seeded,
  distributions, percentiles, contribution analysis).
- `scenarios/`: lever implementations (renewables, efficiency, fuel switching,
  substitution, waste, process, transport), baseline/scenario diff.
- `reporting/`: ReportLab PDF, openpyxl Excel, reconciliation check.
- `app/`: 11-page Streamlit dashboard.
- `database/store.py`: typed CRUD (schema already defined).

---

## 5. Error model (fail-safe policy)

All errors derive from `OpenCarbonChemError` (`core/exceptions.py`):
units (`UnitError` family), factors (`FactorError` family), GWP (`GWPError`),
boundaries (`BoundaryError`, `PeriodError`, `DoubleCountingError`,
`AllocationError`), analytics (`ScenarioError`, `UncertaintyError`,
`ReconciliationError`, `ExportError`).

Rules:
1. Never return `None` or a default where a number is expected.
2. Never apply a conversion across dimensions without an explicit registered
   factor.
3. Never select a factor whose provenance is incomplete.
4. Never pick a GWP basis implicitly for methane when the set distinguishes it.
5. Never claim a feature as implemented without a passing test.

---

## 6. Testing strategy

- `tests/test_units.py` — conversions, incompatible units, ambiguous/unknown
  symbols, compound parsing, currency rule.
- `tests/test_gwp.py` — AR6/AR5/errata values, CH4 basis enforcement, errors.
- `tests/test_calc.py` — hand-computed `E = AD × EF` and CO2e cases, dimension
  closure, mismatched activity/factor rejection.
- `tests/test_factors.py` — CSV provenance completeness, precedence
  (geography/gas/year), missing/ambiguous errors.
- `tests/test_accounting.py` — scope classification, Scope 1 aggregation,
  Scope 2 location vs market, 15 Scope 3 categories.
- `tests/test_database.py` — schema init, activity, result and boundary round-trips.
- `tests/test_boundary.py`, `test_aggregate.py`, `test_comparison.py` — boundary
  consolidation, organisation roll-up/reconciliation, reporting-year comparison.
- `tests/test_pcf.py` — product definition, stage/boundary rules, allocation,
  double-counting guard.
- `tests/test_analytics.py` — hotspots, tornado sensitivity, Monte Carlo
  reproducibility and percentiles.
- `tests/test_scenarios.py` — all seven levers with hand-computed reductions,
  adverse (negative-reduction) results, zero-baseline guard, persistence.
- `tests/test_reporting.py` — Excel/PDF generation and the reconciliation guard.
- `tests/test_cli.py` — CSV loading, three-scope roll-up, exit codes.
- Expected values are calculated independently (by hand) in the test, not
  copied from the implementation.

---

## 7. Roadmap (milestones from handover §15)

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Requirements, architecture, standards mapping | **Done** (this document) |
| 2 | Database schemas and activity data management | **Done** (schema.sql, store, ActivityRecord, synthetic dataset) |
| 3 | Emission factor database and unit conversion | **Done** (unit engine, FactorRegistry, provenanced seed CSV) |
| 4 | Core calculation engine | **Done** (GWP sets, E = AD × EF, CO2e, audit results, tests) |
| 5 | Corporate GHG accounting | **Done** (Scope 1/2/3 catalogue, `OrganisationalBoundary` + consolidation, `OrganizationReport` reconciliation, `PeriodComparison`, boundary persistence) |
| 6 | Product Carbon Footprint | **Done** (stage catalogue + boundary rules, `ProductDefinition`, `InventoryItem`, mass/economic/physical-causality/none allocation, PCF = Σ attributable CO2e / reference flow, double-counting guard vs corporate report, SQLite persistence, 28 tests) |
| 7 | Hotspot, sensitivity and uncertainty analysis | **Done** (hotspot rankings by substance/category/scope/gas; one-at-a-time tornado sensitivity; Monte Carlo with seeded reproducibility, percentile ordering p5 ≤ median ≤ p95; variance-share contributions; >25 tests) |
| 8 | Decarbonisation scenario modelling | **Done** (7 levers as pure `entries -> entries` transforms; `apply_lever` / `run_levers` recompute both totals through the engine; `compare_scenarios` returns baseline/scenario/reduction; `reduction_pct = None` for a zero baseline; `ScenarioError` when a lever is invalid or matches no rows; persistence via `save_scenario` / `save_scenario_results`; 36 tests) |
| 9 | Streamlit interface | **Done** (11 pages, Overview → Report Generation, thin clients over the package API; all pages execute cleanly under `streamlit.testing` AppTest) |
| 10 | Reporting (PDF/Excel), documentation, full test suite | **Done** (Excel workbook with reconciliation guard, PDF executive summary, CLI entry point,
    LICENSE/CONTRIBUTING.md, methodology/assumptions/data-dictionary/provenance-policy/validation
    protocol docs; 125 tests passing) |
| 11 | Final integration and GitHub publication | **Done locally** (CI workflow, LICENSE, CONTRIBUTING, methodology/assumptions/data-dictionary/provenance/validation docs, notebooks/, reports/). Publishing to GitHub awaits the repository owner's authorisation. |

At the end of every milestone: run the test suite, check calculation
consistency, update this roadmap, list completed features and outstanding
issues, and commit working code.
