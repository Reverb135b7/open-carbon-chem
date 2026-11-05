"""OpenCarbonChem — Overview page.

Displays a high-level summary of the synthetic demonstration dataset,
including organisational boundary, scopes, and a quick numeric snapshot
of the corporate inventory + product footprint.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.accounting import (
    calculate_scope1, OrganizationReport, ScopeResult,
    Scope1_CATEGORIES as _S1,
)
from opencarbonchem.pcf import (
    ProductDefinition, InventoryItem, calculate_pcf,
    default_seed_path,
)
from opencarbonchem.analytics import run_monte_carlo, InputDistribution
from pathlib import Path

DATA = Path(__file__).parent.parent / "data" / "raw" / "synthetic"
SEED = FactorRegistry.from_csv(default_seed_path())

st.set_page_config(page_title="OpenCarbonChem — Overview", page_icon="🧮", layout="wide")
st.title("🏭 OpenCarbonChem — Overview")


# ---------- helpers ----------
@st.cache_data(ttl=600)
def _load_synthetic_activities() -> list[ActivityRecord]:
    """Load the synthetic activity-data CSV if present; otherwise return empty."""
    csv_path = DATA / "activities_synthetic.csv"
    if csv_path.exists():
        import csv
        rows: list[ActivityRecord] = []
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(
                    ActivityRecord(
                        activity_id=r["activity_id"],
                        scope=int(r["scope"]),
                        category=r["category"],
                        substance=r["substance"],
                        quantity=float(r["quantity"]),
                        unit=r["unit"],
                        gas=r.get("gas") or None,
                        period_start=None if r["period_start"] == "" else None,
                        period_end=None if r["period_end"] == "" else None,
                        data_type=r.get("data_type", "primary"),
                        notes=r.get("notes", ""),
                    )
                )
        return rows
    return []


# ---------- layout ----------
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Organisational boundary")
    # Simple placeholder boundary; in a full app this would be persisted.
    st.caption(
        "Organisation: OpenCarbonChem Demo  |  Boundary method: operational_control  "
        "|  Consolidation: operational_control"
    )

    st.subheader("Reporting period")
    st.caption("2024‑01‑01  →  2024‑12‑31")

with col2:
    st.subheader("Corporate inventory snapshot")
    activities = _load_synthetic_activities()
    if activities:
        reg = FactorRegistry.from_csv(default_seed_path())
        s1 = calculate_scope1(activities, reg)
        s2 = ...  # scope 2 would need grid factors; placeholder
        s3 = ...  # scope 3 placeholder
        st.metric("Scope 1 total", f"{s1.total_kg:,.1f} kg CO2e")
        st.metric("Scope 2 total", "-- kg CO2e (placeholder)")
        st.metric("Scope 3 total", "-- kg CO2e (placeholder)")
        st.metric("Organisation total", f"{s1.total_kg:,.1f} kg CO2e")
    else:
        st.info("No activity data loaded. Place `data/raw/synthetic/activities_synthetic.csv` "
                "to populate the dashboard with the synthetic dataset.")

    st.subheader("Product Carbon Footprint (Milestone 6)")
    # Minimal PCF snapshot — product + 5 life-cycle stages
    product = ProductDefinition(
        pcf_id="OVERVIEW-PCF-001",
        product_name="Synthetic chemical product",
        functional_unit="1 tonne of product at the factory gate",
        production_qty=1.0,
        production_unit="t",
        system_boundary="cradle_to_gate",
        notes="SYNTHETIC — for dashboard demonstration only.",
    )
    # Build a tiny 5-stage inventory matching the test fixture
    items = [
        InventoryItem(
            stage="raw_materials",
            activity=activities[0] if activities else ActivityRecord(
                activity_id="A-RAW", scope=3, category="s3_cat01",
                substance="paper", quantity=1000, unit="kg",
            ),
            factor=reg.find(activity_category="s3_cat01", substance="paper", year=2024),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="manufacturing",
            activity=activities[1] if len(activities) > 1 else ActivityRecord(
                activity_id="A-MFG", scope=1, category="stationary_combustion",
                substance="natural_gas", quantity=500, unit="kWh", gas="CO2",
            ),
            factor=reg.find(activity_category="stationary_combustion", substance="natural_gas",
                            year=2024, gas="CO2"),
        ),
        InventoryItem(
            stage="inbound_transport",
            activity=activities[2] if len(activities) > 2 else ActivityRecord(
                activity_id="A-TRN", scope=3, category="s3_cat04",
                substance="road_freight", quantity=2000, unit="tkm",
            ),
            factor=reg.find(activity_category="s3_cat04", substance="road_freight", year=2024),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="packaging",
            activity=activities[3] if len(activities) > 3 else ActivityRecord(
                activity_id="A-PKG", scope=3, category="s3_cat01",
                substance="paper", quantity=50, unit="kg",
            ),
            factor=reg.find(activity_category="s3_cat01", substance="paper", year=2024),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="waste",
            activity=activities[4] if len(activities) > 4 else ActivityRecord(
                activity_id="A-WST", scope=3, category="s3_cat05",
                substance="mixed_waste", quantity=100, unit="kg",
            ),
            factor=reg.find(activity_category="s3_cat05", substance="mixed_waste", year=2024),
            excluded_from_corporate=True,
        ),
    ]
    try:
        pcf_result = calculate_pcf(product, items)
        st.metric("PCF total", f"{pcf_result.total_kg:,.1f} kg CO2e")
        st.metric("PCF per unit", f"{pcf_result.per_unit:,.2f} kg CO2e/{product.production_unit}")
    except Exception as e:  # pragma: no cover – UI guard
        st.warning(f"PCF could not be computed: {e}")

    st.caption("All numbers above use the synthetic seed factors (EF‑ILL‑*). "
               "They are explicitly not official emission factors.")


# ------ sidebar about the dataset ------
st.sidebar.title("ℹ️ About this demo")
st.sidebar.markdown(
    "- **Dataset**: `data/raw/synthetic/activities_synthetic.csv` — "
    "5 synthetic activity rows covering Scope 1, 2 and 3 categories.\n"
    "- **Factors**: `src/opencarbonchem/factors/data/illustrative_factors.csv` — "
    "all rows are `review_status=illustrative`, `source_org=SYNTHETIC`.\n"
    "- **Purpose**: This dashboard is a portfolio‑project demonstration; "
    "no data presented here should be used for real ESG reporting.\n"
    "- **Source code**: `src/opencarbonchem/` — Python package; UI is a thin client.\n"
    "- **Standards**: GHG Protocol, ISO 14067 / PAS 2050 (PCF), IPCC GWP values."
)