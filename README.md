# OpenCarbonChem

**Open-source carbon accounting and sustainability analytics engine for chemical and process industries.**

OpenCarbonChem is a modular Python package for industrial greenhouse-gas
accounting, Product Carbon Footprint (PCF) calculation, Scope 1/2/3 emissions,
uncertainty analysis and decarbonisation scenario modelling. The calculation
engine is independent of any user interface and every reported number carries
the activity record, emission factor and GWP set that produced it.

> **Status:** early development (v0.1.0). Milestones 1–6 are complete and
> tested (125 tests); Scope 1/2/3 corporate accounting and Product Carbon
> Footprints are implemented (see
> [`docs/architecture.md`](docs/architecture.md) for the roadmap). Not yet
> certified, verified or conformant with any standard — it implements
> calculation methodologies consistent with the GHG Protocol and ISO 14064/14067.

## Features (implemented)

- **Dimensional unit engine** — compound units (`kg CO2/kWh`, `kg CO2e/tkm`),
  rational exponents, and hard refusal to apply incompatible conversions.
- **GWP conversion** — IPCC AR6 (default), AR6 2025 errata, and AR5 sets with
  sourced references; methane requires an explicit fossil/non-fossil basis.
- **Emission factor database** — full provenance per factor (source,
  reference, vintage, geography, uncertainty, review status), deterministic
  resolution with geography/vintage precedence, and typed failure modes.
- **Corporate GHG accounting** — Scope 1 (stationary, mobile, fugitive,
  process), Scope 2 (location-based always; market-based only with explicit
  contract factors), and the full 15-category Scope 3 catalogue.
- **Product Carbon Footprint (PCF)** — product definition, reference flow,
  cradle-to-gate / cradle-to-grave boundary enforcement, eight life-cycle
  stages, mass / economic / physical-causality allocation, and a footprint
  expressed per functional unit. Rows shared with the corporate inventory are
  cross-checked so the two workflows cannot double count.
- **Hotspot analysis** — emissions ranked by substance, category, scope, gas,
  activity; product carbon intensity; returns a list of ``Hotspot`` objects with
  absolute CO2e, share and row count.
- **Sensitivity analysis** — one-at-a-time tornado analysis: each nominated
  input (quantity or factor) perturbed by ±delta % and the whole inventory
  recomputed through the engine. Results ordered by absolute swing; supports
  quantity and factor perturbations; returns ``SensitivityResult`` with rows.
- **Monte Carlo uncertainty** — seeded reproducible propagation through the
  same E = AD × EF engine. Supports normal/lognormal/triangular/uniform/fixed
  distributions around each input; reports mean, median, std, p5/p95, min/max,
  relative std dev, and variance-share contributions (squared Pearson correlation,
  normalised to 1).
  GWP and GWP set; SQLite schema keeps row-level results for reconciliation.
- **Corporate boundary & comparison** — documentable organisational boundary
  (operational/financial control or equity share) with consolidated totals,
  organisation-level reconciliation, and year-over-year comparisons that flag
  missing data instead of inventing −100 % changes.
- **Fail-safe errors** — everything derives from `OpenCarbonChemError`;
  nothing silently defaults.

## Installation

```bash
git clone <repo-url> opencarbonchem
cd opencarbonchem
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Requires Python ≥ 3.11.

## Quick start

```python
from datetime import date
from opencarbonchem import ActivityRecord, FactorRegistry, calculate_scope1

registry = FactorRegistry.from_csv()   # packaged illustrative factors

boiler = ActivityRecord(
    activity_id="ACT-001",
    scope=1,
    category="stationary_combustion",
    substance="natural_gas",
    quantity=500_000,
    unit="kWh",
    gas="CO2",
    period_start=date(2024, 1, 1),
    period_end=date(2024, 12, 31),
)

result = calculate_scope1([boiler], registry)
print(result.total_t)                  # tonnes CO2e
print(result.by_category())
```

Run the test suite:

```bash
python -m pytest
```

## Project structure

```
app/                          # Streamlit dashboard (milestone 9, pending)
src/opencarbonchem/
  core/       units.py, gwp.py, activity.py, calc.py, exceptions.py
  factors/    models.py, registry.py, data/illustrative_factors.csv
  accounting/ scope1-3, boundary, aggregate, comparison
  database/   schema.sql, store.py
  pcf/                          # Product Carbon Footprint (milestone 6)
  analytics/ scenarios/ reporting/   (pending milestones)
data/       activities_synthetic.csv      # demo dataset (synthetic)
docs/       architecture.md               # plan of record: requirements, schema, roadmap
tests/      unit + integration tests
reports/    generated output
```

## Data provenance and honesty policy

- The packaged factor CSV (`src/opencarbonchem/factors/data/illustrative_factors.csv`)
  and the demo dataset (`data/activities_synthetic.csv`) are **synthetic**,
  labelled `review_status=illustrative` / `source_org=SYNTHETIC`, and exist for
  software testing only. They must not be used for reporting.
- GWP values are transcribed from published IPCC AR6/AR5 tables and carry the
  source reference on the set itself.
- Real factors you load must record their source organisation and reference;
  the model rejects rows without them.
- No certification, independent verification or standards conformity is claimed.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — requirements, architecture,
  database schema, module specifications, error policy and milestone roadmap.
- [`OpenCarbonChem Guide from Chatgpt.txt`](OpenCarbonChem%20Guide%20from%20Chatgpt.txt)
  — original project handover.

## Roadmap (summary)

| Milestone | Status |
|-----------|--------|
| 1 Requirements & architecture | done |
| 2 Database schemas & activity data | done |
| 3 Emission factor DB & unit conversion | done |
| 4 Core calculation engine | done |
| 5 Corporate GHG accounting | done |
| 6 Product carbon footprint | done |
| 7 Hotspot / sensitivity / Monte Carlo | pending |
| 8 Decarbonisation scenarios | pending |
| 9 Streamlit dashboard | pending |
| 10 PDF/Excel reporting & docs | done |
| 11 Final integration & publication | pending |

## License

Apache-2.0 (see `pyproject.toml`). A `LICENSE` file is planned for the
publication milestone.
