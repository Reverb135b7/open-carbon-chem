"""Organisation roll-up and reconciliation tests."""

from datetime import date

import pytest

from opencarbonchem.accounting import OrganizationReport, calculate_scope1
from opencarbonchem.accounting.base import ScopeResult
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.core.exceptions import BoundaryError
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


@pytest.fixture(scope="module")
def report(registry) -> OrganizationReport:
    s1 = calculate_scope1(
        [_act(activity_id="ACT-1")],
        registry,
    )
    from opencarbonchem.accounting import calculate_scope2, calculate_scope3

    s2 = calculate_scope2(
        [_act(activity_id="ACT-2", scope=2, category="purchased_electricity",
              substance="grid_electricity", gas="CO2e")],
        registry,
    ).location
    s3 = calculate_scope3(
        [_act(activity_id="ACT-3", scope=3, category="s3_cat01", substance="paper",
              quantity=1000.0, unit="kg", gas="CO2e")],
        registry,
    )
    return OrganizationReport.from_results([s1, s2, s3])


@pytest.mark.unit
def test_rollup_totals_hand_computed(report):
    # 180 kg (gas) + 450 kg (grid) + 1200 kg (paper) = 1830 kg.
    assert report.total_kg == pytest.approx(1830.0)
    assert report.total_t == pytest.approx(1.83)
    assert report.by_scope() == {
        1: pytest.approx(180.0),
        2: pytest.approx(450.0),
        3: pytest.approx(1200.0),
    }
    assert report.by_category() == {
        "stationary_combustion": pytest.approx(180.0),
        "purchased_electricity": pytest.approx(450.0),
        "s3_cat01": pytest.approx(1200.0),
    }
    assert report.by_gas() == {
        "CO2": pytest.approx(180.0),
        "CO2e": pytest.approx(1650.0),
    }


@pytest.mark.unit
def test_reconciliation_consistency_passes(report):
    reconciliation = report.reconcile()
    assert reconciliation.ok  # every aggregate re-derives from the rows
    consistency = [c for c in reconciliation.checks if c.kind == "consistency"]
    assert {c.name for c in consistency} == {
        "scope_totals_match_report_total",
        "category_totals_match_report_total",
        "gas_totals_match_report_total",
    }
    assert all(c.ok for c in consistency)


@pytest.mark.unit
def test_reconciliation_coverage_flags_gaps(report):
    reconciliation = report.reconcile()
    gap_names = {c.name for c in reconciliation.coverage_gaps}
    # All three scopes are present, but Scope 1 subcategories beyond
    # stationary combustion and most Scope 2 categories have no rows.
    assert not any(name.startswith("scope_1_reported") for name in gap_names)
    assert "scope1_category_mobile_combustion_reported" in gap_names
    assert "scope2_category_purchased_steam_reported" in gap_names
    # Coverage gaps are advisory; they do not fail the reconciliation.
    assert reconciliation.ok


@pytest.mark.unit
def test_reconciliation_flags_missing_scopes(registry):
    s1 = calculate_scope1([_act()], registry)
    reconciliation = OrganizationReport.from_results([s1]).reconcile()
    gap_names = {c.name for c in reconciliation.coverage_gaps}
    assert "scope_2_reported" in gap_names
    assert "scope_3_reported" in gap_names


@pytest.mark.unit
def test_report_rejects_duplicate_scopes(registry):
    s1 = calculate_scope1([_act()], registry)
    with pytest.raises(BoundaryError):
        OrganizationReport.from_results([s1, s1])


@pytest.mark.unit
def test_report_rejects_invalid_scope(registry):
    bogus = ScopeResult.from_results(4, ())
    with pytest.raises(BoundaryError):
        OrganizationReport.from_results([bogus])


@pytest.mark.unit
def test_empty_report_is_valid_baseline():
    report = OrganizationReport.from_results([])
    assert report.total_kg == 0.0
    assert report.by_scope() == {}
