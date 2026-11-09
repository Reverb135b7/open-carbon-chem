"""OpenCarbonChem — Report Generation page.

Builds the Excel workbook and PDF executive summary from the synthetic dataset
through the package API. Both formats are generated from the same row-level
results, and both refuse to be written when their derived total does not match
the report total.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from opencarbonchem.accounting import calculate_inventory
from opencarbonchem.core.activity import load_activities_csv
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.reporting import build_excel_report, build_pdf_report

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_CSV = REPO_ROOT / "data" / "activities_synthetic.csv"
REPORTS_DIR = REPO_ROOT / "reports"

st.set_page_config(page_title="OpenCarbonChem — Report Generation", page_icon="📄", layout="wide")
st.title("📄 Report Generation")


@st.cache_resource
def _registry() -> FactorRegistry:
    return FactorRegistry.from_csv()


@st.cache_data
def _activities():
    return load_activities_csv(DATA_CSV)


run_id = st.text_input("Run ID", value="demo-2024", help="Used as the report file name and header")
gwp_set = st.selectbox("GWP set", options=["AR6", "AR6-ERRATA-2025", "AR5"], index=0)
period_label = st.text_input("Period label", value="2024-01-01 → 2024-12-31")
organisation_name = st.text_input("Organisation name", value="OpenCarbonChem Demo")
boundary_document = st.text_input(
    "Boundary document reference",
    value="",
    placeholder="e.g. BOUNDARY-2024-v3",
    help="Optional; recorded in the PDF methodology appendix",
)

if st.button("Generate reports", type="primary"):
    try:
        report, rows = calculate_inventory(_activities(), _registry(), gwp_set=gwp_set)
    except Exception as exc:
        st.error(f"Calculation failed: {exc}")
    else:
        excel_bytes = build_excel_report(
            report, rows, gwp_set=gwp_set, run_id=run_id, period_label=period_label
        ).save_to_bytes()
        pdf_bytes = build_pdf_report(
            report,
            rows,
            gwp_set=gwp_set,
            run_id=run_id,
            period_label=period_label,
            organisation_name=organisation_name,
            boundary_document=boundary_document or None,
        ).save_to_bytes()

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (REPORTS_DIR / f"{run_id}.xlsx").write_bytes(excel_bytes)
        (REPORTS_DIR / f"{run_id}.pdf").write_bytes(pdf_bytes)

        c1, c2, c3 = st.columns(3)
        c1.metric("Organisation total (kg CO2e)", f"{report.total_kg:,.1f}")
        c2.metric("Organisation total (t CO2e)", f"{report.total_t:,.3f}")
        c3.metric("Rows in the report", f"{len(rows)}")
        st.success(f"Reports written to {REPORTS_DIR} ({run_id}.xlsx, {run_id}.pdf).")

        st.download_button(
            "Download Excel workbook",
            excel_bytes,
            file_name=f"{run_id}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button(
            "Download PDF executive summary",
            pdf_bytes,
            file_name=f"{run_id}.pdf",
            mime="application/pdf",
        )

        st.write("**Reconciliation (consistency checks only):**")
        recon = report.reconcile()
        st.dataframe(
            pd.DataFrame([check.to_dict() for check in recon.checks]),
            width="stretch",
            hide_index=True,
        )
        if recon.coverage_gaps:
            st.warning(
                "Coverage gaps (unreported scopes or categories — not assumed zero): "
                + "; ".join(gap.name for gap in recon.coverage_gaps)
            )
        else:
            st.caption("No coverage gaps: every scope and Scope 1/2 subcategory has rows.")

st.subheader("What each report contains")
c1, c2 = st.columns(2)
with c1:
    st.markdown(
        "**Excel workbook**\n"
        "- Summary: run ID, GWP set, period, organisation total\n"
        "- Scope sheets: every row with activity value/unit, factor value/unit, gas, GWP, CO2e\n"
        "- Reconciliation sheet: derived total vs report total, plus the match flag\n"
        "- Refuses to write when the rows do not reconcile (`ReconciliationError`)"
    )
with c2:
    st.markdown(
        "**PDF executive summary**\n"
        "- Cover: organisation, run ID, period, GWP set, totals\n"
        "- Scope breakdown keyed by scope number; unreported scopes say so\n"
        "- Methodology appendix with the boundary document and formulae\n"
        "- Limitations note for synthetic data\n"
        "- Refuses to write when the rows do not reconcile (`PDFExportError`)"
    )

st.sidebar.title("ℹ️ Report Generation")
st.sidebar.markdown(
    "- Both formats derive every number from the same row-level results, so the Excel "
    "detail, the PDF summary and the CLI cannot disagree.\n"
    "- The packaged factors are `review_status=illustrative` / `source_org=SYNTHETIC`: "
    "these reports are demonstrations, not official ESG disclosures.\n"
    "- Files are also written to `reports/` and offered for download."
)
