"""OpenCarbonChem — Scope 2 Accounting page.

Scope 2: indirect emissions from purchased electricity, steam, heat and cooling.
Location-based Scope 2 is always computed; market-based Scope 2 is only reported
when explicit contract or residual-mix factors are supplied (never inferred from
grid averages).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from opencarbonchem.accounting import (
    OrganizationReport,
    SCOPE2_CATEGORIES,
    calculate_scope2,
)
from opencarbonchem.core.activity import ActivityRecord, load_activities_csv
from opencarbonchem.core.exceptions import PeriodError
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.factors import FactorRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_CSV = REPO_ROOT / "data" / "activities_synthetic.csv"
DB_PATH = REPO_ROOT / "data" / "opencarbonchem.db"

st.set_page_config(page_title="OpenCarbonChem — Scope 2", page_icon="💡", layout="wide")
st.title("💡 Scope 2 Accounting")


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
    st.subheader("Enter / edit a Scope 2 activity")
    with st.form("add_s2_activity", clear_on_submit=True):
        activity_id = st.text_input("Activity ID", help="Unique ID, e.g. A-PURCH-ELEC-01")
        description = st.text_input("Description", help="Optional free-form note")
        category = st.selectbox(
            "Scope 2 category",
            options=list(SCOPE2_CATEGORIES),
            format_func=lambda key: SCOPE2_CATEGORIES[key],
        )
        substance = st.text_input("Energy type", help="e.g. grid_electricity, steam")
        quantity = st.number_input("Quantity (energy units)", min_value=0.0, step=1.0, format="%.2f")
        unit = st.text_input("Energy unit", value="kWh", help="e.g. kWh, GJ, therm")
        gas = st.text_input("Gas (optional)", help="CO2e when the factor is already combined")
        geography = st.text_input(
            "Geography",
            value="GB",
            help="Use the country the site is in, e.g. GB; exact geography beats GLOBAL",
        )
        data_type = st.selectbox("Data type", options=["primary", "secondary"])
        period_start = st.date_input("Period start", value=date(2024, 1, 1))
        period_end = st.date_input("Period end", value=date(2024, 12, 31))
        submitted = st.form_submit_button("Save Scope 2 activity")

        if submitted:
            try:
                activity = ActivityRecord(
                    activity_id=activity_id,
                    description=description,
                    scope=2,
                    category=category,
                    substance=substance,
                    quantity=quantity,
                    unit=unit,
                    gas=gas or None,
                    geography=geography or "GB",
                    data_type=data_type,
                    period_start=period_start,
                    period_end=period_end,
                )
            except (PeriodError, ValueError) as exc:
                st.error(f"Activity rejected: {exc}")
            else:
                with _open_db() as db:
                    db.save_activity(activity)
                st.success(f"Scope 2 activity {activity.activity_id} stored in {DB_PATH.name}.")

    st.caption(
        "Scope 2 activities represent purchased energy. The location-based method uses the "
        "grid-average factor for the declared geography; the market-based method requires "
        "explicit contract or residual-mix factors supplied by the user."
    )

with col_right:
    st.subheader("Synthetic Scope 2 inventory")
    rows = _activities(2)
    if rows:
        st.caption(f"{len(rows)} Scope 2 rows in `{DATA_CSV.name}` (SYNTHETIC).")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "activity_id": a.activity_id,
                        "category": a.category,
                        "substance": a.substance,
                        "quantity": a.quantity,
                        "unit": a.unit,
                        "geography": a.geography,
                    }
                    for a in rows
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info(f"No Scope 2 rows found in `{DATA_CSV}`.")

    st.subheader("Run Scope 2 calculation")
    if st.button("Calculate Scope 2 with synthetic data", type="primary"):
        if not rows:
            st.error("No Scope 2 activities loaded.")
        else:
            try:
                result = calculate_scope2(rows, _registry())
                report = OrganizationReport.from_results([result.location])
            except Exception as exc:
                st.error(f"Calculation failed: {exc}")
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("Location-based (kg CO2e)", f"{result.location.total_kg:,.1f}")
                c2.metric("Location-based (t CO2e)", f"{result.location.total_t:,.3f}")
                if result.market is None:
                    c3.metric("Market-based", "not reported")
                else:
                    c3.metric("Market-based (kg CO2e)", f"{result.market.total_kg:,.1f}")

                st.write("**Location-based by category (kg CO2e):**")
                st.dataframe(
                    pd.DataFrame(
                        [
                            (category, kg)
                            for category, kg in result.location.by_category().items()
                        ],
                        columns=["Category", "CO2e (kg)"],
                    ),
                    width="stretch",
                    hide_index=True,
                )
                if result.market is None:
                    st.caption(
                        "Market-based Scope 2 is not reported: no contract or residual-mix "
                        "factors were supplied, and a grid average is not a market-based factor."
                    )
                recon = report.reconcile()
                st.caption(
                    f"Consistency checks: {'OK' if recon.ok else 'ISSUES'} | "
                    f"coverage gaps: {len(recon.coverage_gaps)}"
                )

st.sidebar.title("ℹ️ Scope 2 Accounting")
st.sidebar.markdown(
    "- Scope 2 covers **indirect** emissions from purchased electricity, steam, heat "
    "and cooling.\n"
    "- **Location-based** uses the grid-average factor for the declared geography and is "
    "always computed.\n"
    "- **Market-based** is only reported when explicit contract or residual-mix factors "
    "are supplied for every activity; the engine never substitutes a grid average.\n"
    "- Both methods must be disclosed when market-based data exists (GHG Protocol "
    "Scope 2 Guidance)."
)
