# OpenCarbonChem — Validation Protocol

This protocol defines the mandatory validation steps that must be performed before any
software release, report generation, or public demonstration of OpenCarbonChem.

## 1. Test Suite Validation

- **Full suite run**: `python -m pytest` must yield **125 passed** with no failures or skips.
- **Unit tests**: all module‑level functions and classes are tested in ``tests/``.
- **Integration tests**: cross‑module tests (e.g. PCF ↔ corporate inventory double‑counting)
  must pass.
- **No test suppression**: no ``pytest.mark.xfail``, no ``pytest.raises`` work‑arounds,
  no commented‑out assertions. Every test must be an assertion of actual behaviour.

## 2. Reconciliation Validation

- **Excel workbook**: after building an Excel report, the derived total (sum of all
  ``co2e_kg`` in the detail sheets) must exactly match ``total_co2e_kg`` of the
  corresponding calculation run. Mismatch → ``ReconciliationError`` and generation
  is aborted.
- **PDF summary**: the organisation total stated on the first page must match the
  ``total_kg`` / ``total_t`` derived from the stored calculation results.
- **Database round‑trip**: save a result set to SQLite, reload it, and recompute the
  totals; they must be identical to the original computation (idempotent ``init_schema``).

## 3. Synthetic‑Data Disclaimer Validation

- Every output that uses the packaged seed factors must include a disclaimer:
  "This report uses synthetic emission factors (review_status=illustrative, source_org=SYNTHETIC)
  for demonstration only. It must not be presented as official ESG reporting."
- The dashboard ``1. Overview`` page includes this disclaimer.
- The PDF executive summary includes a limitations section with the same text.
- The CLI ``opencarbonchem calculate`` output appends the disclaimer.

## 3. Unit and Dimensional Validation

- **Unit engine stress test**: generate random unit expressions and verify that
  incompatible combinations raise ``IncompatibleUnitError``, while compatible
  combinations always succeed.
- **No silent conversion**: verify that the engine never returns a number without a unit
  or a unit conversion that the user did not explicitly request.

## 4. Sensitivity and Monte Carlo Validation

- **Sensitivity**: for a single‑parameter perturbation of ±10%, the computed swing must
  be approximately 20% of the baseline (i.e. −10% and +10% of the baseline value).
- **Monte Carlo reproducibility**: run the same Monte Carlo simulation with two different
  seeds; the two result objects must have different ``p5_kg``, ``p95_kg``, and ``mean_kg``.
- Run the same simulation with the **same seed** twice; the ``mean_kg``, ``median_kg``,
  ``p5_kg``, ``p95_kg``, and ``std_kg`` must be **identical** (byte‑level comparison of the
  saved results).
- Variance‑share contributions must be non‑negative and sum to approximately 1.0 (allow
  for Monte Carlo noise with a small number of draws).

## 5. PCF Validation

- **Boundary enforcement**: adding an inventory item with a stage outside the product's
  declared boundary raises ``PCFError``.
- **Allocation validation**: allocating with ``mass`` method and a non‑mass basis unit
  raises ``AllocationError``; allocating with ``economic`` and a non‑currency basis unit
  raises ``AllocationError``.
- **Double‑counting guard**: a PCF row with ``excluded_from_corporate=False`` that matches
  a corporate inventory row raises ``DoubleCountingError``.
- **Per‑unit calculation**: ``per_unit = total_kg / production_qty`` must be numerically
  stable and consistent across recomputations.

## 6. Decarbonisation Scenario Validation

- **Lever validation**: each lever kind has a dedicated test that verifies:
  - the lever can be instantiated with valid parameters,
  - the lever raises ``ScenarioError`` for invalid parameters,
  - the lever raises ``ScenarioError`` when it matches no rows.
- **Baseline‑scenario comparison**: for a known baseline total and a lever that reduces
  emissions by a known fraction, the computed reduction percentage must match the expected
  value within a tolerance of 0.1%.
- **Zero‑baseline guard**: a scenario with a baseline total of 0 must produce ``reduction_pct = None``,
  never 0 % or ``inf``.

## 6. Dashboard Validation

- All 11 Streamlit pages load without JavaScript errors (checked via ``pytest‑streamlit`` or
  manual inspection).
- Each page displays the synthetic data disclaimer where synthetic factors are used.
- The Excel and PDF report generation buttons are disabled (or produce a warning) when no
  calculation run is available.
- The hotspot, sensitivity, and Monte Carlo pages render their respective tables/plots
  without error using the synthetic dataset.

## 7. Documentation Validation

- ``LICENSE`` file exists and contains the Apache-2.0 text.
- ``CONTRIBUTING.md`` exists and follows the template provided.
- ``methodology_documentation.md``, ``assumptions_documentation.md``,
  ``data_dictionary.md``, ``emission_factor_provenance_policy.md``, and
  ``validation_protocol.md`` all exist under the project root.
- The README.md references these documents and lists them in a "Documentation" section.
- The roadmap in ``docs/architecture.md`` has all rows 1‑10 populated (or explicitly deferred
  with reasons).

## 7. CLI Validation

- ``opencarbonchem --help`` prints the usage string without error.
- ``opencarbonchem calculate --help`` prints the calculate‑subparser help.
- ``opencarbonchem calculate --activities <csv> --run-id test`` generates both Excel and PDF
  reports (when synthetic data is present) without error.
- Missing required arguments print a helpful usage message and exit with code 2.

## 8. Continuous Integration Validation

- On every push, the CI pipeline must run `python -m pytest -q` and confirm 125 passed.
- The CI pipeline must also run the Excel reconciliation check and the PDF generation smoke test.
- If any of the above fail, the CI must block the merge and report the failure.

## 8. Release Checklist

Before a release is tagged, the following must be complete:

- [ ] `python -m pytest -q` yields **125 passed**.
- [ ] Excel reconciliation guard passes for at least one full run.
- [ ] PDF executive summary generates without error for at least one full run.
- [ ] All six documentation files (LICENSE, CONTRIBUTING.md, methodology_documentation.md,
    assumptions_documentation.md, data_dictionary.md, emission_factor_provenance_policy.md,
    validation_protocol.md) exist and are properly formatted.
- [ ] The README.md is up‑to‑date and references all documentation files.
- [ ] The roadmap in ``docs/architecture.md`` has all rows 1‑10 populated (or explicitly deferred).
- [ ] The dashboard (11 pages) is operational and the full test suite passes.
- [ ] A `STATUS.md` file exists at the project root with the current status summary.

## 8. Release Checklist (continued)

- [ ] LICENSE is Apache‑2.0.
- [ ] CONTRIBUTING.md follows the template.
- [ ] Git tag is created (e.g. ``v0.1.0``).
- [ ] GitHub release is drafted with the release notes summarising what was added in the
  release, particularly any new features from the just‑completed milestone.
- [ ] If applicable, user authorisation is obtained before pushing to the GitHub repository
  (the handover specifies: "GitHub publication requires the user's explicit authorization to push").

## 9. Post‑Release

- Monitor the issue tracker for any validation‑related bugs reported within 48 hours of
  release.
- If any critical bug is found, patch the relevant module, re‑run the full test suite,
  and re‑issue the release tag.
- Update the ``STATUS.md`` file with the new release version and date.