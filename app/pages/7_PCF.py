"""OpenCarbonChem — Product Carbon Footprint page.

PCF = sum of attributable life-cycle CO2e / reference-flow output. The page is a
thin client over `calculate_pcf`: boundary enforcement, allocation and the
double-counting guard all live in the package.

The inventory you build here is kept in this session; the product definition is
also stored in the SQLite database. Nothing is inferred: a factor that cannot be
resolved raises, and the page shows the error instead of inventing a value.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.core.exceptions import AllocationError, PCFError
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.pcf import (
    InventoryItem,
    ProductDefinition,
    calculate_pcf,
    stages_for_boundary,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "opencarbonchem.db"

st.set_page_config(
    page_title="OpenCarbonChem — Product Carbon Footprint", page_icon="🧮", layout="wide"
)
st.title("🧮 Product Carbon Footprint")

PERIOD = dict(period_start=None, period_end=None)


@st.cache_resource
def _registry() -> FactorRegistry:
    return FactorRegistry.from_csv()


def _demo_product() -> ProductDefinition:
    return ProductDefinition(
        pcf_id="PCF-DEMO-001",
        product_name="Synthetic chemical product",
        functional_unit="1 tonne of product at the factory gate",
        production_qty=1.0,
        production_unit="t",
        system_boundary="cradle_to_gate",
        notes="SYNTHETIC — dashboard demonstration only.",
    )


def _demo_items(registry: FactorRegistry) -> list[InventoryItem]:
    """Five stages, all factors from the illustrative seed set (SYNTHETIC)."""
    return [
        InventoryItem(
            stage="raw_materials",
            activity=ActivityRecord(
                activity_id="A-RAW", scope=3, category="s3_cat01",
                substance="paper", quantity=1000, unit="kg",
            ),
            factor=registry.find(activity_category="s3_cat01", substance="paper", year=2024),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="manufacturing",
            activity=ActivityRecord(
                activity_id="A-MFG", scope=1, category="stationary_combustion",
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
                activity_id="A-TRN", scope=3, category="s3_cat04",
                substance="road_freight", quantity=2000, unit="tkm",
            ),
            factor=registry.find(activity_category="s3_cat04", substance="road_freight", year=2024),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="packaging",
            activity=ActivityRecord(
                activity_id="A-PKG", scope=3, category="s3_cat01",
                substance="paper", quantity=50, unit="kg",
            ),
            factor=registry.find(activity_category="s3_cat01", substance="paper", year=2024),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="waste",
            activity=ActivityRecord(
                activity_id="A-WST", scope=3, category="s3_cat05",
                substance="mixed_waste", quantity=100, unit="kg",
            ),
            factor=registry.find(activity_category="s3_cat05", substance="mixed_waste", year=2024),
            excluded_from_corporate=True,
        ),
    ]


# ---------- session defaults ---------- #
if "pcf_product" not in st.session_state:
    st.session_state["pcf_product"] = _demo_product()
if "pcf_items" not in st.session_state:
    st.session_state["pcf_items"] = _demo_items(_registry())

product: ProductDefinition = st.session_state["pcf_product"]

col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Define the product")
    with st.form("product_def", clear_on_submit=True):
        pcf_id = st.text_input("PCF ID", value=product.pcf_id)
        product_name = st.text_input("Product name", value=product.product_name)
        functional_unit = st.text_input("Functional unit", value=product.functional_unit)
        production_qty = st.number_input(
            "Production quantity (reference flow)", min_value=0.01, value=float(product.production_qty),
            step=0.1, format="%.3f",
        )
        production_unit = st.text_input("Production unit", value=product.production_unit)
        boundary = st.selectbox(
            "System boundary",
            options=["cradle_to_gate", "cradle_to_grave"],
            index=0 if product.system_boundary == "cradle_to_gate" else 1,
        )
        notes = st.text_area("Notes", value="SYNTHETIC — dashboard demonstration only.")
        submitted = st.form_submit_button("Save product definition")

        if submitted:
            try:
                new_product = ProductDefinition(
                    pcf_id=pcf_id,
                    product_name=product_name,
                    functional_unit=functional_unit,
                    production_qty=production_qty,
                    production_unit=production_unit,
                    system_boundary=boundary,
                    notes=notes,
                )
            except (PCFError, ValueError) as exc:
                st.error(f"Product definition rejected: {exc}")
            else:
                db = CarbonDatabase(DB_PATH)
                db.init_schema()
                with db:
                    db.save_pcf_definition(new_product)
                st.session_state["pcf_product"] = new_product
                st.success(f"Product {new_product.pcf_id} stored in {DB_PATH.name}.")

    st.subheader("Add a life-cycle inventory item")
    st.caption(
        "Each item is one activity record paired with one emission factor. The stage must "
        "be inside the declared boundary, and the factor is looked up — never guessed."
    )
    with st.form("add_pcf_item", clear_on_submit=True):
        stage = st.selectbox("Stage", options=list(stages_for_boundary(product.system_boundary)))
        act_id = st.text_input("Activity ID", value="")
        category = st.text_input("Activity category", value="s3_cat01",
                                 help="Engine vocabulary: s3_catNN, stationary_combustion, …")
        substance = st.text_input("Substance", value="")
        quantity = st.number_input("Quantity", min_value=0.01, value=1.0, step=0.1, format="%.3f")
        unit = st.text_input("Unit", value="kg")
        gas = st.text_input("Gas (optional)", value="")
        excluded = st.checkbox("Excluded from the corporate inventory", value=True)
        submitted_item = st.form_submit_button("Add inventory item")

        if submitted_item:
            try:
                activity = ActivityRecord(
                    activity_id=act_id,
                    scope=3 if category.startswith("s3_") else 1,
                    category=category,
                    substance=substance,
                    quantity=quantity,
                    unit=unit,
                    gas=gas or None,
                    **PERIOD,
                )
                factor = _registry().find(
                    activity_category=category,
                    substance=substance,
                    geography="GB",
                    year=2024,
                    gas=gas or None,
                )
                item = InventoryItem(
                    stage=stage,
                    activity=activity,
                    factor=factor,
                    excluded_from_corporate=excluded,
                )
            except (PCFError, ValueError, Exception) as exc:
                st.error(f"Inventory item rejected: {exc}")
            else:
                st.session_state["pcf_items"] = [*st.session_state["pcf_items"], item]
                st.success(f"Added {activity.activity_id} to stage {stage}.")

    if st.button("Reset inventory to the demo rows"):
        st.session_state["pcf_product"] = _demo_product()
        st.session_state["pcf_items"] = _demo_items(_registry())
        st.rerun()

    st.subheader("Calculate PCF")
    if st.button("Calculate product carbon footprint", type="primary"):
        current_product = st.session_state["pcf_product"]
        items = st.session_state["pcf_items"]
        try:
            result = calculate_pcf(current_product, items)
        except (PCFError, AllocationError) as exc:
            st.error(f"PCF calculation refused: {exc}")
        except Exception as exc:
            st.error(f"PCF calculation failed: {exc}")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total (kg CO2e)", f"{result.total_kg:,.1f}")
            c2.metric("Total (t CO2e)", f"{result.total_t:,.3f}")
            c3.metric(f"Per {current_product.production_unit}", f"{result.per_unit:,.2f}")
            st.write("**Allocated CO2e by stage:**")
            st.dataframe(
                pd.DataFrame(
                    [(stage, kg) for stage, kg in result.by_stage().items()],
                    columns=["Stage", "Allocated CO2e (kg)"],
                ),
                width="stretch",
                hide_index=True,
            )
            st.caption("Stages in this boundary: " + ", ".join(result.boundary_stages))
            if result.consistency_warnings:
                st.warning(
                    "Consistency warnings: " + "; ".join(result.consistency_warnings)
                )
            else:
                st.success("No double-counting contradictions with a corporate inventory.")

with col_right:
    st.subheader("Current inventory")
    items = st.session_state["pcf_items"]
    st.caption(f"{len(items)} items · boundary {product.system_boundary}")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "stage": item.stage,
                    "activity": item.activity_id,
                    "factor": item.factor_id,
                    "excluded": item.excluded_from_corporate,
                }
                for item in items
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    st.subheader("Allowed stages")
    for stage in stages_for_boundary(product.system_boundary):
        st.caption(f"✓ {stage}")
    st.caption(
        "cradle_to_gate: raw materials, manufacturing, inbound transport, packaging, waste. "
        "cradle_to_grave adds distribution, use and end of life. A stage outside the "
        "boundary is rejected by the calculator."
    )

st.sidebar.title("ℹ️ Product Carbon Footprint")
st.sidebar.markdown(
    "- **PCF = Σ attributable life-cycle CO2e / reference-flow output** (ISO 14067).\n"
    "- Every line keeps its activity value/unit, factor value/unit, gas and GWP set, so "
    "the footprint can be re-derived from the result alone.\n"
    "- Allocation (mass / economic / physical causality / none) is only applied when "
    "shared emissions genuinely exist; the share is recorded per line.\n"
    "- `excluded_from_corporate` marks contributions that are absent from the corporate "
    "inventory; a contradiction with a corporate report raises `DoubleCountingError`.\n"
    "- All numbers use the illustrative seed factors (EF-ILL-*), which are explicitly "
    "not official emission factors."
)
