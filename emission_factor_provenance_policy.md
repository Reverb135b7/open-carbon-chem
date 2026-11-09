# OpenCarbonChem — Emission-Factor Provenance Policy

This policy governs how emission factors are sourced, stored, validated, and presented
within OpenCarbonChem. Its purpose is to ensure transparency, traceability, and honest
representation of the provenance of every factor used in the software.

## 1. Source Tagging

Every emission factor must carry the following provenance fields:

| Field          | Requirement | Description                                                                    |
|----------------|-------------|--------------------------------------------------------------------------------|
| ``source_org`` | **Required** | Name of the source organisation (e.g. ``IPCC``, ``DEFRA``, ``EC-JRC``, ``SYNTHETIC``). |
| ``source_reference`` | **Required** | URL, DOI, or document reference for the factor. Must be a persistent, resolvable identifier where possible. |
| ``reporting_year`` | **Required** | Year the factor is valid for. |
| ``version``    | **Required** | Publication or version information (e.g. ``2024``, ``v1.2``, ``draft``).       |
| ``review_status`` | **Required** | Must be one of: ``illustrative``, ``published``, or ``verified``.                |
| ``uncertainty_pct`` | **Optional** | Relative uncertainty, %, where available. If ``None``, the default spread (10%) is used in Monte Carlo uncertainty propagation. |
| ``notes``      | **Optional** | Free‑form methodological notes.                                                  |

## 2. Review Status Values

| Value          | Meaning                                                                                                        |
|----------------|----------------------------------------------------------------------------------|
| ``illustrative`` | Synthetic test data; clearly marked as such. Never presented as an official factor. Used for software testing only. |
| ``published``  | Transcribed from a published authoritative source with a ``source_reference`` recorded. May be used in demonstrations but must not be presented as independently verified. |
| ``verified``   | Independently checked against the source document. Still carries the ``source_reference`` and must not be presented as “certified” or “officially verified” without the relevant assessment. |

## 3. Synthetic and Published Data

- The default seed CSV (`src/opencarbonchem/factors/data/published_factors.csv`) holds values transcribed from the DESNZ 2024 full set and IPCC 2006 Guidelines. Every row is ``review_status=published`` with a document reference and version; per-factor sources are listed in ``docs/FACTOR_SOURCES.md``.
- ``published`` means transcribed, not independently verified. No row may be labelled ``verified`` without the corresponding check being recorded, and none is currently.
- The synthetic seed (`illustrative_factors.csv`, ``source_org=SYNTHETIC``) is retained for software tests and demonstrations. Synthetic factors must **not** be presented as official emission factors in any output (dashboard, report, CLI, etc.).
- Factors flagged ``illustrative`` cause the report writers to append the synthetic-data warning; the dashboard shows ``review_status`` and ``source_org`` for every factor used.
- New factors entered via the Emission Factor DB page keep whatever ``review_status`` the user selects; the UI defaults to ``illustrative`` if uncertain.
- It is an explicit policy violation to auto‑set ``review_status=published`` or ``verified`` for synthetic data.

## 4. Provenance in Reports

- **Excel workbook**: every row sheet includes the factor's ``factor_id``, ``source_org``, ``source_reference``, ``review_status``, and ``uncertainty_pct`` in the detail columns.
- **PDF executive summary**: the methodology appendix lists the GWP set used and notes that all factors are either ``published`` or ``illustrative``; synthetic factors are flagged.
- **CLI output**: the ``opencarbonchem calculate`` command prints the GWP set and a note on factor provenance.

## 4. Validation Workflow

### 4.1 Factor onboarding
1. User provides a CSV or uses the Emission Factor DB UI.
2. Each row is parsed and validated against the ``EmissionFactor`` Pydantic model.
3. ``factor_id`` uniqueness is enforced — duplicate IDs raise ``AmbiguousFactorError``.
4. The factor is stored in the SQLite database with all provenance fields.
5. The factor is indexed for lookup by ``(activity_category, substance, geography, reporting_year)``.

### 4.2 Factor lookup
1. Given an activity's ``category``, ``substance``, ``geography``, and ``reporting_year``,
   the ``FactorRegistry.find()`` method resolves the applicable factor.
2. Geography ranking: exact match > ``GLOBAL`` > no match (raises ``MissingFactorError``).
3. Vintage ranking: the newest factor at or before the reporting year wins; if no factor
   exists at or before the year, a ``MissingFactorError`` is raised with the earliest available
   vintage.
4. If the substance has factors for multiple gases and no ``gas`` is set on the activity,
   ``AmbiguousFactorError`` is raised, prompting the user to set the activity's ``gas`` field.

### 4.3 Factor retirement
- Factors can be retired by updating ``review_status`` to a deprecated value or removing
  them from the database.
- Retired factors remain in the database for audit purposes but are excluded from active lookup
  unless explicitly re‑enabled.

## 5. Policy Enforcement

- The dashboard and CLI display ``review_status`` and ``source_org`` for every factor used.
- The Excel workbook and PDF summary include a provenance note: "All factors are labelled
  ``review_status=published`` or ``illustrative``; synthetic factors are clearly marked."
- If a user attempts to generate a report using only ``illustrative`` factors without a disclaimer,
  the system appends a prominent warning: "This report uses synthetic emission factors for
  demonstration only; it must not be used for official ESG reporting."

## 6. Compliance and Auditing

- The SQLite database schema stores all provenance fields, enabling full audit trails.
- The reconciliation guard in the Excel workbook compares derived totals to ``total_co2e_kg``,
  ensuring that no hidden drift occurs between the report and the database.
- The software never silently assumes zero for missing data; coverage gaps are always flagged
  for human review (per the handover §15).

## 6. Contact and Questions

For questions about factor provenance, policy, or onboarding, please refer to the
``CONTRIBUTING.md`` or open an issue on the GitHub repository.