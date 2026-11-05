"""Shared result container for scope accounting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..core.calc import EmissionResult

__all__ = ["ScopeResult"]


@dataclass(frozen=True)
class ScopeResult:
    """Aggregated emissions for one scope.

    Row-level results are preserved for audit; aggregates are derived from
    them so totals can always be re-checked against the underlying records
    (report reconciliation).
    """

    scope: int
    results: tuple[EmissionResult, ...] = field(default_factory=tuple)

    @classmethod
    def from_results(cls, scope: int, results: Iterable[EmissionResult]) -> "ScopeResult":
        return cls(scope=scope, results=tuple(results))

    @property
    def total_kg(self) -> float:
        """Total CO2e in kilograms."""
        return sum(r.co2e_kg for r in self.results)

    @property
    def total_t(self) -> float:
        """Total CO2e in tonnes."""
        return self.total_kg / 1000.0

    def by_category(self) -> dict[str, float]:
        """CO2e (kg) grouped by activity category."""
        totals: dict[str, float] = {}
        for r in self.results:
            totals[r.category] = totals.get(r.category, 0.0) + r.co2e_kg
        return totals

    def by_gas(self) -> dict[str, float]:
        """CO2e (kg) grouped by the factor's gas."""
        totals: dict[str, float] = {}
        for r in self.results:
            totals[r.gas] = totals.get(r.gas, 0.0) + r.co2e_kg
        return totals

    def __len__(self) -> int:
        return len(self.results)
