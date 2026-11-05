"""One-at-a-time sensitivity analysis (tornado analysis).

Each parameter perturbs exactly one input — an activity quantity (yield, fuel
use, transport distance, packaging mass) or an emission factor (grid intensity,
material sourcing) — by ±``delta_pct`` and recomputes the **whole** inventory
through :func:`compute_emissions`. Nothing is approximated: the reported swing is
the difference between two real engine runs.

The result is ordered by absolute swing so it can be plotted directly as a
tornado diagram.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from ..core.exceptions import AnalyticsError
from ..core.gwp import DEFAULT_GWP_SET
from ..factors.models import EmissionFactor
from .common import InventoryEntry, base_rows, validate_entries

__all__ = [
    "SensitivityParameter",
    "SensitivityRow",
    "SensitivityResult",
    "analyse_sensitivity",
    "build_parameters",
    "PerturbableField",
]

PerturbableField = Literal["quantity", "factor_value"]
_FIELDS: tuple[str, ...] = ("quantity", "factor_value")


@dataclass(frozen=True)
class SensitivityParameter:
    """Perturb one field of one inventory entry by ±``delta_pct`` percent."""

    name: str
    activity_id: str
    field: PerturbableField = "factor_value"
    delta_pct: float = 10.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise AnalyticsError("Sensitivity parameter name must not be blank.")
        if not self.activity_id.strip():
            raise AnalyticsError(f"{self.name}: activity_id must not be blank.")
        if self.field not in _FIELDS:
            raise AnalyticsError(
                f"{self.name}: field must be one of {', '.join(_FIELDS)}; got {self.field!r}."
            )
        if not 0 < self.delta_pct <= 100:
            raise AnalyticsError(
                f"{self.name}: delta_pct must be in (0, 100]; got {self.delta_pct!r}."
            )
        if self.field == "quantity" and self.delta_pct >= 100:
            raise AnalyticsError(
                f"{self.name}: a quantity cannot be reduced by 100 % (negative activity data)."
            )


@dataclass(frozen=True)
class SensitivityRow:
    """Low/high outcomes for one perturbed input."""

    name: str
    activity_id: str
    field: str
    delta_pct: float
    base_kg: float
    low_kg: float
    high_kg: float

    @property
    def swing_kg(self) -> float:
        return abs(self.high_kg - self.low_kg)

    @property
    def low_delta_pct(self) -> float | None:
        if self.base_kg == 0:
            return None
        return (self.low_kg - self.base_kg) / self.base_kg * 100.0

    @property
    def high_delta_pct(self) -> float | None:
        if self.base_kg == 0:
            return None
        return (self.high_kg - self.base_kg) / self.base_kg * 100.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "activity_id": self.activity_id,
            "field": self.field,
            "delta_pct": self.delta_pct,
            "base_kg": self.base_kg,
            "low_kg": self.low_kg,
            "high_kg": self.high_kg,
            "swing_kg": self.swing_kg,
            "low_delta_pct": self.low_delta_pct,
            "high_delta_pct": self.high_delta_pct,
        }


@dataclass(frozen=True)
class SensitivityResult:
    """Base total plus one row per parameter, ordered by swing (largest first)."""

    base_kg: float
    gwp_set: str
    rows: tuple[SensitivityRow, ...] = ()

    def to_rows(self) -> list[dict]:
        return [row.to_dict() for row in self.rows]

    @property
    def most_influential(self) -> SensitivityRow | None:
        return self.rows[0] if self.rows else None


def _perturb(
    entry: InventoryEntry, field: str, multiplier: float
) -> InventoryEntry:
    activity, factor = entry
    if field == "quantity":
        updated = activity.model_copy(update={"quantity": activity.quantity * multiplier})
        return updated, factor
    if multiplier <= 0:
        raise AnalyticsError(
            f"Cannot scale factor {factor.factor_id} to {multiplier:.4g}: factors must stay positive."
        )
    updated_factor: EmissionFactor = factor.model_copy(update={"value": factor.value * multiplier})
    return activity, updated_factor


def analyse_sensitivity(
    entries: Iterable[InventoryEntry],
    parameters: Iterable[SensitivityParameter],
    *,
    gwp_set: str = DEFAULT_GWP_SET,
) -> SensitivityResult:
    """Run a one-at-a-time sensitivity analysis over ``entries``."""
    materialised = validate_entries(entries)
    params = tuple(parameters)
    if not params:
        raise AnalyticsError("At least one sensitivity parameter is required.")

    by_id = {activity.activity_id: (activity, factor) for activity, factor in materialised}
    names: set[str] = set()
    for param in params:
        if param.activity_id not in by_id:
            raise AnalyticsError(
                f"{param.name}: activity {param.activity_id!r} is not in the inventory "
                f"(known IDs: {', '.join(sorted(by_id))})."
            )
        if param.name in names:
            raise AnalyticsError(f"Duplicate sensitivity parameter name {param.name!r}.")
        names.add(param.name)

    base_total = sum(row.co2e_kg for row in base_rows(materialised, gwp_set))
    rows: list[SensitivityRow] = []

    for param in params:
        step = param.delta_pct / 100.0
        outcomes: list[float] = []
        for multiplier in (1.0 - step, 1.0 + step):
            perturbed = [
                _perturb(entry, param.field, multiplier)
                if entry[0].activity_id == param.activity_id
                else entry
                for entry in materialised
            ]
            outcomes.append(sum(row.co2e_kg for row in base_rows(tuple(perturbed), gwp_set)))
        rows.append(
            SensitivityRow(
                name=param.name,
                activity_id=param.activity_id,
                field=param.field,
                delta_pct=param.delta_pct,
                base_kg=base_total,
                low_kg=outcomes[0],
                high_kg=outcomes[1],
            )
        )

    rows.sort(key=lambda row: (-row.swing_kg, row.name))
    return SensitivityResult(base_kg=base_total, gwp_set=gwp_set, rows=tuple(rows))


def build_parameters(
    entries: Iterable[InventoryEntry],
    *,
    fields: Iterable[PerturbableField] = ("quantity",),
    delta_pct: float = 10.0,
    prefix: str = "",
) -> list[SensitivityParameter]:
    """Convenience: one parameter per entry (and field) with readable names."""
    wanted = tuple(fields)
    for field in wanted:
        if field not in _FIELDS:
            raise AnalyticsError(f"Unknown perturbable field {field!r}.")
    return [
        SensitivityParameter(
            name=f"{prefix}{activity.activity_id} · {field}",
            activity_id=activity.activity_id,
            field=field,
            delta_pct=delta_pct,
        )
        for activity, _factor in validate_entries(entries)
        for field in wanted
    ]
