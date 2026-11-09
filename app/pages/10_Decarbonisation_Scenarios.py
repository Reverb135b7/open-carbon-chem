"""OpenCarbonChem — Decarbonisation Scenarios page.

Seven levers (renewable electricity, energy efficiency, fuel switching, material
substitution, waste reduction, process optimisation, transport optimisation) are
applied to the baseline inventory and the absolute and % reduction is computed.

The page is a thin client: levers are pure functions from
:mod:`opencarbonchem.scenarios.levers`; :func:`opencarbonchem.scenarios.apply_lever`
recomputes both totals through the normal calculation engine.

Baseline vs scenario comparison formulas (architecture §2.1)::

    Reduction      = Baseline − Scenario
    Reduction (%)  = Reduction / Baseline × 100

Fail-safe: a zero baseline produces ``reduction_pct = None``, never 0 % or inf.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.core.exceptions import ScenarioError
from opencarbonchem.core.inventory import validate_entries
from opencarbonchem.factors import EmissionFactor, FactorRegistry
from opencarbonchem.scenarios import (
    LEVER_KINDS,
    EnergyEfficiency,
    FuelSwitch,
    MaterialSubstitution,
    ProcessOptimisation,
    RenewableElectricity,
    TransportOptimisation,
    WasteReduction,
    apply_lever,
    baseline_result,
    run_levers,
)

st.set_page_config(
    page_title="OpenCarbonChem — Decarbonisation Scenarios",
    page_icon="🌱",
    layout="wide",
)
st.title("🌱 Decarbonisation Scenarios")

PERIOD = dict(period_start=date(2024, 1, 1), period_end=date(2024, 12, 31))


# ---------- helpers ----------
@st.cache_resource
def _registry() -> FactorRegistry:
    return FactorRegistry.from_csv()


def _factor(registry: FactorRegistry, category: str, substance: str, *,
            gas: str | None = None) -> EmissionFactor:
    return registry.find(
        activity_category=category,
        substance=substance,
        geography="GB",
        year=2024,
        gas=gas,
    )


def _synthetic_factor(substance: str, value: float, unit: str,
                      category: str) -> EmissionFactor:
    """A clearly labelled replacement factor for the demo lever only."""
    return EmissionFactor(
        factor_id=f"SYN-{substance.upper()}",
        activity_category=category,
        substance=substance,
        value=value,
        unit=unit,
        gas="CO2e",
        gases_covered=["CO2e"],
        geography="GB",
        reporting_year=2024,
        source_org="SYNTHETIC",
        source_reference="OpenCarbonChem dashboard demo (not an official factor)",
        version="demo-v1",
        review_status="illustrative",
        notes="SYNTHETIC replacement factor used to demonstrate a scenario lever.",
    )


def _demo_inventory(registry: FactorRegistry):
    """Synthetic inventory covering every lever's target category."""
    rows = [
        (ActivityRecord(activity_id="A-ST1", scope=1, category="stationary_combustion",
                        substance="natural_gas", quantity=500, unit="kWh", gas="CO2",
                        data_type="primary", **PERIOD),
         "stationary_combustion", "natural_gas", "CO2"),
        (ActivityRecord(activity_id="A-POW1", scope=2, category="purchased_electricity",
                        substance="grid_electricity", quantity=1000, unit="kWh",
                        gas="CO2e", data_type="secondary", **PERIOD),
         "purchased_electricity", "grid_electricity", "CO2e"),
        (ActivityRecord(activity_id="A-PAPER", scope=3, category="s3_cat01",
                        substance="paper", quantity=1000, unit="kg",
                        data_type="secondary", **PERIOD), "s3_cat01", "paper", None),
        (ActivityRecord(activity_id="A-FREIGHT", scope=3, category="s3_cat04",
                        substance="road_freight", quantity=2000, unit="tkm",
                        data_type="secondary", **PERIOD), "s3_cat04", "road_freight", None),
        (ActivityRecord(activity_id="A-WASTE", scope=3, category="s3_cat05",
                        substance="mixed_waste_landfill", quantity=1000, unit="kg",
                        data_type="secondary", **PERIOD), "s3_cat05", "mixed_waste_landfill", None),
        (ActivityRecord(activity_id="A-PROC", scope=1, category="process_emissions",
                        substance="limestone", quantity=1000, unit="kg", gas="CO2",
                        data_type="primary", **PERIOD),
         "process_emissions", "limestone", "CO2"),
    ]
    return validate_entries([
        (activity, _factor(registry, category, substance, gas=gas))
        for activity, category, substance, gas in rows
    ])


def _demo_levers(registry: FactorRegistry) -> dict[str, object]:
    """One representative instance of each of the seven levers."""
    return {
        "renewable_electricity": RenewableElectricity(share=0.30),
        "energy_efficiency": EnergyEfficiency(improvement=0.20),
        "fuel_switch": FuelSwitch(
            from_substance="natural_gas",
            to_substance="hydrogen",
            to_factor=_synthetic_factor("hydrogen", 0.01, "kg CO2e/kWh",
                                       "stationary_combustion"),
        ),
        "material_substitution": MaterialSubstitution(
            from_substance="paper",
            to_substance="recycled_paper",
            to_factor=_synthetic_factor("recycled_paper", 0.50, "kg CO2e/kg",
                                       "s3_cat01"),
        ),
        "waste_reduction": WasteReduction(reduction=0.30),
        "process_optimisation": ProcessOptimisation(improvement=0.10),
        "transport_optimisation": TransportOptimisation(efficiency=0.25),
    }


# ---------- layout ----------
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Baseline inventory (synthetic)")
    st.caption(
        "Synthetic activity data x packaged published factors (DESNZ 2024 / IPCC 2006). "
        "Not a real facility inventory."
    )
    if st.button("Load baseline", type="primary"):
        inventory = _demo_inventory(_registry())
        baseline = baseline_result(inventory)
        st.session_state["inventory"] = inventory
        st.session_state["baseline"] = baseline
        st.session_state.pop("scenario", None)
        st.success(f"Baseline total: {baseline.scenario_kg:,.1f} kg CO2e")

    baseline = st.session_state.get("baseline")
    inventory = st.session_state.get("inventory")

    if baseline is not None and inventory is not None:
        st.metric("Baseline (kg CO2e)", f"{baseline.scenario_kg:,.1f}")

        st.subheader("Apply a lever")
        lever_kind = st.selectbox("Lever kind", options=list(LEVER_KINDS))

        with st.form("lever_params"):
            params: dict[str, float] = {}
            if lever_kind == "renewable_electricity":
                params["share"] = st.slider("Renewable share", 0.01, 0.99, 0.30)
                params["residual_ef"] = st.number_input(
                    "Residual emission factor (kg CO2e/kWh)", 0.0, 1.0, 0.0, 0.01
                )
            elif lever_kind == "energy_efficiency":
                params["improvement"] = st.slider(
                    "Efficiency improvement", 0.01, 0.99, 0.20
                )
            elif lever_kind == "waste_reduction":
                params["reduction"] = st.slider("Waste reduction", 0.01, 0.99, 0.30)
            elif lever_kind == "process_optimisation":
                params["improvement"] = st.slider(
                    "Process improvement", 0.01, 0.99, 0.10
                )
            elif lever_kind == "transport_optimisation":
                params["efficiency"] = st.slider(
                    "Transport efficiency", 0.01, 0.99, 0.25
                )
            else:
                st.info(
                    "Fuel switching and material substitution require a replacement "
                    "emission factor with its own provenance. This demo uses a clearly "
                    "labelled SYNTHETIC factor."
                )
            submitted = st.form_submit_button("Apply lever and compute scenario")

        if submitted:
            levers = _demo_levers(_registry())
            lever = levers[lever_kind]
            # Apply the slider values to the demo lever where the kind takes them.
            if lever_kind == "renewable_electricity":
                lever = RenewableElectricity(share=params["share"],
                                             residual_ef=params["residual_ef"])
            elif lever_kind in ("energy_efficiency", "process_optimisation"):
                lever = type(lever)(improvement=params["improvement"])
            elif lever_kind == "waste_reduction":
                lever = WasteReduction(reduction=params["reduction"])
            elif lever_kind == "transport_optimisation":
                lever = TransportOptimisation(efficiency=params["efficiency"])

            try:
                result = apply_lever(lever, inventory)
            except ScenarioError as exc:
                st.error(f"Lever could not be applied: {exc}")
            else:
                st.session_state["scenario"] = result
                if result.reduction_kg < 0:
                    st.warning(
                        "This lever increases emissions. The negative reduction is "
                        "reported as-is."
                    )
                else:
                    st.success("Scenario computed.")

        result = st.session_state.get("scenario")
        if result is not None:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Baseline (kg)", f"{result.baseline_kg:,.1f}")
            c2.metric("Scenario (kg)", f"{result.scenario_kg:,.1f}")
            c3.metric("Reduction (kg)", f"{result.reduction_kg:,.1f}")
            if result.reduction_pct is None:
                c4.metric("Reduction (%)", "—")
                st.caption("Percentage undefined: the baseline total is zero.")
            else:
                c4.metric("Reduction (%)", f"{result.reduction_pct:,.1f}%")

            st.write("**Scenario detail**")
            st.json(result.to_dict())

        st.divider()
        st.subheader("All seven levers (demo parameters)")
        results = run_levers(inventory, _demo_levers(_registry()).values())
        table = pd.DataFrame([
            {
                "Scenario": r.name,
                "Lever": r.lever,
                "Baseline (kg)": round(r.baseline_kg, 3),
                "Scenario (kg)": round(r.scenario_kg, 3),
                "Reduction (kg)": round(r.reduction_kg, 3),
                "Reduction (%)": None if r.reduction_pct is None
                else round(r.reduction_pct, 3),
            }
            for r in results
        ])
        st.dataframe(table, width="stretch", hide_index=True)
        st.download_button(
            "Download scenario comparison (CSV)",
            table.to_csv(index=False).encode("utf-8"),
            file_name="opencarbonchem_scenarios.csv",
            mime="text/csv",
        )
        st.caption(
            "Reduction = Baseline − Scenario; Reduction (%) = Reduction / Baseline × 100. "
            "A zero baseline yields no percentage rather than 0 % or infinity."
        )

    else:
        st.info("Load the baseline inventory to enable the scenario controls.")

with col_right:
    st.subheader("Lever reference")
    st.markdown(
        "Seven levers are available (guide §9, F12):\n\n"
        "**1. Renewable electricity** — replace a share ``s`` of purchased electricity "
        "with a zero-carbon (or residual-mix) supply. ``residual_ef`` is the emission "
        "factor of the residual supply (kg CO₂e/kWh); the default 0 assumes fully "
        "zero-carbon supply.\n\n"
        "**2. Energy efficiency** — reduce energy consumption (stationary combustion "
        "and purchased energy) by ``i``, a fraction of current use.\n\n"
        "**3. Fuel switch** — replace one fuel with another using a supplied "
        "replacement emission factor. Source and target substances must differ, and "
        "the replacement factor must carry its own provenance.\n\n"
        "**4. Material substitution** — replace a raw material with a lower-carbon "
        "alternative, again with a supplied factor.\n\n"
        "**5. Waste reduction** — reduce waste generated (and therefore treated) by "
        "``r``.\n\n"
        "**6. Process optimisation** — reduce process-direct (non-combustion) "
        "emissions by ``i``.\n\n"
        "**7. Transport optimisation** — reduce freight tonne-kilometres by ``e`` "
        "(load factor, routing improvement)."
    )
    st.caption(
        "Each lever is a pure function ``entries -> entries``; the engine then "
        "recomputes totals through the normal calculation engine, so scenario results "
        "cannot drift from the accounting methodology."
    )
    st.caption(
        "If a lever matches no inventory rows, `ScenarioError` is raised naming the "
        "input the lever targets - a scenario that modelled nothing is never reported "
        "as a reduction."
    )

st.sidebar.title("ℹ️ Decarbonisation Scenarios")
st.sidebar.markdown(
    "- **Seven levers** (F12): renewable electricity, energy efficiency, fuel "
    "switching, material substitution, waste reduction, process optimisation, "
    "transport optimisation.\n"
    "- Each lever is a pure function that transforms the inventory (activity "
    "quantities and/or applied emission factors); the engine then recomputes through "
    "the normal calculation API.\n"
    "- Reduction = Baseline − Scenario; Reduction (%) = Reduction / Baseline × 100.\n"
    "- Fail-safe: a zero baseline produces `reduction_pct = None`, never 0 % or "
    "infinity.\n"
    "- Levers never invent emission factors: fuel switching and material substitution "
    "require the replacement factor to be supplied with its own provenance record."
)
