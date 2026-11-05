"""Exception hierarchy for OpenCarbonChem.

Every error raised by the engine derives from :class:`OpenCarbonChemError` so that
callers (API, CLI, Streamlit) can fail safely and surface an actionable message
rather than silently producing a number.
"""

from __future__ import annotations


class OpenCarbonChemError(Exception):
    """Base class for all OpenCarbonChem errors."""


# --------------------------------------------------------------------------- #
# Units and dimensions
# --------------------------------------------------------------------------- #
class UnitError(OpenCarbonChemError):
    """Base class for unit-related failures."""


class UnknownUnitError(UnitError):
    """A unit symbol could not be resolved against the unit registry."""


class IncompatibleUnitError(UnitError):
    """Raised when a conversion or arithmetic operation crosses dimensions.

    The engine never silently applies an incompatible conversion; this error is
    the mechanism that guarantees it.
    """


class CurrencyError(UnitError):
    """A currency conversion was requested without an explicit exchange rate."""


class ConversionFactorMissingError(UnitError):
    """A basis change (e.g. mass -> energy) needs a registered conversion factor."""


# --------------------------------------------------------------------------- #
# Emission factors
# --------------------------------------------------------------------------- #
class FactorError(OpenCarbonChemError):
    """Base class for emission-factor failures."""


class MissingFactorError(FactorError):
    """No emission factor matched the activity's category, substance and geography."""


class AmbiguousFactorError(FactorError):
    """More than one emission factor matched and no deterministic winner exists."""


class FactorScopeError(FactorError):
    """The emission factor's activity unit is not comparable with the activity data."""


class UnverifiedFactorError(FactorError):
    """A factor whose review status forbids reporting use was selected for a report."""


# --------------------------------------------------------------------------- #
# GWP / CO2e
# --------------------------------------------------------------------------- #
class GWPError(OpenCarbonChemError):
    """Base class for global-warming-potential failures."""


class MissingGWPError(GWPError):
    """The requested GWP set has no value for the gas (or methane basis)."""


# --------------------------------------------------------------------------- #
# Accounting boundaries
# --------------------------------------------------------------------------- #
class BoundaryError(OpenCarbonChemError):
    """Organisational or system boundary is incomplete or inconsistent."""


class PeriodError(OpenCarbonChemError):
    """Activity data falls outside the declared reporting period."""


class DoubleCountingError(OpenCarbonChemError):
    """The same emission contribution would be counted twice."""


class PCFError(OpenCarbonChemError):
    """A product definition, life-cycle stage or inventory item is invalid."""


class AllocationError(OpenCarbonChemError):
    """Allocation bases do not sum to unity, or a basis is not supported."""


# --------------------------------------------------------------------------- #
# Analytics, scenarios, reporting
# --------------------------------------------------------------------------- #
class ScenarioError(OpenCarbonChemError):
    """A decarbonisation scenario is malformed or cannot be applied."""


class UncertaintyError(OpenCarbonChemError):
    """A probability distribution or Monte Carlo configuration is invalid."""


class ReconciliationError(OpenCarbonChemError):
    """Reported totals do not reconcile with the underlying calculation records."""


class ExportError(OpenCarbonChemError):
    """PDF/Excel generation failed."""
