"""Emission factor record model.

Every factor carries the full provenance required by the project handover
(§6): identity, activity category, substance, value, unit, gas coverage,
geography, reporting year, source organisation, source reference,
version/publication information, uncertainty where available, review status
and methodological notes.

``review_status`` is the trust gate:

* ``illustrative`` — clearly labelled test/synthetic data. Never presentable
  as an official factor.
* ``published``    — transcribed from a published authoritative source with a
  reference recorded.
* ``verified``     — independently checked against the source document.

The packaged seed CSV contains ``illustrative`` rows only, all with
``source_org=SYNTHETIC``, so software testing never depends on — and never
misrepresents — real-world factors.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

__all__ = ["EmissionFactor"]

ReviewStatus = Literal["illustrative", "published", "verified"]
MethaneBasis = Literal["fossil", "non_fossil"]


class EmissionFactor(BaseModel):
    """One emission factor with complete provenance."""

    model_config = {"extra": "forbid"}

    factor_id: str = Field(min_length=1)
    activity_category: str = Field(min_length=1)
    substance: str = Field(min_length=1, description="Fuel, material or energy type")
    value: float = Field(gt=0, description="Factor magnitude; must be positive")
    unit: str = Field(min_length=1, description="e.g. 'kg CO2/kWh', 'kg CO2e/tkm'")
    gas: str = Field(
        min_length=1,
        description="Gas emitted, or 'CO2e' when the factor is already combined",
    )
    gases_covered: list[str] = Field(
        default_factory=list,
        description="All gases included in the factor (informational coverage)",
    )
    geography: str = "GLOBAL"
    reporting_year: int = Field(ge=1900, le=2100)
    source_org: str = Field(min_length=1, description="Source organisation")
    source_reference: str = Field(
        min_length=1, description="URL, DOI or document reference for the factor"
    )
    version: str = Field(default="", description="Publication/version information")
    uncertainty_pct: float | None = Field(
        default=None, ge=0, le=100, description="Relative uncertainty, %, where available"
    )
    review_status: ReviewStatus = "illustrative"
    methane_basis: MethaneBasis | None = Field(
        default=None,
        description="Required for CH4 factors when the GWP set splits origin",
    )
    notes: str = Field(default="", description="Methodological notes")

    @field_validator("activity_category", "substance", "gas", "geography", "source_org",
                     "source_reference", "factor_id")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("gas")
    @classmethod
    def _gas_label(cls, value: str) -> str:
        if value.upper() not in {"CO2E", "CO2"} and not any(ch.isdigit() for ch in value):
            # Gas labels must be recognisable (CO2, CH4, N2O, HFC-134a, SF6…);
            # a word like "carbon" would silently break GWP lookup later.
            raise ValueError(f"{value!r} is not a gas label")
        return value
