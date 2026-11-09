"""OpenCarbonChem — Sensitivity and Uncertainty page.

One‑at‑a‑time tornado sensitivity analysis and Monte Carlo uncertainty propagation.
The page is a thin client: all analysis goes through the package API
(`analyse_sensitivity`, `run_monte_carlo`, `InputDistribution`, etc.).
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from pathlib import Path

from opencarbonchem.analytics import (
    analyse_sensitivity, build_parameters, InputDistribution, run_monte_carlo,
)
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.core.inventory import validate_entries
from opencarbonchem.core.exceptions import AnalyticsError, UncertaintyError

DATA = Path(__file__).parent.parent / "data" / "raw" / "synthetic"
DEFAULT_CSV = Path(__file__).parent.parent.parent / "src" / "opencarbonchem" / "factors" / "data" / "illustrative_factors.csv"


st.set_page_config(page_title="OpenCarbonChem — Sensitivity & Uncertainty", page_icon="📊", layout="wide")
st.title("📊 Sensitivity & Uncertainty")


# ---------- helpers ----------
@st.cache_resource
def _load_seed() -> FactorRegistry:
    return FactorRegistry.from_csv(DEFAULT_CSV)


@st.cache_data
def _make_inventory():
    """Create a small synthetic inventory (3 entries) for the demo pages."""
    reg = _load_seed()
    entries = [
        # Paper (raw material) — factor value uncertain
        (ActivityRecord(activity_id="A-PAPER", scope=3, category="s3_cat01",
                        substance="paper", quantity=1000, unit="kg"),
         reg.find(activity_category="s3_cat01", substance="paper", year=2024)),
        # Natural gas (energy) — quantity uncertain
        (ActivityRecord(activity_id="A-GAS", scope=1, category="stationary_combustion",
                        substance="natural_gas", quantity=500, unit="kWh", gas="CO2"),
         reg.find(activity_category="stationary_combustion", substance="natural_gas",
                   year=2024, gas="CO2")),
        # Freight — quantity uncertain
        (ActivityRecord(activity_id="A-FREIGHT", scope=3, category="s3_cat04",
                         substance="road_freight", quantity=2000, unit="tkm"),
         reg.find(activity_category="s3_cat04", substance="road_freight", year=2024)),
    ]
    return validate_entries(entries)


# ---------- layout ----------
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("One‑at‑a‑time sensitivity (tornado)")

    st.markdown(
        "Each parameter perturbs exactly one input (quantity or factor value) by ±``delta_pct`` "
        "and recomputes the **whole** inventory through the engine. Results are ordered by "
        "absolute swing (largest first), so they can be plotted directly as a tornado diagram."
    )

    # Build the inventory once
    inventory = _make_inventory()
    entries_t = [ (a, f) for a, f in inventory ]

    # Parameter generation
    st.write("**Generate parameters**")
    delta_choice = st.selectbox("Perturb every input by +/- (%)", options=[5, 10, 20], index=1)
    if st.button("Generate sensitivity parameters"):
        st.session_state["sensitivity_params"] = build_parameters(
            inventory, delta_pct=delta_choice
        )
    # Default to a generated set so the analysis is usable on first render.
    params = st.session_state.setdefault(
        "sensitivity_params", build_parameters(inventory, delta_pct=delta_choice)
    )
    st.info(f"{len(params)} parameters prepared (each shrunk and grown by {delta_choice} %).")

    # Run analysis
    if True:
        params = st.session_state["sensitivity_params"]
        if st.button("Run sensitivity analysis"):
            with st.spinner("Running one‑at‑a‑time perturbations..."):
                try:
                    result = analyse_sensitivity(inventory, params)
                    st.success("Sensitivity analysis complete.")
                    # Display results
                    st.write(f"Base total: **{result.base_kg:,.1f} kg CO₂e**")
                    st.write(f"**Most influential:** {result.most_influential.name} "
                             f"(swing {result.most_influential.swing_kg:,.0f} kg)")
                    rows_df = pd.DataFrame(
                        [(r.name, r.activity_id, r.field, r.delta_pct, r.base_kg,
                          r.low_kg, r.high_kg, r.swing_kg,
                          r.low_delta_pct, r.high_delta_pct)
                         for r in result.rows],
                        columns=["Parameter", "Activity ID", "Field", "delta_pct (%)",
                                  "Base (kg)", "Low (kg)", "High (kg)", "Swing (kg)",
                                  "Low Δ%", "High Δ%"]
                    )
                    st.dataframe(rows_df, use_container_width=True)
                    # Plotly bar chart of swings
                    try:
                        import plotly.express as px
                    except Exception:
                        px = None
                    
                    if px is not None:
                        fig = px.bar(
                            rows_df.head(10),
                            x="Swing (kg)",
                            y="Parameter",
                            orientation="h",
                            title="Top 10 sensitivity swings (kg CO2e)",
                            text_auto=".1f",
                        )
                        st.plotly_chart(fig, width="stretch")
                except AnalyticsError as e:
                    st.error(f"Sensitivity analysis failed: {e}")
                except Exception as e:
                    st.error(f"Unexpected error: {e}")

    st.caption("Sensitivity uses the same `E = AD × EF` engine as every other module; "
               "no hand‑rolled approximations. Each parameter perturbs one input only; all "
               "other inputs stay at their base values.")

with col_right:
    st.subheader("Monte Carlo uncertainty")
    st.markdown(
        "Propagates input uncertainty through the same calculation engine. "
        "Each uncertain input is described by a probability distribution (normal, "
        "lognormal, triangular, uniform, or fixed) around its base value. The same "
        "seed always yields identical output (reproducibility requirement, N4)."
    )

    inventory = _make_inventory()
    with st.form("mc_form"):
        n_draws = st.number_input("Number of draws", min_value=100, value=5000, step=500,
                                  help="More draws → smoother distributions but slower.")
        seed = st.number_input("Random seed", min_value=0, value=42, step=1,
                               help="Same seed ⇒ identical results.")
        dist_kind = st.selectbox("Distribution kind", options=["normal", "lognormal",
                                                               "triangular", "uniform", "fixed"])
        field = st.selectbox(
            "Uncertain input",
            options=["factor_value", "quantity"],
            format_func=lambda f: "Emission factor" if f == "factor_value" else "Activity quantity",
        )
        spread_pct = st.number_input("Spread (%)", min_value=0.0, max_value=99.0, value=15.0,
                                     step=1.0,
                                     help="Relative half-width / standard deviation.")
        submitted = st.form_submit_button("Run Monte Carlo")

        if submitted:
            try:
                # Names must be unique per input: the engine rejects duplicates.
                dists = [
                    InputDistribution(
                        name=f"{activity.activity_id} · {field}",
                        activity_id=activity.activity_id,
                        field=field,
                        kind=dist_kind,
                        spread_pct=spread_pct,
                    )
                    for activity, _factor in inventory
                ]
                with st.spinner("Running Monte Carlo propagation..."):
                    result = run_monte_carlo(inventory, dists, n_draws=n_draws, seed=seed)
                st.success("Monte Carlo complete.")
                # Summary metrics
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Mean (kg)", f"{result.mean_kg:,.1f}")
                c2.metric("Median (kg)", f"{result.median_kg:,.1f}")
                c3.metric("Std dev (kg)", f"{result.std_kg:,.1f}")
                c4.metric("Rel. std dev (%)", f"{result.relative_std_pct:.1f}" if result.relative_std_pct is not None else "N/A")
                # Percentile band
                p1, p2 = st.columns(2)
                p1.metric("5th percentile (kg)", f"{result.p5_kg:,.1f}")
                p2.metric("95th percentile (kg)", f"{result.p95_kg:,.1f}")
                # Min / Max
                c5, c6 = st.columns(2)
                c5.metric("Min (kg)", f"{result.min_kg:,.1f}")
                c6.metric("Max (kg)", f"{result.max_kg:,.1f}")
                # Contribution analysis
                st.write("**Variance‑share contributions:**")
                contrib_df = pd.DataFrame(
                    [(c.name, f"{c.share:.1%}") for c in result.contributions],
                    columns=["Input", "Share of variance"]
                )
                st.dataframe(contrib_df, use_container_width=True)
                # Histogram
                try:
                    import plotly.express as px
                    fig = px.histogram(result.samples, nbins=30, labels={"x": "CO₂e (kg)"},
                                       title="Monte Carlo sample distribution",
                                       opacity=0.7)
                    st.plotly_chart(fig, use_container_width=True)
                except Exception:
                    st.caption("Could not render histogram — plotly not available in this view.")
            except UncertaintyError as e:
                st.error(f"Monte Carlo configuration error: {e}")
            except Exception as e:
                st.error(f"Unexpected error during Monte Carlo: {e}")

    st.caption("Distributions supported: **normal** (mean = base, σ = spread), "
               "**lognormal** (median = base, right‑skewed), **triangular** "
               "((base·(1−s), base, base·(1+s))), **uniform** ([base·(1−s), base·(1+s)]), "
               "**fixed** (no uncertainty, σ = 0).")
    st.caption("Variance‑share contributions are squared Pearson correlations of each "
               "input with the total, normalised to sum ≈ 1. Inputs with very small "
               "contributions may show noise due to the finite number of draws.")


# ----- sidebar -----
st.sidebar.title("ℹ️ Sensitivity & Uncertainty")
st.sidebar.markdown(
    "- **Sensitivity (tornado)**: one‑at‑a‑time perturbation of each nominated input "
    "(quantity or factor value) by ±``delta_pct``; the whole inventory is recomputed "
    "through the engine each time. Results ordered by absolute swing so they plot as a "
    "tornado diagram.\n"
    "- **Monte Carlo uncertainty**: seeded reproducible propagation through the same "
    "`E = AD × EF` engine. Supports normal / lognormal / triangular / uniform / fixed "
    "distributions around each input.\n"
    "- Reports: mean, median, std dev, 5th/95th percentiles, min / max, relative std dev, "
    "and variance‑share contributions (squared Pearson correlation, normalised to 1).\n"
    "- Reproducibility is a hard requirement (N4): the random generator is seeded "
    "explicitly; same seed ⇒ byte‑identical summary statistics.\n"
    "- Sensitivity and Monte Carlo both use the exact same calculation engine — no "
    "hand‑rolled math, no drift from the accounting methodology."
)