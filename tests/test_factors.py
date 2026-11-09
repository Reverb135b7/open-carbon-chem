"""Emission-factor registry tests: provenance, precedence, fail-safe errors."""

from datetime import date

import pytest

from opencarbonchem.core.exceptions import AmbiguousFactorError, MissingFactorError
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.factors.models import EmissionFactor
from opencarbonchem.factors.registry import FactorRegistry, illustrative_seed_path, default_seed_path


@pytest.fixture(scope="module")
def registry() -> FactorRegistry:
    return FactorRegistry.from_csv(illustrative_seed_path())


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


@pytest.mark.integration
def test_published_seed_is_the_default():
    registry = FactorRegistry.from_csv()
    assert len(registry) == 187
    assert {factor.reporting_year for factor in registry} == {2006, 2024, 2025}
    for factor in registry:
        assert factor.review_status == "published"
        assert factor.source_org in {"DESNZ", "IPCC"}
        assert factor.source_reference
        assert factor.version
        assert factor.notes


@pytest.mark.integration
def test_2025_vintage_supersedes_2024_for_2025_activity():
    registry = FactorRegistry.from_csv()
    find_2024 = registry.find(
        activity_category="purchased_electricity", substance="grid_electricity",
        geography="GB", year=2024, gas="CO2e",
    )
    find_2025 = registry.find(
        activity_category="purchased_electricity", substance="grid_electricity",
        geography="GB", year=2025, gas="CO2e",
    )
    assert find_2024.reporting_year == 2024
    assert find_2025.reporting_year == 2025
    assert find_2024.value == pytest.approx(0.20705)
    assert find_2025.value == pytest.approx(0.177)


@pytest.mark.integration
def test_air_freight_has_direct_and_radiative_forcing_variants():
    registry = FactorRegistry.from_csv()
    with_rf = registry.find(
        activity_category="s3_cat04", substance="air_freight_long_haul",
        geography="GB", year=2024, gas="CO2e",
    )
    without_rf = registry.find(
        activity_category="s3_cat04", substance="air_freight_long_haul_no_rf",
        geography="GB", year=2024, gas="CO2e",
    )
    assert with_rf.value == pytest.approx(1.09904)
    assert without_rf.value == pytest.approx(0.64875)
    assert without_rf.value < with_rf.value


@pytest.mark.integration
def test_every_published_factor_has_a_parseable_unit():
    from opencarbonchem.core.units import parse_unit

    for factor in FactorRegistry.from_csv():
        parse_unit(factor.unit)


@pytest.mark.integration
def test_published_seed_has_no_ambiguous_lookup_keys():
    registry = FactorRegistry.from_csv()
    keys = {}
    for factor in registry:
        key = (factor.activity_category, factor.substance, factor.geography,
               factor.reporting_year, factor.gas)
        keys.setdefault(key, []).append(factor.factor_id)
    duplicates = {key: ids for key, ids in keys.items() if len(ids) > 1}
    assert duplicates == {}

    for factor in registry:
        resolved = registry.find(
            activity_category=factor.activity_category,
            substance=factor.substance,
            geography=factor.geography,
            year=factor.reporting_year,
            gas=factor.gas,
        )
        assert resolved.factor_id == factor.factor_id


@pytest.mark.parametrize(
    "category, substance, quantity, unit, gas, scope, expected_kg",
    [
        ("stationary_combustion", "coal_industrial", 1000, "kg", "CO2e", 1, 2399.43994),
        ("fugitive_emissions", "r410a", 1, "kg", "CO2e", 1, 1924.0),
        ("process_emissions", "dolomite", 1000, "kg", "CO2", 1, 477.32),
        ("purchased_heat", "heat", 1000, "kWh", "CO2e", 2, 179.65),
        ("s3_cat03", "electricity_td", 1000, "kWh", "CO2e", 3, 18.3),
        ("s3_cat01", "water_supply", 100, "m3", "CO2e", 3, 15.311),
        ("s3_cat01", "paper_mixed", 1000, "kg", "CO2e", 3, 1282.74402),
        ("s3_cat04", "sea_container", 1000, "tkm", "CO2e", 3, 16.12),
        ("s3_cat05", "paper_waste_landfill", 1000, "kg", "CO2e", 3, 1164.39015),
        ("s3_cat06", "rail_national", 1000, "pkm", "CO2e", 3, 35.46),
    ],
)
@pytest.mark.integration
def test_published_factors_calculate_across_the_catalogue(
    category, substance, quantity, unit, gas, scope, expected_kg
):
    from opencarbonchem.core.calc import compute_emissions

    registry = FactorRegistry.from_csv()
    activity = ActivityRecord(
        activity_id="CAT-1", scope=scope, category=category, substance=substance,
        quantity=quantity, unit=unit, gas=gas,
    )
    factor = registry.find(
        activity_category=category, substance=substance, geography="GB", year=2024, gas=gas,
    )
    result = compute_emissions(activity, factor)
    assert result.co2e_kg == pytest.approx(expected_kg, rel=1e-9)


@pytest.mark.integration
def test_published_seed_uses_uk_geography_and_ipcc_fallback():
    registry = FactorRegistry.from_csv()
    grid = registry.find(
        activity_category="purchased_electricity",
        substance="grid_electricity",
        geography="GB",
        year=2024,
        gas="CO2e",
    )
    assert grid.value == pytest.approx(0.20705)
    assert grid.geography == "GB"

    # No UK-specific calcination factor: the GLOBAL IPCC default must be used.
    limestone = registry.find(
        activity_category="process_emissions",
        substance="limestone",
        geography="GB",
        year=2024,
        gas="CO2",
    )
    assert limestone.geography == "GLOBAL"
    assert limestone.value == pytest.approx(0.43971)


@pytest.mark.integration
def test_factor_spec_covers_every_published_desnz_row():
    """The committed spec must describe exactly the packaged DESNZ rows."""
    import json
    from pathlib import Path

    spec = json.loads(Path("tools/factor_spec.json").read_text(encoding="utf-8"))
    assert len(spec) == 91
    assert len({entry["nn"] for entry in spec}) == 91
    for entry in spec:
        assert set(entry["selector"]) == {"l1", "l2", "l3", "l4", "col", "uom", "ghg"}
        assert entry["selector"]["l1"]
        assert entry["divisor"] > 0

    registry = FactorRegistry.from_csv()
    published = {(f.substance, f.unit, f.gas) for f in registry
                 if f.source_org == "DESNZ" and f.reporting_year == 2024}
    assert published == {(e["substance"], e["unit"], e["gas"]) for e in spec}


@pytest.mark.integration
def test_published_csv_has_no_shifted_rows():
    """Every row must carry exactly the documented columns.

    An unquoted comma in a note silently shifts the trailing fields when the
    file is read with csv.DictReader, so guard the on-disk shape as well.
    """
    import csv

    with open(default_seed_path(), encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    header, body = rows[0], rows[1:]
    assert len(header) == 16
    assert all(len(row) == len(header) for row in body)


@pytest.mark.integration
def test_gwp_basis_note_flags_mixed_reports():
    from opencarbonchem.core.calc import compute_emissions, gwp_basis_note

    registry = FactorRegistry.from_csv()
    co2e_activity = ActivityRecord(
        activity_id="GWP-1", scope=1, category="fugitive_emissions",
        substance="r410a", quantity=1, unit="kg", gas="CO2e",
    )
    co2e_factor = registry.find(
        activity_category="fugitive_emissions", substance="r410a",
        geography="GB", year=2024, gas="CO2e",
    )
    published_result = compute_emissions(co2e_activity, co2e_factor)
    assert gwp_basis_note([published_result]) is None

    ch4_factor = EmissionFactor(
        factor_id="EF-TEST-CH4", activity_category="fugitive_emissions",
        substance="methane", value=0.001, unit="kg CH4/kg", gas="CH4",
        gases_covered=["CH4"], geography="GB", reporting_year=2024,
        source_org="SYNTHETIC", source_reference="unit test", version="test",
        review_status="illustrative", methane_basis="fossil",
    )
    ch4_activity = ActivityRecord(
        activity_id="GWP-2", scope=1, category="fugitive_emissions",
        substance="methane", quantity=1, unit="kg", gas="CH4",
    )
    converted_result = compute_emissions(ch4_activity, ch4_factor)
    note = gwp_basis_note([published_result, converted_result])
    assert note is not None
    assert "Mixed GWP basis" in note
    assert "AR5" in note
