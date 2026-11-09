"""OpenCarbonChem — Activity Data page.

Enter, load and inspect activity records. Every record is validated by the
package model and stored in a SQLite database under `data/`; the page contains no
calculation or validation logic of its own.

The CSV import is strict: a malformed row is reported with its line number and
nothing is silently defaulted or skipped.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from opencarbonchem.core.activity import ActivityRecord, load_activities_csv
from opencarbonchem.database import CarbonDatabase

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_CSV = REPO_ROOT / "data" / "activities_synthetic.csv"
DB_PATH = REPO_ROOT / "data" / "opencarbonchem.db"

st.set_page_config(page_title="OpenCarbonChem - Activity Data", page_icon="📊", layout="wide")
st.title("📊 Activity Data Management")
st.caption(
    "Records are validated by `ActivityRecord` and stored in "
    f"`{DB_PATH.relative_to(REPO_ROOT)}`. A row that fails validation is reported, never "
    "silently defaulted."
)


def _open_db() -> CarbonDatabase:
    db = CarbonDatabase(DB_PATH)
    db.init_schema()
    return db


# ---------- sidebar: import ---------- #
with st.sidebar:
    st.header("📁 Import")
    uploaded = st.file_uploader(
        "Upload activity CSV",
        type=["csv"],
        help="Columns: activity_id, scope, category, substance, quantity, unit, "
        "gas, methane_basis, geography, data_type, period_start, period_end, notes",
    )

    if uploaded is not None:
        with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as handle:
            handle.write(uploaded.getbuffer())
            temp_path = Path(handle.name)
        try:
            records = load_activities_csv(temp_path)
        except ValueError as exc:
            st.error(f"Import rejected: {exc}")
        else:
            st.success(f"Parsed {len(records)} valid rows.")
            if st.button("Store parsed rows"):
                with _open_db() as db:
                    for record in records:
                        db.save_activity(record)
                st.success(f"Stored {len(records)} rows in {DB_PATH.name}.")
        finally:
            temp_path.unlink(missing_ok=True)

    st.divider()
    if DATA_CSV.exists():
        if st.button(f"Load {DATA_CSV.name} (synthetic)"):
            records = load_activities_csv(DATA_CSV)
            with _open_db() as db:
                for record in records:
                    db.save_activity(record)
            st.success(f"Stored {len(records)} synthetic rows in {DB_PATH.name}.")

    st.divider()
    st.header("🔌 Factor connectors")
    try:
        from opencarbonchem.factors.connectors import get_connector
    except Exception as exc:  # optional package/network dependency
        st.caption(f"Connectors unavailable in this environment: {exc}")
    else:
        choice = st.selectbox(
            "Connector",
            options=["none (illustrative seed)", "DEFRA (stub)", "EPA (stub)", "Ecoinvent (stub)"],
        )
        if choice != "none (illustrative seed)":
            st.caption(
                "Connectors are stubs: they return no live factors and never feed a "
                "calculation. Real factor data must be imported with full provenance."
            )
            try:
                connector = get_connector(choice.split(" ")[0].lower())
                st.caption(f"Connector: {type(connector).__name__}")
            except Exception as exc:
                st.caption(f"Connector error: {exc}")
        else:
            st.caption("Using the packaged illustrative factors (SYNTHETIC).")

# ---------- main: add a record ---------- #
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("➕ Add an activity record")
    with st.form("add_activity", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            activity_id = st.text_input("Activity ID", placeholder="e.g. A-NAT-GAS-01")
            scope = st.selectbox(
                "GHG Protocol scope",
                options=[1, 2, 3],
                format_func=lambda x: {
                    1: "Scope 1 (direct)", 2: "Scope 2 (purchased energy)", 3: "Scope 3 (value chain)"
                }[x],
            )
            category = st.text_input(
                "Category",
                value="stationary_combustion",
                help="Scope 1/2 category name, or s3_catNN for Scope 3",
            )
            substance = st.text_input("Substance", placeholder="e.g. natural_gas")
            quantity = st.number_input("Quantity", min_value=0.0, step=10.0, format="%.2f")
            unit = st.text_input("Unit", value="kWh", help="e.g. kWh, L, kg, tkm")
        with c2:
            gas = st.text_input("Gas (optional)", placeholder="CO2")
            geography = st.text_input("Geography", value="GLOBAL")
            data_type = st.selectbox("Data type", options=["primary", "secondary"])
            period_start = st.date_input("Period start", value=date(2024, 1, 1))
            period_end = st.date_input("Period end", value=date(2024, 12, 31))
            notes = st.text_input("Notes (optional)")

        submitted = st.form_submit_button("💾 Save activity record")
        if submitted:
            try:
                record = ActivityRecord(
                    activity_id=activity_id,
                    scope=scope,
                    category=category,
                    substance=substance,
                    quantity=quantity,
                    unit=unit,
                    gas=gas or None,
                    geography=geography or "GLOBAL",
                    data_type=data_type,
                    period_start=period_start,
                    period_end=period_end,
                    notes=notes,
                )
            except Exception as exc:
                st.error(f"Record rejected: {exc}")
            else:
                with _open_db() as db:
                    db.save_activity(record)
                st.success(f"Activity {record.activity_id} stored in {DB_PATH.name}.")

with col_right:
    st.subheader("📋 Stored activities")
    with _open_db() as db:
        stored = db.list_activities()
    if stored:
        st.caption(f"{len(stored)} rows in {DB_PATH.name}.")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "activity_id": a.activity_id,
                        "scope": a.scope,
                        "category": a.category,
                        "substance": a.substance,
                        "quantity": a.quantity,
                        "unit": a.unit,
                    }
                    for a in stored
                ]
            ),
            width="stretch",
            hide_index=True,
            height=280,
        )
        st.download_button(
            "Export stored activities (CSV)",
            pd.DataFrame([a.model_dump() for a in stored]).to_csv(index=False).encode("utf-8"),
            file_name="activities_export.csv",
            mime="text/csv",
        )
    else:
        st.info("No activities stored yet. Add one, import a CSV, or load the synthetic set.")

    st.divider()
    st.subheader("🔍 Packaged synthetic dataset")
    st.caption(f"`{DATA_CSV.relative_to(REPO_ROOT)}` — 10 rows, all SYNTHETIC.")
    st.dataframe(
        pd.read_csv(DATA_CSV, dtype=str),
        width="stretch",
        hide_index=True,
        height=280,
    )

st.caption(
    "Data origin: packaged factors are `review_status=illustrative`, `source_org=SYNTHETIC`. "
    "Connector entries in this build are stubs and contribute no emission factors."
)
