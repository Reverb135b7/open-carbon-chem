"""Activity data model.

Activity data is the measured input to every calculation: a quantity of fuel,
energy, material, transport or waste, with an explicit unit, reporting period,
geography and a flag stating whether it is measured primary data or a secondary
estimate. Construction validates the record; invalid data fails immediately
rather than surfacing later as a wrong number.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .exceptions import OpenCarbonChemError, PeriodError

__all__ = ["ActivityRecord", "load_activities_csv"]

Scope = Literal[1, 2, 3]
DataType = Literal["primary", "secondary"]
MethaneBasis = Literal["fossil", "non_fossil"]


class ActivityRecord(BaseModel):
    """A single activity-data record.

    ``category`` is engine vocabulary:

    * scope 1 — ``stationary_combustion``, ``mobile_combustion``,
      ``fugitive_emissions``, ``process_emissions``
    * scope 2 — ``purchased_electricity``, ``purchased_steam``,
      ``purchased_heat``, ``purchased_cooling``
    * scope 3 — ``s3_cat01`` … ``s3_cat15`` (GHG Protocol's 15 categories)
    """

    model_config = {"extra": "forbid"}

    activity_id: str = Field(min_length=1)
    description: str = ""
    scope: Scope
    category: str = Field(min_length=1)
    substance: str = Field(min_length=1, description="Fuel, material or energy type")
    quantity: float = Field(ge=0, description="Activity data magnitude; must be finite and non-negative")
    unit: str = Field(min_length=1)
    gas: str | None = Field(
        default=None,
        description="Gas emitted (CO2, CH4, N2O, CO2e…); required when the "
        "substance has factors for more than one gas",
    )
    methane_basis: MethaneBasis | None = None
    geography: str = "GLOBAL"
    data_type: DataType = "primary"
    period_start: date | None = None
    period_end: date | None = None
    notes: str = ""

    @field_validator("quantity")
    @classmethod
    def _finite(cls, value: float) -> float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("quantity must be a finite number")
        return value

    @field_validator("unit", "category", "substance", "activity_id")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @model_validator(mode="after")
    def _period_ordered(self) -> "ActivityRecord":
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise PeriodError(
                f"{self.activity_id}: period_start {self.period_start} is after "
                f"period_end {self.period_end}"
            )
        if self.gas and self.gas.upper() == "CH4" and self.methane_basis is None:
            # Allowed here (the factor may carry the basis); the engine still
            # refuses to compute without one. See core/gwp.py.
            pass
        return self

    @property
    def reporting_year(self) -> int | None:
        """Year used for emission-factor vintage selection, if determinable."""
        if self.period_start is not None:
            return self.period_start.year
        if self.period_end is not None:
            return self.period_end.year
        return None


def load_activities_csv(path: str | Path) -> list[ActivityRecord]:
    """Load activity records from a CSV whose columns match :class:`ActivityRecord`.

    A malformed row is a hard error naming its line: silently skipping or
    defaulting a row would drop or alter activity data without telling anyone.
    """
    def text(row: dict, column: str) -> str:
        return (row.get(column) or "").strip()

    def optional_date(row: dict, column: str) -> date | None:
        value = text(row, column)
        return date.fromisoformat(value) if value else None

    records: list[ActivityRecord] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            try:
                records.append(
                    ActivityRecord(
                        activity_id=text(row, "activity_id"),
                        description=text(row, "description"),
                        scope=int(text(row, "scope")),
                        category=text(row, "category"),
                        substance=text(row, "substance"),
                        quantity=float(text(row, "quantity")),
                        unit=text(row, "unit"),
                        gas=text(row, "gas") or None,
                        methane_basis=text(row, "methane_basis") or None,
                        geography=text(row, "geography") or "GLOBAL",
                        data_type=text(row, "data_type") or "primary",
                        period_start=optional_date(row, "period_start"),
                        period_end=optional_date(row, "period_end"),
                        notes=text(row, "notes"),
                    )
                )
            except (OpenCarbonChemError, ValueError, TypeError) as exc:
                raise ValueError(f"{path} line {line_no}: {exc}") from exc
    return records
