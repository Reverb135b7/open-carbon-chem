"""OpenCarbonChem — Scope 1 Accounting page.

Scope 1: direct emissions from stationary combustion, mobile combustion,
fugitive emissions and process emissions. The page is a thin client: every
number comes from `calculate_scope1` / `OrganizationReport`, and every activity
entered here is validated and stored by the package API.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from opencarbonchem.accounting import OrganizationReport, SCOPE1_CATEGORIES, calculate_scope1
from opencarbonchem.core.activity import ActivityRecord, load_activities_csv
from opencarbonchem.core.exceptions import PeriodError
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.factors import FactorRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_CSV = REPO_ROOT / "data" / "activities_synthetic.csv"
DB_PATH = REPO_ROOT / "data" / "opencarbonchem.db"

st.set_page_config(page_title="OpenCarbonChem — Scope 1", page_icon="🔥", layout="wide")
st.title("🔥 Scope 1 Accounting")


@st.cache_resource
def _registry() -> FactorRegistry:
    return FactorRegistry.from_csv()


@st.cache_data
def _activities(scope: int) -> list[ActivityRecord]:
    return [a for a in load_activities_csv(DATA_CSV) if a.scope == scope]


def _open_db() -> CarbonDatabase:
    db = CarbonDatabase(DB_PATH)
    db.init_schema()
    return db


col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Enter / edit a Scope 1 activity")
    with st.form("add_s1_activity", clear_on_submit=True):
        activity_id = st.text_input("Activity ID", help="Unique ID, e.g. A-STATIONARY-01")
        description = st.text_input("Description", help="Optional free-form note")
        category = st.selectbox(
            "Scope 1 category",
            options=list(SCOPE1_CATEGORIES),
            format_func=lambda key: SCOPE1_CATEGORIES[key],
        )
        substance = st.text_input("Substance (fuel/type)", help="e.g. natural_gas, diesel")
        quantity = st.number_input("Quantity", min_value=0.0, step=1.0, format="%.2f")
        unit = st.text_input("Unit", value="kWh", help="e.g. kWh, L, m3, kg")
        gas = st.text_input("Gas emitted", help="CO2, CH4, N2O — required when several exist")
        geography = st.text_input("Geography", value="GLOBAL")
        data_type = st.selectbox("Data type", options=["primary", "secondary"])
        period_start = st.date_input("Period start", value=date(2024, 1, 1))
        period_end = st.date_input("Period end", value=date(2024, 12, 31))
        submitted = st.form_submit_button("Save Scope 1 activity")

        if submitted:
            try:
                activity = ActivityRecord(
                    activity_id=activity_id,
                    description=description,
                    scope=1,
                    category=category,
                    substance=substance,
                    quantity=quantity,
                    unit=unit,
                    gas=gas or None,
                    geography=geography or "GLOBAL",
                    data_type=data_type,
                    period_start=period_start,
                    period_end=period_end,
                )
            except (PeriodError, ValueError) as exc:
                st.error(f"Activity rejected: {exc}")
            else:
                with _open_db() as db:
                    db.save_activity(activity)
                st.success(f"Scope 1 activity {activity.activity_id} stored in {DB_PATH.name}.")

    st.caption(
        "Quantities must be finite and non-negative, the unit must be a registered "
        "unit, and period ordering is checked before anything is stored."
    )

with col_right:
    st.subheader("Synthetic Scope 1 inventory")
    rows = _activities(1)
    if rows:
        st.caption(f"{len(rows)} Scope 1 rows in `{DATA_CSV.name}` (SYNTHETIC).")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "activity_id": a.activity_id,
                        "category": a.category,
                        "substance": a.substance,
                        "quantity": a.quantity,
                        "unit": a.unit,
                        "gas": a.gas or "",
                    }
                    for a in rows
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info(f"No Scope 1 rows found in `{DATA_CSV}`.")

    st.subheader("Run Scope 1 calculation")
    if st.button("Calculate Scope 1 with synthetic data", type="primary"):
        if not rows:
            st.error("No Scope 1 activities loaded.")
        else:
            try:
                result = calculate_scope1(rows, _registry())
                report = OrganizationReport.from_results([result])
            except Exception as exc:  # typed engine errors, shown verbatim
                st.error(f"Calculation failed: {exc}")
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("Scope 1 total (kg)", f"{result.total_kg:,.1f}")
                c2.metric("Scope 1 total (t)", f"{result.total_t:,.3f}")
                c3.metric("Computed from rows", f"{len(result)}")
                st.write("**By category (kg CO2e):**")
                st.dataframe(
                    pd.DataFrame(
                        [(category, kg) for category, kg in result.by_category().items()],
                        columns=["Category", "CO2e (kg)"],
                    ),
                    width="stretch",
                    hide_index=True,
                )
                recon = report.reconcile()
                state = "OK" if recon.ok else "ISSUES"
                st.caption(
                    f"Consistency checks: {state} | coverage gaps: {len(recon.coverage_gaps)} "
                    "(a missing category means 'not reported', not zero)"
                )

st.sidebar.title("ℹ️ Scope 1 Accounting")
st.sidebar.markdown(
    "- Scope 1 covers **direct** emissions: stationary combustion, mobile combustion, "
    "fugitive emissions, process emissions.\n"
    "- Gas is **required** when a substance has factors for more than one gas "
    "(natural gas has CO2 and CH4 factors); otherwise `AmbiguousFactorError` is raised.\n"
    "- The engine resolves the factor by category, substance, geography and vintage, "
    "then applies `E = AD × EF` and the selected IPCC GWP set (AR6 by default).\n"
    "- Reconciliation re-derives every aggregate from the row-level results, so a "
    "total can always be checked against its rows."
)
