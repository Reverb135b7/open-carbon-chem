# OpenCarbonChem Implementation Status

## Project Overview
OpenCarbonChem — open-source carbon accounting and sustainability analytics engine for chemical/process industries.

## Milestones Completed (1–9)
- **M1–M5**: Architecture, unit conversion engine, GWP sets (AR6/AR5), factor registry, SQLite persistence, Scope 1/2/3 corporate accounting with reconciliation
- **M6**: Product Carbon Footprint — stage catalogue, boundary enforcement (cradle→gate/grave), allocation methods, double-counting guard, persistence
- **M7**: Hotspot rankings (5 dimensions), one‑at‑a‑time tornado sensitivity, Monte Carlo uncertainty (5 distributions, seeded reproducibility, variance‑share contributions)
- **M8**: 7 decarbonisation levers (renewable electricity, energy efficiency, fuel switching, material substitution, waste reduction, process optimisation, transport optimisation); baseline/scenario comparison (absolute & % reduction)
- **M9**: 11‑page Streamlit dashboard (Overview → Report Generation) — thin client, synthetic data throughout, clear SYNTHETIC labels

## Test Suite
- **125 tests** across all modules — all green
- Test files: `tests/test_pcf.py`, `tests/test_analytics.py`, plus 97 original M1–M5 tests

## Key Design Principles (from handover §15/§16)
- Scientific correctness: values traceable to IPCC/national grids, no invented factors
- Engineering accuracy: dimensional unit engine refuses incompatible conversions
- Transparent accounting: every `EmissionResult` records AD, EF, factor ID, gas, GWP set
- Reproducible calculations: same seed → identical Monte Carlo output
- No double counting: corporate inventory and PCF cross‑checked via `excluded_from_corporate` flag
- Fail-safe: invalid data raises typed errors; never silently defaults

## Next Steps (M10–M11)
- PDF report generator (ReportLab) + Excel report generator (openpyxl) with reconciliation guard
- Full documentation: `LICENSE`, `CONTRIBUTING.md`, methodology/assumptions/data-dictionary/provenance-policy/validation-protocol
- CLI entry point: `opencarbonchem calculate --activities ... --out ...`
- GitHub publication (repository: `opencarbonchem`) with user authorization
- Final integration run: corporate inventory + PCF + hotspots + uncertainty + scenario + generated report

---
**All 125 tests pass. Ready for M10–M11 or GitHub publication.**