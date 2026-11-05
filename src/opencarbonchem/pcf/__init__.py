"""Product Carbon Footprint (PCF) — ISO 14067 / PAS 2050 style accounting."""

from .allocation import (
    AllocationMethod,
    AllocationRule,
    allocation_share,
    apply_allocation,
    resolve_rules,
)
from .calculator import (
    CorporatePlusProduct,
    PCFLineItem,
    PCFResult,
    calculate_pcf,
    combine_with_corporate,
)
from .models import (
    STAGE_CATALOGUE,
    InventoryItem,
    ProductDefinition,
    StageInfo,
    SystemBoundary,
    normalise_stage,
    stages_for_boundary,
)

__all__ = [
    "STAGE_CATALOGUE",
    "AllocationMethod",
    "AllocationRule",
    "CorporatePlusProduct",
    "InventoryItem",
    "PCFLineItem",
    "PCFResult",
    "ProductDefinition",
    "StageInfo",
    "SystemBoundary",
    "allocation_share",
    "apply_allocation",
    "calculate_pcf",
    "combine_with_corporate",
    "normalise_stage",
    "resolve_rules",
    "stages_for_boundary",
]
