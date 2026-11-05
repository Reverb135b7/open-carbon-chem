"""OpenCarbonChem — Scope 2 Accounting page.

Scope 2: indirect emissions from purchased energy (electricity, steam, heating and cooling).
The page is a thin client: calculations go through the package API. Location‑based
method is always available; market‑based method requires explicit contract/residual‑mix
factors (which the user can enter via the Emission Factor DB page).
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from pathlib import Path
from typing import List

from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.accounting import (
    calculate_scope2, OrganizationReport, Scope2Result, ScopeResult,
)
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.core.exceptions import PeriodError
from datetime import date

DATA = Path(__file__).parent.parent / "data" / "raw" / "synthetic"
DEFAULT_CSV = Path(__file__).parent.parent / "src" / "opencarbonchem" / "factors" / "data" / "illustrative_factors.csv"


st.set_page_config(page_title="OpenCarbonChem — Scope 2", page_icon"💡", layout="wide")
st.title("💡 Scope 2 Accounting")


# ---------- helpers ----------
@st.cache_resource
def _load_seed() -> FactorRegistry:
    return FactorRegistry.from_csv(DEFAULT_CSV)


# ---------- layout ----------
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Enter / edit Scope 2 activities")
    with st.form("add_s2_activity", clear_on_submit=True):
        activity_id = st.text_input("Activity ID", help="Unique ID, e.g. A-PURCH-ELEC-01")
        description = st.text_input("Description", help="Optional free‑form note")
        category = st.selectbox("Scope 2 category", options=[
            "purchased_electricity",
            "purchased_steam",
            "purchased_heat",
            "purchased_cooling",
        ], help="Which type of purchased energy")
        substance = st.text_input("Energy type", help="e.g. grid_electricity, steam")
        quantity = st.number_input("Quantity (energy units)", min_value=0.0, step=1.0, format="%.2f")
        unit = st.text_input("Energy unit", help="e.g. kWh, GJ, therm")
        gas = st.text_input("Gas (optional)", help="CO2e when factor is combined; or leave blank")
        geography = st.text_input("Geography", value="GLOBAL",
                                  help="e.g. GLOBAL; market‑based needs residual‑mix geography")
        data_type = st.selectbox("Data type", options=["primary", "secondary"])
        period_start = st.date_input("Period start", value=date(2024, 1, 1))
        period_end = st.date_input("Period end", value=date(2024, 12, 31))
        submitted = st.form_submit_button("Save Scope 2 activity")

        if submitted:
            if not activity_id or not category or not substance or quantity <= 0:
                st.error("Please fill in all required fields and ensure quantity > 0.")
            else:
                try:
                    a = ActivityRecord(
                        activity_id=activity_id,
                        scope=2,
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
                    st.success(f"Scope 2 activity {activity_id} saved.")
                except PeriodError as e:
                    st.error(str(e))
                except Exception as exc:
                    st.error(f"Failed to save activity: {exc}")

    st.caption("Scope 2 activities represent purchased energy. The location‑based method "
               "uses the grid‑average factor; the market‑based method requires explicit "
               "contract/residual‑mix factors supplied by the user (see the Emission Factor DB page).")

with col_right:
    st.subheader("Scope 2 inventory snapshot (synthetic)")
    csv_path = DATA / "activities_synthetic.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path, dtype=str)
        s2_rows = df[df["scope"].astype(str) == "2"]
        st.caption(f"Found {len(s2_rows)} Scope 2 rows in `{csv_path.name}`.")
        if not s2_rows.empty:
            st.dataframe(s2_rows.head(10), use_container_width=True, height=200)
        else:
            st.info("No Scope 2 rows in the synthetic CSV — add some via the form above.")
    else:
        st.info("No `activities_synthetic.csv` found. "
                "Place it in `data/raw/synthetic/` to populate this section.")

    st.subheader("Run Scope 2 calculation")
    if st.button("Calculate Scope 2 with synthetic data", type="primary"):
        with st.spinner("Loading factors and computing..."):
            reg = _load_seed()
            activities = _load_synthetic_activities_s2()
            if not activities:
                st.error("No Scope 2 activities loaded. Add some via the form above or check the CSV.")
            else:
                try:
                    result = calculate_scope2(activities, reg)
                    s = result  # Scope2Result
                    c = OrganizationReport.from_results([result])
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Scope 2 location‑based (kg)", f"{s.location_kg:,.1f}")
                    c2.metric("Scope 2 location‑based (t)", f"{s.location_t:,.3f}")
                    # market-based is only shown if explicit factors exist
                    if hasattr(s, "market_kg") and s.market_kg is not None:
                        c3.metric("Scope 2 market‑based (kg)", f"{s.market_kg:,.1f}")
                    else:
                        c3.metric("Scope 2 market‑based", "— (no contract factors)")
                    st.write("**By gas:**")
                    gas_df = pd.DataFrame(
                        [(g, kg) for g, kg in s.by_gas().items()],
                        columns=["Gas", "CO2e (kg)"]
                    )
                    st.dataframe(gas_df, use_container_width=True)
                    st.write("**Reconciliation:**")
                    recon = c.reconcile()
                    ok_m = "✅ OK" if recon.ok else "❌ Issues"
                    st.caption(f"Consistency: {ok_m}  |  Coverage gaps: {len(recon.coverage_gaps)}")
                    for check in recon.checks[:4]:
                        st.caption(f"- {check.name}: {check.detail}")
                except Exception as e:
                    st.error(f"Calculation failed: {e}")

    st.caption("Scope 2 always uses the **location‑based** method (grid‑average emission "
               "factor). The **market‑based** method is only available when the user has "
               "supplied explicit contract or residual‑mix factors via the Emission Factor DB.")


# ----- sidebar -----
st.sidebar.title("ℹ️ Scope 2 Accounting")
st.sidebar.markdown(
    "- Scope 2 covers **indirect** emissions from purchased energy: electricity, steam, "
    "heating and cooling.\n"
    "- Location‑based method: uses the default grid‑average emission factor for the "
    "declared geography. Always available.\n"
    "- Market‑based method: only when the user has entered explicit contract or "
    "residual‑mix emission factors (via the Emission Factor DB page).\n"
    "- Each activity needs an energy type, quantity and energy unit (kWh, GJ, therm, etc.).\n"
    "- Gas is typically `CO2e` because the factor already combines gases; otherwise leave blank.\n"
    "- The synthetic dataset includes some Scope 2 rows; add more via the form above.\n"
    "- Reconciliation via `OrganizationReport` flags missing categories and consistency "
    "gaps — never silently assumes zero."
)