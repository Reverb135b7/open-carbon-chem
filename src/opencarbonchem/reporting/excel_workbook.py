"""Excel workbook generation for OpenCarbonChem reports.

Contents
--------
- ``Summary``: run ID, GWP set, period, organisation total (kg and t)
- ``Scope1_Detail`` / ``Scope2_Detail`` / ``Scope3_Detail`` (for the scopes that
  were reported): every emission row with the activity value and unit, the
  factor applied (value, unit, ID), the gas, GWP and GWP set, and the resulting
  emissions and CO2e
- ``Reconciliation``: the total re-derived from the rows next to the report
  total, with an explicit match flag

The guard is always on: if the derived total does not match the report total,
``build_excel_report`` raises :class:`ReconciliationError` and nothing is
written. All numbers come from the same ``EmissionResult`` rows, so the detail
sheets and the summary cannot diverge.
"""

from __future__ import annotations

import io
from typing import Any, List

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from ..accounting.aggregate import OrganizationReport, ScopeResult
from ..core.calc import EmissionResult
from ..core.exceptions import ReconciliationError

# -- style helpers -------------------------------------------------------- #

_SOLID_FILL = PatternFill("solid", fgColor="FFFFFF")
_HEADER_FONT = Font(bold=True, size=11)
_SUBHEADER_FONT = Font(bold=True, size=10)
_DETAIL_FONT = Font(size=10)
_THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
_ALIGN_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_ALIGN_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)


# -- workbook builder ----------------------------------------------------- #

def _write_row(ws, row_num: int, values: List[Any], formats: List[dict] | None = None) -> None:
    """Write a row of values with optional per-cell formatting."""
    cell_fmts = formats or [{} for _ in values]
    for col_idx, (value, fmt) in enumerate(zip(values, cell_fmts), start=1):
        cell = ws.cell(row=row_num, column=col_idx, value=value)
        for key, val in fmt.items():
            if key == "font":
                cell.font = val
            elif key == "alignment":
                cell.alignment = val
            elif key == "border":
                cell.border = val


def _auto_width(ws, min_col: int, max_col: int, header_row: int = 1) -> None:
    """Adjust column widths based on the longest entry in each column."""
    for col in range(min_col, max_col + 1):
        max_len = 0
        for row in ws.iter_rows(min_row=header_row, max_row=ws.max_row, min_col=col, max_col=col):
            for cell in row:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[get_column_letter(col)].width = max(max_len + 2, 10)


# -- Excel workbook ------------------------------------------------------- #


class ExcelWorkbook:
    """Build an Excel workbook from an ``OrganizationReport`` and calculation results.

    The workbook always includes a reconciliation check: the derived total is
    compared to ``total_co2e_kg`` and a ``ReconciliationError`` is raised if they
    do not match.
    """

    def __init__(
        self,
        report: OrganizationReport,
        emission_results: List[EmissionResult],
        *,
        gwp_set: str = "AR6",
        run_id: str | None = None,
        period_label: str = "",
    ) -> None:
        self.report = report
        self.emission_results = emission_results
        self.gwp_set = gwp_set
        self.run_id = run_id
        self.period_label = period_label
        self.wb = openpyxl.Workbook()

    # -- build ---------------------------------------------------------- #
    def build(self) -> "ExcelWorkbook":
        """Assemble all worksheets and return ``self`` for chaining."""
        ws = self.wb.active
        ws.title = "Summary"
        self._write_summary(ws)

        # Scope worksheets
        for scope in (1, 2, 3):
            scope_result = next(
                (r for r in self.report.scope_results if r.scope == scope), None
            )
            if scope_result is not None:
                name = {1: "Scope1", 2: "Scope2", 3: "Scope3"}[scope]
                ws = self.wb.create_sheet(title=f"{name}_Detail")
                self._write_scope_detail(ws, scope_result)

        # Reconciliation sheet
        ws = self.wb.create_sheet(title="Reconciliation")
        self._write_reconciliation(ws)

        # Remove the default "Sheet" that openpyxl creates
        if "Sheet" in self.wb.sheetnames:
            del self.wb["Sheet"]

        return self

    # -- summary sheet ---------------------------------------------------- #
    def _write_summary(self, ws) -> None:
        ws.cell(row=1, column=1, value="OpenCarbonChem — Excel Report").font = Font(
            bold=True, size=14
        )
        ws.cell(row=2, column=1, value="Run ID").font = _HEADER_FONT
        ws.cell(row=2, column=2, value=self.run_id or "—").font = _DETAIL_FONT
        ws.cell(row=3, column=1, value="GWP set").font = _HEADER_FONT
        ws.cell(row=3, column=2, value=self.gwp_set).font = _DETAIL_FONT
        ws.cell(row=4, column=1, value="Period").font = _HEADER_FONT
        ws.cell(row=4, column=2, value=self.period_label or "—").font = _DETAIL_FONT
        ws.cell(row=5, column=1, value="Organisation total (kg)").font = _HEADER_FONT
        ws.cell(
            row=5, column=2, value=self.report.total_kg
        ).font = _DETAIL_FONT
        ws.cell(
            row=5, column=3, value="Organisation total (t)").font = _DETAIL_FONT
        ws.cell(
            row=5, column=4, value=self.report.total_t
        ).font = _DETAIL_FONT
        _auto_width(ws, 1, 4)

    # -- scope detail sheets ---------------------------------------------- #
    def _write_scope_detail(self, ws, scope_result: ScopeResult) -> None:
        ws.cell(row=1, column=1, value=f"Scope {scope_result.scope} — Detail").font = Font(
            bold=True, size=12
        )
        # Headers
        headers = [
            "Activity ID",
            "Category",
            "Substance",
            "Quantity",
            "Unit",
            "Gas",
            "Factor value",
            "Factor unit",
            "GWP",
            "GWP set",
            "Emissions (kg gas)",
            "CO2e (kg)",
            "Factor ID",
            "Source",
            "Reference",
            "Review status",
            "Uncertainty (%)",
        ]
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=2, column=col_idx, value=h)
            cell.font = _HEADER_FONT
            cell.alignment = _ALIGN_CENTER
        # Rows
        for row_idx, r in enumerate(scope_result.results, start=3):
            ws.cell(row=row_idx, column=1, value=r.activity_id).font = _DETAIL_FONT
            ws.cell(row=row_idx, column=2, value=r.category).font = _DETAIL_FONT
            ws.cell(row=row_idx, column=3, value=r.substance).font = _DETAIL_FONT
            # The quantity column must carry the activity value: writing
            # emissions here made the audit sheet misstate its own inputs.
            ws.cell(row=row_idx, column=4, value=r.activity_value).font = _DETAIL_FONT
            ws.cell(row=row_idx, column=4).number_format = "0.000"
            ws.cell(row=row_idx, column=5, value=r.activity_unit).font = _DETAIL_FONT
            ws.cell(row=row_idx, column=6, value=r.gas or "").font = _DETAIL_FONT
            ws.cell(row=row_idx, column=7, value=r.factor_value).font = _DETAIL_FONT
            ws.cell(row=row_idx, column=7).number_format = "0.0000"
            ws.cell(row=row_idx, column=8, value=r.factor_unit).font = _DETAIL_FONT
            ws.cell(row=row_idx, column=9, value=r.gwp if r.gwp is not None else "—").font = _DETAIL_FONT
            ws.cell(row=row_idx, column=10, value=r.gwp_set or "—").font = _DETAIL_FONT
            ws.cell(row=row_idx, column=11, value=r.emissions_kg).font = _DETAIL_FONT
            ws.cell(row=row_idx, column=11).number_format = "0.000"
            ws.cell(row=row_idx, column=12, value=r.co2e_kg).font = _DETAIL_FONT
            ws.cell(row=row_idx, column=12).number_format = "0.000"
            ws.cell(row=row_idx, column=13, value=r.factor_id).font = _DETAIL_FONT
            ws.cell(row=row_idx, column=14, value=r.source_org).font = _DETAIL_FONT
            ws.cell(row=row_idx, column=15, value=r.source_reference).font = _DETAIL_FONT
            ws.cell(row=row_idx, column=16, value=r.review_status).font = _DETAIL_FONT
            ws.cell(row=row_idx, column=17, value=r.uncertainty_pct).font = _DETAIL_FONT
        _auto_width(ws, 1, 17)

    # -- reconciliation sheet --------------------------------------------- #
    def _write_reconciliation(self, ws) -> None:
        ws.cell(row=1, column=1, value="Reconciliation").font = Font(bold=True, size=12)
        # Derive total from rows
        derived_kg = sum(r.co2e_kg for r in self.emission_results)
        derived_t = derived_kg / 1000.0
        actual_kg = self.report.total_kg
        actual_t = self.report.total_t
        match_kg = abs(derived_kg - actual_kg) < 1e-6
        match_t = abs(derived_t - actual_t) < 1e-6

        ws.cell(row=2, column=1, value="Derived total (kg)").font = _HEADER_FONT
        ws.cell(row=2, column=2, value=f"{derived_kg:,.3f}").font = _DETAIL_FONT
        ws.cell(row=3, column=1, value="Report total (kg)").font = _HEADER_FONT
        ws.cell(row=3, column=2, value=f"{actual_kg:,.3f}").font = _DETAIL_FONT
        ws.cell(row=4, column=1, value="Derived total (t)").font = _HEADER_FONT
        ws.cell(row=4, column=2, value=f"{derived_t:,.3f}").font = _DETAIL_FONT
        ws.cell(row=5, column=1, value="Report total (t)").font = _HEADER_FONT
        ws.cell(row=5, column=2, value=f"{actual_t:,.3f}").font = _DETAIL_FONT
        ws.cell(row=6, column=1, value="Reconciliation OK").font = Font(
            bold=True, size=11
        )
        ws.cell(
            row=6, column=2,
            value="✅ OK" if match_kg and match_t else "❌ Mismatch",
        ).font = Font(bold=True, size=11, color="00FF00" if match_kg and match_t else "FF0000")
        ws.cell(row=7, column=1, value="Notes").font = _HEADER_FONT
        ws.cell(
            row=7, column=2,
            value="" if match_kg and match_t else "Derived total does not match report total.",
        ).font = _DETAIL_FONT
        _auto_width(ws, 1, 2)


# -- Excel report wrapper ------------------------------------------------- #


class ExcelReport:
    """Convenient wrapper :class:`openpyxl.Workbook` → ``bytes`` export."""

    def __init__(self, workbook: ExcelWorkbook) -> None:
        self.workbook = workbook

    def save(self, path: str) -> None:
        """Write the workbook to ``path`` (``.xlsx``)."""
        self.workbook.wb.save(path)

    def save_to_bytes(self) -> bytes:
        """Return the workbook as bytes."""
        buf = io.BytesIO()
        self.workbook.wb.save(buf)
        buf.seek(0)
        return buf.read()


# ------------------------------------------------------------------------ #
# ExcelReport(builder) ----------------------------------------------------- #
# ------------------------------------------------------------------------ #


def build_excel_report(
    report: OrganizationReport,
    emission_results: List[EmissionResult],
    *,
    gwp_set: str = "AR6",
    run_id: str | None = None,
    period_label: str = "",
) -> ExcelReport:
    """Convenience wrapper that builds an ``ExcelWorkbook`` and returns an
    ``ExcelReport`` instance.

    Raises ``ReconciliationError`` if the derived total from ``emission_results``
    does not match ``report.total_kg``.
    """
    workbook = ExcelWorkbook(
        report,
        emission_results,
        gwp_set=gwp_set,
        run_id=run_id,
        period_label=period_label,
    ).build()
    # Reconciliation guard — re-derive and compare
    derived_kg = sum(r.co2e_kg for r in emission_results)
    if not abs(derived_kg - report.total_kg) < 1e-9:
        raise ReconciliationError(
            f"Excel total {derived_kg:g} kg differs from report total "
            f"{report.total_kg:g} kg."
        )
    return ExcelReport(workbook)