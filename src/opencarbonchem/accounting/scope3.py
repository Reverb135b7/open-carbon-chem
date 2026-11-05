"""Scope 3 — the 15 value-chain categories of the GHG Protocol.

Scope 3 Technical Guidance categories, with their direction and typical data
needs, are catalogued in :data:`SCOPE3_CATEGORIES`. Calculation uses the same
engine as Scopes 1/2 (``E = AD × EF`` with the selected GWP set) keyed on the
activity category ``s3_cat01`` … ``s3_cat15``.

Category-specific screening rules (which categories are applicable, exclusion
justification, and the refined calculation methods per category) are a later
milestone; the catalogue and generic calculation are implemented and tested
here so downstream modules can rely on the vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..core.activity import ActivityRecord
from ..core.calc import compute_emissions
from ..core.exceptions import BoundaryError
from ..core.gwp import DEFAULT_GWP_SET
from ..factors.registry import FactorRegistry
from .base import ScopeResult

__all__ = ["SCOPE3_CATEGORIES", "Scope3Category", "calculate_scope3", "scope3_category_id"]


@dataclass(frozen=True)
class Scope3Category:
    """One GHG Protocol Scope 3 category."""

    number: int
    name: str
    direction: str  # "upstream" | "downstream"
    applicability: str
    typical_data: str


def scope3_category_id(number: int) -> str:
    """Canonical activity-category id for a Scope 3 category number (1–15)."""
    if not 1 <= number <= 15:
        raise BoundaryError(f"Scope 3 category number must be 1–15, got {number}.")
    return f"s3_cat{number:02d}"


#: All 15 GHG Protocol Scope 3 categories.
SCOPE3_CATEGORIES: dict[int, Scope3Category] = {
    1: Scope3Category(1, "Purchased goods and services", "upstream",
                     "Any organization purchasing goods or services",
                     "Spend or mass of purchased materials × supplier/EEIO or LCA factors"),
    2: Scope3Category(2, "Capital goods", "upstream",
                     "Organizations purchasing capital equipment, machinery, buildings",
                     "Spend or mass of capital goods × supplier/EEIO or LCA factors"),
    3: Scope3Category(3, "Fuel- and energy-related activities (not included in Scope 1 or 2)",
                     "upstream",
                     "All organizations (well-to-tank, transmission & distribution losses, generation of purchased energy)",
                     "Fuel/energy quantities × upstream and T&D factors"),
    4: Scope3Category(4, "Upstream transportation and distribution", "upstream",
                     "Organizations transporting inbound goods by third parties",
                     "Tonnes-km or tonne-miles by mode × mode-specific factors"),
    5: Scope3Category(5, "Waste generated in operations", "upstream",
                     "All organizations generating operational waste",
                     "Mass of waste by treatment route × treatment factors"),
    6: Scope3Category(6, "Business travel", "upstream",
                     "Organizations whose employees travel for business",
                     "Passenger-km or trip-km by mode × travel factors"),
    7: Scope3Category(7, "Employee commuting", "upstream",
                     "Organizations with commuting employees",
                     "Commuting distance/mode survey × mode factors"),
    8: Scope3Category(8, "Upstream leased assets", "upstream",
                     "Organizations operating in leased assets (lessee)",
                     "Energy use of leased asset × applicable factors"),
    9: Scope3Category(9, "Downstream transportation and distribution", "downstream",
                     "Organizations distributing products to customers",
                     "Tonnes-km by mode × mode-specific factors"),
    10: Scope3Category(10, "Processing of sold products", "downstream",
                     "Organizations selling products further processed by customers",
                     "Mass of product sold × processing factors"),
    11: Scope3Category(11, "Use of sold products", "downstream",
                     "Organizations selling products with in-use emissions/energy",
                     "Units sold × use-phase energy × lifetime × factors"),
    12: Scope3Category(12, "End-of-life treatment of sold products", "downstream",
                     "Organizations selling products disposed of by customers",
                     "Mass of product sold × end-of-life treatment factors"),
    13: Scope3Category(13, "Downstream leased assets", "downstream",
                     "Organizations owning leased assets (lessor)",
                     "Energy use of leased asset × applicable factors"),
    14: Scope3Category(14, "Franchises", "downstream",
                     "Organizations operating franchise networks",
                     "Franchise energy/operations × applicable factors"),
    15: Scope3Category(15, "Other (upstream and downstream)", "downstream",
                     "Categories not covered above; must be documented and disclosed",
                     "Varies; requires explicit documentation of method"),
}


def _parse_category(category: str) -> int:
    text = category.strip().lower()
    if not text.startswith("s3_cat"):
        raise BoundaryError(
            f"Scope 3 activity category must look like 's3_cat01'…'s3_cat15', "
            f"got {category!r}."
        )
    suffix = text[len("s3_cat"):]
    if not suffix.isdigit():
        raise BoundaryError(f"Invalid Scope 3 category {category!r}.")
    number = int(suffix)
    if number not in SCOPE3_CATEGORIES:
        raise BoundaryError(f"Unknown Scope 3 category number {number}; must be 1–15.")
    return number


def calculate_scope3(
    activities: Iterable[ActivityRecord],
    registry: FactorRegistry,
    *,
    gwp_set: str = DEFAULT_GWP_SET,
) -> ScopeResult:
    """Compute Scope 3 emissions for activity records tagged ``s3_catNN``."""
    results = []
    for activity in activities:
        if activity.scope != 3:
            raise BoundaryError(
                f"Activity {activity.activity_id} is tagged scope {activity.scope}; "
                "calculate_scope3 only accepts scope 3 records."
            )
        _parse_category(activity.category)
        factor = registry.find(
            activity_category=activity.category,
            substance=activity.substance,
            geography=activity.geography,
            year=activity.reporting_year,
            gas=activity.gas,
        )
        results.append(compute_emissions(activity, factor, gwp_set=gwp_set))
    return ScopeResult.from_results(3, results)
