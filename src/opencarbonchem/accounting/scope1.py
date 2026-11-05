"""Scope 1 — direct emissions from owned or controlled sources.

GHG Protocol Corporate Standard, Scope 1 covers:

* stationary combustion,
* mobile combustion,
* fugitive emissions,
* process emissions.

Every activity must declare ``scope=1`` and one of these categories; anything
else raises :class:`BoundaryError` so miscategorised data cannot leak into the
inventory. Each contribution is computed through the shared engine
(``E = AD × EF`` with the selected GWP set) and retained row by row for audit.
"""

from __future__ import annotations

from typing import Iterable

from ..core.activity import ActivityRecord
from ..core.calc import compute_emissions
from ..core.exceptions import BoundaryError
from ..core.gwp import DEFAULT_GWP_SET
from ..factors.registry import FactorRegistry
from .base import ScopeResult

__all__ = ["SCOPE1_CATEGORIES", "calculate_scope1"]

#: GHG Protocol Scope 1 subcategories.
SCOPE1_CATEGORIES: dict[str, str] = {
    "stationary_combustion": "Stationary combustion",
    "mobile_combustion": "Mobile combustion",
    "fugitive_emissions": "Fugitive emissions",
    "process_emissions": "Process emissions",
}


def calculate_scope1(
    activities: Iterable[ActivityRecord],
    registry: FactorRegistry,
    *,
    gwp_set: str = DEFAULT_GWP_SET,
) -> ScopeResult:
    """Compute Scope 1 emissions for the given activity records."""
    results = []
    for activity in activities:
        if activity.scope != 1:
            raise BoundaryError(
                f"Activity {activity.activity_id} is tagged scope {activity.scope}; "
                "calculate_scope1 only accepts scope 1 records."
            )
        if activity.category not in SCOPE1_CATEGORIES:
            raise BoundaryError(
                f"Activity {activity.activity_id} has category {activity.category!r}; "
                f"Scope 1 categories are {', '.join(sorted(SCOPE1_CATEGORIES))}."
            )
        factor = registry.find(
            activity_category=activity.category,
            substance=activity.substance,
            geography=activity.geography,
            year=activity.reporting_year,
            gas=activity.gas,
        )
        results.append(compute_emissions(activity, factor, gwp_set=gwp_set))
    return ScopeResult.from_results(1, results)
