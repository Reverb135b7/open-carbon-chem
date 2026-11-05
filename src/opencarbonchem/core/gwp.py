"""Global Warming Potential (GWP) conversion sets.

Values are transcribed from published IPCC assessment-report tables:

* ``AR6`` — IPCC AR6 WGI (2021), Table 7.15 / 7.SM.7. AR6 publishes a single
  set of GWPs that *includes* the climate-carbon response, and distinguishes
  fossil methane (29.8) from non-fossil methane (27.0). This is the default
  set and the one the GHG Protocol's current GWP table lists.
* ``AR6-ERRATA-2025`` — the values after the IPCC errata of 7 October 2025,
  which corrected a calculation error in the AR6 tables (CH4 fossil 28.1,
  CH4 non-fossil 25.3, N2O 267, …).
* ``AR5`` — IPCC AR5 WGI (2013), Table 8.7, *without* climate-carbon
  feedbacks (CH4 28, N2O 265): the variant still required by legacy
  frameworks such as UNFCCC inventory reporting and the US EPA GHGRP.

The engine never guesses a methane basis: a CH4 lookup raises
:class:`~opencarbonchem.core.exceptions.MissingGWPError` unless the caller
states ``methane_basis="fossil"`` or ``"non_fossil"`` and the selected set
actually distinguishes the two origins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .exceptions import GWPError, MissingGWPError

__all__ = [
    "AR5",
    "AR6",
    "AR6_ERRATA_2025",
    "DEFAULT_GWP_SET",
    "GWPSet",
    "get_gwp_set",
    "gwp",
    "gwp_sets",
    "to_co2e",
]

#: The set used unless the caller names another one explicitly.
DEFAULT_GWP_SET = "AR6"

#: Accepted spellings for the methane origin.
_METHANE_BASES = ("fossil", "non_fossil")


def _norm_gas(gas: str) -> str:
    """Normalise a gas label: ``'ch4'``, ``'CH₄'``-free input, ``'HFC-134a'``…"""
    return "".join(ch for ch in str(gas).strip().upper() if ch.isalnum())


def _norm_basis(basis: str) -> str:
    return str(basis).strip().lower().replace("-", "_").replace(" ", "_")


@dataclass(frozen=True)
class GWPSet:
    """A named, sourced collection of GWP values.

    ``values`` maps ``(normalised_gas, methane_basis)`` to the dimensionless
    GWP. The methane basis key is ``""`` for gases whose value does not depend
    on origin (and for origin-independent sets such as AR5).
    """

    name: str
    source: str
    reference: str
    values: Mapping[tuple[str, str], float]

    def get(self, gas: str, *, methane_basis: str | None = None) -> float:
        """Return the GWP for ``gas`` or raise :class:`MissingGWPError`."""
        key = _norm_gas(gas)
        if not key:
            raise MissingGWPError("Empty gas label; cannot look up a GWP.")
        candidates: list[tuple[str, str]] = []
        if key == "CH4" and methane_basis is not None:
            basis = _norm_basis(methane_basis)
            if basis not in _METHANE_BASES:
                raise GWPError(
                    f"Unknown methane_basis {methane_basis!r}; "
                    f"expected one of {_METHANE_BASES}."
                )
            candidates.append((key, basis))
        candidates.append((key, ""))
        for candidate in candidates:
            try:
                return self.values[candidate]
            except KeyError:
                continue
        if key == "CH4" and methane_basis is None:
            raise MissingGWPError(
                f"GWP set {self.name!r} distinguishes fossil from non-fossil "
                "methane; pass methane_basis='fossil' or 'non_fossil' "
                "(origin must never be assumed)."
            )
        raise MissingGWPError(f"GWP set {self.name!r} has no value for gas {gas!r}.")


# ---------------------------------------------------------------------------- #
# IPCC AR6 WGI (2021) — Table 7.15 / 7.SM.7, values include carbon-cycle
# response. Source: IPCC AR6 WGI Chapter 7 + Supplementary Material.
# ---------------------------------------------------------------------------- #
AR6 = GWPSet(
    name="AR6",
    source="IPCC AR6 WGI (2021)",
    reference="Table 7.15 / 7.SM.7 (all values include carbon-cycle responses)",
    values={
        ("CO2", ""): 1.0,
        ("CH4", "fossil"): 29.8,
        ("CH4", "non_fossil"): 27.0,
        ("N2O", ""): 273.0,
        ("HFC134A", ""): 1530.0,
        ("HFC32", ""): 771.0,
        ("HFC125", ""): 3740.0,
        ("HFC23", ""): 14600.0,
        ("SF6", ""): 24300.0,
        ("NF3", ""): 17400.0,
        ("CF4", ""): 7380.0,
        ("C2F6", ""): 12400.0,
    },
)

# ---------------------------------------------------------------------------- #
# IPCC errata, 7 October 2025 — correction of the AR6 tables after a
# calculation error (radiative efficiency of CO2 revised 1.33e-5 → 1.39e-5).
# Gases the errata do not revise are omitted deliberately; the engine then
# raises MissingGWPError rather than silently mixing vintages.
# ---------------------------------------------------------------------------- #
AR6_ERRATA_2025 = GWPSet(
    name="AR6-ERRATA-2025",
    source="IPCC AR6 WGI Errata (7 October 2025)",
    reference="AR6 WGI Errata p.3 (Table 7.15) and pp.5-14 (Table 7.SM.7)",
    values={
        ("CO2", ""): 1.0,
        ("CH4", "fossil"): 28.1,
        ("CH4", "non_fossil"): 25.3,
        ("N2O", ""): 267.0,
        ("HFC134A", ""): 1470.0,
        ("HFC32", ""): 743.0,
        ("SF6", ""): 23500.0,
        ("NF3", ""): 16800.0,
        ("CF4", ""): 7110.0,
        ("C2F6", ""): 11100.0,
    },
)

# ---------------------------------------------------------------------------- #
# IPCC AR5 WGI (2013) — Table 8.7 without climate-carbon feedbacks.
# AR5 does not split methane by origin: CH4 = 28 for any basis.
# ---------------------------------------------------------------------------- #
AR5 = GWPSet(
    name="AR5",
    source="IPCC AR5 WGI (2013)",
    reference="Table 8.7, GWP-100 without climate-carbon feedbacks",
    values={
        ("CO2", ""): 1.0,
        ("CH4", ""): 28.0,
        ("N2O", ""): 265.0,
        ("HFC134A", ""): 1300.0,
        ("HFC32", ""): 677.0,
        ("HFC125", ""): 3170.0,
        ("HFC23", ""): 12400.0,
        ("SF6", ""): 22800.0,
        ("NF3", ""): 16100.0,
        ("CF4", ""): 6630.0,
        ("C2F6", ""): 11100.0,
    },
)

_GWP_SETS: dict[str, GWPSet] = {
    "AR6": AR6,
    "AR6-ERRATA-2025": AR6_ERRATA_2025,
    "AR5": AR5,
}


def gwp_sets() -> Mapping[str, GWPSet]:
    """The available GWP sets, keyed by name."""
    return dict(_GWP_SETS)


def get_gwp_set(name: str = DEFAULT_GWP_SET) -> GWPSet:
    """Resolve a GWP set by name; unknown names raise :class:`GWPError`."""
    try:
        return _GWP_SETS[name]
    except KeyError:
        raise GWPError(
            f"Unknown GWP set {name!r}; available: {', '.join(sorted(_GWP_SETS))}."
        ) from None


def gwp(gas: str, *, gwp_set: str = DEFAULT_GWP_SET, methane_basis: str | None = None) -> float:
    """GWP of ``gas`` under ``gwp_set`` (dimensionless, kg CO2e per kg gas)."""
    return get_gwp_set(gwp_set).get(gas, methane_basis=methane_basis)


def to_co2e(
    mass: float,
    gas: str,
    *,
    gwp_set: str = DEFAULT_GWP_SET,
    methane_basis: str | None = None,
) -> float:
    """Convert a mass of ``gas`` (same mass unit in, kg CO2e out)."""
    return float(mass) * gwp(gas, gwp_set=gwp_set, methane_basis=methane_basis)
