"""OpenCarbonChem — Activity Data Management page.

Allows the user to upload or edit activity‑data records (fuel, energy, materials,
transport, waste) with explicit units, reporting periods and geography. The page
is a thin client: all validation and storage goes through the package API.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from pathlib import Path
from typing import List

from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.core.exceptions import PeriodError

DATA = Path(__file__).parent.parent / "data" / "raw" / "synthetic"
SEED = FactorRegistry.from_csv("src/opencarbonchem/factors/data/illustrative_factors.csv")


st.set_page_config(page_title="OpenCarbonChem — Activity Data", page_icon="📊", layout="wide")
st.title("📊 Activity Data Management")


# ---------- helpers ----------
def _key(text: str) -> str:
    return "".join(ch for ch in text.strip().lower() if ch.isalnum())


def _save_activity_to_db(db: CarbonDatabase, a: ActivityRecord, period_id: str | None) -> None:
    db.save_activity(a, period_id=period_id)


# ---------- layout ----------
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Add a new activity record")
    with st.form("add_activity", clear_on_submit=True):
        activity_id = st.text_input("Activity ID", help="Unique identifier, e.g. A-NAT-GAS-01")
        description = st.text_input("Description", help="Optional free‑form note")
        scope = st.selectbox("Scope", options=[1, 2, 3],
                             help="1 = stationary/mobile combustion; 2 = purchased energy; 3 = Scope 3")
        category = st.text_input("Category (GHG Protocol)", help="e.g. stationary_combustion, s3_cat01")
        substance = st.text_input("Substance (fuel/material/energy)", help="e.g. natural_gas, diesel, paper")
        quantity = st.number_input("Quantity", min_value=0.0, step=1.0, format="%.2f")
        unit = st.text_input("Unit", help="e.g. kWh, kg, tkm, L, m3")
        gas = st.text_input("Gas (optional)", help="CO2, CH4, N2O, or leave blank")
        geography = st.text_input("Geography", value="GLOBAL", help="e.g. GLOBAL, GB, DE")
        data_type = st.selectbox("Data type", options=["primary", "secondary"],
                                 help="primary = measured; secondary = estimate / literature")
        period_start = st.date_input("Period start", value=None)
        period_end = st.date_input("Period end", value=None)
        submitted = st.form_submit_button("Save activity")

        if submitted:
            if not activity_id or not category or not substance or quantity <= 0:
                st.error("Please fill in all required fields and ensure quantity > 0.")
            else:
                try:
                    a = ActivityRecord(
                        activity_id=activity_id,
                        scope=scope,
                        category=category,
                        substance=substance,
                        quantity=quantity,
                        unit=unit,
                        gas=gas or None,
                        period_start=period_start if period_start else None,
                        period_end=period_end if period_end else None,
                        data_type=data_type,
                        notes=description or "",
                    )
                    # Basic validation — the engine will catch period ordering etc.
                    if a.period_start and a.period_end and a.period_start > a.period_end:
                        raise PeriodError(f"{a.activity_id}: period_start is after period_end.")
                    with CarbonDatabase(":memory:") as db:
                        db.init_schema()
                        _save_activity_to_db(db, a, period_id=None)
                    st.success(f"Activity {activity_id} saved.")
                except PeriodError as e:
                    st.error(str(e))
                except Exception as exc:
                    st.error(f"Failed to save activity: {exc}")

    st.caption("Activities are stored in the SQLite database via the `CarbonDatabase` API. "
               "No calculation is performed here — the page is a data‑entry thin client.")

with col_right:
    st.subheader("Existing activities (from synthetic dataset)")
    csv_path = DATA / "activities_synthetic.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path, dtype=str)
        st.dataframe(df, use_container_width=True, height=250)
        st.caption(f"Loaded {len(df)} rows from `{csv_path.name}`.")
    else:
        st.info("No `activities_synthetic.csv` found. "
                "Place the file in `data/raw/synthetic/` to see sample rows here.")
    st.caption("Use the form on the left to add new records. "
               "All validation (scope, quantity ≥ 0, period ordering) is enforced by the package API.")


# ----- sidebar -----
st.sidebar.title("ℹ️ Activity Data")
st.sidebar.markdown(
    "- Enter a new record via the form; all fields are validated by the package API.\n"
    "- Scope 1 categories: `stationary_combustion`, `mobile_combustion`, `fugitive_emissions`, `process_emissions`.\n"
    "- Scope 2 categories: `purchased_electricity`, `purchased_steam`, `purchased_heat`, `purchased_cooling`.\n"
    "- Scope 3 categories: `s3_cat01` … `s3_cat15` (full 15‑category GHG Protocol set).\n"
    "- Quantity must be ≥ 0; invalid data raises a typed `OpenCarbonChemError`.\n"
    "- Activities are persisted in SQLite; the dashboard reads them back for the other pages."
)