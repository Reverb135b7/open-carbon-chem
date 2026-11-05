"""Reporting-year comparison tests: deltas, statuses, no fabricated numbers."""

from datetime import date

import pytest

from opencarbonchem.accounting import (
    OrganizationReport,
    compare_line,
    compare_periods,
)
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.factors.registry import FactorRegistry

PERIOD = dict(period_start=date(2024, 1, 1), period_end=date(2024, 12, 31))


@pytest.fixture(scope="module")
def registry() -> FactorRegistry:
    return FactorRegistry.from_csv()


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


def _s1(registry, quantity: float):
    from opencarbonchem.accounting import calculate_scope1

    return calculate_scope1([_act(quantity=quantity)], registry)


@pytest.fixture(scope="module")
def years(registry):
    from opencarbonchem.accounting import calculate_scope2, calculate_scope3

    # Current year: Scope 1 (180 kg) + Scope 2 (450 kg).
    current = OrganizationReport.from_results(
        [
            _s1(registry, 1000.0),
            calculate_scope2(
                [_act(activity_id="ACT-2", scope=2, category="purchased_electricity",
                      substance="grid_electricity", gas="CO2e")],
                registry,
            ).location,
        ]
    )
    # Prior year: Scope 1 at half the gas use (90 kg) + Scope 3 (1200 kg).
    prior = OrganizationReport.from_results(
        [
            _s1(registry, 500.0),
            calculate_scope3(
                [_act(activity_id="ACT-3", scope=3, category="s3_cat01",
                      substance="paper", quantity=1000.0, unit="kg", gas="CO2e")],
                registry,
            ),
        ]
    )
    return current, prior


@pytest.mark.unit
def test_total_comparison_hand_computed(years):
    current, prior = years
    comparison = compare_periods(current, prior, current_label="2024", prior_label="2023")
    # 630 kg vs 1290 kg -> delta -660 kg, -660/1290 x 100 %.
    assert comparison.total.current_kg == pytest.approx(630.0)
    assert comparison.total.prior_kg == pytest.approx(1290.0)
    assert comparison.total.delta_kg == pytest.approx(-660.0)
    assert comparison.total.delta_pct == pytest.approx((-660.0 / 1290.0) * 100.0)
    assert comparison.total.status == "compared"
    assert comparison.current_label == "2024"
    assert comparison.prior_label == "2023"


@pytest.mark.unit
def test_scope_level_comparison(years):
    current, prior = years
    comparison = compare_periods(current, prior)
    scope1 = comparison.by_scope[1]
    assert scope1.current_kg == pytest.approx(180.0)
    assert scope1.prior_kg == pytest.approx(90.0)
    assert scope1.delta_kg == pytest.approx(90.0)
    assert scope1.delta_pct == pytest.approx(100.0)
    assert scope1.status == "compared"


@pytest.mark.unit
def test_new_scope_flags_instead_of_zero_prior(years):
    current, prior = years
    comparison = compare_periods(current, prior)
    scope2 = comparison.by_scope[2]  # only reported in current year
    assert scope2.prior_kg is None
    assert scope2.delta_kg is None
    assert scope2.delta_pct is None
    assert scope2.status == "new_in_current_year"


@pytest.mark.unit
def test_missing_scope_flags_instead_of_100pct_drop(years):
    current, prior = years
    comparison = compare_periods(current, prior)
    scope3 = comparison.by_scope[3]  # only reported in prior year
    assert scope3.current_kg is None
    assert scope3.delta_kg is None
    assert scope3.delta_pct is None
    assert scope3.status == "missing_in_current_year"


@pytest.mark.unit
def test_category_level_union(years):
    current, prior = years
    comparison = compare_periods(current, prior)
    assert comparison.by_category["stationary_combustion"].status == "compared"
    assert comparison.by_category["purchased_electricity"].status == "new_in_current_year"
    assert comparison.by_category["s3_cat01"].status == "missing_in_current_year"


@pytest.mark.unit
def test_zero_prior_year_has_no_percentage(years):
    current, _ = years
    baseline = OrganizationReport.from_results([])  # first reporting year
    comparison = compare_periods(current, baseline)
    assert comparison.total.prior_kg == 0.0
    assert comparison.total.delta_kg == pytest.approx(630.0)
    assert comparison.total.delta_pct is None  # undefined, not 0 % and not infinity
    assert comparison.total.status == "compared"


@pytest.mark.unit
def test_compare_line_direct():
    line = compare_line("x", 150.0, 100.0)
    assert line.delta_kg == pytest.approx(50.0)
    assert line.delta_pct == pytest.approx(50.0)
    assert line.status == "compared"
    # Neither side reported: no delta, flagged missing.
    neither = compare_line("y", None, None)
    assert neither.delta_kg is None and neither.delta_pct is None


@pytest.mark.unit
def test_mapping_input_and_line_ordering(years):
    current, prior = years
    comparison = compare_periods(
        {scope: result for scope, result in zip(current.by_scope(), current.scope_results)},
        prior,
    )
    assert comparison.by_scope[1].current_kg == pytest.approx(180.0)
    lines = comparison.all_lines()
    # Report-table order: total, then scopes ascending, then categories.
    assert lines[0].label == "total"
    assert [line.label for line in lines[1:4]] == ["Scope 1", "Scope 2", "Scope 3"]


@pytest.mark.unit
def test_to_dict_serialisable(years):
    current, prior = years
    payload = compare_periods(current, prior).to_dict()
    assert payload["current"] == "current"
    assert payload["total"]["status"] == "compared"
    assert set(payload["by_scope"]) == {"1", "2", "3"}
    assert "stationary_combustion" in payload["by_category"]
