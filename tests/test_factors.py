"""Emission-factor registry tests: provenance, precedence, fail-safe errors."""

from datetime import date

import pytest

from opencarbonchem.core.exceptions import AmbiguousFactorError, MissingFactorError
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.factors.models import EmissionFactor
from opencarbonchem.factors.registry import FactorRegistry, default_seed_path


@pytest.fixture(scope="module")
def registry() -> FactorRegistry:
    return FactorRegistry.from_csv()


def _factor(**overrides) -> EmissionFactor:
    base = dict(
        factor_id="EF-X1",
        activity_category="stationary_combustion",
        substance="natural_gas",
        value=0.18,
        unit="kg CO2/kWh",
        gas="CO2",
        reporting_year=2024,
        source_org="SYNTHETIC",
        source_reference="unit test",
    )
    base.update(overrides)
    return EmissionFactor(**base)


@pytest.mark.unit
def test_seed_csv_exists():
    assert default_seed_path().is_file()


@pytest.mark.unit
def test_seed_loads_all_rows(registry):
    assert len(registry) == 14


@pytest.mark.unit
def test_every_seed_factor_is_labelled_synthetic(registry):
    # Handover §6: never present illustrative values as official factors.
    for factor in registry:
        assert factor.review_status == "illustrative"
        assert factor.source_org == "SYNTHETIC"
        assert factor.source_reference
        assert factor.notes


@pytest.mark.unit
def test_provenance_fields_populated(registry):
    factor = registry.get("EF-ILL-001")
    assert factor.activity_category == "stationary_combustion"
    assert factor.substance == "natural_gas"
    assert factor.reporting_year == 2024
    assert factor.version
    assert factor.unit == "kg CO2/kWh"


@pytest.mark.unit
def test_year_precedence_picks_newest_at_or_before(registry):
    base = dict(activity_category="stationary_combustion", substance="natural_gas",
                gas="CO2", geography="GLOBAL")
    assert registry.find(year=2024, **base).factor_id == "EF-ILL-001"  # 0.18 (2024)
    assert registry.find(year=2025, **base).factor_id == "EF-ILL-001"  # newest ≤ 2025
    assert registry.find(year=2023, **base).factor_id == "EF-ILL-002"  # 0.20 (2023)
    # A reporting year earlier than every available vintage fails safely.
    with pytest.raises(MissingFactorError) as exc:
        registry.find(year=2022, **base)
    assert "earliest available vintage" in str(exc.value)


@pytest.mark.unit
def test_geography_precedence_exact_beats_global(registry):
    gb = registry.find(
        activity_category="purchased_electricity",
        substance="grid_electricity",
        geography="GB",
        year=2024,
    )
    assert gb.factor_id == "EF-ILL-007"  # 0.21 (GB)
    fr = registry.find(
        activity_category="purchased_electricity",
        substance="grid_electricity",
        geography="FR",
        year=2024,
    )
    assert fr.factor_id == "EF-ILL-005"  # 0.45 (GLOBAL fallback)


@pytest.mark.unit
def test_gas_selection_is_explicit(registry):
    ch4 = registry.find(
        activity_category="stationary_combustion",
        substance="natural_gas",
        gas="CH4",
        year=2024,
    )
    assert ch4.factor_id == "EF-ILL-003"
    assert ch4.methane_basis == "fossil"


@pytest.mark.unit
def test_missing_gas_is_ambiguous_not_guessed(registry):
    # natural_gas has CO2 and CH4 factors: without a gas the registry must not
    # silently choose one (it would silently drop emissions).
    with pytest.raises(AmbiguousFactorError) as exc:
        registry.find(
            activity_category="stationary_combustion",
            substance="natural_gas",
            year=2024,
        )
    assert "CH4" in str(exc.value) and "CO2" in str(exc.value)


@pytest.mark.unit
def test_unknown_substance_fails(registry):
    with pytest.raises(MissingFactorError):
        registry.find(
            activity_category="stationary_combustion",
            substance="coal",
            gas="CO2",
        )


@pytest.mark.unit
def test_duplicate_factor_id_rejected():
    registry = FactorRegistry([_factor()])
    with pytest.raises(AmbiguousFactorError):
        registry.add(_factor())


@pytest.mark.unit
def test_indistinguishable_factors_are_ambiguous():
    registry = FactorRegistry([
        _factor(factor_id="EF-X1"),
        _factor(factor_id="EF-X2"),  # same category/substance/geo/year/gas
    ])
    with pytest.raises(AmbiguousFactorError) as exc:
        registry.find(
            activity_category="stationary_combustion",
            substance="natural_gas",
            geography="GLOBAL",
            year=2024,
            gas="CO2",
        )
    assert "EF-X1" in str(exc.value) and "EF-X2" in str(exc.value)


@pytest.mark.unit
def test_get_by_id_and_missing(registry):
    assert registry.get("EF-ILL-005").value == 0.45
    with pytest.raises(MissingFactorError):
        registry.get("EF-NOPE")


@pytest.mark.unit
def test_activity_reporting_year_feeds_lookup(registry):
    activity = ActivityRecord(
        activity_id="ACT-Y",
        scope=1,
        category="stationary_combustion",
        substance="natural_gas",
        quantity=1.0,
        unit="kWh",
        gas="CO2",
        period_start=date(2023, 6, 1),
        period_end=date(2023, 12, 31),
    )
    assert activity.reporting_year == 2023
    factor = registry.find(
        activity_category=activity.category,
        substance=activity.substance,
        geography=activity.geography,
        year=activity.reporting_year,
        gas=activity.gas,
    )
    assert factor.factor_id == "EF-ILL-002"  # 2023 vintage
