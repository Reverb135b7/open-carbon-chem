# OpenCarbonChem — Handoff for Milestones 6–11

**Audience:** the next AI agent (or developer) picking up this project with zero prior context.
**Status of this handoff:** written after Milestone 5 completion. Milestones 1–5 are done;
**97 tests pass** (`python -m pytest` → `97 passed in 0.76s`). Nothing is committed to git yet.

**Read these three files first, in this order:**

1. `OpenCarbonChem Guide from Chatgpt.txt` — the master project handover (requirements, standards, milestone ritual). It is the source of truth for *what* to build.
2. `docs/architecture.md` — the plan of record produced in Milestone 1 (requirements IDs F1–F15/N1–N7, schema, module specs, roadmap table in §7).
3. This file — current state, APIs, conventions, gotchas, and detailed specs for the remaining milestones.

---

## 1. Project snapshot

**OpenCarbonChem** — open-source carbon accounting and sustainability analytics engine for
chemical/process industries. Two workflows sharing one calculation engine:

- **A. Corporate GHG accounting** — Scope 1/2/3 (all 15 GHG Protocol categories), organisational
  boundaries, reporting-year comparisons. *(Done — Milestone 5.)*
- **B. Product Carbon Footprint (PCF)** — product definition, functional unit, system boundary,
  life-cycle inventory, allocation, PCF per ISO 14067 / PAS 2050. *(Not started — Milestone 6.)*

**Stack (already declared in `pyproject.toml`):** Python ≥3.11 (env runs 3.14.7), pydantic,
pandas, numpy, scipy, plotly, streamlit, reportlab, openpyxl; dev: pytest, pytest-cov, ruff.
The calculation engine is UI-free; the UI/CLI are thin clients (N3).

**Run tests:** from the project root — `python -m pytest` (pyproject sets
`pythonpath = ["src"]`, `testpaths = ["tests"]`, `addopts = "-q --strict-markers"`, markers
`unit` / `integration` / `e2e`). No install step is required for tests.

**Verified demo numbers** (synthetic data, hand-checked in tests):
- 1000 kWh natural gas → **180 kg** Scope 1 (EF = 0.18 kg/kWh, seed row `EF-ILL-001`)
- 1000 kWh grid electricity → **450 kg** Scope 2 location-based (EF = 0.45 kg/kWh)
- 1000 kg paper → **1200 kg** Scope 3 cat. 1 (EF = 1.2 kg/kg)
- Rollup total = **1830 kg** (`OrganizationReport.total_kg`)
- Full demo dataset: Scope 1 = 4,543.608 t, Scope 2 (location) = 910 t, Scope 3 = 82 t CO2e.

---

## 2. Non-negotiable rules (from guide §15/§16 — do not violate)

1. **Milestone ritual** — at the end of every milestone: run automated tests, check calculation
   consistency, update `docs/architecture.md` roadmap (§7), list completed features, identify
   outstanding issues, commit working code.
2. **Never fabricate** data, emission factors, standards references or calculation results.
   The only factor seed is `src/opencarbonchem/factors/data/illustrative_factors.csv` — every row
   is `review_status=illustrative`, `source_org=SYNTHETIC`, for software testing only. New synthetic
   data must be labelled `SYNTHETIC` in notes/IDs.
3. **Fail safely** — invalid/incomplete data raises a typed exception from the
   `OpenCarbonChemError` hierarchy; never return `None`/defaults where a number is expected, never
   silently convert across dimensions, never pick a methane GWP basis implicitly.
4. **No untested feature claims** — a feature counts as implemented only when a passing test
   exists with independently (hand-)computed expected values.
5. **Dependency rule** — `core/` imports nothing from `accounting/`, `pcf/`, `analytics/`,
   `scenarios/`, `reporting/`, `app/`. Arrows point downward only.
6. **No double counting** — PCF and corporate inventory must stay consistent; each emission
   carries `scope`, `category` and (for PCF) `stage`; the double-counting check raises
   `DoubleCountingError` unless an emission is explicitly flagged `excluded_from_corporate`.
7. **Do not attempt the whole project in one pass** — one milestone at a time, tests green before
   moving on.

---

## 3. Repository map (what exists today)

```
OpenCarbonChem/
├── OpenCarbonChem Guide from Chatgpt.txt   # master handover (read first)
├── README.md                               # updated through M5 (roadmap, features)
├── pyproject.toml                          # deps, entry point, pytest config
├── .gitignore
├── data/
│   ├── activities_synthetic.csv            # demo activities (SYNTHETIC)
│   ├── raw/  synthetic/  exports/          # data staging dirs
├── docs/
│   ├── architecture.md                     # plan of record; roadmap §7
│   └── HANDOFF.md                          # this file
├── src/opencarbonchem/
│   ├── core/        units.py, gwp.py, activity.py, calc.py, exceptions.py   [DONE]
│   ├── factors/     registry.py + data/illustrative_factors.csv             [DONE]
│   ├── accounting/  scope1-3.py, base.py, boundary.py, aggregate.py,
│   │                comparison.py                                            [DONE]
│   ├── database/    schema.sql, store.py                                     [DONE]
│   ├── pcf/         (EMPTY — Milestone 6)
│   ├── analytics/   (EMPTY — Milestone 7)
│   ├── scenarios/   (EMPTY — Milestone 8)
│   ├── reporting/   (EMPTY — Milestone 10)
│   └── __init__.py
├── tests/            test_units, test_gwp, test_calc, test_factors,
│                     test_accounting, test_database, test_boundary,
│                     test_aggregate, test_comparison  → 97 tests passing
└── app/              (does not exist — Milestone 9)
```

**Missing vs the guide's target structure (§11):** `app/`, `notebooks/`, `reports/`,
`LICENSE`, `CONTRIBUTING.md`, methodology/assumptions/data-dictionary/provenance-policy/
validation-protocol docs. Note the four package dirs `pcf/ analytics/ scenarios/ reporting/`
exist but are **empty — they have no `__init__.py`**; create the package files when you
implement them.

**Known broken/loose ends:**

- `pyproject.toml` declares the console script `opencarbonchem = "opencarbonchem.cli:main"`
  but **`src/opencarbonchem/cli.py` does not exist** — the installed command fails. (Fix in M10.)
- **Zero git commits.** Everything is untracked (`git status`: `.gitignore`, guide, `README.md`,
  `data/`, `docs/`, `pyproject.toml`, `src/`, `tests/`). The ritual says "commit working code" —
  the natural first action of the next session is to commit the completed Milestones 1–5 work in
  logical chunks (ask the user before pushing; never push without authorization).
- `README.md` promises Apache-2.0 and `pyproject.toml` says the same, but **no `LICENSE` file**.
- `docs/architecture.md` §4.6 header still says "reconciliation pending" and §4.7 still lists
  `database/store.py` as pending — both are stale (done in M5). Cosmetic fix when convenient.

---

## 4. API cheat sheet (reuse these — do not reinvent)

### Core

```python
from opencarbonchem.core.activity import ActivityRecord   # pydantic model
ActivityRecord(activity_id, scope, category, substance, quantity, unit, gas,
               methane_basis=..., geography=..., data_type="primary"|"secondary",
               period_start, period_end, notes, description=...)
# scope must be 1|2|3; quantity > 0; invalid data fails at construction.

from opencarbonchem.core.calc import compute_emissions, EmissionResult
compute_emissions(activity, factor, gwp_set="AR6") -> EmissionResult
# EmissionResult: activity value/unit, factor value/unit, factor_id, emissions_kg,
#                 gwp, gwp_set, co2e_kg  — a complete audit row.

from opencarbonchem.core.gwp import gwp, to_co2e, get_gwp_set, DEFAULT_GWP_SET
# Sets: AR6 (default; CH4 29.8 fossil / 27.0 non-fossil), AR6-ERRATA-2025, AR5 (CH4 28, N2O 265).
# CH4 with a splitting set REQUIRES explicit methane_basis → else MissingGWPError.
```

### Units

```python
from opencarbonchem.core.units import convert, parse_unit, UnitRegistry, Quantity
# Conversion only within one dimension; cross-dimension needs an explicitly registered
# factor else IncompatibleUnitError. Ambiguous symbols (e.g. "ton") rejected.
# Area/volume are powers of length (m2=L², m3=L³); base symbols are kg, m, s, mol, K, etc.
```

### Factors

```python
from opencarbonchem.factors import FactorRegistry, EmissionFactor
registry = FactorRegistry.from_csv()          # packaged seed CSV
registry.from_csv(path)                       # or a user CSV with matching columns
# Resolution: category+substance → gas → geography (exact beats GLOBAL) →
# nearest year at-or-before reporting year. Errors: MissingFactorError,
# AmbiguousFactorError, FactorScopeError, UnverifiedFactorError.
# EmissionFactor provenance fields: factor_id, activity_category, substance, value, unit,
# gas, geography, reporting_year, source_org, source_reference, version,
# uncertainty_pct, review_status (illustrative|published|verified), notes.
```

### Accounting (Milestones 4–5)

```python
from opencarbonchem.accounting import (
    calculate_scope1, calculate_scope2, calculate_scope3,
    ScopeResult, OrganisationalBoundary, BoundaryEntity,
    OrganizationReport, Reconciliation, PeriodComparison, compare_periods,
)
calculate_scope1(activities, registry, *, gwp_set=DEFAULT_GWP_SET) -> ScopeResult
calculate_scope2(...) -> Scope2Result   # .location (always) and .market (only when
                                        # explicit contract/residual-mix factors supplied)
calculate_scope3(...) -> ScopeResult    # categories s3_cat01..s3_cat15

# ScopeResult(scope, results: tuple[EmissionResult, ...])
#   .total_kg .total_t .by_category() .by_gas()

# Boundary: OrganisationalBoundary(org_id, name, method, entities, notes=...)
#   method ∈ {operational_control, financial_control, equity_share}
#   .weight_for(entity_id)  .consolidate({entity_id: kg})  .document()
#   Consolidation fails (BoundaryError) on missing entity, unknown entity, negative kg.

# OrganizationReport.from_results([scope_results])  → .total_kg .by_scope()
#   .by_category() .by_gas() .reconcile() → Reconciliation(.ok, .checks, .coverage_gaps)
#   # consistency checks must pass; coverage gaps are advisory (missing scope/category
#   # rows are "zero or unreported?" flags, never silently assumed zero).

# compare_periods(current, prior, current_label=, prior_label=) → PeriodComparison
#   .total / .by_scope / .by_category → ComparisonLine(current_kg, prior_kg,
#   delta_kg, delta_pct, status ∈ {compared, new_in_current_year,
#   missing_in_current_year})   # delta None — never a fake −100 %; pct None if prior == 0
```

### Persistence

```python
from opencarbonchem.database import CarbonDatabase
with CarbonDatabase(path) as db:            # ":memory:" default
    db.init_schema()                        # idempotent; upgrades older DBs in place
    db.save_factor(f); db.save_activity(a, period_id=None); db.list_activities(period_id)
    db.start_run(run_id, gwp_set, period_id); db.save_results(run_id, results)
    db.save_scope_result(run_id, result); db.total_co2e_kg(run_id)
    db.save_boundary(boundary); db.load_boundary(org_id)   # M5
# Schema: src/opencarbonchem/database/schema.sql (all DDL is IF NOT EXISTS).
# Tables available but UNUSED so far: pcf_definitions, pcf_inventory, allocation_rules,
# scenarios, scenario_results (exact columns quoted in §5/§6 below).
```

### Errors (complete hierarchy — `core/exceptions.py`)

```
OpenCarbonChemError
├─ UnitError → UnknownUnitError, IncompatibleUnitError, CurrencyError,
│              ConversionFactorMissingError
├─ FactorError → MissingFactorError, AmbiguousFactorError, FactorScopeError,
│                UnverifiedFactorError
├─ GWPError → MissingGWPError
├─ BoundaryError, PeriodError, DoubleCountingError, AllocationError
├─ ScenarioError, UncertaintyError, ReconciliationError, ExportError
```

---

## 5. Milestone 6 — Product Carbon Footprint (next)

**Guide §8 / F6–F8 / architecture §2.1–2.2, §4.7.** The empty package is
`src/opencarbonchem/pcf/`.

### Requirements (guide §8)

Allow users to define: product name, functional unit, production quantity, system boundary,
production stages, raw materials, energy inputs, transportation, packaging, waste, allocation
rules. Support **cradle-to-gate** and **cradle-to-grave** boundaries. Support transparent
allocation methods. Product-level and corporate accounting must stay consistent — **no double
counting**.

### Formulas

```
PCF = Σ attributable life-cycle CO2e (kg) / functional-unit output
```

### Schema already waiting (quoted from `schema.sql`)

```sql
pcf_definitions (id TEXT PK, product_name TEXT, functional_unit TEXT,
                 production_qty REAL CHECK (>0), production_unit TEXT,
                 system_boundary TEXT CHECK IN ('cradle_to_gate','cradle_to_grave'),
                 notes TEXT DEFAULT '')
pcf_inventory   (id INTEGER PK, pcf_id → pcf_definitions, stage TEXT,
                 activity_id → activity_data, factor_id → emission_factors,
                 co2e_kg REAL, excluded_from_corporate INTEGER 0|1 CHECK)
allocation_rules(id INTEGER PK, pcf_id → pcf_definitions, stage TEXT,
                 method TEXT CHECK IN ('mass','economic','physical_causality','none'),
                 basis_value REAL, basis_unit TEXT, notes TEXT)
```

### Design guidance

- Model files (suggested): `pcf/models.py` (ProductDefinition, LifeCycleStage,
  AllocationRule — frozen dataclasses/pydantic, validated at construction),
  `pcf/allocation.py` (apply allocation methods), `pcf/calculator.py`
  (assemble inventory → PCF), `pcf/__init__.py` (exports).
- **Allocation:** each stage can carry an allocation rule; split shared emissions across
  co-products by `mass`, `economic` (value), `physical_causality`, or `none`. `basis_value`
  must be > 0 where required; invalid rules → `AllocationError`.
- **Double counting:** implement the architecture §2.2 check — a contribution reported in both
  an included corporate total and a PCF total without `excluded_from_corporate=1` raises
  `DoubleCountingError`. Reuse `OrganizationReport` for the corporate side of the check.
- **Persistence:** add store methods (e.g. `save_pcf_definition`, `save_inventory_item`,
  `save_allocation_rule`, `load_pcf`) following the existing `save_boundary` pattern
  (idempotent re-save, `BoundaryError`-style typed failures on missing rows).
- Reuse `compute_emissions` / `ScopeResult` for the underlying numbers — do not duplicate the
  E = AD × EF engine inside `pcf/`.

### Test plan (`tests/test_pcf.py`, + allocation/double-counting cases)

Hand-computed: a small SYNTHETIC product (e.g. an acid/compound per tonne produced) with
2–3 stages; assert exact PCF value; allocation split by mass (e.g. 60/40 co-products →
0.6×kg / 0.4×kg); cradle-to-gate vs cradle-to-grave boundary validation; `production_qty ≤ 0`
and unknown method → typed errors; double-counting scenario raises `DoubleCountingError`;
round-trip through SQLite.

### Definition of done

Tests green; roadmap row 6 → **Done** in `docs/architecture.md` §7 + `README.md`;
features/outstanding-issues listed; code committed (per ritual).

---

## 6. Milestone 7 — Hotspots, sensitivity, Monte Carlo

**Guide §9 / F9–F11 / architecture §4.7.** Package: `src/opencarbonchem/analytics/`.

### Requirements (guide §9)

- **Hotspots:** emissions by raw material, by process, by energy source, by Scope;
  product carbon intensity (per functional unit, when a PCF exists).
- **Sensitivity:** electricity EF, raw material sourcing, production yield, transport,
  fuel consumption, packaging — one-at-a-time variation of each input.
- **Monte Carlo:** configurable probability distributions, **reproducible random seed** (N4),
  mean, median, standard deviation, 5th and 95th percentiles, uncertainty contribution analysis.

### Design guidance

- `analytics/hotspots.py` — rank `EmissionResult` rows / `OrganizationReport` / PCF inventory
  by dimension (material, process/energy source, scope, category); return sorted structures
  suitable for charts (M9 will plot them).
- `analytics/sensitivity.py` — one-at-a-time: perturb each nominated input (EF, quantity, …)
  by ±X %, recompute total, return deltas → tornado-orderable table. All recomputation goes
  through the normal engine, never hand-rolled math.
- `analytics/uncertainty.py` — seeded `numpy.random.Generator` (explicit `seed` parameter,
  default fixed; same seed ⇒ identical output — test this). Distributions: at least
  normal/lognormal/triangular/uniform around the EF (seed row has `uncertainty_pct` as the
  default spread). Outputs: mean, median, std, p5, p95, plus contribution analysis
  (e.g. correlation/variance share per input). Invalid distribution params → `UncertaintyError`.
- scipy/numpy/pandas are already declared dependencies — use them.

### Test plan (`tests/test_analytics.py`)

Hand-computed hotspot totals from known rows; sensitivity of a single-factor calculation
(e.g. EF +10 % → total +10 % exactly for a one-row inventory); Monte Carlo reproducibility
(same seed ⇒ same p95; different seed ⇒ different), percentile ordering p5 ≤ median ≤ p95,
contribution shares sum ≈ 1, bad params → `UncertaintyError`. Mark heavy runs `unit` with a
small draw count (e.g. 2 000 draws) so the suite stays fast (<2 s).

### Definition of done

Tests green; roadmap row 7 → Done; README/features updated; commit.

---

## 7. Milestone 8 — Decarbonisation scenarios

**Guide §9 / F12 / architecture §4.7.** Package: `src/opencarbonchem/scenarios/`.

### Requirements (guide §9)

Seven levers: **renewable electricity, energy efficiency, fuel switching, material
substitution, waste reduction, process optimisation, transport optimisation.**
Compare baseline vs alternative scenarios with absolute and % reduction.

### Formulas (architecture §2.1)

```
Reduction     = Baseline − Scenario
Reduction (%) = Reduction / Baseline × 100
```

Fail-safe: a zero baseline must not divide — follow the `PeriodComparison` precedent
(`delta_pct = None`, never 0 %/inf) or raise `ScenarioError`; pick one, test it explicitly.

### Schema already waiting

```sql
scenarios        (id TEXT PK, name TEXT, lever TEXT, description TEXT DEFAULT '')
scenario_results (id INTEGER PK, scenario_id → scenarios,
                  run_id → calculation_runs, category TEXT,
                  baseline_kg REAL, scenario_kg REAL, reduction_kg REAL)
```

### Design guidance

- `scenarios/levers.py` — each lever transforms activities/factors (e.g. grid EF × (1 −
  renewable share); quantity × (1 − efficiency gain)) producing a *scenario activity set*;
  then recompute with the normal engine. Invalid lever params (negative shares, >100 %,
  unknown lever) → `ScenarioError`.
- `scenarios/engine.py` — baseline run vs scenario run; aggregate per category; compute
  reductions; persist via `scenarios`/`scenario_results`.
- Keep levers pure functions (input activities + params → output activities) so they are
  trivially unit-testable and reusable by the dashboard.

### Test plan (`tests/test_scenarios.py`)

Hand-computed: baseline 1000 kg vs efficiency lever −20 % → scenario 800 kg, reduction 200 kg,
20 %; renewable-electricity lever on the 450 kg grid row → hand number; zero-baseline guard;
invalid params → `ScenarioError`; round-trip persistence; every one of the 7 levers exercised.

### Definition of done

Tests green; roadmap row 8 → Done; README/features updated; commit.

---

## 8. Milestone 9 — Streamlit interface

**Guide §10 / F13.** Directory: `app/` (does not exist yet). streamlit ≥1.30 and plotly ≥5.18
are already in `pyproject.toml` dependencies.

### The 11 pages (guide §10, exact order)

1. Overview · 2. Activity Data Management · 3. Emission Factor Database ·
4. Scope 1 Accounting · 5. Scope 2 Accounting · 6. Scope 3 Accounting ·
7. Product Carbon Footprint · 8. Hotspot Analysis · 9. Sensitivity and Uncertainty ·
10. Decarbonisation Scenarios · 11. Report Generation.

### Design guidance

- **Thin client only (N3)** — pages call the package API; no calculation logic in `app/`.
- Interactive Plotly charts; downloadable results (CSV/XLSX via the reporting module of M10 —
  if M10 is not done yet, offer CSV download and leave PDF/Excel buttons for M10).
- Multi-page layout: `app/Home.py` (or `app/1_Overview.py`) + `app/pages/*`.
- Use the demo dataset in `data/` (clearly labelled SYNTHETIC) so the dashboard shows data on
  first run; no silent fabrication if data is absent — show an informative empty state.

### Test plan

Streamlit pages are not unit-tested end-to-end; keep logic in the package (unit-tested) and add
at most a smoke test that imports each page module. The ritual's "run tests" still applies to
the package suite.

### Definition of done

All 11 pages render with the synthetic dataset; roadmap row 9 → Done; README (add run
instructions: `streamlit run app/Home.py`) and screenshots placeholder updated; commit.

---

## 9. Milestone 10 — Reporting (PDF/Excel), documentation, CLI

**Guide §11/§13/§14 / F14 / roadmap row 10 (currently "Partial").** Package:
`src/opencarbonchem/reporting/`.

### Reporting

- **Excel (openpyxl):** workbook with summary, per-scope sheets, activity/factor detail —
  must **reconcile with calculation records** (totals equal `total_co2e_kg` of the run; mismatch
  → `ReconciliationError`).
- **PDF (ReportLab):** executive summary, scope breakdown, methodology appendix — include the
  boundary document (`OrganisationalBoundary.document()`) and GWP set used (guide §13
  appendix requirement).
- Export failures → `ExportError`. Charts from M7/M8 embed as images (plotly `fig.to_image`
  needs kaleido — declare it if used, or render simple tables/bars with reportlab).

### Documentation deliverables (guide §11, still missing)

`LICENSE` (Apache-2.0 — already promised in README/pyproject), `CONTRIBUTING.md`,
methodology document, assumptions document, data dictionary, emission-factor provenance
policy, validation protocol. README also wants: installation instructions, usage, example
calculations, screenshots, limitations, references.

### CLI (loose end)

Create `src/opencarbonchem/cli.py` with `main()` so the declared console script
`opencarbonchem = "opencarbonchem.cli:main"` works: thin commands such as
`opencarbonchem calculate --activities … --out …` (load CSV → calculate scopes → print totals /
write SQLite). Keep it a thin client (N3). Add a test that imports `main` and runs a `--help`-style
path or a smoke invocation.

### Test plan

`tests/test_reporting.py`: Excel totals reconcile with a known run (hand totals 1830 kg case);
PDF builds without error and contains the expected strings; missing/invalid inputs →
`ExportError`/`ReconciliationError`. `tests/test_cli.py`: smoke test of the entry point.

### Definition of done

Docs files exist and are linked from README; roadmap row 10 → Done; commit.

---

## 10. Milestone 11 — Final integration & GitHub publication

**Guide §11/§14/§15.** Scope:

- Full end-to-end pass on the **demonstration use case for a chemical/process manufacturing
  facility** (final deliverable 19) using the synthetic datasets — corporate inventory + PCF +
  hotspots + uncertainty + a scenario + a generated report in one coherent story.
- Missing target dirs per guide §11: `notebooks/`, `reports/` (create with README stubs if used).
- CI (GitHub Actions: pytest on push), version bump, final README polish with screenshots.
- **Final deliverables checklist (guide §14, 19 items)** — walk the list and mark each
  ✅/❌ in the final report; fill any gaps.
- **GitHub publication requires the user's explicit authorization to push** — prepare the repo
  locally, then ask. Repository name: `opencarbonchem`.

### Definition of done

All 19 deliverables accounted for; roadmap rows 6–11 all **Done** (or explicitly deferred with
reasons); full suite green; final report: completed features, outstanding issues, limitations
(no conformity/verification claims — guide §13).

---

## 11. Environment & tooling gotchas (learned the hard way)

1. **`str_replace` is unreliable in this workspace** — it fails with
   "The file does not exist, skipping" on most existing files (worked only occasionally).
   Use `write_file` for full rewrites, or better: **write a small Python patch script**
   (`patch_x.py` at repo root) that does exact-anchor `str.replace` with an
   `if old not in src: raise SystemExit(...)` guard, run it, then delete the script.
2. **Long heredocs get truncated** — a `python - <<'PY'` command with ~300+ lines has been cut
   off mid-script, causing SyntaxErrors. Keep heredocs short (<100 lines) or write the script
   to a file first and run it.
3. **Match anchors to actual file bytes** — several files are CRLF (`\r\n`: `schema.sql`,
   `store.py`, `architecture.md`), others LF. Before patching, print `repr()` of the anchor
   region to confirm exact whitespace/indentation; a wrong-indent anchor fails silently
   ("anchor not found") and wastes a cycle.
4. **Test failures you may hit:** parametrised `pytest.raises` cases must pass *all* required
   constructor args (a missing required field raises `TypeError`, not the domain error —
   that was a test bug, not a model bug; fix the test).
5. **Windows environment** — commands run via Git Bash on win32; use POSIX syntax.
   Python 3.14.7, pytest 9.2.0 at repo root.
6. Do not weaken tests, add suppressions, or swallow errors to make the suite pass —
   fix the cause (guide: "fail safely").

---

## 12. Suggested first actions for the next session

1. Run `python -m pytest` (should be **97 passed**) to confirm the baseline.
2. Commit the existing Milestones 1–5 work in logical chunks (ask the user first if
   push/commit policy is unclear; nothing is committed yet — a checkpoint protects the work).
3. Fix the stale `architecture.md` §4.6/§4.7 wording (optional, 2-line edit).
4. Implement **Milestone 6 (PCF)** per §5 of this file — next in the roadmap.
5. Continue sequentially 7 → 8 → 9 → 10 → 11, running the ritual at every milestone.

*End of handoff. When you finish your milestone, update `docs/HANDOFF.md` §1 status line and
the roadmap so the following agent inherits an accurate picture.*
