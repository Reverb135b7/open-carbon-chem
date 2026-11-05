"""GWP set tests: published values, methane-basis enforcement, errors."""

import pytest

from opencarbonchem.core.exceptions import GWPError, MissingGWPError
from opencarbonchem.core.gwp import get_gwp_set, gwp, to_co2e


@pytest.mark.unit
def test_ar6_reference_values():
    # IPCC AR6 WGI Table 7.15 / 7.SM.7 (values include carbon-cycle response).
    assert gwp("CO2") == 1.0
    assert gwp("N2O") == 273.0
    assert gwp("HFC-134a") == 1530.0
    assert gwp("SF6") == 24300.0
    assert gwp("NF3") == 17400.0
    assert gwp("CF4") == 7380.0


@pytest.mark.unit
def test_ar6_methane_is_split_by_origin():
    assert gwp("CH4", methane_basis="fossil") == 29.8
    assert gwp("CH4", methane_basis="non_fossil") == 27.0


@pytest.mark.unit
def test_ch4_basis_is_never_assumed():
    with pytest.raises(MissingGWPError) as exc:
        gwp("CH4")
    assert "methane_basis" in str(exc.value)


@pytest.mark.unit
def test_unknown_methane_basis_rejected():
    with pytest.raises(GWPError):
        gwp("CH4", methane_basis="biogenic")


@pytest.mark.unit
def test_ar5_has_single_methane_value():
    # AR5 Table 8.7 (without feedbacks): CH4 = 28, origin-independent.
    assert gwp("CH4", gwp_set="AR5") == 28.0
    assert gwp("CH4", gwp_set="AR5", methane_basis="fossil") == 28.0
    assert gwp("N2O", gwp_set="AR5") == 265.0


@pytest.mark.unit
def test_ar6_errata_2025_values():
    # IPCC errata of 7 October 2025.
    assert gwp("CH4", gwp_set="AR6-ERRATA-2025", methane_basis="fossil") == 28.1
    assert gwp("CH4", gwp_set="AR6-ERRATA-2025", methane_basis="non_fossil") == 25.3
    assert gwp("N2O", gwp_set="AR6-ERRATA-2025") == 267.0
    assert gwp("SF6", gwp_set="AR6-ERRATA-2025") == 23500.0


@pytest.mark.unit
def test_gas_label_normalisation():
    assert gwp("ch4", methane_basis="FOSSIL") == 29.8
    assert gwp("hfc134a") == 1530.0
    assert gwp("co2") == 1.0


@pytest.mark.unit
def test_unknown_gas_and_set_fail_safely():
    with pytest.raises(MissingGWPError):
        gwp("XYZ-999")
    with pytest.raises(GWPError) as exc:
        gwp("CO2", gwp_set="AR4")
    assert "AR6" in str(exc.value)  # message lists available sets


@pytest.mark.unit
def test_to_co2e_applies_gwp():
    # 10 kg fossil CH4 × 29.8 = 298 kg CO2e (AR6).
    assert to_co2e(10, "CH4", methane_basis="fossil") == pytest.approx(298.0)
    # 4 kg N2O × 273 = 1092 kg CO2e (AR6).
    assert to_co2e(4, "N2O") == pytest.approx(1092.0)


@pytest.mark.unit
def test_gwp_sets_carry_provenance():
    ar6 = get_gwp_set("AR6")
    assert "IPCC AR6" in ar6.source
    assert ar6.reference
    ar5 = get_gwp_set("AR5")
    assert "AR5" in ar5.source
