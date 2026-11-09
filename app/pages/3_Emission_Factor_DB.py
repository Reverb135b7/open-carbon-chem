"""OpenCarbonChem — Emission Factor Database page.

Displays the packaged illustrative factor CSV and allows the user to inspect,
add, or replace factors. The page is a thin client: every factor carries full
provenance (source, reference, vintage, geography, uncertainty, review status)
and resolution is deterministic via the `FactorRegistry`.

**Important**: All factors in the packaged CSV are labelled `review_status=illustrative`
and `source_org=SYNTHETIC`. They are **not** official emission factors and must not
be presented as such. New factors must also be clearly labelled synthetic.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from pathlib import Path

from opencarbonchem.factors import FactorRegistry, default_seed_path
from opencarbonchem.factors.models import EmissionFactor
from opencarbonchem.database import CarbonDatabase

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = default_seed_path()
DB_PATH = REPO_ROOT / "data" / "opencarbonchem.db"


st.set_page_config(page_title="OpenCarbonChem — Emission Factor DB", page_icon="📈", layout="wide")
st.title("📈 Emission Factor Database")


# ---------- helpers ----------
@st.cache_resource
def _load_seed_registry() -> FactorRegistry:
    return FactorRegistry.from_csv(DEFAULT_CSV)


# ---------- layout ----------
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Packaged illustrative factors")
    reg = _load_seed_registry()
    st.caption(f"Loaded {len(reg)} factors from `{DEFAULT_CSV.name}`.")
    st.markdown(
        "**All rows are synthetic (review_status=illustrative, source_org=SYNTHETIC).** "
        "Never present these as official emission factors."
    )
    # Show a table preview — only columns that matter for lookup
    preview_df = pd.DataFrame([
        {
            "factor_id": f.factor_id,
            "category": f.activity_category,
            "substance": f.substance,
            "value": f.value,
            "unit": f.unit,
            "gas": f.gas,
            "geography": f.geography,
            "year": f.reporting_year,
            "review_status": f.review_status,
        }
        for f in reg
    ])
    st.dataframe(preview_df, use_container_width=True, height=300)

    st.caption("Use the filters below to explore the registry.")

    # Simple filter UI
    with st.expander("Filter factors"):
        cat = st.text_input("Category (contains)", help="e.g. stationary_combustion")
        subst = st.text_input("Substance (contains)", help="e.g. natural_gas")
        geo = st.text_input("Geography (contains)", help="e.g. GLOBAL")
        yr = st.number_input("Reporting year ≥", min_value=1900, value=2024, step=1)
        if st.button("Apply filter"):
            filtered = reg
            if cat:
                filtered = [f for f in filtered if cat.lower() in f.activity_category.lower()]
            if subst:
                filtered = [f for f in filtered if subst.lower() in f.substance.lower()]
            if geo:
                filtered = [f for f in filtered if geo.lower() in f.geography.lower()]
            if yr:
                filtered = [f for f in filtered if f.reporting_year == yr]
            preview2 = pd.DataFrame([
                {"factor_id": f.factor_id, "substance": f.substance, "value": f.value,
                 "unit": f.unit, "year": f.reporting_year}
                for f in filtered
            ])
            st.dataframe(preview2, use_container_width=True)
            st.caption(f"{len(filtered)} factors match the filter.")

with col_right:
    st.subheader("Add / replace a factor")
    st.markdown("Enter a new factor or modify an existing one. "
                "Every factor **must** have a unique `factor_id`.")
    with st.form("add_factor"):
        fid = st.text_input("Factor ID", help="Must be unique across the registry")
        activity_category = st.text_input("Activity category", help="e.g. stationary_combustion")
        substance = st.text_input("Substance", help="e.g. natural_gas")
        value = st.number_input("Value", min_value=0.0001, step=0.1, format="%.4f")
        unit = st.text_input("Unit", help="e.g. kg CO2/kWh")
        gas = st.text_input("Gas", help="e.g. CO2; or CO2e if already combined")
        geography = st.text_input("Geography", value="GB")
        reporting_year = st.number_input("Reporting year", min_value=1900, value=2024, step=1)
        source_org = st.text_input("Source organisation", help="e.g. IPCC, DEFRA, SYNTHETIC")
        source_reference = st.text_input(
            "Source reference (URL/DOI)",
            help="Required by the factor model; synthetic entries should say so explicitly",
        )
        version = st.text_input("Version", help="e.g. 2024, v1.2")
        uncertainty_pct = st.number_input("Uncertainty (% , optional)", min_value=0.0, max_value=100.0,
                                          value=0.0, step=1.0, format="%.1f")
        review_status = st.selectbox("Review status", options=["illustrative", "published", "verified"],
                                     help="illustrative = synthetic test data only")
        notes = st.text_area("Methodological notes", help="Free‑form notes")
        submitted = st.form_submit_button("Save factor")

        if submitted:
            if not fid or not activity_category or not substance:
                st.error("Factor ID, activity category and substance are required.")
            elif not source_reference.strip():
                st.error("A source reference is required: an unattributed factor is not auditable.")
            else:
                try:
                    new_factor = EmissionFactor(
                        factor_id=fid,
                        activity_category=activity_category,
                        substance=substance,
                        value=value,
                        unit=unit,
                        gas=gas or "CO2",
                        gases_covered=[],
                        geography=geography,
                        reporting_year=int(reporting_year),
                        source_org=source_org or "UNKNOWN",
                        source_reference=source_reference or "",
                        version=version or "",
                        uncertainty_pct=uncertainty_pct if uncertainty_pct > 0 else None,
                        review_status=review_status,
                        methane_basis=None,
                        notes=notes or "",
                    )
                    db = CarbonDatabase(DB_PATH)
                    db.init_schema()
                    with db:
                        db.save_factor(new_factor)
                    st.success(f"Factor {fid} stored in {DB_PATH.name}.")
                except Exception as e:
                    st.error(f"Failed to save factor: {e}")

    st.caption("Factors are stored in the same SQLite schema used by the rest of the "
               "dashboard. The packed seed CSV is read‑only; use this form to experiment "
               "with adding your own provenance‑rich factors — always label them "
               "`review_status=illustrative` if they are not from an official source.")


# ----- sidebar -----
st.sidebar.title("ℹ️ Emission Factor DB")
st.sidebar.markdown(
    "- All packaged factors are **illustrative** and **synthetic** — they must never be "
    "presented as official emission factors.\n"
    "- New factors entered via the form are stored in the in‑memory SQLite database; "
    "they are not written to the packaged CSV.\n"
    "- Resolution is deterministic: category → substance → geography (exact beats GLOBAL) → "
    "vintage (newest at or before reporting year).\n"
    "- Ambiguous substances with factors for multiple gases raise `AmbiguousFactorError`; "
    "the user must set the activity's `gas` field.\n"
    "- Uncertainty values are informational only; they are used by the Monte Carlo "
    "module (M9, page 9) to build probability distributions."
)