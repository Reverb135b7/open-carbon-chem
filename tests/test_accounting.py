"""Accounting tests: scope classification, Scope 1/2/3 calculations."""

from datetime import date

import pytest

from opencarbonchem.accounting import (
    SCOPE1_CATEGORIES,
    SCOPE2_CATEGORIES,
    SCOPE3_CATEGORIES,
    calculate_scope1,
    calculate_scope2,
    calculate_scope3,
    scope3_category_id,
)
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.core.exceptions import BoundaryError, MissingFactorError
from opencarbonchem.factors.models import EmissionFactor
from opencarbonchem.factors.registry import FactorRegistry, illustrative_seed_path

PERIOD = dict(period_start=date(2024, 1, 1), period_end=date(2024, 12, 31))


@pytest.fixture(scope="module")
def registry() -> FactorRegistry:
    return FactorRegistry.from_csv(illustrative_seed_path())


def _act(**overrides) -> ActivityRecord:
    base = dict(
        activity_id="ACT-A",
        scope=1,
        category="stationary_combustion",
        substance="natural_gas",
        quantity=1000.0,
        unit="kWh",
        gas="CO2",
        geography="GLOBAL",
        **PERIOD,
    )
    base.update(overrides)
    return ActivityRecord(**base)


# --------------------------------------------------------------------------- #
# Scope 1
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_scope1_aggregation_hand_computed(registry):
    # 1000 kWh × 0.18 kg/kWh = 180 kg; 100 L × 2.68 kg/L = 268 kg → 448 kg total.
    activities = [
        _act(),
        _act(activity_id="ACT-B", category="mobile_combustion", substance="diesel",
             quantity=100.0, unit="L"),
    ]
    result = calculate_scope1(activities, registry)
    assert result.scope == 1
    assert len(result) == 2
    assert result.total_kg == pytest.approx(448.0)
    assert result.total_t == pytest.approx(0.448)
    assert result.by_category() == {
        "stationary_combustion": pytest.approx(180.0),
        "mobile_combustion": pytest.approx(268.0),
    }
    assert result.by_gas() == {"CO2": pytest.approx(448.0)}


@pytest.mark.unit
def test_scope1_rejects_other_scopes(registry):
    with pytest.raises(BoundaryError):
        calculate_scope1([_act(scope=2, category="purchased_electricity",
                               substance="grid_electricity", gas="CO2e")], registry)


@pytest.mark.unit
def test_scope1_rejects_unknown_category(registry):
    with pytest.raises(BoundaryError):
        calculate_scope1([_act(category="purchased_electricity")], registry)


@pytest.mark.unit
def test_scope1_categories_match_ghg_protocol():
    assert set(SCOPE1_CATEGORIES) == {
        "stationary_combustion", "mobile_combustion",
        "fugitive_emissions", "process_emissions",
    }


# --------------------------------------------------------------------------- #
# Scope 2
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_scope2_location_based(registry):
    activity = _act(scope=2, category="purchased_electricity",
                    substance="grid_electricity", gas="CO2e",
                    quantity=1000.0, unit="kWh")
    result = calculate_scope2([activity], registry)
    # 1000 kWh × 0.45 kg CO2e/kWh (GLOBAL 2024) = 450 kg.
    assert result.location.total_kg == pytest.approx(450.0)
    assert result.location.total_t == pytest.approx(0.45)
    assert result.market is None  # no contract factors supplied


@pytest.mark.unit
def test_scope2_market_based_requires_explicit_factors(registry):
    activity = _act(scope=2, category="purchased_electricity",
                    substance="grid_electricity", gas="CO2e",
                    quantity=1000.0, unit="kWh")
    market_factor = EmissionFactor(
        factor_id="EF-MKT-001",
        activity_category="purchased_electricity",
        substance="grid_electricity",
        value=0.80,
        unit="kg CO2e/kWh",
        gas="CO2e",
        reporting_year=2024,
        source_org="SYNTHETIC",
        source_reference="unit test contract factor",
        notes="Synthetic supplier contract factor for testing.",
    )
    result = calculate_scope2(
        [activity], registry, market_factors={activity.activity_id: market_factor}
    )
    # 1000 kWh × 0.80 = 800 kg market-based; 450 kg location-based.
    assert result.location.total_kg == pytest.approx(450.0)
    assert result.market is not None
    assert result.market.total_kg == pytest.approx(800.0)


@pytest.mark.unit
def test_scope2_partial_market_coverage_fails(registry):
    activity = _act(scope=2, category="purchased_electricity",
                    substance="grid_electricity", gas="CO2e",
                    quantity=1000.0, unit="kWh")
    with pytest.raises(MissingFactorError):
        calculate_scope2([activity], registry, market_factors={})


@pytest.mark.unit
def test_scope2_rejects_wrong_category(registry):
    with pytest.raises(BoundaryError):
        calculate_scope2([_act(scope=2, category="stationary_combustion")], registry)


@pytest.mark.unit
def test_scope2_categories_match_ghg_protocol():
    assert set(SCOPE2_CATEGORIES) == {
        "purchased_electricity", "purchased_steam",
        "purchased_heat", "purchased_cooling",
    }


# --------------------------------------------------------------------------- #
# Scope 3
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_scope3_has_all_fifteen_categories():
    assert sorted(SCOPE3_CATEGORIES) == list(range(1, 16))
    # Spot-checks against the GHG Protocol Scope 3 Technical Guidance.
    assert SCOPE3_CATEGORIES[4].name == "Upstream transportation and distribution"
    assert SCOPE3_CATEGORIES[11].name == "Use of sold products"
    assert SCOPE3_CATEGORIES[12].name == "End-of-life treatment of sold products"
    assert SCOPE3_CATEGORIES[4].direction == "upstream"
    assert SCOPE3_CATEGORIES[9].direction == "downstream"
    for category in SCOPE3_CATEGORIES.values():
        assert category.typical_data


@pytest.mark.unit
def test_scope3_category_ids():
    assert scope3_category_id(1) == "s3_cat01"
    assert scope3_category_id(15) == "s3_cat15"
    with pytest.raises(BoundaryError):
        scope3_category_id(16)
    with pytest.raises(BoundaryError):
        scope3_category_id(0)


@pytest.mark.unit
def test_scope3_calculation(registry):
    activity = _act(scope=3, category="s3_cat01", substance="paper",
                    quantity=1000.0, unit="kg", gas="CO2e")
    result = calculate_scope3([activity], registry)
    # 1000 kg paper × 1.20 kg CO2e/kg = 1200 kg.
    assert result.total_kg == pytest.approx(1200.0)
    assert result.scope == 3


@pytest.mark.unit
def test_scope3_rejects_invalid_category(registry):
    with pytest.raises(BoundaryError):
        calculate_scope3([_act(scope=3, category="s3_cat16", gas="CO2e")], registry)
    with pytest.raises(BoundaryError):
        calculate_scope3([_act(scope=3, category="waste", gas="CO2e")], registry)


@pytest.mark.unit
def test_scope3_rejects_other_scopes(registry):
    with pytest.raises(BoundaryError):
        calculate_scope3([_act(scope=1)], registry)


@pytest.mark.unit
def test_scope_result_rejects_rows_from_another_scope(registry):
    from opencarbonchem.accounting import ScopeResult
    from opencarbonchem.core.exceptions import BoundaryError

    scope1 = calculate_scope1([_act()], registry)
    with pytest.raises(BoundaryError, match="being reported as Scope 2"):
        ScopeResult.from_results(2, scope1.results)


@pytest.mark.integration
def test_demo_dataset_uses_published_factors():
    """The shipped dataset must reconcile against the packaged published factor set."""
    from pathlib import Path

    from opencarbonchem.accounting import calculate_inventory
    from opencarbonchem.core.activity import load_activities_csv
    from opencarbonchem.factors import FactorRegistry

    csv_path = Path(__file__).resolve().parent.parent / "data" / "activities_synthetic.csv"
    registry = FactorRegistry.from_csv()
    report, rows = calculate_inventory(load_activities_csv(csv_path), registry)

    refrigerant = next(r for r in rows if r.activity_id == "ACT-003")
    # 7.5 kg R-134a released x DEFRA HFC-134a factor 1300 kg CO2e/kg
    assert refrigerant.co2e_kg == pytest.approx(9_750.0)
    assert report.by_scope()[1] == pytest.approx(4_550_678.6)
    assert report.by_scope()[2] == pytest.approx(423_082.5)
    assert report.by_scope()[3] == pytest.approx(72_909.8674, abs=0.01)
    assert report.total_kg == pytest.approx(5_046_670.9674, abs=0.01)
    assert report.reconcile().ok
