"""OpenCarbonChem — Decarbonisation Scenarios page.

Seven levers (renewable electricity, energy efficiency, fuel switching, material
substitution, waste reduction, process optimisation, transport optimisation) are
applied to the baseline inventory and the absolute and % reduction is computed.

The page is a thin client: levers are pure functions from the `scenarios.levers`
module; the engine recomputes totals through the normal calculation API.

Baseline vs scenario comparison formulas (architecture §2.1):
    Reduction      = Baseline − Scenario
    Reduction (%)  = Reduction / Baseline × 100

Fail‑safe: a zero baseline produces ``reduction_pct = None``, never 0 % or inf.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from pathlib import Path
from typing import List

from opencarbonchem.scenarios.levers import (
    RenewableElectricity, EnergyEfficiency, FuelSwitch,
    MaterialSubstitution, WasteReduction, ProcessOptimisation,
    TransportOptimisation, LEVER_KINDS, lever_from_kind,
)
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.core.inventory import validate_entries, base_rows
from opencarbonchem.core.calc import compute_emissions
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.core.exceptions import ScenarioError
from datetime import date

DATA = Path(__file__).parent.parent / "data" / "raw" / "synthetic"
DEFAULT_CSV = Path(__file__).parent.parent / "src" / "opencarbonchem" / "factors" / "data" / "illustrative_factors.csv"


st.set_page_config(page_title="OpenCarbonChem — Decarbonisation Scenarios", page_icon"🌱", layout="wide")
st.title("🌱 Decarbonisation Scenarios")


# ---------- helpers ----------
@st.cache_resource
def _load_seed() -> FactorRegistry:
    return FactorRegistry.from_csv(DEFAULT_CSV)


# ---------- layout ----------
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Baseline inventory (synthetic)")
    if st.button("Load baseline and run scenarios", type="primary"):
        with st.spinner("Loading baseline..."):
            reg = _load_seed()
            inventory = validate_entries([
                # Scope 1: stationary combustion
                (ActivityRecord(activity_id="A-ST1", scope=1, category="stationary_combustion",
                               substance="natural_gas", quantity=500, unit="kWh", gas="CO2"),
                 reg.find(activity_category="stationary_combustion", substance="natural_gas",
                           year=2024, gas="CO2")),
                # Scope 2: purchased electricity
                (ActivityRecord(activity_id="A-POW1", scope=2, category="purchased_electricity",
                               substance="grid_electricity", quantity=1000, unit="kWh"),
                 reg.find(activity_category="purchased_electricity", substance="grid_electricity",
                           year=2024)),
                # Scope 3: paper (raw material)
                (ActivityRecord(activity_id="A-S3", scope=3, category="s3_cat01",
                               substance="paper", quantity=1000, unit="kg"),
                 reg.find(activity_category="s3_cat01", substance="paper", year=2024)),
            ])
            # Compute baseline totals
            results = base_rows(inventory)
            baseline_kg = sum(r.co2e_kg for r in results)
            st.session_state["baseline_kg"] = baseline_kg
            st.session_state["inventory"] = inventory
            st.success(f"Baseline total: {baseline_kg:,.1f} kg CO₂e")

    # Scenario controls appear after baseline is loaded
    if "baseline_kg" in st.session_state:
        baseline_kg = st.session_state["baseline_kg"]
        inventory = st.session_state["inventory"]

        st.subheader("Select a lever and its parameter")
        lever_kind = st.selectbox("Lever kind", options=LEVER_KINDS,
                                  help="""
                      renewable_electricity  – replace a share of grid electricity
                      energy_efficiency      – reduce energy consumption by a fraction
                      fuel_switch            – replace one fuel with another (supply replacement factor)
                      material_substitution  – replace a raw material with a lower‑carbon alternative
                      waste_reduction        – reduce waste generated and treated
                      process_optimisation   – reduce process‑direct emissions
                      transport_optimisation – reduce freight tonne‑km
                      """)

        # Lever‑specific parameters
        try:
            LeverCls = lever_from_kind(lever_kind)
        except ScenarioError as e:
            st.error(str(e))
            LeverCls = None

        params = {}
        if LeverCls is not None:
            with st.form("lever_params"):
                if lever_kind == "renewable_electricity":
                    params["share"] = st.slider("Renewable share", min_value=0.01, max_value=0.99, value=0.30,
                                                format="%s")
                    params["residual_ef"] = st.number_input("Residual emission factor (kg CO2e/kWh)",
                                                            min_value=0.0, value=0.0, step=0.01,
                                                            format="%.4f")
                elif lever_kind == "energy_efficiency":
                    params["improvement"] = st.slider("Efficiency improvement", min_value=0.01, max_value=0.99,
                                                      value=0.20, format="%s")
                elif lever_kind == "fuel_switch":
                    # Need a replacement factor; for the demo we just ask for substance and value
                    params["from_substance"] = st.selectbox("From substance", options=["natural_gas",
                                                                                     "grid_electricity"])
                    params["to_substance"] = st.selectbox("To substance", options=["grid_electricity",
                                                                                      "natural_gas"])
                    # Skip full factor spec for demo; just note it
                    st.info("Full replacement factor required for a realistic fuel switch.")
                elif lever_kind == "material_substitution":
                    params["from_substance"] = st.selectbox("From substance", options=["paper",
                                                                                      "steel"])
                    params["to_substance"] = st.selectbox("To substance", options=["steel",
                                                                                      "paper"])
                    st.info("Full replacement factor required for a realistic material substitution.")
                elif lever_kind == "waste_reduction":
                    params["reduction"] = st.slider("Waste reduction fraction", min_value=0.01, max_value=0.99,
                                                    value=0.30, format="%s")
                elif lever_kind == "process_optimisation":
                    params["improvement"] = st.slider("Process improvement fraction", min_value=0.01,
                                                      max_value=0.99, value=0.20, format="%s")
                elif lever_kind == "transport_optimisation":
                    params["efficiency"] = st.slider("Transport efficiency fraction", min_value=0.01,
                                                     max_value=0.99, value=0.30, format="%s")
                submitted = st.form_submit_button("Apply lever and compute scenario")

                if submitted:
                    try:
                        # Build the lever object
                        if lever_kind == "renewable_electricity":
                            lever = RenewableElectricity(share=params["share"], residual_ef=params["residual_ef"])
                        elif lever_kind == "energy_efficiency":
                            lever = EnergyEfficiency(improvement=params["improvement"])
                        elif lever_kind == "fuel_switch":
                            lever = FuelSwitch(from_substance=params["from_substance"],
                                               to_substance=params["to_substance"],
                                               to_factor=None)  # placeholder – full factor needed
                        elif lever_kind == "material_substitution":
                            lever = MaterialSubstitution(from_substance=params["from_substance"],
                                                         to_substance=params["to_substance"],
                                                         to_factor=None)  # placeholder
                        elif lever_kind == "waste_reduction":
                            lever = WasteReduction(reduction=params["reduction"])
                        elif lever_kind == "process_optimisation":
                            lever = ProcessOptimisation(improvement=params["improvement"])
                        elif lever_kind == "transport_optimisation":
                            lever = TransportOptimisation(efficiency=params["efficiency"])

                        # Apply the lever via the scenario engine
                        scenario = type("S", (), {"name": f"{lever_kind} scenario", "lever": lever})()
                        from opencarbonchem.scenarios.engine import ScenarioResult
                        # We need to use the engine's apply_to – but it expects InventoryEntry tuple.
                        # For simplicity, we'll compute baseline then scenario manually.
                        # Re‑compute with the lever applied
                        from opencarbonchem.scenarios.engine import apply_lever
                        try:
                            res = apply_lever(lever, inventory, DEFAULT_CSV)
                            # res is a ScenarioResult
                            reduction_kg = baseline_kg - res.scenario_kg
                            reduction_pct = (reduction_kg / baseline_kg * 100.0) if baseline_kg > 0 else None
                            st.session_state["scenario_result"] = res
                            st.session_state["reduction_kg"] = reduction_kg
                            st.session_state["reduction_pct"] = reduction_pct
                            st.success(f"Scenario complete.")
                        except ScenarioError as e:
                            st.error(f"Lever could not be applied: {e}")
                    except Exception as e:
                        st.error(f"Failed to apply lever: {e}")

        # Display results if they exist
        if "reduction_kg" in st.session_state:
            rkg = st.session_state["reduction_kg"]
            rpct = st.session_state["reduction_pct"]
            res: ScenarioResult = st.session_state.get("scenario_result")
            c1, c2, c3 = st.columns(3)
            c1.metric("Baseline (kg)", f"{baseline_kg:,.1f}")
            c2.metric("Scenario (kg)", f"{res.scenario_kg:,.1f}" if res else "—")
            c3.metric("Reduction (kg)", f"{rkg:,.1f}" if rkg is not None else "—")
            if rpct is not None:
                c4.metric("Reduction (%)", f"{rpct:,.1f}%")
            else:
                c4.metric("Reduction (%)", "— (baseline was zero or negative)")

            st.write("**Scenario result details:**")
            if res:
                st.write(f"- Name: {res.name}")
                st.write(f"- Baseline: {res.baseline_kg:,.1f} kg CO₂e")
                st.write(f"- Scenario: {res.scenario_kg:,.1f} kg CO₂e")
                st.write(f"- Reduction: {res.reduction_kg:,.1f} kg CO₂e")
                st.write(f"- Reduction %: {res.reduction_pct:.1f}%" if res.reduction_pct is not None
                         else "- Reduction %: N/A (baseline was zero)")

        st.caption(
            "Reduction formulas (architecture §2.1):\n"
            "  Reduction      = Baseline − Scenario\n"
            "  Reduction (%)  = Reduction / Baseline × 100\n"
            "Fail‑safe: zero baseline → ``reduction_pct = None``, never 0 % or inf."
        )

with col_right:
    st.subheader("Lever reference")
    st.markdown(
        "Seven levers are available (guide §9, F12):\n\n"
        "**1. Renewable electricity** – Replace a share ``s`` of purchased electricity "
        "with a zero‑carbon (or residual‑mix) supply. ``residual_ef`` is the emission "
        "factor of the residual supply (kg CO₂e/kWh). Default 0 assumes fully zero‑carbon.\n\n"
        "**2. Energy efficiency** – Reduce energy consumption by ``i`` (fraction of current use).\n\n"
        "**3. Fuel switch** – Replace one fuel with another using a supplied replacement "
        "emission factor. Source and target substances must differ; the replacement factor "
        "must have provenance (source, reference, vintage).\n\n"
        "**4. Material substitution** – Replace a raw material with a lower‑carbon alternative, "
        "again with a supplied factor.\n\n"
        "**5. Waste reduction** – Reduce waste generated (and therefore treated) by ``r``.\n\n"
        "**6. Process optimisation** – Reduce process‑direct emissions (non‑combustion) by ``i``.\n\n"
        "**7. Transport optimisation** – Reduce freight tonne‑km by ``e`` (load factor, routing improvement)."
    )
    st.caption("Each lever is a pure function ``entries → entries``; the scenario engine "
               "then recomputes totals through the normal calculation engine, so there is no "
               "hand‑rolled math that can drift from the methodology.")
    st.caption("If a lever matches no rows, `ScenarioError` is raised with a helpful message "
               "telling the user which input the lever targets.")


# ----- sidebar -----
st.sidebar.title("ℹ️ Decarbonisation Scenarios")
st.sidebar.markdown(
    "- **Seven levers** (F12): renewable electricity, energy efficiency, fuel switching, "
    "material substitution, waste reduction, process optimisation, transport optimisation.\n"
    "- Each lever is a pure function that transforms the inventory (activity quantities and/or "
    "applied emission factors); the engine then recomputes through the normal calculation API.\n"
    "- Baseline vs scenario comparison uses the exact formulas from architecture §2.1:\n"
    "    Reduction      = Baseline − Scenario\n"
    "    Reduction (%)  = Reduction / Baseline × 100\n"
    "- Fail‑safe: a zero baseline produces ``reduction_pct = None``, never 0 % or inf.\n"
    "- Levers never invent emission factors: fuel switching and material substitution require "
    "the replacement factor to be supplied with its own provenance record.\n"
    "- If a lever matches no inventory rows, `ScenarioError` is raised with a message "
    "indicating which input the lever targets."
)