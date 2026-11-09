"""Milestone 8 — decarbonisation scenario tests.

Expected values are hand-computed from the synthetic seed factors (EF-ILL-*).

Baseline inventory used throughout::

    paper     1000 kg   @ 1.20 kg CO2e/kg  = 1200 kg   (s3_cat01)
    gas        500 kWh  @ 0.18 kg CO2/kWh  =   90 kg   (stationary_combustion)
    freight   2000 tkm  @ 0.10 kg CO2e/tkm =  200 kg   (s3_cat04)
    ------------------------------------------------------------------
    baseline                                1490 kg CO2e
"""

from __future__ import annotations

from datetime import date

import pytest

from opencarbonchem.accounting import OrganizationReport, calculate_scope1
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.core.calc import compute_emissions
from opencarbonchem.core.exceptions import ScenarioError
from opencarbonchem.core.gwp import DEFAULT_GWP_SET
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.factors import EmissionFactor, FactorRegistry, illustrative_seed_path
from opencarbonchem.scenarios import (
    LEVER_KINDS,
    EnergyEfficiency,
    FuelSwitch,
    MaterialSubstitution,
    ProcessOptimisation,
    RenewableElectricity,
    Scenario,
    TransportOptimisation,
    WasteReduction,
    apply_lever,
    baseline_result,
    compare_scenarios,
    lever_from_kind,
    persist_scenarios,
    run_levers,
    scenario_from_kind,
)

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


def _entry(registry: FactorRegistry, activity: ActivityRecord):
    return activity, registry.find(
        activity_category=activity.category,
        substance=activity.substance,
        geography="GLOBAL",
        year=2024,
        gas=activity.gas,
    )


@pytest.fixture(scope="module")
def baseline(registry):
    """paper 1200 + gas 90 + freight 200 = 1490 kg CO2e."""
    return [
        _entry(registry, act("A-PAPER", "s3_cat01", "paper", 1000, "kg", scope=3)),
        _entry(registry, act("A-GAS", "stationary_combustion", "natural_gas", 500, "kWh",
                             gas="CO2")),
        _entry(registry, act("A-FREIGHT", "s3_cat04", "road_freight", 2000, "tkm", scope=3)),
    ]


@pytest.fixture(scope="module")
def with_electricity(registry, baseline):
    """baseline + 1000 kWh grid electricity @ 0.45 = 450 kg -> 1940 kg."""
    return list(baseline) + [
        _entry(registry, act("A-ELEC", "purchased_electricity", "grid_electricity",
                             1000, "kWh", gas="CO2e", scope=2)),
    ]


def _factor(substance: str, value: float, unit: str = "kg CO2/kWh",
            category: str = "stationary_combustion") -> EmissionFactor:
    """A clearly synthetic replacement factor (never a real-world claim)."""
    return EmissionFactor(
        factor_id=f"SYN-{substance.upper()}",
        activity_category=category,
        substance=substance,
        value=value,
        unit=unit,
        gas="CO2",
        gases_covered=["CO2"],
        geography="GLOBAL",
        reporting_year=2024,
        source_org="SYNTHETIC",
        source_reference="OpenCarbonChem scenario test data",
        version="test-v1",
        review_status="illustrative",
        notes="SYNTHETIC replacement factor used only to test scenario levers.",
    )


# --------------------------------------------------------------------------- #
# Baseline
# --------------------------------------------------------------------------- #
def test_baseline_matches_engine(baseline):
    result = baseline_result(baseline)
    # Hand check: 1200 + 90 + 200.
    assert result.baseline_kg == pytest.approx(1490.0)
    assert result.scenario_kg == pytest.approx(1490.0)
    assert result.reduction_kg == pytest.approx(0.0)
    assert result.reduction_pct == pytest.approx(0.0)
    assert result.lever == "baseline"
    assert not result.changed

    # Consistent with the corporate inventory for the same rows.
    report = OrganizationReport.from_results([calculate_scope1([baseline[1][0]], FactorRegistry.from_csv(illustrative_seed_path()))])
    assert report.total_kg == pytest.approx(90.0)


def test_baseline_matches_manual_engine_sum(baseline):
    manual = sum(
        compute_emissions(activity, factor, gwp_set=DEFAULT_GWP_SET).co2e_kg
        for activity, factor in baseline
    )
    assert baseline_result(baseline).baseline_kg == pytest.approx(manual)


# --------------------------------------------------------------------------- #
# The seven levers
# --------------------------------------------------------------------------- #
def test_renewable_electricity_half_share(with_electricity):
    # 0.45 x (1 - 0.5) = 0.225 kg/kWh -> 225 kg for 1000 kWh.
    result = apply_lever(RenewableElectricity(share=0.5), with_electricity)
    assert result.baseline_kg == pytest.approx(1940.0)
    assert result.scenario_kg == pytest.approx(1715.0)
    assert result.reduction_kg == pytest.approx(225.0)
    assert result.reduction_pct == pytest.approx(225.0 / 1940.0 * 100.0)
    assert result.lever == "renewable_electricity"


def test_renewable_electricity_full_share_drops_the_rows(with_electricity):
    # 100 % renewable with a zero residual factor: the contribution vanishes
    # and the scenario total is the remaining inventory, not an error.
    result = apply_lever(RenewableElectricity(share=1.0), with_electricity)
    assert result.scenario_kg == pytest.approx(1490.0)
    assert result.reduction_kg == pytest.approx(450.0)
    assert result.reduction_pct == pytest.approx(100.0 * 450.0 / 1940.0)


def test_renewable_electricity_residual_mix(with_electricity):
    # 0.45 x 0.5 + 0.10 x 0.5 = 0.275 kg/kWh -> 275 kg.
    result = apply_lever(RenewableElectricity(share=0.5, residual_ef=0.10), with_electricity)
    assert result.scenario_kg == pytest.approx(1490.0 + 275.0)


def test_energy_efficiency(baseline):
    # Gas 500 -> 400 kWh -> 72 kg. 1200 + 72 + 200 = 1472 kg.
    result = apply_lever(EnergyEfficiency(improvement=0.2), baseline)
    assert result.scenario_kg == pytest.approx(1472.0)
    assert result.reduction_kg == pytest.approx(18.0)
    assert result.reduction_pct == pytest.approx(18.0 / 1490.0 * 100.0)


def test_fuel_switch(registry):
    entries = [_entry(registry, act("A-GAS", "stationary_combustion", "natural_gas",
                                    500, "kWh", gas="CO2"))]
    result = apply_lever(
        FuelSwitch(from_substance="natural_gas", to_substance="hydrogen",
                   to_factor=_factor("hydrogen", 0.01)),
        entries,
    )
    # 500 kWh x 0.01 = 5 kg, down from 90 kg.
    assert result.baseline_kg == pytest.approx(90.0)
    assert result.scenario_kg == pytest.approx(5.0)
    assert result.reduction_kg == pytest.approx(85.0)


def test_material_substitution(registry):
    entries = [_entry(registry, act("A-PAPER", "s3_cat01", "paper", 1000, "kg", scope=3))]
    result = apply_lever(
        MaterialSubstitution(
            from_substance="paper",
            to_substance="recycled_paper",
            to_factor=_factor("recycled_paper", 0.50, unit="kg CO2e/kg", category="s3_cat01"),
        ),
        entries,
    )
    # 1200 kg -> 1000 kg x 0.50 = 500 kg.
    assert result.scenario_kg == pytest.approx(500.0)
    assert result.reduction_kg == pytest.approx(700.0)
    assert result.reduction_pct == pytest.approx(700.0 / 1200.0 * 100.0)


def test_waste_reduction(registry):
    entries = [_entry(registry, act("A-WASTE", "s3_cat05", "mixed_waste", 1000, "kg", scope=3))]
    result = apply_lever(WasteReduction(reduction=0.5), entries)
    # 500 kg -> 250 kg.
    assert result.baseline_kg == pytest.approx(500.0)
    assert result.scenario_kg == pytest.approx(250.0)
    assert result.reduction_pct == pytest.approx(50.0)


def test_process_optimisation(registry):
    entries = [_entry(registry, act("A-LIME", "process_emissions", "limestone",
                                    1000, "kg", gas="CO2"))]
    result = apply_lever(ProcessOptimisation(improvement=0.1), entries)
    # 440 kg -> 396 kg.
    assert result.scenario_kg == pytest.approx(396.0)
    assert result.reduction_kg == pytest.approx(44.0)
    assert result.reduction_pct == pytest.approx(10.0)


def test_transport_optimisation(baseline):
    # Freight 2000 -> 1500 tkm -> 150 kg. 1200 + 90 + 150 = 1440 kg.
    result = apply_lever(TransportOptimisation(efficiency=0.25), baseline)
    assert result.scenario_kg == pytest.approx(1440.0)
    assert result.reduction_kg == pytest.approx(50.0)
    assert result.reduction_pct == pytest.approx(50.0 / 1490.0 * 100.0)


def test_all_seven_levers_are_exercised():
    assert len(LEVER_KINDS) == 7


# --------------------------------------------------------------------------- #
# Fail-safe behaviour
# --------------------------------------------------------------------------- #
def test_adverse_lever_reports_negative_reduction(registry):
    # Switching to a *higher*-carbon fuel must show an increase, not be hidden.
    entries = [_entry(registry, act("A-GAS", "stationary_combustion", "natural_gas",
                                    500, "kWh", gas="CO2"))]
    result = apply_lever(
        FuelSwitch(from_substance="natural_gas", to_substance="heavy_fuel_oil",
                   to_factor=_factor("heavy_fuel_oil", 0.40)),
        entries,
    )
    assert result.scenario_kg == pytest.approx(200.0)
    assert result.reduction_kg == pytest.approx(-110.0)
    assert result.reduction_pct == pytest.approx(-110.0 / 90.0 * 100.0)


def test_zero_baseline_has_no_percentage(registry):
    entries = [_entry(registry, act("A-GAS", "stationary_combustion", "natural_gas",
                                    0, "kWh", gas="CO2"))]
    result = apply_lever(EnergyEfficiency(improvement=0.2), entries)
    assert result.baseline_kg == pytest.approx(0.0)
    assert result.scenario_kg == pytest.approx(0.0)
    assert result.reduction_kg == pytest.approx(0.0)
    assert result.reduction_pct is None  # undefined, never 0 % or inf


def test_lever_matching_nothing_raises(baseline):
    with pytest.raises(ScenarioError, match="no inventory rows matched"):
        apply_lever(WasteReduction(reduction=0.5), baseline)


@pytest.mark.parametrize(
    "build",
    [
        lambda: RenewableElectricity(share=0.0),
        lambda: RenewableElectricity(share=1.5),
        lambda: RenewableElectricity(share=0.5, residual_ef=-0.1),
        lambda: EnergyEfficiency(improvement=0.0),
        lambda: EnergyEfficiency(improvement=1.0),
        lambda: WasteReduction(reduction=-0.1),
        lambda: ProcessOptimisation(improvement=1.2),
        lambda: TransportOptimisation(efficiency=0.0),
        lambda: FuelSwitch(from_substance="diesel", to_substance="diesel",
                           to_factor=_factor("diesel", 1.0, unit="kg CO2/L")),
        lambda: FuelSwitch(from_substance="natural_gas", to_substance="hydrogen",
                           to_factor=_factor("biomethane", 0.1)),
    ],
)
def test_invalid_lever_parameters_raise(build):
    # Construction itself is the failing operation: an unusable lever never
    # reaches the engine, so no scenario can silently model nothing.
    with pytest.raises(ScenarioError):
        build()


def test_unknown_lever_kind_raises():
    with pytest.raises(ScenarioError, match="Unknown lever"):
        lever_from_kind("cold_fusion")


# --------------------------------------------------------------------------- #
# Composition helpers
# --------------------------------------------------------------------------- #
def test_run_levers_returns_baseline_then_each_lever(baseline):
    results = run_levers(
        baseline,
        [EnergyEfficiency(improvement=0.2), TransportOptimisation(efficiency=0.25)],
    )
    assert len(results) == 3
    assert results[0].lever == "baseline"
    assert [r.lever for r in results[1:]] == ["energy_efficiency", "transport_optimisation"]


def test_named_scenario_keeps_its_label(baseline):
    scenario = Scenario(name="2030 pathway", lever=EnergyEfficiency(improvement=0.2))
    result = scenario.apply_to(baseline)
    assert result.name == "2030 pathway"
    assert result.scenario_kg == pytest.approx(1472.0)


def test_compare_scenarios_hand_computed(baseline):
    base = baseline_result(baseline)
    alternative = apply_lever(EnergyEfficiency(improvement=0.2), baseline)
    comparison = compare_scenarios(base, alternative)
    assert comparison["baseline_kg"] == pytest.approx(1490.0)
    assert comparison["alternative_kg"] == pytest.approx(1472.0)
    assert comparison["reduction_kg"] == pytest.approx(18.0)
    assert comparison["reduction_pct"] == pytest.approx(18.0 / 1490.0 * 100.0)
    assert comparison["status"] == "compared"


def test_compare_scenarios_zero_baseline(registry):
    empty = [_entry(registry, act("A-GAS", "stationary_combustion", "natural_gas",
                                  0, "kWh", gas="CO2"))]
    comparison = compare_scenarios(baseline_result(empty), baseline_result(empty))
    assert comparison["reduction_pct"] is None
    assert comparison["status"] == "baseline_is_zero"


def test_scenario_from_kind_builds_the_right_lever():
    lever = scenario_from_kind("energy_efficiency", improvement=0.3)
    assert isinstance(lever, EnergyEfficiency)
    assert lever.improvement == pytest.approx(0.3)


def test_result_serialises(baseline):
    payload = apply_lever(EnergyEfficiency(improvement=0.2), baseline).to_dict()
    assert payload["lever"] == "energy_efficiency"
    assert payload["reduction_kg"] == pytest.approx(18.0)


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_scenario_results_round_trip(baseline, tmp_path):
    results = run_levers(baseline, [EnergyEfficiency(improvement=0.2)])
    db_path = tmp_path / "scenarios.db"
    with CarbonDatabase(db_path) as db:
        db.init_schema()
        persist_scenarios(db, "RUN-SC-1", results, period_id=None)
        stored = db.list_scenario_results("RUN-SC-1")

    assert len(stored) == 2
    baseline_row = next(r for r in stored if r["scenario_id"] == "Baseline")
    assert baseline_row["baseline_kg"] == pytest.approx(1490.0)
    assert baseline_row["scenario_kg"] == pytest.approx(1490.0)
    assert baseline_row["reduction_kg"] == pytest.approx(0.0)

    efficiency_row = next(
        r for r in stored if r["scenario_id"].startswith("Energy efficiency")
    )
    assert efficiency_row["scenario_kg"] == pytest.approx(1472.0)
    assert efficiency_row["reduction_kg"] == pytest.approx(18.0)


@pytest.mark.integration
def test_reusing_a_run_id_is_refused(baseline):
    results = run_levers(baseline, [EnergyEfficiency(improvement=0.2)])
    with CarbonDatabase(":memory:") as db:
        db.init_schema()
        persist_scenarios(db, "RUN-SC-2", results)
        with pytest.raises(ScenarioError, match="already exists"):
            persist_scenarios(db, "RUN-SC-2", results)


@pytest.mark.integration
def test_persisting_nothing_raises():
    with CarbonDatabase(":memory:") as db:
        db.init_schema()
        with pytest.raises(ScenarioError, match="no scenario results"):
            persist_scenarios(db, "RUN-EMPTY", [])


@pytest.mark.integration
def test_unknown_scenario_id_is_refused():
    with CarbonDatabase(":memory:") as db:
        db.init_schema()
        db.start_run("RUN-SC-3", DEFAULT_GWP_SET)
        with pytest.raises(ScenarioError, match="must be saved first"):
            db.save_scenario_results(
                "RUN-SC-3", [("does-not-exist", "", 100.0, 90.0, 10.0)]
            )
