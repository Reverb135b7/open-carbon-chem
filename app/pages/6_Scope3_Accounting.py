"""OpenCarbonChem — Scope 3 Accounting page.

Scope 3: the 15 GHG Protocol value-chain categories. The page is a thin client
over `calculate_scope3`; category labels come from the package catalogue so the
UI cannot drift from the engine's vocabulary.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from opencarbonchem.accounting import (
    OrganizationReport,
    SCOPE3_CATEGORIES,
    calculate_scope3,
    scope3_category_id,
)
from opencarbonchem.core.activity import ActivityRecord, load_activities_csv
from opencarbonchem.core.exceptions import PeriodError
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.factors import FactorRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_CSV = REPO_ROOT / "data" / "activities_synthetic.csv"
DB_PATH = REPO_ROOT / "data" / "opencarbonchem.db"

st.set_page_config(page_title="OpenCarbonChem — Scope 3", page_icon="🌐", layout="wide")
st.title("🌐 Scope 3 Accounting")

_CATEGORY_OPTIONS = [scope3_category_id(number) for number in sorted(SCOPE3_CATEGORIES)]


def _category_label(category_id: str) -> str:
    try:
        number = int(category_id.rsplit("cat", 1)[1])
    except (IndexError, ValueError):
        return category_id
    info = SCOPE3_CATEGORIES.get(number)
    return f"{category_id} — {info.name}" if info else category_id


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
    st.subheader("Enter / edit a Scope 3 activity")
    with st.form("add_s3_activity", clear_on_submit=True):
        activity_id = st.text_input("Activity ID", help="Unique ID, e.g. A-S3-012")
        description = st.text_input("Description", help="Optional free-form note")
        category = st.selectbox(
            "Scope 3 category",
            options=_CATEGORY_OPTIONS,
            format_func=_category_label,
        )
        substance = st.text_input("Substance (product/material)", help="e.g. paper, road_freight")
        quantity = st.number_input("Quantity", min_value=0.0, step=1.0, format="%.2f")
        unit = st.text_input("Unit", value="kg", help="e.g. kg, tkm, pkm")
        gas = st.text_input("Gas (optional)", help="CO2e when the factor is already combined")
        geography = st.text_input("Geography", value="GLOBAL")
        data_type = st.selectbox("Data type", options=["primary", "secondary"])
        period_start = st.date_input("Period start", value=date(2024, 1, 1))
        period_end = st.date_input("Period end", value=date(2024, 12, 31))
        submitted = st.form_submit_button("Save Scope 3 activity")

        if submitted:
            try:
                activity = ActivityRecord(
                    activity_id=activity_id,
                    description=description,
                    scope=3,
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
                st.success(f"Scope 3 activity {activity.activity_id} stored in {DB_PATH.name}.")

    st.caption(
        "Category ids run from s3_cat01 to s3_cat15. The engine rejects any other "
        "category for a Scope 3 record, so a typo cannot silently create a sixteenth category."
    )

with col_right:
    st.subheader("Synthetic Scope 3 inventory")
    rows = _activities(3)
    if rows:
        st.caption(f"{len(rows)} Scope 3 rows in `{DATA_CSV.name}` (SYNTHETIC).")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "activity_id": a.activity_id,
                        "category": a.category,
                        "substance": a.substance,
                        "quantity": a.quantity,
                        "unit": a.unit,
                    }
                    for a in rows
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info(f"No Scope 3 rows found in `{DATA_CSV}`.")

    st.subheader("Run Scope 3 calculation")
    if st.button("Calculate Scope 3 with synthetic data", type="primary"):
        if not rows:
            st.error("No Scope 3 activities loaded.")
        else:
            try:
                result = calculate_scope3(rows, _registry())
                report = OrganizationReport.from_results([result])
            except Exception as exc:
                st.error(f"Calculation failed: {exc}")
            else:
                c1, c2 = st.columns(2)
                c1.metric("Scope 3 total (kg CO2e)", f"{result.total_kg:,.1f}")
                c2.metric("Scope 3 total (t CO2e)", f"{result.total_t:,.3f}")

                st.write("**By category (kg CO2e):**")
                st.dataframe(
                    pd.DataFrame(
                        [
                            (_category_label(category), kg)
                            for category, kg in sorted(result.by_category().items())
                        ],
                        columns=["Category", "CO2e (kg)"],
                    ),
                    width="stretch",
                    hide_index=True,
                )
                st.caption(
                    "Only categories with rows appear here. Absent categories are "
                    "'not reported', not zero; `OrganizationReport.reconcile()` lists them "
                    "as coverage gaps for review."
                )

st.sidebar.title("ℹ️ Scope 3 Accounting")
st.sidebar.markdown(
    "- All **15 GHG Protocol categories** are available (s3_cat01 … s3_cat15).\n"
    "- Units must match the category's factor (kg for goods, tkm for freight, pkm for "
    "passenger travel); the engine refuses a dimensionally incompatible pairing.\n"
    "- Factors are resolved by category, substance, geography and vintage.\n"
    "- Categories with no rows are reported as unreported, never as zero."
)
