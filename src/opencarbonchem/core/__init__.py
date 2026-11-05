"""Core calculation engine: units, GWP, activity data, emission computation.

This package is UI-free and imports nothing from the application layers.
"""

from .activity import ActivityRecord
from .calc import EmissionResult, compute_emissions
from .exceptions import OpenCarbonChemError
from .gwp import DEFAULT_GWP_SET, GWPSet, get_gwp_set, gwp, to_co2e
from .units import Quantity, UnitRegistry, convert, default_registry, parse_unit, q

__all__ = [
    "DEFAULT_GWP_SET",
    "ActivityRecord",
    "EmissionResult",
    "GWPSet",
    "OpenCarbonChemError",
    "Quantity",
    "UnitRegistry",
    "compute_emissions",
    "convert",
    "default_registry",
    "get_gwp_set",
    "gwp",
    "parse_unit",
    "q",
    "to_co2e",
]
