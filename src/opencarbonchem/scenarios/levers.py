"""Decarbonisation levers.

Every lever is a pure function ``entries -> entries``: it transforms the
inventory (activity quantities and/or the applied emission factors) and the
scenario engine then recomputes totals through the normal calculation engine.
Levers therefore cannot drift from the accounting methodology.

A lever that matches **no** rows raises :class:`ScenarioError`. Silently
modelling nothing would let a user publish a "reduction" that was never applied.

Levers never invent emission factors: fuel switching and material substitution
require the replacement factor to be supplied with its own provenance record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, ClassVar, Iterable

from ..core.activity import ActivityRecord
from ..core.exceptions import ScenarioError
from ..core.inventory import InventoryEntry
from ..factors.models import EmissionFactor

__all__ = [
    "Lever",
    "RenewableElectricity",
    "EnergyEfficiency",
    "FuelSwitch",
    "MaterialSubstitution",
    "WasteReduction",
    "ProcessOptimisation",
    "TransportOptimisation",
    "LEVER_KINDS",
    "lever_from_kind",
]

_SCOPE2_ENERGY = ("purchased_electricity", "purchased_steam", "purchased_heat", "purchased_cooling")


def _key(text: str) -> str:
    return "".join(ch for ch in text.strip().lower() if ch.isalnum())


def _check_share(value: float, label: str) -> None:
    if not 0 <= value <= 1:
        raise ScenarioError(f"{label} must be between 0 and 1 (a fraction); got {value!r}.")


class Lever:
    """Base class for all levers."""

    kind: ClassVar[str] = "lever"

    @property
    def name(self) -> str:  # pragma: no cover - overridden
        return self.kind

    def apply(self, entries: Iterable[InventoryEntry]) -> tuple[InventoryEntry, ...]:
        raise NotImplementedError  # pragma: no cover

    # -- helpers ------------------------------------------------------------ #
    def _map_matching(
        self,
        entries: Iterable[InventoryEntry],
        predicate: Callable[[InventoryEntry], bool],
        transform: Callable[[InventoryEntry], InventoryEntry | None],
    ) -> tuple[InventoryEntry, ...]:
        """Apply ``transform`` to matching entries; ``None`` drops the entry."""
        result: list[InventoryEntry] = []
        matched = 0
        for entry in entries:
            if predicate(entry):
                matched += 1
                updated = transform(entry)
                if updated is not None:
                    result.append(updated)
            else:
                result.append(entry)
        if matched == 0:
            raise ScenarioError(
                f"{self.name}: no inventory rows matched, so the lever would have no "
                "effect. Check the category/substance it targets."
            )
        return tuple(result)

    @staticmethod
    def _scale(entry: InventoryEntry, multiplier: float, *, field: str) -> InventoryEntry:
        activity, factor = entry
        if field == "quantity":
            return activity.model_copy(update={"quantity": activity.quantity * multiplier}), factor
        value = factor.value * multiplier
        if value <= 0:
            # A zero-emission factor means the contribution disappears entirely.
            raise _ZeroFactor()
        return activity, factor.model_copy(update={"value": value})


class _ZeroFactor(Exception):
    """Internal signal: the transformed factor has zero emissions."""


@dataclass(frozen=True)
class RenewableElectricity(Lever):
    """Replace a share of purchased electricity with zero-carbon or low-carbon supply.

    ``residual_ef`` is the emission factor of the residual supply (kg CO2e/kWh).
    The default 0.0 assumes fully zero-carbon supply; supply a residual-mix
    factor for a conservative estimate.
    """

    share: float
    residual_ef: float = 0.0
    categories: tuple[str, ...] = ("purchased_electricity",)
    kind: ClassVar[str] = "renewable_electricity"

    def __post_init__(self) -> None:
        _check_share(self.share, "Renewable share")
        if self.share == 0:
            raise ScenarioError("Renewable share must be greater than 0.")
        if self.residual_ef < 0:
            raise ScenarioError("residual_ef cannot be negative.")

    @property
    def name(self) -> str:
        return f"Renewable electricity {self.share:.0%}"

    def apply(self, entries: Iterable[InventoryEntry]) -> tuple[InventoryEntry, ...]:
        wanted = {_key(c) for c in self.categories}

        def matches(entry: InventoryEntry) -> bool:
            return _key(entry[0].category) in wanted

        def transform(entry: InventoryEntry) -> InventoryEntry | None:
            activity, factor = entry
            blended = factor.value * (1 - self.share) + self.residual_ef * self.share
            if blended <= 0:
                return None  # fully zero-carbon: the contribution vanishes
            return activity, factor.model_copy(update={"value": blended})

        return self._map_matching(entries, matches, transform)


@dataclass(frozen=True)
class EnergyEfficiency(Lever):
    """Reduce energy consumption by ``improvement`` (fraction of current use)."""

    improvement: float
    categories: tuple[str, ...] = ("stationary_combustion",) + _SCOPE2_ENERGY
    kind: ClassVar[str] = "energy_efficiency"

    def __post_init__(self) -> None:
        _check_share(self.improvement, "Efficiency improvement")
        if self.improvement == 0:
            raise ScenarioError("Efficiency improvement must be greater than 0.")
        if self.improvement >= 1:
            raise ScenarioError("Efficiency improvement must be below 100 %.")

    @property
    def name(self) -> str:
        return f"Energy efficiency +{self.improvement:.0%}"

    def apply(self, entries: Iterable[InventoryEntry]) -> tuple[InventoryEntry, ...]:
        wanted = {_key(c) for c in self.categories}
        return self._map_matching(
            entries,
            lambda entry: _key(entry[0].category) in wanted,
            lambda entry: self._scale(entry, 1 - self.improvement, field="quantity"),
        )


@dataclass(frozen=True)
class FuelSwitch(Lever):
    """Replace one fuel with another, using a supplied replacement factor."""

    from_substance: str
    to_substance: str
    to_factor: EmissionFactor
    categories: tuple[str, ...] = ()
    kind: ClassVar[str] = "fuel_switch"

    def __post_init__(self) -> None:
        if _key(self.from_substance) == _key(self.to_substance):
            raise ScenarioError("Fuel switch source and target substances are identical.")
        if _key(self.to_factor.substance) != _key(self.to_substance):
            raise ScenarioError(
                f"Replacement factor {self.to_factor.factor_id} covers "
                f"{self.to_factor.substance!r}, not {self.to_substance!r}."
            )

    @property
    def name(self) -> str:
        return f"Fuel switch {self.from_substance} → {self.to_substance}"

    def apply(self, entries: Iterable[InventoryEntry]) -> tuple[InventoryEntry, ...]:
        wanted = {_key(c) for c in self.categories}
        source = _key(self.from_substance)

        def matches(entry: InventoryEntry) -> bool:
            activity, _factor = entry
            if _key(activity.substance) != source:
                return False
            return not wanted or _key(activity.category) in wanted

        def transform(entry: InventoryEntry) -> InventoryEntry:
            activity, _factor = entry
            updated = activity.model_copy(update={"substance": self.to_substance})
            return updated, self.to_factor

        return self._map_matching(entries, matches, transform)


@dataclass(frozen=True)
class MaterialSubstitution(Lever):
    """Replace a raw material with a lower-carbon alternative."""

    from_substance: str
    to_substance: str
    to_factor: EmissionFactor
    categories: tuple[str, ...] = ("s3_cat01",)
    kind: ClassVar[str] = "material_substitution"

    def __post_init__(self) -> None:
        if _key(self.from_substance) == _key(self.to_substance):
            raise ScenarioError("Material substitution source and target are identical.")
        if _key(self.to_factor.substance) != _key(self.to_substance):
            raise ScenarioError(
                f"Replacement factor {self.to_factor.factor_id} covers "
                f"{self.to_factor.substance!r}, not {self.to_substance!r}."
            )

    @property
    def name(self) -> str:
        return f"Material substitution {self.from_substance} → {self.to_substance}"

    def apply(self, entries: Iterable[InventoryEntry]) -> tuple[InventoryEntry, ...]:
        wanted = {_key(c) for c in self.categories}
        source = _key(self.from_substance)

        def matches(entry: InventoryEntry) -> bool:
            activity, _factor = entry
            return _key(activity.substance) == source and _key(activity.category) in wanted

        def transform(entry: InventoryEntry) -> InventoryEntry:
            activity, _factor = entry
            return activity.model_copy(update={"substance": self.to_substance}), self.to_factor

        return self._map_matching(entries, matches, transform)


@dataclass(frozen=True)
class WasteReduction(Lever):
    """Reduce waste generated (and therefore treated) by ``reduction``."""

    reduction: float
    categories: tuple[str, ...] = ("s3_cat05",)
    kind: ClassVar[str] = "waste_reduction"

    def __post_init__(self) -> None:
        _check_share(self.reduction, "Waste reduction")
        if self.reduction == 0:
            raise ScenarioError("Waste reduction must be greater than 0.")
        if self.reduction >= 1:
            raise ScenarioError("Waste reduction must be below 100 %.")

    @property
    def name(self) -> str:
        return f"Waste reduction {self.reduction:.0%}"

    def apply(self, entries: Iterable[InventoryEntry]) -> tuple[InventoryEntry, ...]:
        wanted = {_key(c) for c in self.categories}
        return self._map_matching(
            entries,
            lambda entry: _key(entry[0].category) in wanted,
            lambda entry: self._scale(entry, 1 - self.reduction, field="quantity"),
        )


@dataclass(frozen=True)
class ProcessOptimisation(Lever):
    """Reduce process (non-combustion) emissions by ``improvement``."""

    improvement: float
    categories: tuple[str, ...] = ("process_emissions",)
    kind: ClassVar[str] = "process_optimisation"

    def __post_init__(self) -> None:
        _check_share(self.improvement, "Process improvement")
        if self.improvement == 0:
            raise ScenarioError("Process improvement must be greater than 0.")
        if self.improvement >= 1:
            raise ScenarioError("Process improvement must be below 100 %.")

    @property
    def name(self) -> str:
        return f"Process optimisation {self.improvement:.0%}"

    def apply(self, entries: Iterable[InventoryEntry]) -> tuple[InventoryEntry, ...]:
        wanted = {_key(c) for c in self.categories}
        return self._map_matching(
            entries,
            lambda entry: _key(entry[0].category) in wanted,
            lambda entry: self._scale(entry, 1 - self.improvement, field="quantity"),
        )


@dataclass(frozen=True)
class TransportOptimisation(Lever):
    """Reduce freight tonne-kilometres by ``efficiency`` (load factor, routing)."""

    efficiency: float
    categories: tuple[str, ...] = ("s3_cat04",)
    kind: ClassVar[str] = "transport_optimisation"

    def __post_init__(self) -> None:
        _check_share(self.efficiency, "Transport efficiency")
        if self.efficiency == 0:
            raise ScenarioError("Transport efficiency must be greater than 0.")
        if self.efficiency >= 1:
            raise ScenarioError("Transport efficiency must be below 100 %.")

    @property
    def name(self) -> str:
        return f"Transport optimisation {self.efficiency:.0%}"

    def apply(self, entries: Iterable[InventoryEntry]) -> tuple[InventoryEntry, ...]:
        wanted = {_key(c) for c in self.categories}
        return self._map_matching(
            entries,
            lambda entry: _key(entry[0].category) in wanted,
            lambda entry: self._scale(entry, 1 - self.efficiency, field="quantity"),
        )


LEVER_KINDS: tuple[str, ...] = (
    "renewable_electricity",
    "energy_efficiency",
    "fuel_switch",
    "material_substitution",
    "waste_reduction",
    "process_optimisation",
    "transport_optimisation",
)


def lever_from_kind(kind: str) -> type[Lever]:
    """Map a lever kind string to its class (used by the UI and persistence)."""
    mapping = {
        cls.kind: cls
        for cls in (
            RenewableElectricity,
            EnergyEfficiency,
            FuelSwitch,
            MaterialSubstitution,
            WasteReduction,
            ProcessOptimisation,
            TransportOptimisation,
        )
    }
    try:
        return mapping[kind]
    except KeyError:
        raise ScenarioError(
            f"Unknown lever {kind!r}; expected one of {', '.join(LEVER_KINDS)}."
        ) from None
