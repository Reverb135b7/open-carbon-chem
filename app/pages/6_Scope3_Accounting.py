"""OpenCarbonChem — Scope 3 Accounting page.

Scope 3: all 15 GHG Protocol categories. The page is a thin client: calculations
go through the package API. The synthetic dataset in `data/` is used so the
dashboard shows data on first run.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from pathlib import Path
from typing import List

from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.accounting import (
    calculate_scope3, OrganizationReport, ScopeResult, Scope3Category,
)
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.core.exceptions import PeriodError
from datetime import date

DATA = Path(__file__).parent.parent / "data" / "raw" / "synthetic"
DEFAULT_CSV = Path(__file__).parent.parent / "src" / "opencarbonchem" / "factors" / "data" / "illustrative_factors.csv"


st.set_page_config(page_title="OpenCarbonChem — Scope 3", page_icon"🌐", layout="wide")
st.title("🌐 Scope 3 Accounting")


# ---------- helpers ----------
@st.cache_resource
def _load_seed() -> FactorRegistry:
    return FactorRegistry.from_csv(DEFAULT_CSV)


# Scope 3 category labels (GHG Protocol)
_S3_CAT_LABELS = {
    "s3_cat01": "Purchased goods and services",
    "s3_cat02": "Capital goods",
    "s3_cat03": "Fuel‑related activities (not included in Scope 1)",
    "s3_cat04": "Upstream transportation and distribution",
    "s3_cat05": "Waste generated in operations",
    "s3_cat06": "Business travel",
    "s3_cat07": "Employee commuting",
    "s3_cat08": "Upstream leased assets",
    "s3_cat09": "Downstream transportation and distribution",
    "s3_cat10": "Processing of sold products",
    "s3_cat11": "Use of sold products",
    "s3_cat12": "End‑of‑life treatment of sold products",
    "s3_cat13": "Downstream leased assets",
    "s3_cat14": "Franchises",
    "s3_cat15": "Investments",
}


# ---------- layout ----------
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Enter / edit Scope 3 activities")
    with st.form("add_s3_activity", clear_on_submit=True):
        activity_id = st.text_input("Activity ID", help="Unique ID, e.g. A-S3-012")
        description = st.text_input("Description", help="Optional free‑form note")
        category = st.selectbox("Scope 3 category", options=list(_S3_CAT_LABELS.keys()),
                                format_func=lambda k: _S3_CAT_LABELS[k],
                                help="One of the 15 GHG Protocol categories")
        substance = st.text_input("Substance (product/material)", help="e.g. paper, steel, road_freight")
        quantity = st.number_input("Quantity", min_value=0.0, step=1.0, format="%.2f")
        unit = st.text_input("Unit", help="e.g. kg, tkm, pkm, passenger")
        gas = st.text_input("Gas (optional)", help="CO2e or leave blank")
        geography = st.text_input("Geography", value="GLOBAL")
        data_type = st.selectbox("Data type", options=["primary", "secondary"])
        period_start = st.date_input("Period start", value=date(2024, 1, 1))
        period_end = st.date_input("Period end", value=date(2024, 12, 31))
        submitted = st.form_submit_button("Save Scope 3 activity")

        if submitted:
            if not activity_id or not category or not substance or quantity <= 0:
                st.error("Please fill in all required fields and ensure quantity > 0.")
            else:
                try:
                    a = ActivityRecord(
                        activity_id=activity_id,
                        scope=3,
                        category=category,
                        substance=substance,
                        quantity=quantity,
                        unit=unit,
                        gas=gas or None,
                        period_start=period_start,
                        period_end=period_end,
                        data_type=data_type,
                        notes=description or "",
                    )
                    if a.period_start and a.period_end and a.period_start > a.period_end:
                        raise PeriodError(f"{a.activity_id}: period_start is after period_end.")
                    with CarbonDatabase(":memory:") as db:
                        db.init_schema()
                        db.save_activity(a, period_id=None)
                    st.success(f"Scope 3 activity {activity_id} saved.")
                except PeriodError as e:
                    st.error(str(e))
                except Exception as exc:
                    st.error(f"Failed to save activity: {exc}")

    st.caption("All 15 GHG Protocol Scope 3 categories are available via the dropdown. "
               "Quantity must be ≥ 0; period ordering is checked by the package API.")

with col_right:
    st.subheader("Scope 3 inventory snapshot (synthetic)")
    csv_path = DATA / "activities_synthetic.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path, dtype=str)
        s3_rows = df[df["scope"].astype(str) == "3"]
        st.caption(f"Found {len(s3_rows)} Scope 3 rows in `{csv_path.name}`.")
        if not s3_rows.empty:
            st.dataframe(s3_rows.head(10), use_container_width=True, height=200)
            # Show category distribution
            cat_counts = s3_rows["category"].value_counts()
            st.write("**Category distribution (in CSV):**")
            st.dataframe(cat_counts.rename("rows").reset_index().rename(columns={"index": "category_id"}))
        else:
            st.info("No Scope 3 rows in the synthetic CSV — add some via the form above.")
    else:
        st.info("No `activities_synthetic.csv` found. "
                "Place it in `data/raw/synthetic/` to populate this section.")

    st.subheader("Run Scope 3 calculation")
    if st.button("Calculate Scope 3 with synthetic data", type="primary"):
        with st.spinner("Loading factors and computing..."):
            reg = _load_seed()
            activities = _load_synthetic_activities_s3()
            if not activities:
                st.error("No Scope 3 activities loaded. Add some via the form above or check the CSV.")
            else:
                try:
                    result = calculate_scope3(activities, reg)
                    s = result  # ScopeResult
                    c = OrganizationReport.from_results([result])
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Scope 3 total (kg)", f"{s.total_kg:,.1f}")
                    c2.metric("Scope 3 total (t)", f"{s.total_t:,.3f}")
                    c3.metric("Organisation total (kg)", f"{c.total_kg:,.1f}")
                    st.write("**By category:**")
                    cat_df = pd.DataFrame(
                        [(Scope3Category.label(cat), kg) for cat, kg in s.by_category().items()],
                        columns=["Category", "CO2e (kg)"]
                    )
                    # Only show categories that have data
                    cat_df = cat_df[cat_df["CO2e (kg)"] > 0]
                    st.dataframe(cat_df, use_container_width=True)
                    st.write("**Reconciliation:**")
                    recon = c.reconcile()
                    ok_m = "✅ OK" if recon.ok else "❌ Issues"
                    st.caption(f"Consistency: {ok_m}  |  Coverage gaps: {len(recon.coverage_gaps)}")
                    for check in recon.checks[:6]:
                        st.caption(f"- {check.name}: {check.detail}")
                except Exception as e:
                    st.error(f"Calculation failed: {e}")

    st.caption("Scope 3 covers all 15 GHG Protocol categories (purchased goods, capital goods, "
               "fuel‑related activities, upstream/downstream transport, waste, business travel, "
               "commuting, leased assets, use of sold products, end‑of‑life, franchises, investments). "
               "The engine resolves the correct emission factor for each category/substance/geography "
               "combination; ambiguous cases raise `AmbiguousFactorError` and require the user to "
               "set the activity's `gas` field.")


# ----- sidebar -----
st.sidebar.title("ℹ️ Scope 3 Accounting")
st.sidebar.markdown(
    "- Scope 3 covers **all 15 GHG Protocol categories** — from purchased goods and services "
    "through to end‑of‑life treatment of sold products.\n"
    "- Select a category from the dropdown; the full label is shown for reference.\n"
    "- Each activity needs a substance, quantity and unit appropriate to the category "
    "(e.g. `kg` for purchased goods, `tkm` for transportation, `passenger` for commuting).\n"
    "- Gas is typically `CO2e`; leave blank if the factor is already combined.\n"
    "- The engine automatically resolves the correct emission factor based on category, "
    "substance and geography, with vintage precedence (newest at or before the reporting year).\n"
    "- If a substance has factors for multiple gases, the user must set the activity's `gas` "
    "field; otherwise `AmbiguousFactorError` is raised.\n"
    "- Reconciliation via `OrganizationReport` flags missing categories and consistency gaps — "
    "never silently assumes zero."
)