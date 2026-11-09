"""OpenCarbonChem — Overview page.

High-level snapshot of the synthetic demonstration dataset: organisational
boundary, scope totals computed from the packaged activity data, and a small
product footprint. Every number comes from the package API; the page performs
no arithmetic of its own.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from opencarbonchem.accounting import calculate_inventory
from opencarbonchem.core.activity import ActivityRecord, load_activities_csv
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.pcf import InventoryItem, ProductDefinition, calculate_pcf

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_CSV = REPO_ROOT / "data" / "activities_synthetic.csv"

st.set_page_config(page_title="OpenCarbonChem — Overview", page_icon="🧮", layout="wide")
st.title("🏭 OpenCarbonChem — Overview")


@st.cache_resource
def _registry() -> FactorRegistry:
    return FactorRegistry.from_csv()


@st.cache_data
def _activities() -> list[ActivityRecord]:
    return load_activities_csv(DATA_CSV)


@st.cache_data
def _report():
    return calculate_inventory(_activities(), _registry())


def _demo_pcf() -> tuple[ProductDefinition, list[InventoryItem]]:
    """Five life-cycle stages built from the packaged published factor set."""
    registry = _registry()
    product = ProductDefinition(
        pcf_id="OVERVIEW-PCF-001",
        product_name="Synthetic chemical product",
        functional_unit="1 tonne of product at the factory gate",
        production_qty=1.0,
        production_unit="t",
        system_boundary="cradle_to_gate",
        notes="SYNTHETIC — for dashboard demonstration only.",
    )
    items = [
        InventoryItem(
            stage="raw_materials",
            activity=ActivityRecord(
                activity_id="OV-RAW", scope=3, category="s3_cat01",
                substance="paper", quantity=1000, unit="kg",
            ),
            factor=registry.find(activity_category="s3_cat01", substance="paper", year=2024),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="manufacturing",
            activity=ActivityRecord(
                activity_id="OV-MFG", scope=1, category="stationary_combustion",
                substance="natural_gas", quantity=500, unit="kWh", gas="CO2",
            ),
            factor=registry.find(
                activity_category="stationary_combustion", substance="natural_gas",
                year=2024, gas="CO2",
            ),
        ),
        InventoryItem(
            stage="inbound_transport",
            activity=ActivityRecord(
                activity_id="OV-TRN", scope=3, category="s3_cat04",
                substance="road_freight", quantity=2000, unit="tkm",
            ),
            factor=registry.find(activity_category="s3_cat04", substance="road_freight", year=2024),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="packaging",
            activity=ActivityRecord(
                activity_id="OV-PKG", scope=3, category="s3_cat01",
                substance="paper", quantity=50, unit="kg",
            ),
            factor=registry.find(activity_category="s3_cat01", substance="paper", year=2024),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="waste",
            activity=ActivityRecord(
                activity_id="OV-WST", scope=3, category="s3_cat05",
                substance="mixed_waste_landfill", quantity=100, unit="kg",
            ),
            factor=registry.find(activity_category="s3_cat05", substance="mixed_waste_landfill", year=2024),
            excluded_from_corporate=True,
        ),
    ]
    return product, items


col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Organisational boundary")
    st.caption(
        "Organisation: OpenCarbonChem Demo · boundary method: operational_control · "
        "consolidation: operational_control (100 % of controlled entities)."
    )
    st.caption("Reporting period: 2024-01-01 to 2024-12-31.")

    st.subheader("Synthetic inventory")
    activities = _activities()
    st.caption(
        f"{len(activities)} activity rows in `{DATA_CSV.name}`; factors from the packaged "
        "illustrative set (review_status=illustrative, source_org=SYNTHETIC)."
    )
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
                    "gas": a.gas or "",
                }
                for a in activities
            ]
        ),
        width="stretch",
        hide_index=True,
    )

with col2:
    st.subheader("Corporate inventory snapshot")
    try:
        report, rows = _report()
    except Exception as exc:
        st.error(f"Inventory could not be computed: {exc}")
    else:
        by_scope = report.by_scope()
        for scope, label in ((1, "Scope 1"), (2, "Scope 2"), (3, "Scope 3")):
            if scope in by_scope:
                st.metric(f"{label} total", f"{by_scope[scope]:,.1f} kg CO2e")
            else:
                st.metric(f"{label} total", "not reported")
        st.metric("Organisation total", f"{report.total_kg:,.1f} kg CO2e")
        st.caption(f"{len(rows)} emission rows · reconciled: {'yes' if report.reconcile().ok else 'no'}")

    st.subheader("Product carbon footprint")
    try:
        product, items = _demo_pcf()
        pcf = calculate_pcf(product, items)
    except Exception as exc:
        st.warning(f"PCF could not be computed: {exc}")
    else:
        st.metric("PCF total", f"{pcf.total_kg:,.1f} kg CO2e")
        st.metric(
            f"PCF per {product.production_unit}",
            f"{pcf.per_unit:,.2f} kg CO2e/{product.production_unit}",
        )
        st.caption(f"cradle-to-gate, {len(pcf.items)} life-cycle rows")

st.caption(
    "Activity data are synthetic; emission factors are published DESNZ 2024 / IPCC "
    "defaults (see the factor page). This dashboard is not an ESG disclosure."
)

st.sidebar.title("ℹ️ About this demo")
st.sidebar.markdown(
    f"- **Dataset**: `{DATA_CSV.relative_to(REPO_ROOT)}` — {len(_activities())} synthetic "
    "rows covering Scope 1, 2 and 3.\n"
    "- **Factors**: `src/opencarbonchem/factors/data/published_factors.csv` — DESNZ 2024 and IPCC 2006 values, "
    "`review_status=published`, each with a source reference.\n"
    "- **Purpose**: portfolio demonstration; no data here is suitable for real ESG reporting.\n"
    "- **Standards**: GHG Protocol Corporate Standard, ISO 14067 (PCF), IPCC AR6 GWPs."
)
