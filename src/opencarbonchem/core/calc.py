"""Fundamental emission calculation: E = Activity Data x Emission Factor.

The engine is UI-free and dimensionally strict:

1. The activity quantity and the factor unit must multiply out to a mass.
   If they do not, :class:`IncompatibleUnitError` is raised - an incompatible
   conversion is never applied silently.
2. The factor must describe the same category, substance and gas as the
   activity (:class:`FactorScopeError`), so a natural-gas factor can never be
   applied to a diesel record and a CO2 factor never stands in for a CH4 row.
3. Gas-specific emissions are converted to CO2e with the GWP set named on the
   result row, so every reported number is reproducible from its audit fields.

A factor whose gas is ``CO2e`` is already a combined factor; no GWP is applied
(and ``gwp`` is recorded as ``None`` to make that visible).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..factors.models import EmissionFactor
from .activity import ActivityRecord
from .exceptions import FactorScopeError, IncompatibleUnitError, OpenCarbonChemError
from .gwp import DEFAULT_GWP_SET, gwp
from .units import Dimension, Quantity, default_registry

if TYPE_CHECKING:  # pandas stays an optional import at call time
    import pandas as pd

__all__ = ["EmissionResult", "compute_emissions", "compute_emissions_batch"]

_MASS = Dimension({"M": 1})


def _key(text: str) -> str:
    """Normalise identifiers for comparison: lower-case, no separators."""
    return "".join(ch for ch in text.strip().lower() if ch.isalnum())


@dataclass(frozen=True)
class EmissionResult:
    """One auditable emission contribution.

    Every field needed to re-derive the number is on the row: activity value
    and unit, factor value and unit, factor ID, gas, GWP and GWP set.
    """

    activity_id: str
    factor_id: str
    scope: int
    category: str
    substance: str
    gas: str
    activity_value: float
    activity_unit: str
    factor_value: float
    factor_unit: str
    emissions_kg: float  # mass of `gas` (or of CO2e when gas == "CO2e")
    gwp: float | None    # None when the factor is already combined CO2e
    gwp_set: str | None
    co2e_kg: float
    # Factor provenance, carried through so reports can be audited.
    source_org: str = ""
    source_reference: str = ""
    review_status: str = ""
    uncertainty_pct: float | None = None

    @property
    def co2e_t(self) -> float:
        """The contribution in tonnes CO2e."""
        return self.co2e_kg / 1000.0


def compute_emissions(
    activity: ActivityRecord,
    factor: EmissionFactor,
    *,
    gwp_set: str = DEFAULT_GWP_SET,
) -> EmissionResult:
    """Apply ``factor`` to ``activity`` and return the CO2e contribution."""
    # 1. The factor must belong to this activity.
    if _key(factor.activity_category) != _key(activity.category):
        raise FactorScopeError(
            f"Factor {factor.factor_id} covers category "
            f"{factor.activity_category!r}, not {activity.category!r} "
            f"(activity {activity.activity_id})."
        )
    if _key(factor.substance) != _key(activity.substance):
        raise FactorScopeError(
            f"Factor {factor.factor_id} covers substance {factor.substance!r}, "
            f"not {activity.substance!r} (activity {activity.activity_id})."
        )
    # An explicit gas on the activity must be the gas (or the combined CO2e
    # factor) actually applied; otherwise the row would report a gas the
    # inventory never declared.
    if activity.gas and _key(factor.gas) != "co2e" and _key(factor.gas) != _key(activity.gas):
        raise FactorScopeError(
            f"Activity {activity.activity_id} declares gas {activity.gas!r} but "
            f"factor {factor.factor_id} is a {factor.gas!r} factor. Supply the "
            "factor for the declared gas, or correct the activity."
        )

    # 2. Dimensional closure: quantity x factor must be a mass.
    registry = default_registry()
    quantity = Quantity(float(activity.quantity), registry.parse(activity.unit))
    factor_unit = registry.parse(factor.unit)
    total = quantity.dimension * factor_unit.dimension
    if total != _MASS:
        raise IncompatibleUnitError(
            f"Activity {activity.activity_id}: {activity.quantity:g} "
            f"{activity.unit} (dimension {quantity.dimension}) x factor "
            f"{factor.factor_id} {factor.value:g} {factor.unit} "
            f"(dimension {factor_unit.dimension}) gives {total}, not mass. "
            "A registered conversion factor is required before these units can "
            "be combined."
        )

    # 3. E = AD x EF, computed in coherent base units (kg of gas).
    emissions_kg = quantity.base_value * (factor.value * factor_unit.scale)

    # 4. Gas-specific CO2e.
    if _key(factor.gas) == "co2e":
        applied_gwp: float | None = None
        applied_set: str | None = None
        co2e_kg = emissions_kg
    else:
        basis = factor.methane_basis or activity.methane_basis
        applied_gwp = gwp(factor.gas, gwp_set=gwp_set, methane_basis=basis)
        applied_set = gwp_set
        co2e_kg = emissions_kg * applied_gwp

    return EmissionResult(
        activity_id=activity.activity_id,
        factor_id=factor.factor_id,
        scope=activity.scope,
        category=activity.category,
        substance=activity.substance,
        gas=factor.gas,
        activity_value=float(activity.quantity),
        activity_unit=activity.unit,
        factor_value=factor.value,
        factor_unit=factor.unit,
        emissions_kg=emissions_kg,
        gwp=applied_gwp,
        gwp_set=applied_set,
        co2e_kg=co2e_kg,
        source_org=factor.source_org,
        source_reference=factor.source_reference,
        review_status=factor.review_status,
        uncertainty_pct=factor.uncertainty_pct,
    )


def _result_to_dict(result: EmissionResult) -> dict:
    """Convert an EmissionResult dataclass to a plain dict for DataFrame construction."""
    return {
        "activity_id": result.activity_id,
        "factor_id": result.factor_id,
        "scope": result.scope,
        "category": result.category,
        "substance": result.substance,
        "gas": result.gas,
        "activity_value": result.activity_value,
        "activity_unit": result.activity_unit,
        "factor_value": result.factor_value,
        "factor_unit": result.factor_unit,
        "emissions_kg": result.emissions_kg,
        "gwp": result.gwp,
        "gwp_set": result.gwp_set,
        "source_org": result.source_org,
        "source_reference": result.source_reference,
        "review_status": result.review_status,
        "uncertainty_pct": result.uncertainty_pct,
        "co2e_kg": result.co2e_kg,
    }


_BATCH_COLUMNS = [
    "activity_id", "factor_id", "scope", "category", "substance",
    "gas", "activity_value", "activity_unit",
    "factor_value", "factor_unit", "emissions_kg", "gwp",
    "gwp_set", "co2e_kg", "error", "validation_kind",
]


def compute_emissions_batch(
    activities,
    factors,
    *,
    gwp_set: str = DEFAULT_GWP_SET,
    validate: bool = True,
) -> "pd.DataFrame":
    """Compute emissions for **positionally paired** activity/factor records.

    Accepts either a ``list`` of ``ActivityRecord``/``EmissionFactor`` objects
    or ``pandas`` ``DataFrame``s with matching column names. The two inputs are
    paired by position (activity *i* with factor *i*) and must therefore have
    the same length; there is no cross product, because an activity must never
    be paired with an unrelated factor.

    Parameters
    ----------
    activities, factors:
        Lists or DataFrames of the same length.
    gwp_set:
        GWP set to use for gas conversion. Defaults to ``AR6``.
    validate:
        If ``True`` (default), the first failing pair raises its typed
        exception. If ``False``, failures are recorded in the returned frame's
        ``error`` / ``validation_kind`` columns and the remaining pairs still
        compute.

    Returns
    -------
    pd.DataFrame
        One row per pair with all ``EmissionResult`` fields plus ``error`` and
        ``validation_kind`` (empty strings for successful rows).
    """
    import pandas as pd

    activities_list = (
        _activity_dataframe_to_list(activities) if isinstance(activities, pd.DataFrame)
        else list(activities)
    )
    factors_list = (
        _factor_dataframe_to_list(factors) if isinstance(factors, pd.DataFrame)
        else list(factors)
    )
    if len(activities_list) != len(factors_list):
        raise ValueError(
            "activities and factors are paired by position: got "
            f"{len(activities_list)} activities and {len(factors_list)} factors."
        )

    records: list[dict] = []
    for activity, factor in zip(activities_list, factors_list):
        try:
            result = compute_emissions(activity, factor, gwp_set=gwp_set)
        except OpenCarbonChemError as exc:
            if validate:
                raise
            records.append(
                {
                    "activity_id": activity.activity_id,
                    "factor_id": factor.factor_id,
                    "scope": activity.scope,
                    "category": activity.category,
                    "substance": activity.substance,
                    "gas": factor.gas,
                    "activity_value": float(activity.quantity),
                    "activity_unit": activity.unit,
                    "factor_value": factor.value,
                    "factor_unit": factor.unit,
                    "emissions_kg": None,
                    "gwp": None,
                    "gwp_set": None,
                    "co2e_kg": None,
                    "error": str(exc),
                    "validation_kind": type(exc).__name__,
                }
            )
        else:
            records.append({**_result_to_dict(result), "error": "", "validation_kind": ""})

    return pd.DataFrame(records, columns=_BATCH_COLUMNS)


def _activity_dataframe_to_list(df: "pd.DataFrame") -> list[ActivityRecord]:
    """Convert a DataFrame of activity records to ActivityRecord objects.

    Required columns raise on missing/blank values: a silently defaulted scope
    or quantity would change the reported inventory without telling anyone.
    """
    import pandas as pd

    def required(row, column: str, index) -> str:
        value = row.get(column)
        if value is None or pd.isna(value) or not str(value).strip():
            raise ValueError(f"activity row {index}: column {column!r} is required")
        return str(value).strip()

    def optional(row, column: str):
        value = row.get(column)
        return None if value is None or pd.isna(value) else value

    def optional_date(row, column: str, index):
        value = optional(row, column)
        if value is None:
            return None
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            raise ValueError(f"activity row {index}: {column!r} is not a date: {value!r}")
        return parsed.date()

    records: list[ActivityRecord] = []
    for index, row in df.iterrows():
        try:
            scope = int(float(required(row, "scope", index)))
            quantity = float(required(row, "quantity", index))
        except ValueError as exc:
            raise ValueError(f"activity row {index}: {exc}") from exc
        records.append(
            ActivityRecord(
                activity_id=required(row, "activity_id", index),
                description=str(optional(row, "description") or ""),
                scope=scope,
                category=required(row, "category", index),
                substance=required(row, "substance", index),
                quantity=quantity,
                unit=required(row, "unit", index),
                gas=optional(row, "gas"),
                methane_basis=optional(row, "methane_basis"),
                geography=optional(row, "geography") or "GLOBAL",
                data_type=optional(row, "data_type") or "primary",
                period_start=optional_date(row, "period_start", index),
                period_end=optional_date(row, "period_end", index),
                notes=str(optional(row, "notes") or ""),
            )
        )
    return records


def _factor_dataframe_to_list(df: "pd.DataFrame") -> list[EmissionFactor]:
    """Convert a DataFrame of emission factors to EmissionFactor objects."""
    import pandas as pd

    factors: list[EmissionFactor] = []
    for _, row in df.iterrows():
        factors.append(
            EmissionFactor(
                factor_id=str(row["factor_id"]),
                activity_category=str(row["activity_category"]),
                substance=str(row["substance"]),
                value=float(row["value"]),
                unit=str(row["unit"]) if not pd.isna(row.get("unit")) else "",
                gas=str(row["gas"]) if not pd.isna(row.get("gas")) else "",
                reporting_year=int(row["reporting_year"]) if not pd.isna(row.get("reporting_year")) else 2024,
                source_org=row.get("source_org", "SYNTHETIC") if not pd.isna(row.get("source_org")) else "SYNTHETIC",
                source_reference=str(row.get("source_reference", "test")) if not pd.isna(row.get("source_reference")) else "test",
                version=str(row.get("version", "")) if not pd.isna(row.get("version")) else "",
                uncertainty_pct=float(row["uncertainty_pct"]) if row.get("uncertainty_pct") is not None and not pd.isna(row.get("uncertainty_pct")) else None,
                review_status=row.get("review_status", "illustrative") if not pd.isna(row.get("review_status")) else "illustrative",
                methane_basis=row.get("methane_basis") if not pd.isna(row.get("methane_basis")) else None,
                notes=str(row.get("notes", "")) if not pd.isna(row.get("notes")) else "",
            )
        )
    return factors
