"""Reporting-year comparison (handover §7).

Compares two reporting years line by line — total, per scope and per
category — with absolute and percentage change. Missing data is *flagged*,
never converted into a fake −100 % drop or 0 % baseline: a scope absent from
one year may be unreported rather than zero, and a percentage change from a
zero prior year is undefined.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from .aggregate import OrganizationReport
from .base import ScopeResult

__all__ = ["ComparisonLine", "PeriodComparison", "compare_line", "compare_periods"]

STATUS_COMPARED = "compared"
STATUS_NEW = "new_in_current_year"
STATUS_MISSING = "missing_in_current_year"


def compare_line(label: str, current_kg: float | None, prior_kg: float | None) -> ComparisonLine:
    """Build one comparison row; both sides must be *reported* to compute a delta."""
    if current_kg is None and prior_kg is None:
        return ComparisonLine(label, None, None, None, None, STATUS_MISSING)
    if prior_kg is None:
        return ComparisonLine(label, current_kg, None, None, None, STATUS_NEW)
    if current_kg is None:
        return ComparisonLine(label, None, prior_kg, None, None, STATUS_MISSING)
    delta = current_kg - prior_kg
    delta_pct = (delta / prior_kg) * 100.0 if prior_kg != 0.0 else None
    return ComparisonLine(label, current_kg, prior_kg, delta, delta_pct, STATUS_COMPARED)


@dataclass(frozen=True)
class ComparisonLine:
    """One row of a year-over-year comparison (kg CO2e)."""

    label: str
    current_kg: float | None
    prior_kg: float | None
    delta_kg: float | None
    delta_pct: float | None  # None when a side is unreported or prior is zero
    status: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PeriodComparison:
    """Full year-over-year comparison for one organisation."""

    current_label: str
    prior_label: str
    total: ComparisonLine
    by_scope: dict[int, ComparisonLine]
    by_category: dict[str, ComparisonLine]

    def all_lines(self) -> list[ComparisonLine]:
        """Total, scope and category lines in report-table order."""
        lines = [self.total]
        lines.extend(self.by_scope[key] for key in sorted(self.by_scope))
        lines.extend(self.by_category[key] for key in sorted(self.by_category))
        return lines

    def to_dict(self) -> dict:
        return {
            "current": self.current_label,
            "prior": self.prior_label,
            "total": self.total.to_dict(),
            "by_scope": {str(k): v.to_dict() for k, v in self.by_scope.items()},
            "by_category": {k: v.to_dict() for k, v in self.by_category.items()},
        }


def _as_report(value: OrganizationReport | Mapping[int, ScopeResult]) -> OrganizationReport:
    if isinstance(value, OrganizationReport):
        return value
    return OrganizationReport.from_results(value.values())


def compare_periods(
    current: OrganizationReport | Mapping[int, ScopeResult],
    prior: OrganizationReport | Mapping[int, ScopeResult],
    current_label: str = "current",
    prior_label: str = "prior",
) -> PeriodComparison:
    """Compare two reporting years at total, scope and category level."""
    cur = _as_report(current)
    prv = _as_report(prior)

    total = compare_line("total", cur.total_kg, prv.total_kg)

    cur_scopes, prv_scopes = cur.by_scope(), prv.by_scope()
    by_scope = {
        scope: compare_line(f"Scope {scope}", cur_scopes.get(scope), prv_scopes.get(scope))
        for scope in sorted(set(cur_scopes) | set(prv_scopes))
    }

    cur_categories, prv_categories = cur.by_category(), prv.by_category()
    by_category = {
        category: compare_line(category, cur_categories.get(category), prv_categories.get(category))
        for category in sorted(set(cur_categories) | set(prv_categories))
    }

    return PeriodComparison(
        current_label=current_label,
        prior_label=prior_label,
        total=total,
        by_scope=by_scope,
        by_category=by_category,
    )
