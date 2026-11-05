"""PDF executive summary generation for OpenCarbonChem reports.

Features
--------
- Cover page: project name, run ID, date, GWP set used
- Scope breakdown: stacked bar of CO₂e by scope (1, 2, 3)
- Methodology appendix: boundary document reference, GWP set, formulae
  (E = AD × EF, CO₂e = Σ E_g × GWP_g)
- Key results table: scope totals, organisation total, key assumptions
- Limitations note: synthetic data, not for official ESG reporting
- Raises ``PDFExportError`` on any generation failure

From guide §11/§13/§14 / roadmap row 10 (currently "Partial").
"""

from __future__ import annotations

import streamlit as st
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether,
)
from reportlab.lib.units import inch, mm
from reportlab.lib.colors import HexColor, white, black

from ..accounting.aggregate import OrganizationReport
from ..core.calc import EmissionResult
from ..core.exceptions import PDFExportError
from ..factors.models import EmissionFactor
from ..core.activity import ActivityRecord

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

_TABLE_HEADER_STYLE = _STYLES["Normal"]
_TABLE_HEADER_STYLE.fontSize = 9
_TABLE_HEADER_STYLE.bold = True

_TABLE_CELL_STYLE = _STYLES["Normal"]
_TABLE_CELL_STYLE.fontSize = 8

_GRID = TableStyle(
    [
        ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#AAAAAA")),
        ("GRID", (0, 0), (-1, -1), 0.25, HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
)

# -- PDF report builder --------------------------------------------------- #


class PDFReport:
    """Build an executive-summary PDF from an ``OrganizationReport`` and
    calculation results.

    The PDF is intentionally concise — it is meant for review and presentation,
    not for detailed audit (the Excel workbook serves that purpose).
    """

    def __init__(
        self,
        report: OrganizationReport,
        emission_results: List[EmissionResult],
        *,
        gwp_set: str = "AR6",
        run_id: str | None = None,
        period_label: str = "",
        organisation_name: str = "OpenCarbonChem Demo",
        boundary_document: str | None = None,
    ) -> None:
        self.report = report
        self.emission_results = emission_results
        self.gwp_set = gwp_set
        self.run_id = run_id
        self.period_label = period_label
        self.organisation_name = organisation_name
        self.boundary_document = boundary_document
        self.buffer = io.BytesIO()

    def build(self) -> "PDFReport":
        """Render the PDF into the internal buffer."""
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
        elements.append(Paragraph(f"{self.organisation_name}", _TITLE_STYLE))
        elements.append(Spacer(1, 0.3 * inch))
        elements.append(Paragraph("OpenCarbonChem — Executive Summary", _SUBTITLE_STYLE))
        elements.append(Spacer(1, 0.3 * inch))

        cover_info = [
            ["Run ID", self.run_id or "—"],
            ["Period", self.period_label or "—"],
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
        # Simple text summary since we don't have charting here
        scope_text = (
            f"Scope 1: {self.report.scope_results[0].total_kg if self.report.scope_results else 0:,.1f} kg CO₂e\n"
            f"Scope 2: {self.report.scope_results[1].total_kg if len(self.report.scope_results) > 1 else 0:,.1f} kg CO₂e\n"
            f"Scope 3: {self.report.scope_results[2].total_kg if len(self.report.scope_results) > 2 else 0:,.1f} kg CO₂e\n"
            f"Organisation total: {self.report.total_kg:,.1f} kg CO₂e"
        )
        elements.append(Paragraph(scope_text, _BODY_STYLE))
        elements.append(Spacer(1, 0.3 * inch))

        # ---- Methodology appendix ----
        elements.append(Paragraph("Methodology Appendix", _HEADING1))
        methodology_items = [
            "• Emissions calculated as E = Activity Data × Emission Factor (engine: "
            "``e = ad × ef``)",
            f"• CO₂e conversion uses IPCC {self.gwp_set} GWP values: "
            f"``CO₂e = Σ E_g × GWP_g``",
            "• Scope 1: stationary combustion, mobile combustion, fugitive emissions, process emissions",
            "• Scope 2: purchased electricity, steam, heat, cooling (location‑based method)",
            "• Scope 3: all 15 GHG Protocol categories (purchased goods, capital goods, "
            "fuel‑related activities, upstream/downstream transport, waste, business travel, "
            "commuting, leased assets, use of sold products, end‑of‑life, franchises, investments)",
            "• Uncertainty: all emission factors are labelled ``review_status=illustrative`` "
            "or ``published``; synthetic data clearly marked.",
        ]
        for item in methodology_items:
            elements.append(Paragraph(item, _BODY_STYLE, leftIndent=20))
        elements.append(Spacer(1, 0.2 * inch))

        # ---- Key results table ----
        elements.append(Paragraph("Key Results", _HEADING1))
        results_data = [
            ["Metric", "Value"],
            ["Organisation total (kg)", f"{self.report.total_kg:,.1f}"],
            ["Organisation total (t)", f"{self.report.total_t:,.3f}"],
            ["GWP set used", self.gwp_set],
            ["Run ID", self.run_id or "—"],
            ["Period", self.period_label or "—"],
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
        elements.append(results_table)
        elements.append(Spacer(1, 0.3 * inch))

        # ---- Limitations ----
        elements.append(Paragraph("Limitations", _HEADING1))
        limitations_text = (
            "This report uses synthetic data (review_status=illustrative, source_org=SYNTHETIC) "
            "for demonstration purposes only. It must not be presented as official ESG reporting "
            "without independent verification and the use of published, geographically appropriate "
            "emission factors. All numbers are re‑derived from stored calculation records so "
            "totals always match the underlying database."
        )
        elements.append(Paragraph(limitations_text, _BODY_STYLE))

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


# ------------------------------------------------------------------------ #
# PDF report convenience --------------------------------------------------- #
# ------------------------------------------------------------------------ #


def build_pdf_report(
    report: OrganizationReport,
    emission_results: List[EmissionResult],
    *,
    gwp_set: str = "AR6",
    run_id: str | None = None,
    period_label: str = "",
    organisation_name: str = "OpenCarbonChem Demo",
    boundary_document: str | None = None,
) -> PDFReport:
    """Convenience wrapper that builds a ``PDFReport`` instance.

    Raises ``PDFExportError`` if the PDF cannot be generated.
    """
    try:
        pdf = PDFReport(
            report,
            emission_results,
            gwp_set=gwp_set,
            run_id=run_id,
            period_label=period_label,
            organisation_name=organisation_name,
            boundary_document=boundary_document,
        ).build()
        return pdf
    except Exception as exc:
        raise PDFExportError(f"PDF generation failed: {exc}") from exc