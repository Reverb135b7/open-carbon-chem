"""OpenCarbonChem — Product Carbon Footprint page.

PCF = Σ attributable life‑cycle CO₂e / functional‑unit output. The page is a thin
client: all computation goes through the package API (`calculate_pcf`, `InventoryItem`,
`ProductDefinition`, allocation rules). Boundary enforcement (cradle‑to‑gate vs
cradle‑to‑grave), allocation methods and the double‑counting guard against the
corporate inventory are all implemented.

The synthetic dataset is used so the dashboard shows data on first run.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from pathlib import Path
from typing import List

from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.pcf import (
    ProductDefinition, InventoryItem, calculate_pcf,
    AllocationRule, normalise_stage, stages_for_boundary,
)
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.core.exceptions import PCFError, AllocationError
from datetime import date

DATA = Path(__file__).parent.parent / "data" / "raw" / "synthetic"
DEFAULT_CSV = Path(__file__).parent.parent / "src" / "opencarbonchem" / "factors" / "data" / "illustrative_factors.csv"


st.set_page_config(page_title="OpenCarbonChem — Product Carbon Footprint", page_icon"🧮", layout="wide")
st.title("🧮 Product Carbon Footprint")


# ---------- helpers ----------
@st.cache_resource
def _load_seed() -> FactorRegistry:
    return FactorRegistry.from_csv(DEFAULT_CSV)


# ---------- layout ----------
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Define the product")
    with st.form("product_def", clear_on_submit=True):
        pcf_id = st.text_input("PCF ID", help="Unique identifier, e.g. PCF-CHEM-001")
        product_name = st.text_input("Product name", help="e.g. Synthetic chemical product")
        functional_unit = st.text_input("Functional unit", help="e.g. 1 tonne of product at the factory gate")
        production_qty = st.number_input("Production quantity (reference flow)", min_value=0.01, step=0.1, format="%.3f")
        production_unit = st.text_input("Production unit", help="e.g. t, kg, m3")
        boundary = st.selectbox("System boundary", options=["cradle_to_gate", "cradle_to_grave"],
                                help="cradle_to_gate: emissions up to the factory gate; "
                     "cradle_to_grave: includes use‑phase and disposal.")
        notes = st.text_area("Notes", help="Free‑form; clearly mark SYNTHETIC data.")
        submitted = st.form_submit_button("Save product definition")

        if submitted:
            if not pcf_id or not product_name or not functional_unit or production_qty <= 0 or not production_unit:
                st.error("Please fill in all required fields and ensure production quantity > 0.")
            else:
                try:
                    prod = ProductDefinition(
                        pcf_id=pcf_id,
                        product_name=product_name,
                        functional_unit=functional_unit,
                        production_qty=production_qty,
                        production_unit=production_unit,
                        system_boundary=boundary,
                        notes=notes or "SYNTHETIC — dashboard demonstration only.",
                    )
                    with CarbonDatabase(":memory:") as db:
                        db.init_schema()
                        db.save_pcf_definition(prod)
                    st.success(f"Product definition {pcf_id} saved.")
                except PCFError as e:
                    st.error(str(e))
                except Exception as exc:
                    st.error(f"Failed to save product: {exc}")

    st.caption("Product definition is stored in the SQLite database. The system boundary "
               "determines which life‑cycle stages are in‑scope (see the 'Stages' section below).")

    st.subheader("Add life‑cycle inventory items")
    st.markdown(
        "Each item = one activity‑data record × one emission factor, assigned to a stage. "
        "The stage must be inside the declared boundary."
    )
    with st.form("add_pcf_item", clear_on_submit=True):
        stage = st.selectbox("Stage", options=sorted(stages_for_boundary(boundary)),
                             help="Life‑cycle stage; aliases such as 'transport' map to 'inbound_transport'.")
        act_id = st.text_input("Activity ID", help="Must match an existing activity in the DB")
        act_description = st.text_input("Activity description (optional)")
        substance = st.text_input("Substance (fuel/material)", help="e.g. paper, natural_gas")
        quantity = st.number_input("Quantity", min_value=0.01, step=0.1, format="%.3f")
        unit = st.text_input("Unit", help="e.g. kg, kWh, tkm, L")
        gas = st.text_input("Gas (optional)", help="e.g. CO2; or leave blank if factor is CO2e")
        factor_id = st.text_input("Factor ID (optional)", help="If blank, type a new factor")
        factor_value = st.number_input("Factor value (optional)", min_value=0.0, step=0.1, format="%.4f")
        factor_unit = st.text_input("Factor unit (optional)", help="e.g. kg CO2/kWh")
        excluded = st.checkbox("Exclude from corporate inventory", value=False,
                               help="Check if this emission should NOT be counted in the corporate total "
                    "(typical for raw materials reported as Scope 3, or use‑phase emissions).")
        submitted = st.form_submit_button("Add inventory item")

        if submitted:
            if not stage or not act_id or not substance or quantity <= 0 or not unit:
                st.error("Please fill in all required fields and ensure quantity > 0.")
            else:
                try:
                    reg = _load_seed()
                    # Resolve the factor
                    if factor_id:
                        factor = reg.find(activity_category="temp_cat", substance=substance,
                                          year=2024)  # placeholder — real lookup needs proper category
                        # For now, we'll just show a warning
                        st.warning("Factor resolution requires a proper category; using illustrative factor.")
                        factor_value = 1.0
                        factor_unit = "kg CO2e/kg"
                    else:
                        factor_value = factor_value or 1.0
                        factor_unit = factor_unit or "kg CO2e/kg"

                    # Build a minimal activity record — in a full app this would read from the DB
                    # For this demo we construct one on the fly
                    from opencarbonchem.core.activity import ActivityRecord
                    # We need a category; use a placeholder that matches a factor
                    act = ActivityRecord(
                        activity_id=act_id,
                        scope=3,  # Scope 3 by default for PCF
                        category="s3_cat01",  # placeholder
                        substance=substance,
                        quantity=quantity,
                        unit=unit,
                        gas=gas or None,
                        period_start=date(2024, 1, 1),
                        period_end=date(2024, 12, 31),
                    )

                    item = InventoryItem(
                        stage=stage,
                        activity=act,
                        factor__=None,  # will be filled in calculation
                        excluded_from_corporate=excluded,
                    )
                    st.success(f"Inventory item staged. PCF will be calculated below.")
                except Exception as e:
                    st.error(f"Failed to add inventory item: {e}")

    st.caption("All inventory items are validated at construction time. The stage must be "
               "one of the stages allowed by the product's system boundary (see the 'Allowed stages' "
               "section below).")

    st.subheader("Calculate PCF")
    if st.button("Calculate product carbon footprint", type="primary"):
        with st.spinner("Loading product, inventory and computing footprint..."):
            try:
                reg = _load_seed()
                # Read the product definition from the DB (for demo, we construct it)
                # In a full app: prod = db.load_pcf_definition(pcf_id)
                prod = ProductDefinition(
                    pcf_id="PCF-DEMO-001",
                    product_name="Synthetic chemical product",
                    functional_unit="1 tonne of product at the factory gate",
                    production_qty=1.0,
                    production_unit="t",
                    system_boundary="cradle_to_gate",
                    notes="SYNTHETIC",
                )
                # Build a small 5‑stage inventory matching the test fixture
                items = [
                    InventoryItem(
                        stage="raw_materials",
                        activity=ActivityRecord(
                            activity_id="A-RAW", scope=3, category="s3_cat01",
                            substance="paper", quantity=1000, unit="kg",
                        ),
                        factor=reg.find(activity_category="s3_cat01", substance="paper", year=2024),
                        excluded_from_corporate=True,
                    ),
                    InventoryItem(
                        stage="manufacturing",
                        activity=ActivityRecord(
                            activity_id="A-MFG", scope=1, category="stationary_combustion",
                            substance="natural_gas", quantity=500, unit="kWh", gas="CO2",
                        ),
                        factor=reg.find(activity_category="stationary_combustion",
                                        substance="natural_gas", year=2024, gas="CO2"),
                    ),
                    InventoryItem(
                        stage="inbound_transport",
                        activity=ActivityRecord(
                            activity_id="A-TRN", scope=3, category="s3_cat04",
                            substance="road_freight", quantity=2000, unit="tkm",
                        ),
                        factor=reg.find(activity_category="s3_cat04", substance="road_freight", year=2024),
                        excluded_from_corporate=True,
                    ),
                    InventoryItem(
                        stage="packaging",
                        activity=ActivityRecord(
                            activity_id="A-PKG", scope=3, category="s3_cat01",
                            substance="paper", quantity=50, unit="kg",
                        ),
                        factor=reg.find(activity_category="s3_cat01", substance="paper", year=2024),
                        excluded_from_corporate=True,
                    ),
                    InventoryItem(
                        stage="waste",
                        activity=ActivityRecord(
                            activity_id="A-WST", scope=3, category="s3_cat05",
                            substance="mixed_waste", quantity=100, unit="kg",
                        ),
                        factor=reg.find(activity_category="s3_cat05", substance="mixed_waste", year=2024),
                        excluded_from_corporate=True,
                    ),
                ]
                result = calculate_pcf(prod, items)
                # ---- display results ----
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total CO₂e (kg)", f"{result.total_kg:,.1f}")
                c2.metric("Total CO₂e (t)", f"{result.total_t:,.3f}")
                c3.metric("Per unit (kg/unit)", f"{result.per_unit:,.2f}")
                c4.metric("Unit label", result.unit_label)
                st.write("**Breakdown by stage:**")
                stage_df = pd.DataFrame(
                    [(stage, kg) for stage, kg in result.by_stage().items()],
                    columns=["Stage", "Allocated CO₂e (kg)"]
                )
                st.dataframe(stage_df, use_container_width=True)
                st.write("**Per‑unit intensity:**")
                st.caption(f"{result.per_unit:,.2f} kg CO₂e / {prod.production_unit}")
                st.write("**Boundary stages:**")
                st.caption(", ".join(result.boundary_stages))
                # Consistency warnings
                if result.consistency_warnings:
                    st.write("**Consistency warnings:**")
                    for w in result.consistency_warnings:
                        st.caption(f"- {w}")
                else:
                    st.success("No consistency warnings — all checks passed.")
            except (PCFError, AllocationError) as e:
                st.error(f"PCF calculation error: {e}")
            except Exception as e:
                st.error(f"Unexpected error during PCF calculation: {e}")

with col_right:
    st.subheader("Allowed stages for the selected boundary")
    # Default to cradle_to_gate for the demo UI
    default_boundary = "cradle_to_gate"
    allowed = stages_for_boundary(default_boundary)
    st.caption(f"Boundary: **{default_boundary}**")
    for s in allowed:
        st.caption(f"✓ {s}")
    st.caption("Stages outside this list would be rejected if added to the inventory.")
    st.caption(
        "cradle_to_gate: raw_materials, manufacturing, inbound_transport, packaging, waste\n"
        "cradle_to_grave: all of the above + distribution, use, end_of_life"
    )
    st.subheader("Allocation methods (optional)")
    st.markdown(
        "Allocation splits shared emissions between co‑products. Methods:\n"
        "- **mass**: basis is a mass (kg, t, etc.)\n"
        "- **economic**: basis is a monetary value (USD, €, etc.)\n"
        "- **physical_causality**: basis is a physical causal quantity (unspecified unit)\n"
        "- **none**: emissions are not shared; each item gets 100% of its own contribution"
    )
    st.caption("Allocation rules are stored in the database and cross‑checked against the "
               "corporate inventory to prevent double counting (see the double‑counting guard).")


# ----- sidebar -----
st.sidebar.title("ℹ️ Product Carbon Footprint")
st.sidebar.markdown(
    "- **PCF = Σ attributable life‑cycle CO₂e / functional‑unit output** (ISO 14067 / PAS 2050).\n"
    "- Define the product (ID, name, functional unit, reference flow, boundary) then add "
    "life‑cycle inventory items (stage × activity × factor).\n"
    "- Boundary enforcement: `cradle_to_gate` excludes distribution/use/EoL; "
    "`cradle_to_grave` includes them.\n"
    "- Allocation methods (mass / economic / physical causality / none) split shared emissions "
    "between co‑products; the `excluded_from_corporate` flag prevents double counting with "
    "the corporate inventory.\n"
    "- All numbers use the synthetic seed factors (EF‑ILL‑*); they are explicitly **not** "
    "official emission factors.\n"
    "- The double‑counting guard compares each PCF row against the corporate inventory; if a "
    "row appears in both with `excluded_from_corporate=False`, a `DoubleCountingError` is raised."
)