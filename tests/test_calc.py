"""Core calculation tests: E = AD × EF and CO2e assembly.

Expected values are computed by hand from the inputs, independently of the
implementation.
"""

from datetime import date

import pytest

from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.core.calc import compute_emissions
from opencarbonchem.core.exceptions import FactorScopeError, IncompatibleUnitError
from opencarbonchem.factors.models import EmissionFactor


def _activity(**overrides) -> ActivityRecord:
    base = dict(
        activity_id="ACT-T1",
        scope=1,
        category="stationary_combustion",
        substance="natural_gas",
        quantity=1000.0,
        unit="kWh",
        gas="CO2",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
    )
    base.update(overrides)
    return ActivityRecord(**base)


def _factor(**overrides) -> EmissionFactor:
    base = dict(
        factor_id="EF-T1",
        activity_category="stationary_combustion",
        substance="natural_gas",
        value=0.5,
        unit="kg CO2/kWh",
        gas="CO2",
        reporting_year=2024,
        source_org="SYNTHETIC",
        source_reference="unit test",
    )
    base.update(overrides)
    return EmissionFactor(**base)


@pytest.mark.unit
def test_basic_emission_calculation():
    # 1000 kWh × 0.5 kg CO2/kWh = 500 kg CO2 = 500 kg CO2e (GWP 1).
    result = compute_emissions(_activity(), _factor())
    assert result.emissions_kg == pytest.approx(500.0)
    assert result.gwp == 1.0
    assert result.co2e_kg == pytest.approx(500.0)
    assert result.co2e_t == pytest.approx(0.5)


@pytest.mark.unit
def test_gas_specific_factor_applies_gwp():
    # 10 kg natural gas × 1.0 kg CH4/kg = 10 kg CH4; × GWP 29.8 = 298 kg CO2e.
    activity = _activity(quantity=10.0, unit="kg", gas="CH4")
    factor = _factor(
        factor_id="EF-T2",
        value=1.0,
        unit="kg CH4/kg",
        gas="CH4",
        methane_basis="fossil",
    )
    result = compute_emissions(activity, factor)
    assert result.emissions_kg == pytest.approx(10.0)
    assert result.gwp == pytest.approx(29.8)
    assert result.co2e_kg == pytest.approx(298.0)


@pytest.mark.unit
def test_ch4_without_basis_fails():
    activity = _activity(quantity=10.0, unit="kg", gas="CH4")
    factor = _factor(factor_id="EF-T3", value=1.0, unit="kg CH4/kg", gas="CH4")
    from opencarbonchem.core.exceptions import MissingGWPError

    with pytest.raises(MissingGWPError):
        compute_emissions(activity, factor)


@pytest.mark.unit
def test_combined_factor_skips_gwp():
    # A CO2e factor is already combined: no GWP applied, and that is visible.
    factor = _factor(factor_id="EF-T4", value=0.45, unit="kg CO2e/kWh", gas="CO2e")
    result = compute_emissions(_activity(gas="CO2e"), factor)
    assert result.gwp is None
    assert result.gwp_set is None
    assert result.co2e_kg == pytest.approx(450.0)


@pytest.mark.unit
def test_dimensional_closure_enforced():
    # Length activity × mass-per-energy factor cannot produce a mass.
    activity = _activity(quantity=100.0, unit="m")
    with pytest.raises(IncompatibleUnitError) as exc:
        compute_emissions(activity, _factor())
    assert "not mass" in str(exc.value)


@pytest.mark.unit
def test_factor_category_mismatch_rejected():
    with pytest.raises(FactorScopeError):
        compute_emissions(_activity(), _factor(activity_category="mobile_combustion"))


@pytest.mark.unit
def test_factor_substance_mismatch_rejected():
    with pytest.raises(FactorScopeError):
        compute_emissions(_activity(), _factor(substance="diesel"))


@pytest.mark.unit
def test_result_carries_full_audit_trail():
    result = compute_emissions(_activity(), _factor())
    assert result.activity_id == "ACT-T1"
    assert result.factor_id == "EF-T1"
    assert result.activity_value == 1000.0
    assert result.activity_unit == "kWh"
    assert result.factor_value == 0.5
    assert result.factor_unit == "kg CO2/kWh"
    assert result.gwp_set == "AR6"
    assert result.scope == 1


@pytest.mark.unit
def test_selected_gwp_set_is_recorded():
    result = compute_emissions(_activity(), _factor(), gwp_set="AR5")
    assert result.gwp_set == "AR5"
