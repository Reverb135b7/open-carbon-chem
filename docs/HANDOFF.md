# OpenCarbonChem — Handoff (current state)

**Audience:** the next AI agent or developer picking this up cold.
**Last updated:** after the pre-publication audit. All eleven milestones of
`OpenCarbonChem Guide from Chatgpt.txt` are implemented in the working tree;
**239 tests pass** (`python -m pytest`).

Read in this order:

1. `OpenCarbonChem Guide from Chatgpt.txt` — the master handover (requirements, standards, ritual).
2. `docs/architecture.md` — plan of record: requirements F1–F15/N1–N7, schema, module specs, roadmap (§7).
3. This file — as-built state, APIs, what is genuinely unfinished, and workspace gotchas.

---

## 1. Status

| # | Milestone | State |
|---|-----------|-------|
| 1 | Requirements, architecture, standards mapping | Done (`docs/architecture.md`) |
| 2 | Database schemas and activity data | Done (`database/schema.sql`, `store.py`, `ActivityRecord`, synthetic dataset) |
| 3 | Emission factor DB and unit conversion | Done (`core/units.py`, `factors/`, provenanced seed CSV) |
| 4 | Core calculation engine | Done (`core/gwp.py`, `core/calc.py`, `core/inventory.py`) |
| 5 | Corporate GHG accounting | Done (`accounting/scope1-3`, `boundary`, `aggregate`, `comparison`) |
| 6 | Product Carbon Footprint | Done (`pcf/`: models, allocation, calculator) |
| 7 | Hotspot, sensitivity, Monte Carlo | Done (`analytics/`: hotspots, sensitivity, uncertainty) |
| 8 | Decarbonisation scenarios | Done (`scenarios/levers.py`, `scenarios/engine.py`) — **repaired this pass** |
| 9 | Streamlit interface | Done (`app/1_Overview.py` + `app/pages/1–11`) |
| 10 | Reporting, CLI, documentation | Done (`reporting/`, `cli.py`, `LICENSE`, `CONTRIBUTING.md`, docs) — **repaired this pass** |
| 11 | Final integration & publication | Done locally (CI workflow fixed, `LICENSE`, `CONTRIBUTING.md`, methodology/assumptions/data-dictionary/provenance/validation docs at repo root); **GitHub push not authorised yet** |

**Verified numbers** (illustrative seed factors, used as test expectations):

- 1000 kWh natural gas → **180 kg**; 1000 kWh grid electricity → **450 kg**; 1000 kg paper → **1200 kg**.
- Three-scope roll-up → **1830 kg** (`OrganizationReport.total_kg`).
- Full demo dataset (`data/activities_synthetic.csv`, resolved against `published_factors.csv`):
  Scope 1 **4,550,678.6 kg**, Scope 2 **423,082.5 kg**, Scope 3 **72,909.87 kg**, total
  **5,046.671 t** - reproduced by the CLI and `m11_demo.py`. The R-134a row is the 7.5 kg
  topped-up mass multiplied by the published 1300 kg CO2e/kg factor = **9,750 kg CO2e**
  (DEFRA top-up method, so the factor already embeds the GWP).
- Demo PCF (five stages, published factors) -> **1,788.10 kg CO2e per tonne**.
- Scenario baseline (gas 500 kWh + electricity 1000 kWh + paper 1000 kg + freight 2000 tkm +
  waste 1000 kg + limestone 1000 kg) → **2880 kg**; every lever's reduction is hand-checked in
  `tests/test_scenarios.py`.

---

## 2. What earlier passes fixed (context for odd-looking code)

These modules existed in commits but **had never been importable or tested**:

1. **`scenarios/engine.py` was a syntax error** (`//` comment), imported a non-existent
   `scenarios.models.AllocationRule`, referenced an undefined `InventoryEntry`, reached into
   `db._conn`, and stored `None` into a `NOT NULL` column. It was rewritten against
   `core/inventory.py` (`InventoryEntry`, `validate_entries`, `base_rows`) and the store now owns
   persistence (`save_scenario`, `save_scenario_results`, `list_scenario_results`).
2. **`cli.py`** used `from ..database import ...` (beyond the top-level package), imported
   `calculate_scope1` from `aggregate`, and passed the *activities* CSV path to the factor loader.
   Rewritten as a real three-scope thin client with exit codes 0/1/2.
3. **`reporting/`** imported `PDFExportError` (absent from `core/exceptions.py`), imported a
   non-existent `reporting.cli`, used `io` without importing it, imported streamlit for no reason,
   and passed `leftIndent` to `Paragraph` instead of a `ParagraphStyle`. All fixed;
   `ExcelExportError` / `PDFExportError` now subclass `ExportError`.
4. **New tests** for the repaired code: `tests/test_scenarios.py` (36), `tests/test_reporting.py` (7),
   `tests/test_cli.py` (8). Suite: 149 → 200 at that point, 239 after the audit below.

### 2.1 Pre-publication audit (this pass)

A full read of every module plus a click-through of every dashboard button found and fixed:

- `Quantity` arithmetic multiplied the *coherent base* value but kept the original unit, so
  `q(2, "km") * 3` was 6000 km; multiplication/division likewise double-scaled. Fixed and
  covered by regression tests.
- `tkm` was registered as 1000 kg·m; a tonne-kilometre is 1e6 kg·m. The error cancelled inside
  a single calculation (quantity and factor both used tkm) but broke every conversion between
  `tkm` and `t*km`.
- `compute_emissions_batch` paired every activity with every factor (cross product), dropped
  the error column it promised, and silently defaulted a missing scope to 1. It now pairs by
  position, requires equal lengths, and records or raises typed errors.
- `compute_emissions` now rejects an activity whose declared gas differs from the factor's gas
  (a CO2 factor can no longer stand in for a CH4 row).
- An unused `_compute_analytical_uncertainty` helper invented 10 %/30 % activity spreads and
  presented them as calculated uncertainty; deleted rather than shipped.
- The Excel "Quantity" column held the emission result and the factor value/GWP were absent;
  the audit sheet now carries the activity value, factor value/unit, GWP and GWP set.
- The PDF labelled scopes by list position, so a report without Scope 1 called Scope 2
  "Scope 1"; it now keys by scope number, says "not reported", uses the boundary document, stays
  inside WinAnsi, and refuses mismatched rows.
- `allocation_rules.stage` was `NOT NULL`, so a default (stage-less) rule raised an
  IntegrityError; the schema and a table-rebuild migration fix it. PCF rows now persist the
  allocation share and allocated kg, and `pcf_allocated_total_kg` matches `PCFResult.total_kg`.
- `ScopeResult` now refuses rows from another scope; `calculate_pcf` refuses a duplicate activity.
- Dashboard: page 2 could not import (`from src.opencarbonchem…` inside the connectors, now
  relative imports with lazy `requests`), every "save" wrote to a throwaway `:memory:` database,
  pages 4–6 called undefined loaders, page 5 used non-existent `Scope2Result` attributes, page 7
  passed a `factor__` keyword and a placeholder category, page 8 hit a genuine factor ambiguity
  (missing geography), page 9 built duplicate Monte Carlo names and passed an object where an id
  was required, and page 11 only pretended to generate reports. All are now real, verified
  calls; page 11 writes and offers the actual `.xlsx`/`.pdf`.

The dashboard page `app/pages/10_Decarbonisation_Scenarios.py` was rewritten (it used an undefined
`c4`, a concatenated CSV path, `to_factor=None`, and passed a CSV path as the GWP set). All eleven
pages now execute cleanly under `streamlit.testing.v1.AppTest`.

---

## 3. Layout

```
src/opencarbonchem/
├── core/        units.py gwp.py activity.py calc.py inventory.py exceptions.py
├── factors/     models.py registry.py data/{published,illustrative}_factors.csv
├── accounting/  base.py scope1.py scope2.py scope3.py boundary.py aggregate.py comparison.py
├── pcf/         models.py allocation.py calculator.py
├── analytics/   common.py hotspots.py sensitivity.py uncertainty.py
├── scenarios/   levers.py engine.py
├── reporting/   excel_workbook.py pdf_generator.py
├── database/    schema.sql store.py
└── cli.py
app/             1_Overview.py + pages/1–11
tests/           14 modules, 239 tests
docs/            architecture.md HANDOFF.md + connector/real-data notes
(root)           methodology_documentation.md assumptions_documentation.md data_dictionary.md
                 emission_factor_provenance_policy.md validation_protocol.md STATUS.md
data/            activities_synthetic.csv, raw/, synthetic/, exports/
```

---

## 4. API cheat sheet

```python
# Core
ActivityRecord(activity_id, scope=1|2|3, category, substance, quantity, unit, gas=None,
               methane_basis=None, geography="GLOBAL", data_type="primary"|"secondary",
               period_start=None, period_end=None, description="", notes="")
compute_emissions(activity, factor, gwp_set="AR6") -> EmissionResult   # audit row
InventoryEntry = tuple[ActivityRecord, EmissionFactor]
validate_entries(entries) / base_rows(entries, gwp_set)                # shared entry helpers
gwp(gas, gwp_set=..., methane_basis=...)  # AR6 default; AR5; AR6-ERRATA-2025

# Factors
registry = FactorRegistry.from_csv()            # packaged seed
registry.find(activity_category=, substance=, geography=, year=, gas=)
# Errors: MissingFactorError, AmbiguousFactorError, FactorScopeError, UnverifiedFactorError

# Accounting
calculate_scope1(activities, registry, *, gwp_set) -> ScopeResult
calculate_scope2(...) -> Scope2Result(.location, .market)
calculate_scope3(...) -> ScopeResult
OrganizationReport.from_results([scope_results])  # .total_kg/.total_t/.by_scope()/.by_category()/.by_gas()
                                                  # .reconcile() -> Reconciliation(.ok, .checks, .coverage_gaps)
OrganisationalBoundary(org_id, name, method, entities)  # .consolidate()/.document()
compare_periods(current, prior) -> PeriodComparison     # statuses: compared / new_in_current_year /
                                                       # missing_in_current_year; delta None, never fake -100 %

# PCF
ProductDefinition(...), InventoryItem(...), calculate_pcf(...)   # see pcf/__init__.py exports

# Analytics / scenarios
rank_emissions / report_hotspots / analyse_sensitivity / run_monte_carlo
apply_lever(lever, entries, *, gwp_set) -> ScenarioResult(name, lever, baseline_kg, scenario_kg,
                                                          reduction_kg, reduction_pct|None)
run_levers(entries, levers, *, gwp_set) -> (baseline, ...)      # dashboard/report order
compare_scenarios(baseline, alternative) -> dict               # reduction_kg / reduction_pct / status
persist_scenarios(db, run_id, results, period_id=None, *, gwp_set)   # run_id must be new

# Reporting / CLI
build_excel_report(report, rows, *, gwp_set, run_id, period_label) -> ExcelReport(.save/.save_to_bytes)
build_pdf_report(report, rows, *, gwp_set, run_id, period_label, organisation_name) -> PDFReport
python -m opencarbonchem.cli calculate --activities CSV --run-id ID [--out DIR] [--report-types excel pdf]
```

Errors all derive from `OpenCarbonChemError` (`core/exceptions.py`): unit, factor, GWP, boundary,
period, double-counting, PCF, allocation, scenario, uncertainty, analytics, reconciliation, export.

---

## 5. Genuinely remaining work

1. **GitHub publication (M11).** The repo is committed locally with a CI workflow; pushing needs the
   owner's explicit authorisation. Repository name per guide §11: `opencarbonchem`.
2. **Factors cover UK 2024-2026, not other regions.** `published_factors.csv` holds
   91 DESNZ rows for each of 2024, 2025 and 2026 generated from the flat-format workbooks, plus IPCC
   2006 defaults; overseas electricity and other regions still need published rows of their
   own. DEFRA CO2e factors keep their AR5 basis, so a report can mix AR5 combined values with
   AR6 gas conversions; reports that do so now carry a "Mixed GWP basis" warning
   (`docs/FACTOR_SOURCES.md`).
3. **Scenario result granularity.** `scenario_results.category` is currently written as `""` — one row
   per scenario totals. A per-category breakdown would need the lever output grouped by category.
4. **Connectors (DEFRA / EPA / Ecoinvent) are stubs.** They make no live fetch, hold no
   licensed data, and return an empty set when no packaged file exists. Page 2 labels them as
   stubs. A real integration needs licensing, provenance mapping and a cache snapshot.
5. **Dashboard verification is behavioural, not visual.** Every page and action button is
   exercised through `AppTest` and the resulting metrics/tables/files are checked, but chart
   rendering and layout are not asserted. Calculation logic is unit-tested in the package
   (by design, N3).
6. **Coverage gaps are advisory.** `OrganizationReport.reconcile().coverage_gaps` flags unreported
   scopes/categories for human review — it is not an error and never blocks a report.

---

## 6. Non-negotiable rules (guide §15/§16)

1. Milestone ritual: run tests, check calculation consistency, update `docs/architecture.md` §7 and
   `README.md`, list completed features and outstanding issues, commit working code.
2. Never fabricate data, factors, references or results. Synthetic data is labelled `SYNTHETIC`.
3. Fail safely: typed exceptions, no silent defaults, no cross-dimension conversion, no implicit
   methane basis. Never emit a number that cannot be re-derived from its audit row.
4. No untested feature claims: expected values in tests are computed by hand, not copied.
5. Dependency rule: `core/` imports nothing from `accounting/`, `pcf/`, `analytics/`, `scenarios/`,
   `reporting/`, `app/`. No UI imports inside the engine (reporting must not import streamlit).
6. No double counting: PCF rows shared with the corporate inventory are cross-checked
   (`DoubleCountingError` unless `excluded_from_corporate`).

---

## 7. Workspace gotchas (learned the hard way)

1. **`str_replace` is unreliable here** — it often answers "The file does not exist, skipping" for
   existing files. Use `write_file`, or a small Python patch script with an
   `if old not in src: raise SystemExit(...)` guard; delete the script afterwards.
2. **Writing over a CRLF file with no trailing newline can fail** ("Failed to apply patch"). Remove the
   file first (`rm`) and recreate it with `write_file`.
3. **Long heredocs get truncated** (~300+ lines) producing SyntaxErrors. Keep them short, or write a
   script file first.
4. **Backslashes inside heredoc patch strings get mangled** (`\r`, `\n` become real CR/LF). For regexes
   or byte literals, write the target file with `write_file` instead of patching via heredoc.
5. **Match anchors exactly** — several files are CRLF (`schema.sql`, `store.py`, `architecture.md`),
   others LF. Print `repr()` of the region before patching; else "anchor not found".
6. **Parametrised failure cases**: build the invalid object *inside* the test (lambda), otherwise the
   error fires at collection time. Missing constructor args raise `TypeError`, not the domain error.
7. **PDF text is not greppable as bytes** — ReportLab writes ASCII85 + Flate streams; decode
   (`a85decode` then `zlib.decompress`) if you need to assert on content (see `tests/test_reporting.py`).
8. Windows + Git Bash; Python 3.14.7; pytest 9.2.0. Run `python -m pytest` from the repo root.

---

## 8. Suggested next actions

1. `python -m pytest` → expect **239 passed**.
2. `python -m compileall -q src app` → clean.
3. `PYTHONPATH=src python -m opencarbonchem.cli calculate --activities data/activities_synthetic.csv
   --run-id demo --out /tmp/demo` → totals above plus an `.xlsx` and `.pdf`.
4. `streamlit run app/1_Overview.py` for the dashboard.
5. Decide with the owner about publishing (M11) and about sourcing real, provenanced factors.

*End of handoff. Keep §1 and the roadmap in `docs/architecture.md` current as you work.*
