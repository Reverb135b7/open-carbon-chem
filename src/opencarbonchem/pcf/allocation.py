"""Allocation of shared life-cycle emissions to the product under study.

Allocation is only applied when emissions are genuinely shared between
co-products, and the method must be stated explicitly. The rule records both the
product's basis amount and the total basis amount, so the share is reproducible
from stored data (``share = basis_value / basis_total``).

Supported methods (ISO 14044 hierarchy):

* ``physical_causality`` — the process is split by a causal physical quantity
  (mass, energy, volume, …). No dimension constraint is imposed because the
  causality may legitimately be any physical quantity.
* ``mass`` — basis must be a mass.
* ``economic`` — basis must be a monetary value.
* ``none`` — no shared emissions; share is exactly 1.0.

The unit engine is used to check the basis dimension, so an economic rule with a
mass basis fails loudly instead of producing a plausible-looking number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from ..core.exceptions import AllocationError
from ..core.units import Dimension, default_registry
from .models import normalise_stage

__all__ = [
    "AllocationMethod",
    "AllocationRule",
    "resolve_rules",
    "allocation_share",
    "apply_allocation",
]

AllocationMethod = Literal["mass", "economic", "physical_causality", "none"]

_METHODS: frozenset[str] = frozenset({"mass", "economic", "physical_causality", "none"})
_MASS = Dimension({"M": 1})
_MONEY = Dimension({"CUR": 1})


@dataclass(frozen=True)
class AllocationRule:
    """How shared emissions at ``stage`` are split for the product under study.

    ``stage=None`` makes the rule the default for every stage without its own
    rule. ``basis_value`` is this product's basis amount and ``basis_total`` the
    sum over all co-products.
    """

    method: AllocationMethod
    stage: str | None = None
    basis_value: float | None = None
    basis_total: float | None = None
    basis_unit: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        method = self.method
        if method not in _METHODS:
            raise AllocationError(
                f"Unknown allocation method {method!r}; expected one of "
                f"{', '.join(sorted(_METHODS))}."
            )
        if self.stage is not None:
            object.__setattr__(self, "stage", normalise_stage(self.stage))

        if method == "none":
            if any(v is not None for v in (self.basis_value, self.basis_total, self.basis_unit)):
                raise AllocationError(
                    "Allocation method 'none' means emissions are not shared; "
                    "do not supply basis_value, basis_total or basis_unit."
                )
            return

        if self.basis_value is None or self.basis_total is None:
            raise AllocationError(
                f"Allocation method {method!r} requires both basis_value and basis_total."
            )
        if self.basis_value <= 0 or self.basis_total <= 0:
            raise AllocationError("Allocation basis amounts must be positive.")
        if self.basis_value > self.basis_total:
            raise AllocationError(
                f"basis_value ({self.basis_value:g}) cannot exceed basis_total "
                f"({self.basis_total:g})."
            )
        if not (self.basis_unit or "").strip():
            raise AllocationError(f"Allocation method {method!r} requires a basis_unit.")
        self._check_basis_dimension()

    def _check_basis_dimension(self) -> None:
        unit = default_registry().parse(self.basis_unit or "")
        if self.method == "mass" and unit.dimension != _MASS:
            raise AllocationError(
                f"Method 'mass' requires a mass basis unit; {self.basis_unit!r} is "
                f"{unit.dimension}."
            )
        if self.method == "economic" and unit.dimension != _MONEY:
            raise AllocationError(
                f"Method 'economic' requires a currency basis unit; {self.basis_unit!r} is "
                f"{unit.dimension}."
            )

    @property
    def share(self) -> float:
        """Fraction of the stage's emissions attributable to this product (0, 1]."""
        if self.method == "none":
            return 1.0
        assert self.basis_value is not None and self.basis_total is not None
        return self.basis_value / self.basis_total

    @property
    def is_default(self) -> bool:
        return self.stage is None


def resolve_rules(rules: Iterable[AllocationRule]) -> dict[str | None, AllocationRule]:
    """Index rules by stage, rejecting duplicates and conflicts."""
    index: dict[str | None, AllocationRule] = {}
    for rule in rules:
        if rule.stage in index:
            where = "the default rule" if rule.stage is None else f"stage {rule.stage!r}"
            raise AllocationError(f"More than one allocation rule supplied for {where}.")
        index[rule.stage] = rule
    return index


def allocation_share(stage: str, rules: dict[str | None, AllocationRule]) -> float:
    """Share for ``stage``: stage rule if present, else the default rule, else 1.0."""
    rule = rules.get(normalise_stage(stage)) or rules.get(None)
    return rule.share if rule is not None else 1.0


def apply_allocation(emissions_kg: float, share: float) -> float:
    """Scale ``emissions_kg`` by ``share`` after validating the share."""
    if not 0.0 < share <= 1.0:
        raise AllocationError(f"Allocation share must be in (0, 1]; got {share!r}.")
    if emissions_kg < 0:
        raise AllocationError(f"Allocated emissions cannot be negative; got {emissions_kg!r} kg.")
    return emissions_kg * share
