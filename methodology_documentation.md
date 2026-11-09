# OpenCarbonChem — Methodology Documentation

This document describes the calculation methodologies implemented in OpenCarbonChem,
referenced standards, and the assumptions that underpin the software.

## 1. Core Calculation Engine

The fundamental emissions calculation follows the GHG Protocol formula:

```
E = Activity Data × Emission Factor
```

where:
- **Activity Data**: measured or estimated quantity of fuel, energy, material, transport, or waste
- **Emission Factor**: mass of greenhouse gas emitted per unit of activity

Gas-specific CO₂-equivalent conversion:

```
CO₂e = Σ (E_g × GWP_g)
```

where `E_g` is the emission of gas `g` and `GWP_g` is its 100-year Global Warming Potential.

## 2. GWP Sets

OpenCarbonChem supports the following IPCC Global Warming Potential sets (100-year horizon):

| Gas         | AR6     | AR5     | AR6 2025 Errata |
|-------------|---------|---------|-----------------|
| CO₂         | 1 (ref) | 1 (ref) | 1 (ref)         |
| CH₄ (fossil)| 29.8    | 28      | 29.8*           |
| CH₄ (non-fossil) | 27.0 | 26      | 27.0*           |
| N₂O         | 273     | 265     | 273*            |

*\*Errata values may differ; the software defaults to the AR6 set.*

Methane requires an explicit ``methane_basis`` (``fossil`` or ``non_fossil``) when using a GWP set that distinguishes origin. If ``methane_basis`` is not provided, a ``MissingGWPError`` is raised.

## 3. Organisational Boundaries

Three boundary methods are supported (per GHG Protocol):

| Method          | Description                                                                    |
|-----------------|--------------------------------------------------------------------------------|
| operational_control | Controls over operations; includes all emissions from operations controlled       |
| financial_control   | Financial control over; includes majority of emissions from operations           |
| equity_share        | Equity share method; includes emissions proportional to equity ownership        |

Organisational boundary is documented via ``OrganisationalBoundary`` with a consolidation
method (operational_control, financial_control, equity_share).

## 4. Scope Definitions

| Scope | Description                                                                                   |
|-------|-----------------------------------------------------------------------------------------------|
| 1     | Direct emissions from sources owned or controlled by the organisation (stationary/mobile combustion, fugitive, process) |
| 2     | Indirect emissions from imported energy (electricity, steam, heat, cooling)                      |
| 3     | All other indirect emissions upstream and downstream of the organisation (15 GHG Protocol categories) |

## 5. Allocation Methods (Product Carbon Footprint)

When emissions are shared between co-products, the following allocation methods are supported:

| Method          | Basis                                                                                  |
|-----------------|----------------------------------------------------------------------------------------|
| mass            | Mass of each co-product (kg, t, etc.)                                                  |
| economic        | Economic value of each co-product (USD, €, etc.)                                       |
| physical_causality| Physical causal quantity (no specific unit required; e.g., energy input ratio)           |
| none            | Emissions are not shared; each contribution keeps its full value                        |

All allocation methods are validated such that ``basis_value ≤ basis_total`` and both must be positive.

## 6. Boundary Enforcement (PCF)

Product Carbon Footprints support two system boundaries:

| Boundary          | Included Stages                                                                     |
|-------------------|-------------------------------------------------------------------------------------|
| cradle_to_gate    | raw_materials, manufacturing, inbound_transport, packaging, waste                      |
| cradle_to_grave   | all of the above + distribution, use, end_of_life                                      |

Stages outside the declared boundary raise ``PCFError`` if attempted.

## 7. Double-Counting Guard

Rows shared between the corporate inventory and the PCF are cross-checked:

- If a PCF row has ``excluded_from_corporate=False`` and the same ``(activity_id, factor_id)`` pair appears in the corporate inventory, a ``DoubleCountingError`` is raised.
- If ``excluded_from_corporate=True``, the row is intentionally absent from the corporate total.

## 8. Sensitivity Analysis

One-at-a-time perturbation of nominated inputs (quantity or factor value) by ±``delta_pct``%
and recomputation through the normal engine. Results ordered by absolute swing (largest first).

## 9. Monte Carlo Uncertainty Propagation

Probabilistic propagation through the same ``E = AD × EF`` engine. Distributions supported:
- **normal** (mean = base, σ = spread)
- **lognormal** (median = base, right‑skewed)
- **triangular** ((base·(1−s), base, base·(1+s))
- **uniform** ([base·(1−s), base·(1+s)])
- **fixed** (no uncertainty, σ = 0)

Reported statistics: mean, median, std dev, 5th/95th percentiles, min/max, relative std dev,
and variance‑share contributions (squared Pearson correlation, normalised to 1).

Reproducibility (N4): the random generator is seeded explicitly; same seed ⇒ byte‑identical output.

## 10. Decarbonisation Levers

Seven levers for scenario modelling, each a pure function ``entries → entries``:

| Lever                      | Target                                   |
|----------------------------|------------------------------------------|
| renewable_electricity      | Replace a share of purchased electricity |
| energy_efficiency          | Reduce energy consumption by a fraction  |
| fuel_switch                | Replace one fuel with another (factor required) |
| material_substitution      | Replace a raw material with a lower‑carbon alternative |
| waste_reduction            | Reduce waste generated and treated         |
| process_optimisation       | Reduce process‑direct emissions            |
| transport_optimisation     | Reduce freight tonne‑km by a fraction      |

## 11. Standards and Frameworks

- **GHG Protocol**: corporate accounting, Scope 1/2/3, product category rules
- **ISO 14064**: greenhouse gas validation and verification
- **ISO 14067**: carbon footprint of product
- **IPCC AR5/AR6**: GWP values and methodologies
- **PAS 2050**: specification for carbon footprint of goods and services

## 11. Assumptions and Limitations

- The default packaged factors are ``review_status=published`` (DESNZ 2024, IPCC 2006)
  with document references; the synthetic test set is marked ``source_org=SYNTHETIC``.
  Published values retain their source's GWP basis (DEFRA uses AR5 for CO2e factors).
- The unit engine refuses incompatible conversions; no silent unit conversion is ever applied.
- Monte Carlo distributions are always right‑skewed or bounded; negative emission values are physically meaningless and truncated.
- All calculations use the same engine; there is no hand-rolled math that can drift from the accounting methodology.

## 12. Change Log

| Version | Date       | Changes                                        |
|---------|------------|------------------------------------------------|
| 0.1.0   | 2026-11-02 | Initial release with M1–M9                     |