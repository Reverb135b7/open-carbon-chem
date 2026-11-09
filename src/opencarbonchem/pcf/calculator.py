"""PCF assembly: life-cycle inventory → attributable emissions → carbon footprint.

``PCF = Σ attributable life-cycle CO2e / reference-flow output``

Every line item keeps the activity value/unit, factor value/unit, gas, GWP set,
allocation share and the raw and allocated CO2e, so any reported footprint can be
re-derived from the result object alone (auditability requirement).

The calculator never re-implements ``E = AD × EF``: it calls
:func:`opencarbonchem.core.calc.compute_emissions`, which keeps corporate and
product accounting on one engine (no double counting by construction).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isclose
from typing import Iterable

from ..accounting.aggregate import OrganizationReport
from ..core.calc import EmissionResult, compute_emissions
from ..core.exceptions import DoubleCountingError, PCFError
from ..core.gwp import DEFAULT_GWP_SET
from ..core.units import Quantity
from .allocation import AllocationRule, allocation_share, apply_allocation, resolve_rules
from .models import STAGE_CATALOGUE, InventoryItem, ProductDefinition

__all__ = [
    "PCFLineItem",
    "PCFResult",
    "CorporatePlusProduct",
    "calculate_pcf",
    "combine_with_corporate",
]


@dataclass(frozen=True)
class PCFLineItem:
    """One auditable PCF contribution, before and after allocation."""

    stage: str
    activity_id: str
    factor_id: str
    gas: str
    co2e_kg: float           # contribution before allocation
    allocation_share: float
    allocated_kg: float      # contribution attributable to the product
    excluded_from_corporate: bool
    activity_value: float
    activity_unit: str
    factor_value: float
    factor_unit: str
    description: str = ""

    @property
    def allocated_t(self) -> float:
        return self.allocated_kg / 1000.0

    def to_row(self) -> dict:
        return {
            "stage": self.stage,
            "stage_label": STAGE_CATALOGUE[self.stage].label,
            "activity_id": self.activity_id,
            "description": self.description,
            "factor_id": self.factor_id,
            "gas": self.gas,
            "activity_value": self.activity_value,
            "activity_unit": self.activity_unit,
            "factor_value": self.factor_value,
            "factor_unit": self.factor_unit,
            "co2e_kg": self.co2e_kg,
            "allocation_share": self.allocation_share,
            "allocated_kg": self.allocated_kg,
            "excluded_from_corporate": self.excluded_from_corporate,
        }


@dataclass(frozen=True)
class PCFResult:
    """A product carbon footprint with its full inventory and audit trail."""

    product: ProductDefinition
    gwp_set: str
    items: tuple[PCFLineItem, ...] = field(default_factory=tuple)
    consistency_warnings: tuple[str, ...] = ()

    # -- totals ------------------------------------------------------------- #
    @property
    def total_kg(self) -> float:
        """Attributable life-cycle CO2e in kilograms."""
        return sum(i.allocated_kg for i in self.items)

    @property
    def total_t(self) -> float:
        return self.total_kg / 1000.0

    @property
    def per_unit(self) -> float:
        """kg CO2e per unit of the declared production unit."""
        return self.total_kg / self.product.production_qty

    @property
    def unit_label(self) -> str:
        return f"kg CO2e/{self.product.production_unit}"

    def per_unit_in(self, unit: str) -> float:
        """kg CO2e per ``unit`` of product, converting the reference flow."""
        reference = Quantity(self.product.production_qty,
                             self.product.production_unit).to(unit)
        return self.total_kg / reference.value

    # -- breakdowns --------------------------------------------------------- #
    def by_stage(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for item in self.items:
            totals[item.stage] = totals.get(item.stage, 0.0) + item.allocated_kg
        return totals

    def by_stage_share(self) -> dict[str, float]:
        """Stage totals as fractions of the footprint (empty when total is zero)."""
        total = self.total_kg
        if isclose(total, 0.0):
            return {}
        return {stage: kg / total for stage, kg in self.by_stage().items()}

    def by_gas(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for item in self.items:
            totals[item.gas] = totals.get(item.gas, 0.0) + item.allocated_kg
        return totals

    def by_activity(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for item in self.items:
            totals[item.activity_id] = totals.get(item.activity_id, 0.0) + item.allocated_kg
        return totals

    # -- audit -------------------------------------------------------------- #
    def to_rows(self) -> list[dict]:
        return [item.to_row() for item in self.items]

    @property
    def boundary_stages(self) -> tuple[str, ...]:
        return self.product.included_stages


@dataclass(frozen=True)
class CorporatePlusProduct:
    """A corporate total with PCF additions that are provably not double counted."""

    corporate_kg: float
    additions_kg: float
    combined_kg: float
    added_items: tuple[str, ...]


def _corporate_index(report: OrganizationReport) -> dict[tuple[str, str], list[EmissionResult]]:
    index: dict[tuple[str, str], list[EmissionResult]] = {}
    for scope_result in report.scope_results:
        for row in scope_result.results:
            index.setdefault((row.activity_id, row.factor_id), []).append(row)
    return index


def calculate_pcf(
    product: ProductDefinition,
    items: Iterable[InventoryItem],
    *,
    allocation_rules: Iterable[AllocationRule] = (),
    gwp_set: str = DEFAULT_GWP_SET,
    corporate_report: OrganizationReport | None = None,
) -> PCFResult:
    """Compute the product carbon footprint for ``product``.

    Raises :class:`PCFError` for out-of-boundary or missing inventory,
    :class:`AllocationError` for invalid allocation rules and
    :class:`DoubleCountingError` when the corporate-inventory flag contradicts
    the corporate report.
    """
    inventory = tuple(items)
    if not inventory:
        raise PCFError(
            f"{product.pcf_id}: no life-cycle inventory items supplied; a footprint "
            "cannot be computed from an empty inventory."
        )

    rules = resolve_rules(allocation_rules)
    allowed = set(product.included_stages)
    lines: list[PCFLineItem] = []

    seen: dict[str, str] = {}
    for item in inventory:
        if item.activity_id in seen:
            raise PCFError(
                f"{product.pcf_id}: activity {item.activity_id!r} appears in both "
                f"{seen[item.activity_id]!r} and {item.stage!r}. One activity row "
                "contributes once; a duplicate would be counted twice."
            )
        seen[item.activity_id] = item.stage

    for item in inventory:
        if item.stage not in allowed:
            raise PCFError(
                f"{product.pcf_id}: stage {item.stage!r} is outside the declared "
                f"{product.system_boundary} boundary. Included stages: "
                f"{', '.join(product.included_stages)}."
            )
        emission = compute_emissions(item.activity, item.factor, gwp_set=gwp_set)
        share = allocation_share(item.stage, rules)
        allocated = apply_allocation(emission.co2e_kg, share)
        lines.append(
            PCFLineItem(
                stage=item.stage,
                activity_id=emission.activity_id,
                factor_id=emission.factor_id,
                gas=emission.gas,
                co2e_kg=emission.co2e_kg,
                allocation_share=share,
                allocated_kg=allocated,
                excluded_from_corporate=item.excluded_from_corporate,
                activity_value=emission.activity_value,
                activity_unit=emission.activity_unit,
                factor_value=emission.factor_value,
                factor_unit=emission.factor_unit,
                description=item.activity.description or item.notes,
            )
        )

    warnings = (
        _check_double_counting(lines, corporate_report) if corporate_report is not None else ()
    )
    return PCFResult(
        product=product,
        gwp_set=gwp_set,
        items=tuple(lines),
        consistency_warnings=tuple(warnings),
    )


def _check_double_counting(
    lines: Iterable[PCFLineItem], report: OrganizationReport
) -> tuple[str, ...]:
    """Cross-check PCF rows against the corporate inventory.

    * A row present in the corporate inventory but flagged
      ``excluded_from_corporate=True`` is a contradiction and raises
      :class:`DoubleCountingError` — it would be added twice by
      :func:`combine_with_corporate`.
    * A row present in both with different CO2e is a reconciliation failure and
      raises :class:`DoubleCountingError`.
    * A row *claimed* as corporate-included but absent from the report is a
      consistency warning (the corporate inventory may simply be incomplete);
      it is reported, never silently ignored.
    """
    index = _corporate_index(report)
    warnings: list[str] = []
    for line in lines:
        key = (line.activity_id, line.factor_id)
        matches = index.get(key)
        if matches is not None:
            if line.excluded_from_corporate:
                raise DoubleCountingError(
                    f"{line.activity_id}/{line.factor_id} is present in the corporate "
                    "inventory but is flagged excluded_from_corporate; adding the PCF "
                    "to the corporate total would double count it."
                )
            if not any(isclose(m.co2e_kg, line.co2e_kg, rel_tol=1e-9, abs_tol=1e-9)
                       for m in matches):
                reported = ", ".join(f"{m.co2e_kg:g}" for m in matches)
                raise DoubleCountingError(
                    f"{line.activity_id}/{line.factor_id}: PCF computes "
                    f"{line.co2e_kg:g} kg CO2e but the corporate inventory reports "
                    f"{reported} kg. One emission cannot have two values."
                )
        elif not line.excluded_from_corporate:
            warnings.append(
                f"{line.activity_id}/{line.factor_id} is not flagged "
                "excluded_from_corporate but has no matching corporate row; confirm "
                "whether the corporate inventory is incomplete."
            )
    return tuple(warnings)


def combine_with_corporate(
    pcf: PCFResult, report: OrganizationReport
) -> CorporatePlusProduct:
    """Add only the PCF rows that are provably outside the corporate inventory.

    Raises :class:`DoubleCountingError` if any row being added already appears in
    the corporate report.
    """
    index = _corporate_index(report)
    additions: list[PCFLineItem] = []
    for line in pcf.items:
        if line.excluded_from_corporate:
            if (line.activity_id, line.factor_id) in index:
                raise DoubleCountingError(
                    f"{line.activity_id}/{line.factor_id} already appears in the "
                    "corporate inventory and cannot be added again."
                )
            additions.append(line)
    corporate_kg = report.total_kg
    additions_kg = sum(line.allocated_kg for line in additions)
    return CorporatePlusProduct(
        corporate_kg=corporate_kg,
        additions_kg=additions_kg,
        combined_kg=corporate_kg + additions_kg,
        added_items=tuple(line.activity_id for line in additions),
    )
