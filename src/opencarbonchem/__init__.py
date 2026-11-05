"""OpenCarbonChem — open-source carbon accounting and sustainability analytics
engine for chemical and process industries.

Two workflows share one calculation engine:

* **Corporate GHG accounting** — Scope 1, Scope 2 (location- and market-based)
  and all 15 Scope 3 categories.
* **Product carbon footprint** — life-cycle inventory, allocation and PCF per
  functional unit (milestone 6).

Everything is dimensionally validated and auditable: each result row records
the activity, the emission factor and the GWP set used to produce it.
"""

from .accounting import (
    ScopeResult,
    calculate_scope1,
    calculate_scope2,
    calculate_scope3,
)
from .core.activity import ActivityRecord
from .core.calc import EmissionResult, compute_emissions
from .core.gwp import DEFAULT_GWP_SET, gwp, to_co2e
from .core.units import Quantity, convert, parse_unit, q
from .factors.models import EmissionFactor
from .factors.registry import FactorRegistry

__version__ = "0.1.0"

__all__ = [
    "ActivityRecord",
    "DEFAULT_GWP_SET",
    "EmissionFactor",
    "EmissionResult",
    "FactorRegistry",
    "Quantity",
    "ScopeResult",
    "calculate_scope1",
    "calculate_scope2",
    "calculate_scope3",
    "compute_emissions",
    "convert",
    "gwp",
    "parse_unit",
    "q",
    "to_co2e",
    "__version__",
]
