"""Organisation-level roll-up and report reconciliation.

``OrganizationReport`` combines the per-scope results into one auditable
inventory view (total, by scope, by category, by gas) and can re-check itself:

- **consistency** checks re-derive every aggregate from the row-level
  results, so any future refactor that stores totals instead of deriving them
  is caught immediately;
- **coverage** checks flag what the inventory does *not* contain (missing
  scopes or Scope 1/2 subcategories), because an absent category cannot be
  distinguished from an unreported zero and must be reviewed by a human.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Iterable

from ..core.exceptions import BoundaryError
from .base import ScopeResult
from .scope1 import SCOPE1_CATEGORIES
from .scope2 import SCOPE2_CATEGORIES

__all__ = ["OrganizationReport", "Reconciliation", "ReconciliationCheck"]

_VALID_SCOPES = (1, 2, 3)


@dataclass(frozen=True)
class ReconciliationCheck:
    """One reconciliation line: expected vs. actual, or a coverage gap."""

    name: str
    kind: str  # "consistency" | "coverage"
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "ok": self.ok,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Reconciliation:
    """Result of re-checking a report against its underlying rows."""

    checks: tuple[ReconciliationCheck, ...]

    @property
    def ok(self) -> bool:
        """True when every *consistency* check passes (coverage is advisory)."""
        return all(c.ok for c in self.checks if c.kind == "consistency")

    @property
    def coverage_gaps(self) -> tuple[ReconciliationCheck, ...]:
        """Checks that flag unreported scopes/categories for human review."""
        return tuple(c for c in self.checks if c.kind == "coverage" and not c.ok)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "checks": [c.to_dict() for c in self.checks]}


@dataclass(frozen=True)
class OrganizationReport:
    """One reporting year's inventory across Scope 1, 2 and 3."""

    scope_results: tuple[ScopeResult, ...] = ()

    @classmethod
    def from_results(cls, results: Iterable[ScopeResult]) -> "OrganizationReport":
        ordered = sorted(results, key=lambda r: r.scope)
        seen: set[int] = set()
        for result in ordered:
            if result.scope in seen:
                raise BoundaryError(
                    f"duplicate Scope {result.scope} result in organisation report"
                )
            if result.scope not in _VALID_SCOPES:
                raise BoundaryError(
                    f"invalid scope {result.scope} in organisation report "
                    "(expected 1, 2 or 3)"
                )
            seen.add(result.scope)
        return cls(scope_results=tuple(ordered))

    @property
    def total_kg(self) -> float:
        return sum(r.total_kg for r in self.scope_results)

    @property
    def total_t(self) -> float:
        return self.total_kg / 1000.0

    def by_scope(self) -> dict[int, float]:
        return {r.scope: r.total_kg for r in self.scope_results}

    def by_category(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for result in self.scope_results:
            for category, kg in result.by_category().items():
                totals[category] = totals.get(category, 0.0) + kg
        return totals

    def by_gas(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for result in self.scope_results:
            for gas, kg in result.by_gas().items():
                totals[gas] = totals.get(gas, 0.0) + kg
        return totals

    # -- reconciliation ---------------------------------------------------- #
    def reconcile(self, rel_tol: float = 1e-9) -> Reconciliation:
        """Re-derive aggregates from rows and flag unreported coverage."""
        checks: list[ReconciliationCheck] = []
        total = self.total_kg

        def consistency(name: str, actual: float) -> None:
            ok = isclose(actual, total, rel_tol=rel_tol, abs_tol=rel_tol)
            checks.append(
                ReconciliationCheck(
                    name=name,
                    kind="consistency",
                    ok=ok,
                    detail=f"expected {total!r} kg, derived {actual!r} kg",
                )
            )

        consistency("scope_totals_match_report_total", sum(self.by_scope().values()))
        consistency("category_totals_match_report_total", sum(self.by_category().values()))
        consistency("gas_totals_match_report_total", sum(self.by_gas().values()))

        reported = set(self.by_scope())
        for scope in _VALID_SCOPES:
            checks.append(
                ReconciliationCheck(
                    name=f"scope_{scope}_reported",
                    kind="coverage",
                    ok=scope in reported,
                    detail=(
                        f"Scope {scope} present"
                        if scope in reported
                        else f"Scope {scope} not reported — confirm whether it is zero or missing"
                    ),
                )
            )

        for scope, categories in ((1, SCOPE1_CATEGORIES), (2, SCOPE2_CATEGORIES)):
            if scope not in reported:
                continue
            result = next(r for r in self.scope_results if r.scope == scope)
            present = set(result.by_category())
            for category in categories:
                if category not in present:
                    checks.append(
                        ReconciliationCheck(
                            name=f"scope{scope}_category_{category}_reported",
                            kind="coverage",
                            ok=False,
                            detail=(
                                f"Scope {scope} category {category!r} has no rows — "
                                "zero or unreported?"
                            ),
                        )
                    )
        return Reconciliation(checks=tuple(checks))
