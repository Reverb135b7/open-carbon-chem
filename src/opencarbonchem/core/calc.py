"""Fundamental emission calculation: E = Activity Data × Emission Factor.

The engine is UI-free and dimensionally strict:

1. The activity quantity and the factor unit must multiply out to a mass.
   If they do not, :class:`IncompatibleUnitError` is raised — an incompatible
   conversion is never applied silently.
2. The factor must describe the same category and substance as the activity
   (:class:`FactorScopeError`), so a natural-gas factor can never be applied
   to a diesel record.
3. Gas-specific emissions are converted to CO2e with the GWP set named on the
   result row, so every reported number is reproducible from its audit fields.

A factor whose gas is ``CO2e`` is already a combined factor; no GWP is applied
(and ``gwp`` is recorded as ``None`` to make that visible).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..factors.models import EmissionFactor
from .activity import ActivityRecord
from .exceptions import FactorScopeError, IncompatibleUnitError
from .gwp import DEFAULT_GWP_SET, gwp
from .units import Dimension, Quantity, default_registry

__all__ = ["EmissionResult", "compute_emissions"]

_MASS = Dimension({"M": 1})


def _key(text: str) -> str:
    """Normalise identifiers for comparison: lower-case, no separators."""
    return "".join(ch for ch in text.strip().lower() if ch.isalnum())


@dataclass(frozen=True)
class EmissionResult:
    """One auditable emission contribution.

    Every field needed to re-derive the number is on the row: activity value
    and unit, factor value and unit, factor ID, gas, GWP and GWP set.
    """

    activity_id: str
    factor_id: str
    scope: int
    category: str
    substance: str
    gas: str
    activity_value: float
    activity_unit: str
    factor_value: float
    factor_unit: str
    emissions_kg: float  # mass of `gas` (or of CO2e when gas == "CO2e")
    gwp: float | None    # None when the factor is already combined CO2e
    gwp_set: str | None
    co2e_kg: float

    @property
    def co2e_t(self) -> float:
        """The contribution in tonnes CO2e."""
        return self.co2e_kg / 1000.0


def compute_emissions(
    activity: ActivityRecord,
    factor: EmissionFactor,
    *,
    gwp_set: str = DEFAULT_GWP_SET,
) -> EmissionResult:
    """Apply ``factor`` to ``activity`` and return the CO2e contribution."""
    # 1. The factor must belong to this activity.
    if _key(factor.activity_category) != _key(activity.category):
        raise FactorScopeError(
            f"Factor {factor.factor_id} covers category "
            f"{factor.activity_category!r}, not {activity.category!r} "
            f"(activity {activity.activity_id})."
        )
    if _key(factor.substance) != _key(activity.substance):
        raise FactorScopeError(
            f"Factor {factor.factor_id} covers substance {factor.substance!r}, "
            f"not {activity.substance!r} (activity {activity.activity_id})."
        )

    # 2. Dimensional closure: quantity × factor must be a mass.
    registry = default_registry()
    quantity = Quantity(float(activity.quantity), registry.parse(activity.unit))
    factor_unit = registry.parse(factor.unit)
    total = quantity.dimension * factor_unit.dimension
    if total != _MASS:
        raise IncompatibleUnitError(
            f"Activity {activity.activity_id}: {activity.quantity:g} "
            f"{activity.unit} (dimension {quantity.dimension}) × factor "
            f"{factor.factor_id} {factor.value:g} {factor.unit} "
            f"(dimension {factor_unit.dimension}) gives {total}, not mass. "
            "A registered conversion factor is required before these units can "
            "be combined."
        )

    # 3. E = AD × EF, computed in coherent base units (kg of gas).
    emissions_kg = quantity.base_value * (factor.value * factor_unit.scale)

    # 4. Gas-specific → CO2e.
    if _key(factor.gas) == "co2e":
        applied_gwp: float | None = None
        applied_set: str | None = None
        co2e_kg = emissions_kg
    else:
        basis = factor.methane_basis or activity.methane_basis
        applied_gwp = gwp(factor.gas, gwp_set=gwp_set, methane_basis=basis)
        applied_set = gwp_set
        co2e_kg = emissions_kg * applied_gwp

    return EmissionResult(
        activity_id=activity.activity_id,
        factor_id=factor.factor_id,
        scope=activity.scope,
        category=activity.category,
        substance=activity.substance,
        gas=factor.gas,
        activity_value=float(activity.quantity),
        activity_unit=activity.unit,
        factor_value=factor.value,
        factor_unit=factor.unit,
        emissions_kg=emissions_kg,
        gwp=applied_gwp,
        gwp_set=applied_set,
        co2e_kg=co2e_kg,
    )
