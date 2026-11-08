"""Reporting module for OpenCarbonChem.

Provides Excel workbook and PDF executive summary generation with reconciliation
guards (mismatch → ReconciliationError). All numbers are re-derived from stored
calculation records so totals always match total_co2e_kg of the run.

From guide §11/§13/§14 / roadmap row 10.
"""

from __future__ import annotations

from .excel_workbook import ExcelReport, ExcelWorkbook, build_excel_report
from .pdf_generator import PDFExportError, PDFReport, build_pdf_report

__all__ = [
    "ExcelWorkbook",
    "ExcelReport",
    "build_excel_report",
    "PDFReport",
    "PDFExportError",
    "build_pdf_report",
]