"""Unit engine tests: conversions, dimensional safety, fail-safe errors."""

import pytest

from opencarbonchem.core.exceptions import (
    CurrencyError,
    IncompatibleUnitError,
    UnknownUnitError,
)
from opencarbonchem.core.units import default_registry, parse_unit, q


@pytest.mark.unit
def test_mass_conversion():
    assert q(2.5, "t").to("kg").value == pytest.approx(2500.0)


@pytest.mark.unit
def test_energy_conversion():
    # 1 kWh = 1000 W × 3600 s = 3.6e6 J by definition.
    assert q(1, "kWh").to("J").value == pytest.approx(3.6e6)


@pytest.mark.unit
def test_time_conversion():
    assert q(2, "h").to("min").value == pytest.approx(120.0)


@pytest.mark.unit
def test_length_conversion():
    assert q(1, "km").to("m").value == pytest.approx(1000.0)


@pytest.mark.unit
def test_compound_factor_units_share_dimension():
    # kg CO2/GJ and kg CO2e/kWh are both mass-per-energy.
    gj = parse_unit("kg CO2/GJ")
    kwh = parse_unit("kg CO2e/kWh")
    assert gj.dimension == kwh.dimension
    # 1 kg/GJ = 1 kg per 1e9 J → scale check against kg/kWh (1 kg per 3.6e6 J).
    assert gj.scale / kwh.scale == pytest.approx((3.6e6) / (1e9))


@pytest.mark.unit
def test_transport_units_are_mass_times_length():
    assert parse_unit("kg CO2e/tkm").dimension == parse_unit("kg").dimension / parse_unit(
        "tkm"
    ).dimension


@pytest.mark.unit
def test_incompatible_conversion_is_rejected():
    with pytest.raises(IncompatibleUnitError):
        q(1, "kg").to("L")


@pytest.mark.unit
def test_incompatible_arithmetic_is_rejected():
    with pytest.raises(IncompatibleUnitError):
        q(1, "kg") + q(1, "L")


@pytest.mark.unit
def test_unknown_unit_is_rejected():
    with pytest.raises(UnknownUnitError):
        q(1, "furlong")


@pytest.mark.unit
def test_ambiguous_ton_is_rejected():
    # 'ton' could be metric, short or long — the registry refuses to guess.
    with pytest.raises(UnknownUnitError) as exc:
        parse_unit("ton")
    assert "ambiguous" in str(exc.value)


@pytest.mark.unit
def test_quantity_arithmetic_preserves_dimension():
    total = q(1, "t") + q(500, "kg")
    assert total.value == pytest.approx(1500.0)
    assert total.unit.dimension == q(1, "kg").unit.dimension


@pytest.mark.unit
def test_quantity_multiplication_composes_dimensions():
    area = q(2, "m") * q(3, "m")
    assert area.unit.dimension == q(1, "m2").unit.dimension
    assert area.value == pytest.approx(6.0)


@pytest.mark.unit
def test_non_usd_currency_needs_explicit_rate():
    # There is no built-in exchange rate; EUR is unknown until configured.
    with pytest.raises(UnknownUnitError):
        q(1, "USD").to("EUR")

    registry = default_registry()
    registry.configure_exchange_rates({"EUR": 1.10})
    converted = q(1, "USD").to("EUR")
    assert converted.value == pytest.approx(1 / 1.10)


@pytest.mark.unit
def test_zero_and_negative_rates_rejected():
    with pytest.raises(CurrencyError):
        default_registry().configure_exchange_rates({"XYZ": 0})
