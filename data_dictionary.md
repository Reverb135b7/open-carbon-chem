# OpenCarbonChem — Data Dictionary

This document defines all data fields used throughout the OpenCarbonChem codebase.

## 1. Activity Record Fields

| Field name         | Type                | Description                                                                 |
|--------------------|---------------------|-----------------------------------------------------------------------------|
| activity_id        | `str` (required)    | Unique identifier for the activity record                                    |
| scope              | `int` (required)    | 1 = Scope 1, 2 = Scope 2, 3 = Scope 3                                       |
| category           | `str` (required)    | GHG Protocol category (e.g. ``stationary_combustion``, ``s3_cat01`` … ``s3_cat15``) |
| substance          | `str` (required)    | Fuel, material or energy type (e.g. ``natural_gas``, ``diesel``, ``paper``) |
| quantity           | `float` (required)  | Activity data magnitude; must be finite and non‑negative                     |
| unit               | `str` (required)    | Unit of the activity quantity (e.g. ``kWh``, ``kg``, ``tkm``, ``L``, ``m³``) |
| gas                | `str \| None`       | Gas emitted (``CO2``, ``CH4``, ``N2O``); required when the substance has factors for more than one gas |
| methane_basis      | `str \| None`       | Required for CH4 factors when the GWP set splits origin: ``fossil`` or ``non_fossil`` |
| geography          | `str` (`"GLOBAL"`)  | Geography of the emission factor; ``GLOBAL`` is the default                  |
| data_type          | `str` (`"primary"` / `"secondary"`) | ``primary`` = measured data; ``secondary`` = estimate / literature value     |
| period_start       | `date \| None`      | Start date of the reporting period                                             |
| period_end         | `date \| None`      | End date of the reporting period                                               |
| description        | `str`               | Free‑form description of the activity                                          |
| notes              | `str`               | Additional methodological notes                                                |

## 2. Emission Factor Fields

| Field name               | Type                     | Description                                                                 |
|--------------------------|--------------------------|-----------------------------------------------------------------------------|
| factor_id                | `str` (required)         | Unique identifier for the emission factor                                    |
| activity_category        | `str` (required)         | GHG Protocol category the factor applies to                                  |
| substance                | `str` (required)         | Fuel, material or energy type                                                |
| value                    | `float` (required)       | Factor magnitude; must be positive                                           |
| unit                     | `str` (required)         | Unit of the factor (e.g. ``kg CO2/kWh``, ``kg CO2e/tkm``)                  |
| gas                      | `str` (required)         | Gas emitted, or ``CO2e`` when the factor is already combined                 |
| gases_covered            | `list[str]`              | All gases included in the factor (informational coverage)                   |
| geography                | `str` (`"GLOBAL"` by default) | Geography of the factor; ``GLOBAL`` is the default                         |
| reporting_year           | `int` (required)         | Year the factor is valid for; used for vintage precedence                   |
| source_org               | `str` (required)         | Source organisation (e.g. ``IPCC``, ``DEFRA``, ``SYNTHETIC``)               |
| source_reference         | `str`                    | URL, DOI or document reference for the factor                                |
| version                  | `str`                    | Publication/version information                                              |
| uncertainty_pct          | `float \| None`          | Relative uncertainty, %; ``None`` if not available                           |
| review_status            | `str` (`"illustrative"` / `"published"` / `"verified"`) | Trust gate: ``illustrative`` = synthetic test data only                  |
| methane_basis            | `str \| None`            | Required for CH4 factors when the GWP set splits origin                      |
| notes                    | `str`                    | Methodological notes                                                         |

## 3. GWP Value Fields

| Field name | Type   | Description                              |
|------------|--------|------------------------------------------|
| gwp_set    | `str`  | Name of the GWP set (``AR6``, ``AR5``, etc.) |
| gas        | `str`  | Gas symbol (``CO2``, ``CH4``, ``N2O``)   |
| methane_basis | `str \| None` | ``fossil`` or ``non_fossil`` when applicable |
| value      | `float` | GWP value (``CO2`` = 1 by definition)    |

## 4. Organisation Report Fields

| Field name         | Type                                   | Description                                              |
|--------------------|----------------------------------------------------------|----------------------------------------------------------|
| scope_results      | `tuple[ScopeResult, ...]`                               | Per‑scope aggregation of emission results                 |
| total_kg           | `float`                                                   | Total CO₂e in kilograms                                  |
| total_t            | `float`                                                   | Total CO₂e in tonnes                                     |
| by_scope()         | `dict[int, float]`                                      | CO₂e total per scope                                     |
| by_category()      | `dict[str, float]`                                      | CO₂e total per category                                  |
| by_gas()           | `dict[str, float]`                                      | CO₂e total per gas                                       |
| reconcile()        | ``Reconciliation``                                      | Reconciliation result (checks + coverage gaps)           |

## 5. Scope Result Fields

| Field name         | Type                   | Description                                          |
|--------------------|------------------------|-------------------------------------------------------|
| scope              | `int`                  | 1, 2, or 3                                            |
| results            | `tuple[EmissionResult, ...]`                         | Row‑level emission results                            |
| total_kg           | `float`                | Sum of ``co2e_kg`` over all results                    |
| total_t            | `float`                | ``total_kg / 1000.0``                                  |
| by_category()      | `dict[str, float]`     | CO₂e total per category                                |
| by_gas()           | `dict[str, float]`     | CO₂e total per gas                                     |

## 6. Emission Result Fields

| Field name         | Type                   | Description                                          |
|--------------------|------------------------|-------------------------------------------------------|
| activity_id        | `str`                  | Identifier of the activity that produced the emission  |
| factor_id          | `str`                  | Identifier of the emission factor used                 |
| scope              | `int`                  | 1, 2, or 3                                            |
| category           | `str`                  | GHG Protocol category                                  |
| substance          | `str`                  | Fuel, material or energy type                          |
| gas                | `str`                  | Gas emitted (``CO2``, ``CH4``, ``N2O``, or ``CO2e``) |
| activity_value     | `float`                | The activity quantity (as entered)                     |
| activity_unit      | `str`                  | Unit of the activity value                             |
| factor_value       | `float`                | The factor value (as entered)                          |
| factor_unit        | `str`                  | Unit of the factor value                               |
| emissions_kg       | `float`                | Mass of gas emitted (before GWP conversion)            |
| gwp                | `float \| None`        | GWP applied (``None`` when factor is already ``CO2e``) |
| gwp_set            | `str \| None`          | Name of the GWP set used (``AR6``, ``AR5``, etc.)     |
| co2e_kg            | `float`                | Emission expressed as CO₂‑equivalents                  |

## 7. PCF (Product Carbon Footprint) Fields

| Field name              | Type                                   | Description                                               |
|-------------------------|----------------------------------------------------------|-----------------------------------------------------------|
| pcf_id                  | `str` (required)                                         | Unique product identifier                                |
| product_name          | `str` (required)                                         | Name of the product                                      |
| functional_unit       | `str` (required)                                         | Declared functional unit                                 |
| production_qty          | `float` (required)                                       | Reference flow: quantity of product the inventory relates to|
| production_unit         | `str` (required)                                         | Unit of the production quantity (e.g. ``t``, ``kg``, ``m³``) |
| system_boundary         | `str` (`"cradle_to_gate"` / `"cradle_to_grave"`)          | Boundary scope                                           |
| included_stages         | `tuple[str, ...]`                                        | Stages included for the declared boundary                 |
| items                   | `tuple[InventoryItem, ...]`                              | Life‑cycle inventory items                               |
| total_kg              | `float`                                                  | Attributable life‑cycle CO₂e in kilograms                 |
| total_t               | `float`                                                  | ``total_kg / 1000.0``                                    |
| per_unit              | `float`                                                  | kg CO₂e per unit of the declared production unit          |
| unit_label            | `str`                                                    | Formatted unit label (e.g. ``"kg CO2e/t"``)               |

## 7. Inventory Item Fields

| Field name         | Type                   | Description                                               |
|--------------------|------------------------|-----------------------------------------------------------|
| stage              | `str` (required)       | Life‑cycle stage (must be inside the declared boundary)   |
| activity           | `ActivityRecord` (required)                              | The activity data record                                   |
| factor             | `EmissionFactor` (required)                               | The emission factor                                       |
| excluded_from_corporate | `bool` (default ``False``)                           | If ``True``, the contribution is absent from the corporate total |

## 8. Allocation Rule Fields

| Field name         | Type                   | Description                                               |
|--------------------|------------------------|-----------------------------------------------------------|
| method             | `str` (required)       | ``mass``, ``economic``, ``physical_causality``, or ``none`` |
| stage              | `str \| None`          | Stage the rule applies to (``None`` = default for all stages) |
| basis_value        | `float`                | This product's basis amount                                |
| basis_total        | `float`                | Sum of basis amounts over all co‑products                  |
| basis_unit         | `str`                  | Unit of the basis values (e.g. ``kg``, ``USD``, ``MJ``)   |
| notes              | `str`                  | Free‑form methodological notes                            |

## 9. Allocation Rule Validation Rules

- ``basis_value`` and ``basis_total`` must both be positive.
- ``basis_value`` must not exceed ``basis_total``.
- ``basis_unit`` must be a non‑empty string.
- Method ``mass`` requires a mass basis unit; method ``economic`` requires a currency basis unit.
- Method ``none`` must not have ``basis_value``, ``basis_total``, or ``basis_unit`` set.

## 9. Lever Fields (Decarbonisation Scenarios)

| Field name         | Type                   | Description                                               |
|--------------------|------------------------|-----------------------------------------------------------|
| kind               | `str`                  | Lever kind (``renewable_electricity``, ``energy_efficiency``, etc.) |
| name               | `str`                  | Human‑readable lever name                                |
| share              | `float`                | Fraction of the target to replace (0 < share < 1)         |
| improvement          | `float`                | Fraction of reduction (0 < improvement < 1)               |
| efficiency           | `float`                | Fraction of reduction (0 < efficiency < 1)                |
| from_substance     | `str`                  | Source substance for fuel switch or material substitution  |
| to_substance       | `str`                  | Target substance for fuel switch or material substitution  |
| to_factor          | `EmissionFactor`       | Replacement emission factor (required for fuel switch / material substitution) |
| reduction          | `float`                | Fraction of waste/process emissions to reduce (0 < reduction < 1) |

## 10. Monte Carlo Input Distribution Fields

| Field name         | Type                   | Description                                               |
|--------------------|------------------------|-----------------------------------------------------------|
| name               | `str` (required)         | Description of the input                                 |
| activity_id        | `str` (required)         | Identifier of the activity the input belongs to           |
| field              | `str` (required)         | ``quantity`` or ``factor_value``                         |
| kind               | `str`                  | ``normal``, ``lognormal``, ``triangular``, ``uniform``, or ``fixed`` |
| spread_pct         | `float`                | Relative spread / standard deviation in percent            |

## 11. Scenario Result Fields

| Field name         | Type                   | Description                                               |
|--------------------|------------------------|-----------------------------------------------------------|
| name               | `str`                  | Scenario name                                            |
| baseline_kg        | `float`                | Baseline total CO₂e (kg)                                 |
| scenario_kg        | `float`                | Scenario total CO₂e (kg)                                 |
| reduction_kg       | `float`                | ``baseline_kg - scenario_kg``                           |
| reduction_pct      | `float \| None`          | ``reduction_kg / baseline_kg * 100``; ``None`` if baseline is zero |

## 12. Excel Report Fields

| Field name         | Type                   | Description                                               |
|--------------------|------------------------|-----------------------------------------------------------|
| workbook           | `openpyxl.Workbook`    | The generated Excel workbook                             |
| summary_sheet      | `openpyxl.Worksheet`    | Summary worksheet with organisation totals                |
| scope_sheets       | `dict[int, openpyxl.Worksheet]`                         | Per‑scope worksheets (Scope 1, 2, 3)                     |
| detail_sheets      | `dict[str, openpyxl.Worksheet]`                         | Detail worksheets (activity/factor rows)                 |
| reconciliation_sheet | `openpyxl.Worksheet`                              | Reconciliation check (derived total vs stored total)      |

## 13. PDF Report Fields

| Field name         | Type                   | Description                                               |
|--------------------|------------------------|-----------------------------------------------------------|
| pdf                | `bytes`                | The generated PDF binary                                 |
| cover_page         | `bool`                 | If ``True``, includes a cover page                       |
| scope_breakdown    | `str`                  | Text summary of scope totals                             |
| methodology        | `str`                  | Text summary of the methodology used                     |
| key_results        | `list[tuple[str, str]]`  | List of (metric, value) pairs for the key results table   |
| limitations        | `str`                  | Text describing limitations and data provenance           |

## 14. CLI Arguments

| Argument           | Type                   | Description                                               |
|--------------------|------------------------|-----------------------------------------------------------|
| --activities       | `str` (required)         | Path to CSV file with activity data                      |
| --gwp-set          | `str`                  | GWP set to use (``AR6``, ``AR5``, ``AR6-ERRATA-2025``)  |
| --run-id           | `str` (required)         | Identifier for the calculation run                       |
| --period-label     | `str`                  | Label for the reporting period                           |
| --organisation-name| `str`                  | Organisation name for PDF reports                        |
| --report-types     | `list[str]`              | Report types to generate (``excel``, ``pdf``)            |

## 14. Error Codes (selected)

| Error class                      | Raised when ...                                                                 |
|------------------------------------|----------------------------------------------------------------------------------|
| ``OpenCarbonChemError``            | Base class for all errors                                                        |
| ``IncompatibleUnitError``          | A unit conversion crosses dimensions without a registered factor                  |
| ``MissingFactorError``             | No emission factor matches the activity's category/substance/geography/year      |
| ``AmbiguousFactorError``           | The substance has factors for multiple gases and no ``gas`` is set on the activity |
| ``MissingGWPError``                | A GWP set has no value for the gas (or methane basis is missing)                |
| ``PCFError``                       | A product definition, life‑cycle stage, or inventory item is invalid              |
| ``AllocationError``                | An allocation rule is malformed (wrong basis, unknown method, etc.)               |
| ``DoubleCountingError``            | The same emission appears in both corporate inventory and PCF without being flagged |
| ``ScenarioError``                  | A decarbonisation lever is invalid or matches no rows                             |
| ``UncertaintyError``               | A Monte Carlo configuration is invalid (bad distribution, bad params, etc.)      |
| ``PDFExportError``                 | PDF generation failed                                                             |
| ``ReconciliationError``            | Excel totals do not match the stored ``total_co2e_kg``                            |