"""Corporate GHG accounting: Scope 1, Scope 2 and Scope 3."""

from .aggregate import OrganizationReport, Reconciliation, ReconciliationCheck
from .base import ScopeResult
from .boundary import CONSOLIDATION_METHODS, BoundaryEntity, OrganisationalBoundary
from .comparison import ComparisonLine, PeriodComparison, compare_line, compare_periods
from .scope1 import SCOPE1_CATEGORIES, calculate_scope1
from .scope2 import SCOPE2_CATEGORIES, Scope2Result, calculate_scope2
from .scope3 import SCOPE3_CATEGORIES, Scope3Category, calculate_scope3, scope3_category_id

__all__ = [
    "CONSOLIDATION_METHODS",
    "SCOPE1_CATEGORIES",
    "SCOPE2_CATEGORIES",
    "SCOPE3_CATEGORIES",
    "BoundaryEntity",
    "ComparisonLine",
    "OrganizationReport",
    "OrganisationalBoundary",
    "PeriodComparison",
    "Reconciliation",
    "ReconciliationCheck",
    "Scope2Result",
    "Scope3Category",
    "ScopeResult",
    "calculate_scope1",
    "calculate_scope2",
    "calculate_scope3",
    "compare_line",
    "compare_periods",
    "scope3_category_id",
]
