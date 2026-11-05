# OpenCarbonChem — Assumptions Documentation

This document lists all assumptions made in the implementation of OpenCarbonChem.
Assumptions are declared explicitly so that users can assess the suitability of the
software for their particular context.

## 1. Emission Factor Assumptions

- **All packaged factors in the seed CSV (`illustrative_factors.csv`) are labelled
  ``review_status=illustrative`` and ``source_org=SYNTHETIC``.**
  They are **not** official emission factors and must not be presented as such.
- New factors entered via the Emission Factor DB page are stored in the in-memory
  SQLite database; they are not written to the packaged CSV.
- Resolution is deterministic: category → substance → geography (exact beats GLOBAL) →
  vintage (newest at or before the reporting year).
- Ambiguous substances with factors for multiple gases raise ``AmbiguousFactorError``;
  the user must set the activity's ``gas`` field.
- Uncertainty values listed in factors are informational only; they are used by the
  Monte Carlo module (M9, page 9) to build probability distributions.
- Where a factor has no recorded ``uncertainty_pct``, the default spread of 10% is
  used in Monte Carlo uncertainty propagation; this is always visible in the returned
  names/values.

## 2. Unit and Dimensional Assumptions

- The unit engine **never silently applies an incompatible conversion**.
  Crossing dimensions (mass → energy, volume → mass) requires an explicitly registered
  conversion factor; otherwise ``IncompatibleUnitError`` is raised.
- Area/volume are powers of length: ``m² = L²``, ``m³ = L³``.
- Base symbols are kg, m, s, mol, and K (where K appears in temperature-related contexts
  but is not a base dimension in the current implementation).
- Currency conversion requires an exchange rate supplied deliberately by the user;
  there is no built-in rate for non‑USD currencies.

## 3. Boundary and Allocation Assumptions

- **PCF boundary enforcement**: ``cradle_to_gate`` excludes distribution, use, and end-of-life;
  ``cradle_to_grave`` includes them. Stages outside the declared boundary raise ``PCFError``.
- **Allocation methods**: mass, economic, physical_causality, and none are supported.
  ``none`` means emissions are not shared; each item gets 100% of its own contribution.
- **Double-counting guard**: rows shared between the corporate inventory and the PCF are
  cross-checked via the ``excluded_from_corporate`` flag. If ``excluded_from_corporate=False``
  and the same ``(activity_id, factor_id)`` pair appears in the corporate inventory, a
  ``DoubleCountingError`` is raised.

## 4. Sensitivity and Monte Carlo Assumptions

- **Sensitivity (tornado)**: one‑at‑a‑time perturbation of each nominated input by ±``delta_pct``%.
  The whole inventory is recomputed through the engine each time; no hand‑rolled approximations.
- **Monte Carlo (N4)**: seeded reproducibility is a hard requirement.
  The random generator is seeded explicitly; same seed ⇒ byte‑identical summary statistics.
- Variance‑share contributions are squared Pearson correlations of each input with the total,
  normalised to sum ≈ 1. Inputs with very small contributions may show noise due to the
  finite number of draws.
- Distributions are always right‑skewed or bounded; negative emission values are physically
  meaningless and truncated at zero.

## 5. Scenario Assumptions

- Each lever is a pure function ``entries → entries``; the scenario engine then recomputes
  totals through the normal calculation API, so there is no hand‑rolled math that can drift.
- Levers never invent emission factors: fuel switching and material substitution require the
  replacement factor to be supplied with its own provenance record.
- If a lever matches no inventory rows, ``ScenarioError`` is raised with a helpful message
  indicating which input the lever targets.
- Baseline vs scenario comparison uses the exact formulas from architecture §2.1:
  ``Reduction = Baseline − Scenario``, ``Reduction (%) = Reduction / Baseline × 100``.
  Fail‑safe: zero baseline → ``reduction_pct = None``, never 0 % or inf.

## 6. Data Assumptions

- The synthetic dataset in ``data/`` is clearly labelled ``SYNTHETIC`` and must not be used
  for real ESG reporting without independent verification.
- All calculation results are persisted in SQLite with the same schema; the Excel workbook
  and PDF summary are re-derived from this stored data, guaranteeing reconciliation.
- The demo dataset contains 5 activity rows covering Scope 1, 2, and 3 categories; it is
  not exhaustive and does not represent a real facility.

## 7. Standards Assumptions

- GWP values follow IPCC AR6 by default; AR5 and AR6 2025 errata are also supported.
- The software implements GHG Protocol and ISO 14064/14067 calculation methodologies;
  it does **not** claim certification, independent verification, or formal standards conformity
  without the relevant assessment.
- Boundary methods (operational_control, financial_control, equity_share) follow the GHG
  Protocol framework; other boundary definitions may differ.

## 7. Limitations

- The software is a portfolio-project demonstration; it is not a certified ESG tool.
- All numbers from the packaged seed CSV are synthetic; real-world use requires loading
  verified, geographically appropriate emission factors.
- The Monte Carlo engine truncates negative draw values to zero; true physical emissions
  are always non‑negative.
- The unit engine has a fixed set of base dimensions; unconventional units must be
  converted to a supported representation before use.