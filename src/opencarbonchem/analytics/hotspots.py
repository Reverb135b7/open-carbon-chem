"""Hotspot analysis: where do the emissions actually come from?

Hotspots rank contributions along one dimension at a time (substance/material,
process or activity, energy source, gas, scope, category, life-cycle stage) and
report each group's absolute CO2e, its share of the total and the number of rows
behind it. Shares are computed only when the total is non-zero; a zero total
returns shares of 0.0 rather than dividing by zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Iterable, Literal

from ..accounting.aggregate import OrganizationReport
from ..core.calc import EmissionResult
from ..core.exceptions import AnalyticsError
from ..pcf.calculator import PCFLineItem, PCFResult

__all__ = [
    "Hotspot",
    "EMISSION_DIMENSIONS",
    "rank_emissions",
    "report_hotspots",
    "pcf_hotspots",
    "product_carbon_intensity",
]

#: Dimensions available for :func:`rank_emissions`.
EMISSION_DIMENSIONS: tuple[str, ...] = (
    "substance",
    "category",
    "scope",
    "gas",
    "activity",
)


@dataclass(frozen=True)
class Hotspot:
    """One ranked group of emissions."""

    key: str
    label: str
    kg: float
    share: float
    rank: int
    rows: int

    @property
    def t(self) -> float:
        return self.kg / 1000.0

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "kg": self.kg,
            "t": self.t,
            "share": self.share,
            "rank": self.rank,
            "rows": self.rows,
        }


def _rank(groups: dict[str, list[float]], labels: dict[str, str] | None = None) -> list[Hotspot]:
    total = sum(sum(values) for values in groups.values())
    ordered = sorted(groups.items(), key=lambda item: (-sum(item[1]), item[0]))
    result: list[Hotspot] = []
    for index, (key, values) in enumerate(ordered, start=1):
        kg = sum(values)
        share = 0.0 if isclose(total, 0.0) else kg / total
        result.append(
            Hotspot(
                key=key,
                label=(labels or {}).get(key, key),
                kg=kg,
                share=share,
                rank=index,
                rows=len(values),
            )
        )
    return result


def rank_emissions(
    results: Iterable[EmissionResult],
    by: Literal["substance", "category", "scope", "gas", "activity"] = "substance",
) -> list[Hotspot]:
    """Rank emission rows by ``by``, largest first."""
    if by not in EMISSION_DIMENSIONS:
        raise AnalyticsError(
            f"Unknown hotspot dimension {by!r}; expected one of {', '.join(EMISSION_DIMENSIONS)}."
        )
    groups: dict[str, list[float]] = {}
    for row in results:
        if by == "substance":
            key = row.substance
        elif by == "category":
            key = row.category
        elif by == "scope":
            key = str(row.scope)
        elif by == "gas":
            key = row.gas
        else:
            key = row.activity_id
        groups.setdefault(key, []).append(row.co2e_kg)
    labels = {str(s): f"Scope {s}" for s in (1, 2, 3)} if by == "scope" else None
    return _rank(groups, labels)


def report_hotspots(report: OrganizationReport) -> dict[str, list[Hotspot]]:
    """All corporate hotspot views in one call."""
    rows = [row for scope in report.scope_results for row in scope.results]
    return {dimension: rank_emissions(rows, by=dimension) for dimension in EMISSION_DIMENSIONS}


def pcf_hotspots(pcf: PCFResult) -> dict[str, list[Hotspot]]:
    """Hotspots for a product footprint: by stage, activity and gas."""
    groups: dict[str, dict[str, list[float]]] = {"stage": {}, "activity": {}, "gas": {}}
    for item in pcf.items:
        groups["stage"].setdefault(item.stage, []).append(item.allocated_kg)
        groups["activity"].setdefault(item.activity_id, []).append(item.allocated_kg)
        groups["gas"].setdefault(item.gas, []).append(item.allocated_kg)
    return {dimension: _rank(values) for dimension, values in groups.items()}


def product_carbon_intensity(pcf: PCFResult) -> dict:
    """Product carbon intensity plus the reference flow it is expressed against."""
    return {
        "pcf_id": pcf.product.pcf_id,
        "product_name": pcf.product.product_name,
        "total_kg": pcf.total_kg,
        "production_qty": pcf.product.production_qty,
        "production_unit": pcf.product.production_unit,
        "per_unit": pcf.per_unit,
        "unit_label": pcf.unit_label,
        "functional_unit": pcf.product.functional_unit,
    }
