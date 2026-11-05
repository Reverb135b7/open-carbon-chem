"""Product Carbon Footprint domain models.

A PCF is defined by a *product*, a *reference flow* (production quantity), a
*system boundary* and a *life-cycle inventory*: the activity-data rows and
emission factors that belong to each production stage.

Boundary rules (ISO 14067 / PAS 2050 vocabulary, implemented explicitly so an
out-of-boundary stage can never be summed by accident):

===================== ============ ============
Stage                 cradle→gate  cradle→grave
===================== ============ ============
raw_materials         included     included
manufacturing         included     included
inbound_transport     included     included
packaging             included     included
waste                 included     included
distribution          excluded     included
use                   excluded     included
end_of_life           excluded     included
===================== ============ ============

Stage names are normalised, so ``"transport"`` is accepted as an alias for
``inbound_transport`` and ``"disposal"`` for ``end_of_life``. An unknown stage
raises :class:`PCFError` — the engine will not guess where an emission belongs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..core.activity import ActivityRecord
from ..core.exceptions import PCFError
from ..factors.models import EmissionFactor

__all__ = [
    "STAGE_CATALOGUE",
    "StageInfo",
    "SystemBoundary",
    "ProductDefinition",
    "InventoryItem",
    "normalise_stage",
    "stages_for_boundary",
]

SystemBoundary = Literal["cradle_to_gate", "cradle_to_grave"]


def _key(text: str) -> str:
    """Alphanumeric-only key so 'end-of-life', 'End Of Life' and 'end_of_life' agree."""
    return re.sub(r"[^a-z0-9]", "", text.strip().lower())


@dataclass(frozen=True)
class StageInfo:
    """One life-cycle stage and the boundaries that include it."""

    key: str
    label: str
    in_cradle_to_gate: bool
    in_cradle_to_grave: bool
    description: str

    def included_in(self, boundary: SystemBoundary) -> bool:
        return self.in_cradle_to_gate if boundary == "cradle_to_gate" else self.in_cradle_to_grave


STAGE_CATALOGUE: dict[str, StageInfo] = {
    "raw_materials": StageInfo(
        "raw_materials", "Raw materials", True, True,
        "Extraction and production of purchased raw materials and feedstocks.",
    ),
    "manufacturing": StageInfo(
        "manufacturing", "Manufacturing energy", True, True,
        "Fuel and electricity consumed to convert raw materials into product.",
    ),
    "inbound_transport": StageInfo(
        "inbound_transport", "Inbound transport", True, True,
        "Transport of raw materials and packaging to the production site.",
    ),
    "packaging": StageInfo(
        "packaging", "Packaging", True, True,
        "Packaging materials that leave the gate with the product.",
    ),
    "waste": StageInfo(
        "waste", "Waste treatment", True, True,
        "Treatment of production waste arising at the manufacturing site.",
    ),
    "distribution": StageInfo(
        "distribution", "Distribution", False, True,
        "Outbound transport and storage from the gate to the customer.",
    ),
    "use": StageInfo(
        "use", "Use phase", False, True,
        "Emissions during the product's use, including required energy carriers.",
    ),
    "end_of_life": StageInfo(
        "end_of_life", "End of life", False, True,
        "Collection, treatment and disposal of the product after use.",
    ),
}

#: Accepted spellings mapped onto catalogue keys.
_STAGE_ALIASES: dict[str, str] = {
    "rawmaterial": "raw_materials",
    "rawmaterials": "raw_materials",
    "materials": "raw_materials",
    "manufacturing": "manufacturing",
    "manufacturingenergy": "manufacturing",
    "production": "manufacturing",
    "process": "manufacturing",
    "inboundtransport": "inbound_transport",
    "transport": "inbound_transport",
    "transportation": "inbound_transport",
    "upstreamtransport": "inbound_transport",
    "packaging": "packaging",
    "packing": "packaging",
    "waste": "waste",
    "wastetreatment": "waste",
    "distribution": "distribution",
    "outboundtransport": "distribution",
    "downstreamtransport": "distribution",
    "use": "use",
    "usephase": "use",
    "endoflife": "end_of_life",
    "disposal": "end_of_life",
    "eol": "end_of_life",
}


def normalise_stage(stage: str) -> str:
    """Map a user-supplied stage name onto a catalogue key."""
    resolved = _STAGE_ALIASES.get(_key(stage))
    if resolved is None:
        allowed = ", ".join(sorted(STAGE_CATALOGUE))
        raise PCFError(f"Unknown life-cycle stage {stage!r}. Allowed stages: {allowed}.")
    return resolved


def stages_for_boundary(boundary: SystemBoundary) -> tuple[str, ...]:
    """Stage keys included in ``boundary``, in catalogue order."""
    if boundary not in ("cradle_to_gate", "cradle_to_grave"):
        raise PCFError(
            f"Unknown system boundary {boundary!r}; expected 'cradle_to_gate' or 'cradle_to_grave'."
        )
    return tuple(k for k, info in STAGE_CATALOGUE.items() if info.included_in(boundary))


class ProductDefinition(BaseModel):
    """The product, its reference flow and its declared system boundary."""

    model_config = {"extra": "forbid"}

    pcf_id: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    functional_unit: str = Field(
        min_length=1,
        description="Declared functional unit, e.g. '1 tonne of product at the factory gate'",
    )
    production_qty: float = Field(
        gt=0, description="Reference flow: quantity of product the inventory relates to"
    )
    production_unit: str = Field(min_length=1, description="e.g. 't', 'kg', 'm3'")
    system_boundary: SystemBoundary = "cradle_to_gate"
    notes: str = ""

    @field_validator("pcf_id", "product_name", "functional_unit", "production_unit")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @model_validator(mode="after")
    def _boundary_known(self) -> "ProductDefinition":
        if self.system_boundary not in ("cradle_to_gate", "cradle_to_grave"):
            raise PCFError(f"{self.pcf_id}: unknown system boundary {self.system_boundary!r}")
        return self

    @property
    def included_stages(self) -> tuple[str, ...]:
        return stages_for_boundary(self.system_boundary)


class InventoryItem(BaseModel):
    """One life-cycle inventory line: activity data × emission factor in a stage.

    ``excluded_from_corporate`` states whether this contribution is *absent* from
    the organisation's corporate inventory (typical for purchased raw materials
    reported as Scope 3 upstream, or for use-phase emissions). The flag is used
    by the double-counting guard in :mod:`opencarbonchem.pcf.calculator`.
    """

    model_config = {"extra": "forbid"}

    stage: str = Field(min_length=1)
    activity: ActivityRecord
    factor: EmissionFactor
    excluded_from_corporate: bool = False
    notes: str = ""

    @field_validator("stage")
    @classmethod
    def _stage_known(cls, value: str) -> str:
        return normalise_stage(value)

    @property
    def activity_id(self) -> str:
        return self.activity.activity_id

    @property
    def factor_id(self) -> str:
        return self.factor.factor_id
