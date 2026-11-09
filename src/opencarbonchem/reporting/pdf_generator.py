"""PDF executive summary generation for OpenCarbonChem reports.

Features
--------
- Cover page: organisation name, run ID, period, GWP set used
- Scope breakdown: totals for every reported scope (missing scopes are shown
  as "not reported", never as a number borrowed from another scope)
- Methodology appendix: optional boundary document reference, GWP set, formulae
  (E = AD x EF, CO2e = sum E_g x GWP_g)
- Key results table: organisation total and period metadata
- Limitations note: synthetic data, not for official ESG reporting
- Raises ``PDFExportError`` when generation fails or when the supplied rows do
  not reconcile with the report total

All text is restricted to the WinAnsi character set of the built-in Helvetica
font, so subscripts or Greek letters are written out (CO2e, sum) rather than
rendered as missing-glyph boxes.
"""

from __future__ import annotations

import io
from typing import Iterable

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white

from ..accounting.aggregate import OrganizationReport
from ..core.calc import EmissionResult, gwp_basis_note
from ..core.exceptions import PDFExportError

# -- style definitions ---------------------------------------------------- #

_STYLES = getSampleStyleSheet()

_TITLE_STYLE = ParagraphStyle(
    "TitleCustom",
    parent=_STYLES["Title"],
    fontSize=18,
    spaceAfter=6,
    alignment=1,  # center
)

_SUBTITLE_STYLE = ParagraphStyle(
    "SubTitleCustom",
    parent=_STYLES["Normal"],
    fontSize=11,
    spaceAfter=4,
    alignment=1,
)

_BODY_STYLE = _STYLES["Normal"]
_BODY_STYLE.fontSize = 10
_BODY_STYLE.spaceAfter = 4

_HEADING1 = _STYLES["Heading1"]
_HEADING1.fontSize = 14
_HEADING1.spaceAfter = 6

_INDENTED_STYLE = ParagraphStyle(
    "IndentedBody",
    parent=_BODY_STYLE,
    leftIndent=20,
    bulletIndent=0,
)

_METHODOLOGY_ITEMS = [
    "- Emissions calculated as E = Activity Data x Emission Factor "
    "(one engine: opencarbonchem.core.calc).",
    "- CO2e conversion uses IPCC {gwp_set} GWP values: "
    "CO2e = sum over gases of (E_g x GWP_g).",
    "- Scope 1: stationary combustion, mobile combustion, fugitive emissions, process emissions.",
    "- Scope 2: purchased electricity, steam, heat and cooling (location-based method; "
    "market-based totals are reported separately when contract factors are supplied).",
    "- Scope 3: GHG Protocol categories s3_cat01-s3_cat15.",
    "- Emission factors carry review_status=illustrative|published|verified; synthetic "
    "factors are labelled SYNTHETIC.",
]


class PDFReport:
    """Build an executive-summary PDF from an ``OrganizationReport`` and rows."""

    def __init__(
        self,
        report: OrganizationReport,
        emission_results: Iterable[EmissionResult],
        *,
        gwp_set: str = "AR6",
        run_id: str | None = None,
        period_label: str = "",
        organisation_name: str = "OpenCarbonChem Demo",
        boundary_document: str | None = None,
    ) -> None:
        self.report = report
        self.emission_results = tuple(emission_results)
        self.gwp_set = gwp_set
        self.run_id = run_id
        self.period_label = period_label
        self.organisation_name = organisation_name
        self.boundary_document = boundary_document
        self.buffer = io.BytesIO()

    # -- helpers ------------------------------------------------------------ #
    def _reconcile(self) -> float:
        """Return the row-derived total, refusing to publish a mismatched report."""
        derived = sum(r.co2e_kg for r in self.emission_results)
        if abs(derived - self.report.total_kg) > 1e-6:
            raise PDFExportError(
                f"row total {derived:g} kg does not match report total "
                f"{self.report.total_kg:g} kg"
            )
        return derived

    def scope_rows(self) -> list[list[str]]:
        """Scope lines keyed by the scope actually reported (never by position)."""
        by_scope = self.report.by_scope()
        rows = [["Scope", "CO2e (kg)", "CO2e (t)"]]
        for scope in (1, 2, 3):
            if scope in by_scope:
                kg = by_scope[scope]
                rows.append([f"Scope {scope}", f"{kg:,.1f}", f"{kg / 1000:,.3f}"])
            else:
                rows.append([f"Scope {scope}", "not reported", "-"])
        rows.append(["Total", f"{self.report.total_kg:,.1f}", f"{self.report.total_t:,.3f}"])
        return rows

    # -- build -------------------------------------------------------------- #
    def build(self) -> "PDFReport":
        """Render the PDF into the internal buffer."""
        self._reconcile()

        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=LETTER,
            topMargin=0.6 * inch,
            bottomMargin=0.6 * inch,
            leftMargin=0.6 * inch,
            rightMargin=0.6 * inch,
        )

        elements = []

        # ---- Cover page ----
        elements.append(Spacer(1, 1.5 * inch))
        elements.append(Paragraph(self.organisation_name, _TITLE_STYLE))
        elements.append(Spacer(1, 0.3 * inch))
        elements.append(Paragraph("OpenCarbonChem - Executive Summary", _SUBTITLE_STYLE))
        elements.append(Spacer(1, 0.3 * inch))

        cover_info = [
            ["Run ID", self.run_id or "-"],
            ["Period", self.period_label or "-"],
            ["GWP set", self.gwp_set],
            ["Organisation total (kg)", f"{self.report.total_kg:,.1f}"],
            ["Organisation total (t)", f"{self.report.total_t:,.3f}"],
        ]
        cover_table = Table(cover_info, colWidths=[1.5 * inch, 3 * inch])
        cover_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [white, HexColor("#F0F0F0")]),
                ]
            )
        )
        elements.append(cover_table)
        elements.append(Spacer(1, 0.5 * inch))

        # ---- Scope breakdown ----
        elements.append(Paragraph("Scope Breakdown", _HEADING1))
        scope_table = Table(self.scope_rows(), colWidths=[1.6 * inch, 1.7 * inch, 1.3 * inch])
        scope_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#E0E0E0")),
                    ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#AAAAAA")),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ]
            )
        )
        elements.append(scope_table)
        elements.append(Spacer(1, 0.2 * inch))
        elements.append(
            Paragraph(
                "A scope shown as 'not reported' has no rows in this run; it is not "
                "treated as a zero. Confirm before publishing the inventory.",
                _BODY_STYLE,
            )
        )
        elements.append(Spacer(1, 0.3 * inch))

        # ---- Methodology appendix ----
        elements.append(Paragraph("Methodology Appendix", _HEADING1))
        if self.boundary_document:
            elements.append(
                Paragraph(f"Boundary document: {self.boundary_document}", _BODY_STYLE)
            )
        else:
            elements.append(
                Paragraph(
                    "Boundary document: not supplied for this run. The organisational "
                    "boundary and consolidation method must be documented before the "
                    "report is used externally.",
                    _BODY_STYLE,
                )
            )
        for item in _METHODOLOGY_ITEMS:
            elements.append(Paragraph(item.format(gwp_set=self.gwp_set), _INDENTED_STYLE))
        elements.append(Spacer(1, 0.2 * inch))

        # ---- Key results table ----
        elements.append(Paragraph("Key Results", _HEADING1))
        results_data = [
            ["Metric", "Value"],
            ["Organisation total (kg CO2e)", f"{self.report.total_kg:,.1f}"],
            ["Organisation total (t CO2e)", f"{self.report.total_t:,.3f}"],
            ["GWP set used", self.gwp_set],
            ["Run ID", self.run_id or "-"],
            ["Period", self.period_label or "-"],
            ["Rows reconciled", str(len(self.emission_results))],
        ]
        results_table = Table(results_data, colWidths=[3 * inch, 2.5 * inch])
        results_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#E0E0E0")),
                    ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#AAAAAA")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [white, HexColor("#F5F5F5")]),
                ]
            )
        )
        elements.append(KeepTogether([results_table]))
        elements.append(Spacer(1, 0.3 * inch))

        # ---- Limitations ----
        elements.append(Paragraph("Limitations", _HEADING1))
        limitations_text = (
            "This report was generated from the calculation rows supplied to the "
            "report builder; the totals above were re-derived from those rows and "
            "checked against the report total. If the packaged illustrative factors "
            "(review_status=illustrative, source_org=SYNTHETIC) were used, the numbers "
            "are demonstration data only and must not be presented as official ESG "
            "reporting without independent verification and published, geographically "
            "appropriate emission factors."
        )
        elements.append(Paragraph(limitations_text, _BODY_STYLE))
        basis_note = gwp_basis_note(self.emission_results)
        if basis_note:
            elements.append(Spacer(1, 0.1 * inch))
            elements.append(Paragraph(basis_note, _BODY_STYLE))

        # ---- Build PDF ----
        doc.build(elements)
        return self

    def save(self, path: str) -> None:
        """Write the PDF to ``path``."""
        self.buffer.seek(0)
        with open(path, "wb") as f:
            f.write(self.buffer.read())

    def save_to_bytes(self) -> bytes:
        """Return the PDF as bytes."""
        self.buffer.seek(0)
        return self.buffer.read()


def build_pdf_report(
    report: OrganizationReport,
    emission_results: Iterable[EmissionResult],
    *,
    gwp_set: str = "AR6",
    run_id: str | None = None,
    period_label: str = "",
    organisation_name: str = "OpenCarbonChem Demo",
    boundary_document: str | None = None,
) -> PDFReport:
    """Convenience wrapper that builds a ``PDFReport`` instance.

    Raises ``PDFExportError`` if the PDF cannot be generated or the rows do not
    reconcile with the report total.
    """
    try:
        return PDFReport(
            report,
            emission_results,
            gwp_set=gwp_set,
            run_id=run_id,
            period_label=period_label,
            organisation_name=organisation_name,
            boundary_document=boundary_document,
        ).build()
    except PDFExportError:
        raise
    except Exception as exc:
        raise PDFExportError(f"PDF generation failed: {exc}") from exc
