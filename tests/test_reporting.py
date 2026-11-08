"""Milestone 10 — report generation tests (Excel and PDF).

The reporting layer must reconcile with the calculation records: a workbook
whose numbers do not re-derive from the results is refused, not written.
"""

from __future__ import annotations

import io
import zlib
from base64 import a85decode
from datetime import date

import pytest
from openpyxl import load_workbook

from opencarbonchem.accounting import (
    OrganizationReport,
    calculate_scope1,
    calculate_scope2,
    calculate_scope3,
)
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.core.exceptions import (
    ExportError,
    PDFExportError,
    ReconciliationError,
)
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.reporting import build_excel_report, build_pdf_report

pytestmark = pytest.mark.unit

PERIOD = dict(period_start=date(2024, 1, 1), period_end=date(2024, 12, 31))


@pytest.fixture(scope="module")
def registry() -> FactorRegistry:
    return FactorRegistry.from_csv()


def act(activity_id: str, category: str, substance: str, quantity: float, unit: str,
        gas: str | None = None, scope: int = 1) -> ActivityRecord:
    return ActivityRecord(
        activity_id=activity_id, scope=scope, category=category, substance=substance,
        quantity=quantity, unit=unit, gas=gas, **PERIOD,
    )


@pytest.fixture(scope="module")
def inventory(registry):
    """180 kg (gas) + 450 kg (grid) + 1200 kg (paper) = 1830 kg CO2e."""
    s1 = calculate_scope1(
        [act("A-GAS", "stationary_combustion", "natural_gas", 1000, "kWh", gas="CO2")],
        registry,
    )
    s2 = calculate_scope2(
        [act("A-ELEC", "purchased_electricity", "grid_electricity", 1000, "kWh",
             gas="CO2e", scope=2)],
        registry,
    ).location
    s3 = calculate_scope3(
        [act("A-PAPER", "s3_cat01", "paper", 1000, "kg", scope=3)],
        registry,
    )
    report = OrganizationReport.from_results([s1, s2, s3])
    rows = [row for result in (s1, s2, s3) for row in result.results]
    return report, rows


def _pdf_text(payload: bytes) -> bytes:
    """Decode the ASCII85 + Flate content streams so text can be inspected."""
    chunks: list[bytes] = []
    for chunk in payload.split(b"endstream")[:-1]:
        body = chunk.split(b"stream")[-1].strip()
        if body.endswith(b"~>"):
            body = body[:-2]
        try:
            chunks.append(zlib.decompress(a85decode(body, adobe=False)))
        except (zlib.error, ValueError):
            continue
    return b"\n".join(chunks)


def test_excel_totals_match_calculation_records(inventory):
    report, rows = inventory
    excel = build_excel_report(report, rows, gwp_set="AR6", run_id="RUN-XLSX",
                               period_label="2024")
    workbook = load_workbook(io.BytesIO(excel.save_to_bytes()))

    assert "Summary" in workbook.sheetnames
    assert "Reconciliation" in workbook.sheetnames

    values = [
        cell.value
        for row in workbook["Summary"].iter_rows()
        for cell in row
        if isinstance(cell.value, (int, float))
    ]
    # The report total (1830 kg) must appear in the summary sheet.
    assert any(abs(float(value) - 1830.0) < 1e-6 for value in values)


def test_excel_refuses_to_write_mismatched_rows(inventory):
    report, rows = inventory
    # Dropping a row leaves the report total inconsistent with the records.
    with pytest.raises(ReconciliationError):
        build_excel_report(report, rows[:-1])


def test_excel_save_writes_a_file(inventory, tmp_path):
    report, rows = inventory
    path = tmp_path / "report.xlsx"
    build_excel_report(report, rows, run_id="RUN-SAVE").save(str(path))
    assert path.exists() and path.stat().st_size > 0


def test_pdf_builds_and_contains_the_summary(inventory):
    report, rows = inventory
    pdf = build_pdf_report(
        report, rows, gwp_set="AR6", run_id="RUN-PDF",
        period_label="2024", organisation_name="Synthetic Chemicals Ltd",
    )
    payload = pdf.save_to_bytes()
    assert payload.startswith(b"%PDF")

    text = _pdf_text(payload)
    assert b"Synthetic Chemicals Ltd" in text
    assert b"Executive Summary" in text
    # The reported total must appear in the document (1830 kg).
    assert b"1830" in text.replace(b",", b"")


def test_pdf_save_writes_a_file(inventory, tmp_path):
    report, rows = inventory
    path = tmp_path / "report.pdf"
    build_pdf_report(report, rows).save(str(path))
    assert path.exists() and path.stat().st_size > 0


def test_export_errors_are_typed():
    # The reporting layer raises ExportError subclasses, never bare exceptions.
    assert issubclass(PDFExportError, ExportError)
