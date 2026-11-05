"""Scope 2 — indirect emissions from purchased energy.

GHG Protocol Scope 2 Guidance requires two accounting methods:

* **Location-based** — grid-average (or supplier-average) factors for
  purchased electricity, steam, heat and cooling. Always computed.
* **Market-based** — factors reflecting contracts, supplier mixes and
  residual mixes. Computed *only* when the caller supplies explicit factors
  keyed by activity ID; the engine never silently substitutes a grid-average
  factor for a market-based one, because that would report a number the
  methodology does not support.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from ..core.activity import ActivityRecord
from ..core.calc import compute_emissions
from ..core.exceptions import BoundaryError, MissingFactorError
from ..core.gwp import DEFAULT_GWP_SET
from ..factors.models import EmissionFactor
from ..factors.registry import FactorRegistry
from .base import ScopeResult

__all__ = ["SCOPE2_CATEGORIES", "Scope2Result", "calculate_scope2"]

#: GHG Protocol Scope 2 purchased-energy categories.
SCOPE2_CATEGORIES: dict[str, str] = {
    "purchased_electricity": "Purchased electricity",
    "purchased_steam": "Purchased steam",
    "purchased_heat": "Purchased heat",
    "purchased_cooling": "Purchased cooling",
}


@dataclass(frozen=True)
class Scope2Result:
    """Location-based totals, plus market-based totals when provided."""

    location: ScopeResult
    market: ScopeResult | None = None

    @property
    def total_t(self) -> float:
        return self.location.total_t


def calculate_scope2(
    activities: Iterable[ActivityRecord],
    registry: FactorRegistry,
    *,
    gwp_set: str = DEFAULT_GWP_SET,
    market_factors: Mapping[str, EmissionFactor] | None = None,
) -> Scope2Result:
    """Compute Scope 2 emissions.

    ``market_factors`` maps ``activity_id`` → contract/residual-mix factor.
    When supplied, every listed activity must resolve or
    :class:`MissingFactorError` is raised — a partial market-based total would
    be misleading. When omitted, ``market`` is ``None`` and only the
    location-based method is reported.
    """
    activities = list(activities)
    location_results = []
    for activity in activities:
        if activity.scope != 2:
            raise BoundaryError(
                f"Activity {activity.activity_id} is tagged scope {activity.scope}; "
                "calculate_scope2 only accepts scope 2 records."
            )
        if activity.category not in SCOPE2_CATEGORIES:
            raise BoundaryError(
                f"Activity {activity.activity_id} has category {activity.category!r}; "
                f"Scope 2 categories are {', '.join(sorted(SCOPE2_CATEGORIES))}."
            )
        factor = registry.find(
            activity_category=activity.category,
            substance=activity.substance,
            geography=activity.geography,
            year=activity.reporting_year,
            gas=activity.gas,
        )
        location_results.append(compute_emissions(activity, factor, gwp_set=gwp_set))

    market_results = None
    if market_factors is not None:
        market_results = []
        for activity in activities:
            factor = market_factors.get(activity.activity_id)
            if factor is None:
                raise MissingFactorError(
                    f"No market-based factor supplied for activity "
                    f"{activity.activity_id}; market-based Scope 2 requires an "
                    "explicit contract or residual-mix factor for every activity."
                )
            market_results.append(compute_emissions(activity, factor, gwp_set=gwp_set))

    return Scope2Result(
        location=ScopeResult.from_results(2, location_results),
        market=ScopeResult.from_results(2, market_results) if market_results is not None else None,
    )
