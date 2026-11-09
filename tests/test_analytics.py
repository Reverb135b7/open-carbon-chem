"""Milestone 7 — hotspot, sensitivity and Monte Carlo tests.

Expected values are hand-computed from the synthetic seed factors (EF-ILL-*).
"""

from __future__ import annotations

from datetime import date

import pytest

from opencarbonchem.accounting import OrganizationReport, calculate_scope1
from opencarbonchem.analytics import (
    InputDistribution,
    SensitivityParameter,
    analyse_sensitivity,
    build_parameters,
    default_distributions,
    pcf_hotspots,
    product_carbon_intensity,
    rank_emissions,
    report_hotspots,
    run_monte_carlo,
)
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.core.calc import compute_emissions
from opencarbonchem.core.exceptions import AnalyticsError, UncertaintyError
from opencarbonchem.core.gwp import DEFAULT_GWP_SET
from opencarbonchem.factors import FactorRegistry, illustrative_seed_path
from opencarbonchem.pcf import InventoryItem, ProductDefinition, calculate_pcf

pytestmark = pytest.mark.unit

PERIOD = dict(period_start=date(2024, 1, 1), period_end=date(2024, 12, 31))


@pytest.fixture(scope="module")
def registry() -> FactorRegistry:
    return FactorRegistry.from_csv(illustrative_seed_path())


def act(activity_id: str, category: str, substance: str, quantity: float, unit: str,
        gas: str | None = None, scope: int = 1) -> ActivityRecord:
    return ActivityRecord(
        activity_id=activity_id, scope=scope, category=category, substance=substance,
        quantity=quantity, unit=unit, gas=gas, **PERIOD,
    )


def entries(registry: FactorRegistry):
    """1200 kg paper + 90 kg gas + 200 kg freight = 1490 kg CO2e."""
    return [
        (act("A-PAPER", "s3_cat01", "paper", 1000, "kg", scope=3),
         registry.find(activity_category="s3_cat01", substance="paper", year=2024)),
        (act("A-GAS", "stationary_combustion", "natural_gas", 500, "kWh", gas="CO2"),
         registry.find(activity_category="stationary_combustion", substance="natural_gas",
                       year=2024, gas="CO2")),
        (act("A-FREIGHT", "s3_cat04", "road_freight", 2000, "tkm", scope=3),
         registry.find(activity_category="s3_cat04", substance="road_freight", year=2024)),
    ]


# --------------------------------------------------------------------------- #
# Hotspots
# --------------------------------------------------------------------------- #
def test_rank_by_substance_orders_and_shares(registry):
    rows = [compute_emissions(a, f) for a, f in entries(registry)]
    ranked = rank_emissions(rows, by="substance")
    assert [h.key for h in ranked] == ["paper", "road_freight", "natural_gas"]
    assert ranked[0].kg == pytest.approx(1200.0)
    assert ranked[0].share == pytest.approx(1200 / 1490)
    assert sum(h.share for h in ranked) == pytest.approx(1.0)
    assert [h.rank for h in ranked] == [1, 2, 3]


def test_rank_by_scope_labels(registry):
    report = corporate_report(registry)
    ranked = report_hotspots(report)["scope"]
    assert ranked[0].label.startswith("Scope ")
    assert sum(h.kg for h in ranked) == pytest.approx(report.total_kg)


def test_unknown_dimension_rejected(registry):
    with pytest.raises(AnalyticsError, match="Unknown hotspot dimension"):
        rank_emissions([], by="vibes")


def test_zero_total_gives_zero_shares():
    from opencarbonchem.core.calc import EmissionResult

    zero = EmissionResult(
        activity_id="A", factor_id="F", scope=1, category="stationary_combustion",
        substance="x", gas="CO2", activity_value=0, activity_unit="kWh",
        factor_value=1, factor_unit="kg CO2/kWh", emissions_kg=0, gwp=1, gwp_set="AR6",
        co2e_kg=0.0,
    )
    ranked = rank_emissions([zero], by="substance")
    assert ranked[0].share == 0.0


def corporate_report(registry: FactorRegistry) -> OrganizationReport:
    activities = [
        act("A-GAS", "stationary_combustion", "natural_gas", 500, "kWh", gas="CO2"),
        act("A-DIESEL", "mobile_combustion", "diesel", 100, "L", gas="CO2"),
    ]
    return OrganizationReport.from_results([calculate_scope1(activities, registry)])


def test_pcf_hotspots_and_intensity(registry):
    product = ProductDefinition(
        pcf_id="PCF-A", product_name="Synthetic acid", functional_unit="1 t",
        production_qty=1.0, production_unit="t",
    )
    items = [
        InventoryItem(stage="raw_materials",
                      activity=act("A-PAPER", "s3_cat01", "paper", 1000, "kg", scope=3),
                      factor=registry.find(activity_category="s3_cat01", substance="paper",
                                           year=2024)),
        InventoryItem(stage="manufacturing",
                      activity=act("A-GAS", "stationary_combustion", "natural_gas", 500,
                                   "kWh", gas="CO2"),
                      factor=registry.find(activity_category="stationary_combustion",
                                           substance="natural_gas", year=2024, gas="CO2")),
    ]
    pcf = calculate_pcf(product, items)
    hotspots = pcf_hotspots(pcf)
    assert hotspots["stage"][0].key == "raw_materials"
    assert hotspots["stage"][0].kg == pytest.approx(1200.0)
    assert hotspots["stage"][0].share == pytest.approx(1200 / 1290)

    intensity = product_carbon_intensity(pcf)
    assert intensity["per_unit"] == pytest.approx(1290.0)
    assert intensity["unit_label"] == "kg CO2e/t"


# --------------------------------------------------------------------------- #
# Sensitivity
# --------------------------------------------------------------------------- #
def test_sensitivity_single_row_is_exactly_plus_10_percent(registry):
    """1200 kg ± 10 % → 1080 / 1320 kg; swing 240 kg."""
    one = entries(registry)[:1]
    result = analyse_sensitivity(
        one, [SensitivityParameter(name="paper EF", activity_id="A-PAPER",
                                   field="factor_value", delta_pct=10.0)],
    )
    assert result.base_kg == pytest.approx(1200.0)
    row = result.rows[0]
    assert row.low_kg == pytest.approx(1080.0)
    assert row.high_kg == pytest.approx(1320.0)
    assert row.swing_kg == pytest.approx(240.0)
    assert row.low_delta_pct == pytest.approx(-10.0)
    assert row.high_delta_pct == pytest.approx(10.0)


def test_sensitivity_quantity_perturbation_matches_factor_perturbation(registry):
    one = entries(registry)[:1]
    by_quantity = analyse_sensitivity(
        one, [SensitivityParameter(name="q", activity_id="A-PAPER", field="quantity")],
    )
    by_factor = analyse_sensitivity(
        one, [SensitivityParameter(name="ef", activity_id="A-PAPER", field="factor_value")],
    )
    assert by_quantity.rows[0].swing_kg == pytest.approx(by_factor.rows[0].swing_kg)


def test_tornado_orders_by_swing(registry):
    """Paper swing 240 kg dominates gas swing 18 kg."""
    result = analyse_sensitivity(entries(registry), build_parameters(entries(registry)))
    assert result.base_kg == pytest.approx(1490.0)
    assert [r.activity_id for r in result.rows] == ["A-PAPER", "A-FREIGHT", "A-GAS"]
    assert result.most_influential is not None
    assert result.most_influential.swing_kg == pytest.approx(240.0)
    assert result.rows[1].swing_kg == pytest.approx(40.0)   # freight 200 × 20 %
    assert result.rows[2].swing_kg == pytest.approx(18.0)   # gas 90 × 20 %


def test_sensitivity_leaves_other_rows_untouched(registry):
    result = analyse_sensitivity(
        entries(registry),
        [SensitivityParameter(name="paper", activity_id="A-PAPER", field="quantity")],
    )
    # base 1490; -10 % of paper (120 kg) → 1370; +10 % → 1610.
    assert result.rows[0].low_kg == pytest.approx(1370.0)
    assert result.rows[0].high_kg == pytest.approx(1610.0)


def test_sensitivity_parameter_validation(registry):
    with pytest.raises(AnalyticsError, match="delta_pct must be in"):
        SensitivityParameter(name="x", activity_id="A", delta_pct=0)
    with pytest.raises(AnalyticsError, match="cannot be reduced by 100"):
        SensitivityParameter(name="x", activity_id="A", field="quantity", delta_pct=100)
    with pytest.raises(AnalyticsError, match="field must be one of"):
        SensitivityParameter(name="x", activity_id="A", field="price")
    with pytest.raises(AnalyticsError, match="not in the inventory"):
        analyse_sensitivity(
            entries(registry),
            [SensitivityParameter(name="ghost", activity_id="NOPE")],
        )
    with pytest.raises(AnalyticsError, match="At least one sensitivity parameter"):
        analyse_sensitivity(entries(registry), [])


def test_duplicate_parameter_names_rejected(registry):
    params = [
        SensitivityParameter(name="same", activity_id="A-PAPER"),
        SensitivityParameter(name="same", activity_id="A-GAS"),
    ]
    with pytest.raises(AnalyticsError, match="Duplicate sensitivity parameter"):
        analyse_sensitivity(entries(registry), params)


def test_empty_inventory_rejected():
    with pytest.raises(AnalyticsError, match="At least one inventory entry"):
        analyse_sensitivity([], [])


# --------------------------------------------------------------------------- #
# Monte Carlo
# --------------------------------------------------------------------------- #
def test_monte_carlo_is_reproducible_with_the_same_seed(registry):
    dists = [InputDistribution(name="paper EF", activity_id="A-PAPER", spread_pct=20)]
    first = run_monte_carlo(entries(registry), dists, n_draws=2000, seed=7)
    second = run_monte_carlo(entries(registry), dists, n_draws=2000, seed=7)
    assert first.p95_kg == second.p95_kg
    assert first.mean_kg == second.mean_kg
    assert first.seed == 7 and first.n_draws == 2000


def test_monte_carlo_differs_with_a_different_seed(registry):
    dists = [InputDistribution(name="paper EF", activity_id="A-PAPER", spread_pct=20)]
    a = run_monte_carlo(entries(registry), dists, n_draws=2000, seed=1)
    b = run_monte_carlo(entries(registry), dists, n_draws=2000, seed=2)
    assert a.p95_kg != b.p95_kg


def test_monte_carlo_percentile_ordering(registry):
    dists = [InputDistribution(name="paper EF", activity_id="A-PAPER", spread_pct=25)]
    result = run_monte_carlo(entries(registry), dists, n_draws=4000, seed=11)
    assert result.p5_kg <= result.median_kg <= result.p95_kg
    assert result.min_kg <= result.p5_kg
    assert result.p95_kg <= result.max_kg
    assert result.base_kg == pytest.approx(1490.0)
    assert result.std_kg > 0
    assert result.relative_std_pct is not None


def test_monte_carlo_mean_tracks_base_for_symmetric_distribution(registry):
    dists = [InputDistribution(name="paper EF", activity_id="A-PAPER", kind="uniform",
                               spread_pct=30)]
    result = run_monte_carlo(entries(registry), dists, n_draws=20000, seed=5)
    assert result.mean_kg == pytest.approx(result.base_kg, rel=0.01)
    assert result.median_kg == pytest.approx(result.base_kg, rel=0.01)


def test_contribution_shares_sum_to_one(registry):
    dists = [
        InputDistribution(name="paper", activity_id="A-PAPER", spread_pct=20),
        InputDistribution(name="gas", activity_id="A-GAS", spread_pct=20),
    ]
    result = run_monte_carlo(entries(registry), dists, n_draws=5000, seed=3)
    assert sum(c.share for c in result.contributions) == pytest.approx(1.0)
    # Paper is 1200 of 1490 kg and equally uncertain → dominant contributor.
    assert result.contributions[0].activity_id == "A-PAPER"


def test_contribution_shares_split_evenly_for_equal_rows(registry):
    dists = [
        InputDistribution(name="paper", activity_id="A-PAPER", spread_pct=20),
        InputDistribution(name="paper2", activity_id="A-FREIGHT", spread_pct=20),
    ]
    # Equal-emission rows: compare 1200 kg paper against 1200 kg of freight.
    rows = [
        entries(registry)[0],
        (act("A-FREIGHT", "s3_cat04", "road_freight", 12000, "tkm", scope=3),
         registry.find(activity_category="s3_cat04", substance="road_freight", year=2024)),
    ]
    result = run_monte_carlo(rows, dists, n_draws=8000, seed=9)
    shares = {c.name: c.share for c in result.contributions}
    assert shares["paper"] == pytest.approx(0.5, abs=0.05)
    assert shares["paper2"] == pytest.approx(0.5, abs=0.05)


def test_fixed_distribution_has_zero_spread(registry):
    dists = [InputDistribution(name="paper EF", activity_id="A-PAPER", kind="fixed",
                               spread_pct=0)]
    result = run_monte_carlo(entries(registry), dists, n_draws=100, seed=1)
    assert result.std_kg == 0.0
    assert result.mean_kg == pytest.approx(1490.0)
    assert result.contributions == ()


def test_histogram_is_consistent(registry):
    dists = [InputDistribution(name="paper EF", activity_id="A-PAPER", spread_pct=15)]
    result = run_monte_carlo(entries(registry), dists, n_draws=1000, seed=2)
    hist = result.histogram(bins=20)
    assert len(hist["counts"]) == 20
    assert len(hist["edges"]) == 21
    assert sum(hist["counts"]) == 1000


def test_invalid_monte_carlo_configuration_raises(registry):
    with pytest.raises(UncertaintyError, match="n_draws"):
        run_monte_carlo(entries(registry), [InputDistribution(name="x", activity_id="A-PAPER")],
                        n_draws=0)
    with pytest.raises(UncertaintyError, match="At least one input distribution"):
        run_monte_carlo(entries(registry), [])
    with pytest.raises(UncertaintyError, match="not in the inventory"):
        run_monte_carlo(entries(registry), [InputDistribution(name="x", activity_id="NOPE")])
    with pytest.raises(UncertaintyError, match="unknown distribution"):
        InputDistribution(name="x", activity_id="A-PAPER", kind="cauchy")
    with pytest.raises(UncertaintyError, match="spread_pct must be in"):
        InputDistribution(name="x", activity_id="A-PAPER", spread_pct=0)
    with pytest.raises(UncertaintyError, match="fixed input must have spread_pct = 0"):
        InputDistribution(name="x", activity_id="A-PAPER", kind="fixed", spread_pct=5)


def test_default_distributions_use_recorded_uncertainty(registry):
    """EF-ILL-005 (grid electricity) records uncertainty_pct = 5."""
    grid = (act("A-GRID", "purchased_electricity", "grid_electricity", 1000, "kWh", scope=2),
            registry.find(activity_category="purchased_electricity",
                          substance="grid_electricity", year=2024, geography="GLOBAL"))
    dists = default_distributions([grid])
    assert dists[0].spread_pct == pytest.approx(5.0)
    assert dists[0].activity_id == "A-GRID"


def test_default_distributions_reject_inputs_without_uncertainty(registry):
    no_uncertainty = entries(registry)[1]  # natural-gas CO2 factor records no uncertainty
    dists = default_distributions([no_uncertainty], spread_pct=12.0)
    assert dists[0].spread_pct == pytest.approx(12.0)


def test_monte_carlo_gwp_set_is_recorded(registry):
    dists = [InputDistribution(name="paper", activity_id="A-PAPER", spread_pct=10)]
    result = run_monte_carlo(entries(registry), dists, n_draws=50, seed=1)
    assert result.gwp_set == DEFAULT_GWP_SET
    assert result.to_dict()["seed"] == 1
