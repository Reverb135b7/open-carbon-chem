"""OpenCarbonChem — Hotspot Analysis page.

Ranks emissions by dimension (substance, category, scope, gas, activity) and
displays the results as a table of Hotspot objects (key, label, kg, share, rank, rows).
Also shows product‑level hotspots if a PCF is available.

The page is a thin client: all ranking goes through the package API
(`rank_emissions`, `report_hotspots`, `pcf_hotspots`).
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from pathlib import Path

from opencarbonchem.analytics import (
    rank_emissions, report_hotspots, pcf_hotspots, product_carbon_intensity,
)
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.accounting import OrganizationReport
from opencarbonchem.pcf import ProductDefinition, InventoryItem, calculate_pcf
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.core.calc import compute_emissions
from datetime import date

DATA = Path(__file__).parent.parent / "data" / "raw" / "synthetic"
DEFAULT_CSV = Path(__file__).parent.parent / "src" / "opencarbonchem" / "factors" / "data" / "illustrative_factors.csv"


st.set_page_config(page_title="OpenCarbonChem — Hotspot Analysis", page_icon"🔍", layout="wide")
st.title("🔍 Hotspot Analysis")


# ---------- helpers ----------
@st.cache_resource
def _load_seed() -> FactorRegistry:
    return FactorRegistry.from_csv(DEFAULT_CSV)


# ---------- layout ----------
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Corporate hotspots (Scope 1‑3 inventory)")
    if st.button("Load synthetic corporate inventory and run hotspots", type="primary"):
        with st.spinner("Loading factors and computing..."):
            reg = _load_seed()
            # Build a small synthetic Scope 1‑3 inventory
            activities = [
                # Scope 1
                ActivityRecord(activity_id="A-ST1", scope=1, category="stationary_combustion",
                               substance="natural_gas", quantity=500, unit="kWh", gas="CO2"),
                # Scope 2
                ActivityRecord(activity_id="A-POW1", scope=2, category="purchased_electricity",
                               substance="grid_electricity", quantity=1000, unit="kWh"),
                # Scope 3
                ActivityRecord(activity_id="A-S3-001", scope=3, category="s3_cat01",
                               substance="paper", quantity=1000, unit="kg"),
                ActivityRecord(activity_id="A-S3-002", scope=3, category="s3_cat04",
                               substance="road_freight", quantity=2000, unit="tkm"),
            ]
            results = [compute_emissions(a, reg.find(activity_category=a.category,
                                                  substance=a.substance,
                                                  year=2024, gas=a.gas))
                       for a in activities if a.gas or a.category != "stationary_combustion"]
            # Run hotspot rankings
            dims = ["substance", "category", "scope", "gas", "activity"]
            st.write("**Hotspot rankings (corporate):**")
            for dim in dims:
                try:
                    ranked = rank_emissions(results, by=dim)
                    st.write(f"**by {dim}**")
                    hr_df = pd.DataFrame(
                        [(h.key, h.label, h.kg, h.share, h.rank, h.rows)
                         for h in ranked],
                        columns=["Key", "Label", "kg CO2e", "Share", "Rank", "Rows"]
                    )
                    st.dataframe(hr_df, use_container_width=True)
                    total_pct = sum(h.share for h in ranked)
                    st.caption(f"Total share: {total_pct:.1%}  (rows ranked: {len(ranked)})")
                except Exception as e:
                    st.caption(f"Could not rank by {dim}: {e}")

    st.subheader("Product hotspots (PCF)")
    st.markdown(
        "If a Product Carbon Footprint has been computed (see the PCF page), "
        "hotspots can be shown per stage, per activity and per gas."
    )
    if st.button("Show product hotspots (demo PCF)", type="secondary"):
        with st.spinner("Computing product hotspots..."):
            try:
                prod = ProductDefinition(
                    pcf_id="PCF-HOTSPOT-001",
                    product_name="Synthetic chemical product",
                    functional_unit="1 tonne of product at the factory gate",
                    production_qty=1.0,
                    production_unit="t",
                    system_boundary="cradle_to_gate",
                    notes="SYNTHETIC",
                )
                items = [
                    InventoryItem(
                        stage="raw_materials",
                        activity=ActivityRecord(activity_id="A-RAW", scope=3, category="s3_cat01",
                                                substance="paper", quantity=1000, unit="kg"),
                        factor=_load_seed().find(activity_category="s3_cat01", substance="paper", year=2024),
                    ),
                    InventoryItem(
                        stage="manufacturing",
                        activity=ActivityRecord(activity_id="A-MFG", scope=1, category="stationary_combustion",
                                                substance="natural_gas", quantity=500, unit="kWh", gas="CO2"),
                        factor=_load_seed().find(activity_category="stationary_combustion",
                                                 substance="natural_gas", year=2024, gas="CO2"),
                    ),
                ]
                pcf = calculate_pcf(prod, items)
                hot = pcf_hotspots(pcf)
                st.write("**By stage:**")
                stage_df = pd.DataFrame(
                    [(h.key, h.label, h.kg, h.share, h.rank, h.rows)
                     for h in hot["stage"]],
                    columns=["Stage", "Label", "kg CO2e", "Share", "Rank", "Rows"]
                )
                st.dataframe(stage_df, use_container_width=True)
                st.write("**By activity:**")
                act_df = pd.DataFrame(
                    [(h.key, h.label, h.kg, h.share, h.rank, h.rows)
                     for h in hot["activity"]],
                    columns=["Activity ID", "Label", "kg CO2e", "Share", "Rank", "Rows"]
                )
                st.dataframe(act_df, use_container_width=True)
                st.write("**By gas:**")
                gas_df = pd.DataFrame(
                    [(h.key, h.label, h.kg, h.share, h.rank, h.rows)
                     for h in hot["gas"]],
                    columns=["Gas", "Label", "kg CO2e", "Share", "Rank", "Rows"]
                )
                st.dataframe(gas_df, use_container_width=True)
                # Product intensity
                intens = product_carbon_intensity(pcf)
                st.caption(f"Product intensity: {intens['per_unit']:,.2f} kg CO₂e / {intens['production_unit']}")
            except Exception as e:
                st.error(f"Could not compute product hotspots: {e}")

with col_right:
    st.subheader("Hotspot summary")
    st.markdown(
        "Hotspots rank emission contributors along one dimension at a time. "
        "Each row shows:\n"
        "- **Key**: the grouping key (substance name, category code, scope number, gas name, activity ID)\n"
        "- **Label**: a human‑readable description\n"
        "- **kg CO2e**: absolute contribution (allocated, after allocation if a PCF)\n"
        "- **Share**: fraction of the total (0 when total is zero, to avoid division‑by‑zero)\n"
        "- **Rank**: 1 = largest contributor\n"
        "- **Rows**: number of individual activity‑factor rows behind this grouping"
    )
    st.caption(
        "The corporate hotspots use the `rank_emissions` function with the five available "
        "dimensions: substance, category, scope, gas, activity. The share is computed as "
        "`kg / total`; when the total is zero all shares are 0.0 rather than raising an error."
    )
    st.caption(
        "Product hotspots (page 7 PCF → Hotspot Analysis) rank by stage, activity and gas, "
        "using the allocated CO₂e from the PCF result."
    )
    st.caption(
        "Product carbon intensity (kg CO₂e per functional unit) is shown at the bottom of "
        "the product hotspots section."
    )


# ----- sidebar -----
st.sidebar.title("ℹ️ Hotspot Analysis")
st.sidebar.markdown(
    "- **Five ranking dimensions**: substance, category, scope, gas, activity.\n"
    "- Each ranking returns a list of `Hotspot` objects sorted by kg CO₂e (largest first).\n"
    "- Share = kg / total; when total = 0 all shares are 0.0 (no division‑by‑zero).\n"
    "- Corporate hotspots use synthetic Scope 1‑3 activities; product hotspots use the "
    "PCF allocated contributions.\n"
    "- Product carbon intensity is shown at the bottom of the product hotspots section, "
    "expressed per the declared functional unit.\n"
    "- The underlying engine never silently assumes zero — coverage gaps and missing data "
    "are always surfaced as flags or warnings."
)