"""Reporting module for OpenCarbonChem.

Provides Excel workbook and PDF executive summary generation with reconciliation
guards (mismatch → ReconciliationError). All numbers are re-derived from stored
calculation records so totals always match total_co2e_kg of the run.

From guide §11/§13/§14 / roadmap row 10 (currently "Partial").
"""

from __future__ import annotations

from .excel_workbook import ExcelWorkbook, ExcelReport
from .pdf_generator import PDFReport, PDFExportError
from .cli import main

__all__ = [
    "ExcelWorkbook",
    "ExcelReport",
    "PDFReport",
    "PDFExportError",
    "main",
]