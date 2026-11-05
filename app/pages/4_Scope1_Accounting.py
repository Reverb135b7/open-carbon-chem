"""OpenCarbonChem — Scope 1 Accounting page.

Scope 1: direct emissions from stationary combustion, mobile combustion, fugitive
emissions and process emissions. The page is a thin client: all calculations go
through the package API (`calculate_scope1`, `OrganizationReport`, reconciliation,
etc.). The synthetic dataset in `data/` is used so the dashboard shows data on first run.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from pathlib import Path
from typing import List

from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.accounting import (
    calculate_scope1, OrganizationReport, ScopeResult,
    Scope1_CATEGORIES, BoundaryEntity, OrganisationalBoundary,
    compare_periods, PeriodComparison,
)
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.core.exceptions import PeriodError
from datetime import date

DATA = Path(__file__).parent.parent / "data" / "raw" / "synthetic"
DEFAULT_CSV = Path(__file__).parent.parent / "src" / "opencarbonchem" / "factors" / "data" / "illustrative_factors.csv"


st.set_page_config(page_title="OpenCarbonChem — Scope 1", page_icon"🔥", layout="wide")
st.title("🔥 Scope 1 Accounting")


# ---------- helpers ----------
@st.cache_resource
def _load_seed() -> FactorRegistry:
    return FactorRegistry.from_csv(DEFAULT_CSV)


# ---------- layout ----------
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Enter / edit Scope 1 activities")
    with st.form("add_s1_activity", clear_on_submit=True):
        activity_id = st.text_input("Activity ID", help="Unique ID, e.g. A-STATIONARY-01")
        description = st.text_input("Description", help="Optional free‑form note")
        category = st.selectbox("Scope 1 category", options=[
            "stationary_combustion",
            "mobile_combustion",
            "fugitive_emissions",
            "process_emissions",
        ], help="Which type of Scope 1 emission")
        substance = st.text_input("Substance (fuel/type)", help="e.g. natural_gas, diesel")
        quantity = st.number_input("Quantity", min_value=0.0, step=1.0, format="%.2f")
        unit = st.text_input("Unit", help="e.g. kWh, L, m3")
        gas = st.text_input("Gas emitted", help="e.g. CO2, CH4, N2O")
        geography = st.text_input("Geography", value="GLOBAL")
        data_type = st.selectbox("Data type", options=["primary", "secondary"])
        period_start = st.date_input("Period start", value=date(2024, 1, 1))
        period_end = st.date_input("Period end", value=date(2024, 12, 31))
        submitted = st.form_submit_button("Save Scope 1 activity")

        if submitted:
            if not activity_id or not category or not substance or quantity <= 0:
                st.error("Please fill in all required fields and ensure quantity > 0.")
            else:
                try:
                    a = ActivityRecord(
                        activity_id=activity_id,
                        scope=1,
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
                    st.success(f"Scope 1 activity {activity_id} saved.")
                except PeriodError as e:
                    st.error(str(e))
                except Exception as exc:
                    st.error(f"Failed to save activity: {exc}")

    st.caption("All Scope 1 activities are validated by the package API. "
               "Quantities must be finite and non‑negative; period ordering is checked.")

with col_right:
    st.subheader("Scope 1 inventory snapshot (synthetic)")
    csv_path = DATA / "activities_synthetic.csv"
    if csv_path.exists():
        # Show only Scope 1 rows
        df = pd.read_csv(csv_path, dtype=str)
        s1_rows = df[df["scope"].astype(str) == "1"]
        st.caption(f"Found {len(s1_rows)} Scope 1 rows in `{csv_path.name}`.")
        if not s1_rows.empty:
            st.dataframe(s1_rows.head(10), use_container_width=True, height=200)
        else:
            st.info("No Scope 1 rows in the synthetic CSV — add some via the form above.")
    else:
        st.info("No `activities_synthetic.csv` found. "
                "Place it in `data/raw/synthetic/` to populate this section.")

    st.subheader("Run Scope 1 calculation")
    if st.button("Calculate Scope 1 with synthetic data", type="primary"):
        with st.spinner("Loading factors and computing..."):
            reg = _load_seed()
            activities = _load_synthetic_activities_s1()
            if not activities:
                st.error("No Scope 1 activities loaded. Add some via the form above or check the CSV.")
            else:
                try:
                    result = calculate_scope1(activities, reg)
                    st.success("Scope 1 calculation complete.")
                    # ---- results ----
                    s = result  # ScopeResult
                    c = OrganizationReport.from_results([result])
                    # Metrics
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Scope 1 total (kg)", f"{s.total_kg:,.1f}")
                    c2.metric("Scope 1 total (t)", f"{s.total_t:,.3f}")
                    c3.metric("Organisation total (kg)", f"{c.total_kg:,.1f}")
                    # Breakdown by category
                    st.write("**By category:**")
                    cat_df = pd.DataFrame(
                        [(cat, kg) for cat, kg in s.by_category().items()],
                        columns=["Category", "CO2e (kg)"]
                    )
                    st.dataframe(cat_df, use_container_width=True)
                    # Reconciliation
                    st.write("**Reconciliation:**")
                    recon = c.reconcile()
                    ok_m = "✅ OK" if recon.ok else "❌ Issues"
                    st.caption(f"Consistency checks: {ok_m}  |  Coverage gaps: {len(recon.coverage_gaps)}")
                    for check in recon.checks[:5]:
                        st.caption(f"- {check.name}: {check.detail}")
                except Exception as e:
                    st.error(f"Calculation failed: {e}")

    st.caption("The calculation uses the `E = Activity Data × Emission Factor` engine "
               "with IPCC AR6 GWP values (CH4 requires an explicit fossil/non‑fossil basis).")


# ------ sidebar -----
st.sidebar.title("ℹ️ Scope 1 Accounting")
st.sidebar.markdown(
    "- Scope 1 covers **direct** emissions: stationary combustion, mobile combustion, "
    "fugitive emissions, process emissions.\n"
    "- Each activity must have a category from the 4 Scope 1 vocabularies, a substance, "
    "a quantity and a unit.\n"
    "- Gas is **required** when the substance has factors for more than one gas (e.g. "
    "natural_gas can emit CO2 or CH4).\n"
    "- Quantity must be ≥ 0; invalid data raises a typed error — never silently defaults.\n"
    "- The engine uses the same `E = AD × EF` core as every other module; GWP sets are "
    "AR6 (default), AR6 2025 errata, or AR5.\n"
    "- Organisational boundary and reconciliation are handled by `OrganizationReport`; "
    "coverage gaps flag missing categories for human review, never silently assume zero."
)