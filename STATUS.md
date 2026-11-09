# OpenCarbonChem — implementation status

All eleven milestones of the handover guide are implemented and tested locally.
Publication to GitHub is the one remaining step and needs the repository owner's
authorisation.

## Milestones

| # | Scope | State |
|---|-------|-------|
| 1 | Requirements and architecture | Done (`docs/architecture.md`) |
| 2 | Database schema, activity data | Done (`database/schema.sql`, `store.py`, `ActivityRecord`) |
| 3 | Emission factors and units | Done (`core/units.py`, `factors/`) |
| 4 | Calculation engine | Done (`core/calc.py`, `core/gwp.py`, `core/inventory.py`) |
| 5 | Corporate accounting | Done (Scope 1/2/3, boundary, roll-up, comparison) |
| 6 | Product carbon footprint | Done (`pcf/`) |
| 7 | Hotspots, sensitivity, Monte Carlo | Done (`analytics/`) |
| 8 | Decarbonisation scenarios | Done (`scenarios/`) |
| 9 | Streamlit dashboard (11 pages) | Done (`app/`) |
| 10 | Reporting, CLI, documentation | Done (`reporting/`, `cli.py`) |
| 11 | Final integration | Done locally; publication pending owner authorisation |

## Verification

- `python -m pytest` → **219 passed**.
- `python -m compileall -q src app` → clean.
- `ruff check src app --select F,E9` → no undefined names or unused imports.
- CLI: `opencarbonchem calculate --activities data/activities_synthetic.csv --run-id demo --out build/reports`
  writes an `.xlsx` and a `.pdf`; the totals (Scope 1 4,555,075 kg,
  Scope 2 910,000 kg, Scope 3 82,000 kg) match the package API.
- Every dashboard page and every action button was executed through
  `streamlit.testing.v1.AppTest`; results were compared with the package API.

## Data

- `data/activities_synthetic.csv` — 10 synthetic activity rows (Scope 1/2/3).
- `src/opencarbonchem/factors/data/illustrative_factors.csv` — 14 factors, every
  row `review_status=illustrative`, `source_org=SYNTHETIC`.

Neither dataset is official and none of the output is an ESG disclosure.

## Known limitations

1. **No real emission factors are bundled.** Real use requires importing a
   published factor set with full provenance; the packaged rows are illustrative.
2. **Connectors (DEFRA / EPA / Ecoinvent) are stubs.** They return no live
   factors, make no claim of licensed access, and never feed a calculation.
3. **Scope 2 market-based** totals require explicit contract/residual-mix
   factors; the engine never substitutes a grid average.
4. **Dashboard persistence** is a local SQLite file (`data/opencarbonchem.db`,
   git-ignored) with no authentication; it is a demonstration workspace.
5. **Scenario results** are stored per scenario total, not broken down by
   category.

## Design rules in force

- Typed errors (`OpenCarbonChemError`) instead of silent defaults.
- `E = AD × EF` computed once in `core/calc.py`; every higher layer recomputes
  through it.
- Every result row carries the activity, factor, gas and GWP set needed to
  re-derive it.
- Reports refuse to be generated when their rows do not reconcile with the
  report total.
- Synthetic data is labelled `SYNTHETIC` and never presented as official.
