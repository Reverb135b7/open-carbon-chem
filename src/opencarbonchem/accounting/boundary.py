"""Organisational boundary definition and consolidation (GHG Protocol chapter 3).

The boundary is a first-class, documentable object: which entities are inside
the corporate group, which consolidation method applies, and what share of
each entity the organisation reports. Consolidation never guesses — a method
decides the weight, and every entity in the boundary must contribute to the
consolidated total so a partially populated inventory cannot be presented as
complete.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..core.exceptions import BoundaryError

__all__ = ["CONSOLIDATION_METHODS", "BoundaryEntity", "OrganisationalBoundary"]

CONSOLIDATION_METHODS: tuple[str, ...] = (
    "operational_control",
    "financial_control",
    "equity_share",
)


@dataclass(frozen=True)
class BoundaryEntity:
    """One entity (subsidiary, JV or facility) inside the boundary."""

    entity_id: str
    name: str
    equity_share: float = 1.0
    geography: str = "GLOBAL"
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.entity_id.strip():
            raise BoundaryError("boundary entity requires a non-empty entity_id")
        if not self.name.strip():
            raise BoundaryError(f"boundary entity {self.entity_id!r} requires a name")
        if not 0.0 < self.equity_share <= 1.0:
            raise BoundaryError(
                f"boundary entity {self.entity_id!r}: equity_share must be in (0, 1], "
                f"got {self.equity_share}"
            )


@dataclass(frozen=True)
class OrganisationalBoundary:
    """Documented corporate boundary: consolidation method plus its entities.

    Consolidation rules:
    - ``operational_control`` / ``financial_control``: report 100% of every
      entity the organisation controls (equity shares are documented but do
      not weight the total).
    - ``equity_share``: report the organisation's equity share of each
      entity's emissions.
    """

    org_id: str
    name: str
    method: str
    entities: tuple[BoundaryEntity, ...]
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.org_id.strip():
            raise BoundaryError("boundary requires a non-empty org_id")
        if not self.name.strip():
            raise BoundaryError(f"boundary {self.org_id!r} requires a name")
        if self.method not in CONSOLIDATION_METHODS:
            raise BoundaryError(
                f"unknown consolidation method {self.method!r}; "
                f"choose one of {', '.join(CONSOLIDATION_METHODS)}"
            )
        if not self.entities:
            raise BoundaryError(
                f"boundary {self.org_id!r} must list at least one entity"
            )
        seen: set[str] = set()
        duplicates: set[str] = set()
        for entity in self.entities:
            if entity.entity_id in seen:
                duplicates.add(entity.entity_id)
            seen.add(entity.entity_id)
        if duplicates:
            raise BoundaryError(
                f"boundary {self.org_id!r} has duplicate entity ids: "
                f"{', '.join(sorted(duplicates))}"
            )

    def weight_for(self, entity_id: str) -> float:
        """Reporting weight for one entity under the chosen method."""
        for entity in self.entities:
            if entity.entity_id == entity_id:
                return entity.equity_share if self.method == "equity_share" else 1.0
        raise BoundaryError(
            f"entity {entity_id!r} is not part of boundary {self.org_id!r}"
        )

    def consolidate(self, emissions_by_entity: Mapping[str, float]) -> float:
        """Weighted organisation total (kg CO2e) for this boundary.

        Every boundary entity must appear in ``emissions_by_entity`` (pass an
        explicit ``0.0`` for a genuine zero) and no unknown entity may
        contribute — this prevents a partially populated inventory from being
        silently reported as complete.
        """
        known = {e.entity_id for e in self.entities}
        given = set(emissions_by_entity)
        unknown = given - known
        if unknown:
            raise BoundaryError(
                f"emissions supplied for entities outside boundary {self.org_id!r}: "
                f"{', '.join(sorted(unknown))}"
            )
        missing = known - given
        if missing:
            raise BoundaryError(
                f"boundary {self.org_id!r} has no emissions entry for: "
                f"{', '.join(sorted(missing))} (pass 0.0 explicitly if truly zero)"
            )
        total = 0.0
        for entity in self.entities:
            value = emissions_by_entity[entity.entity_id]
            if value < 0:
                raise BoundaryError(
                    f"entity {entity.entity_id!r}: emissions must be >= 0, got {value}"
                )
            total += value * self.weight_for(entity.entity_id)
        return total

    def document(self) -> dict:
        """Structured payload for the report's boundary appendix (handover §7)."""
        return {
            "org_id": self.org_id,
            "name": self.name,
            "method": self.method,
            "entities": [
                {
                    "entity_id": e.entity_id,
                    "name": e.name,
                    "equity_share": e.equity_share,
                    "reporting_weight": self.weight_for(e.entity_id),
                    "geography": e.geography,
                    "notes": e.notes,
                }
                for e in self.entities
            ],
            "notes": self.notes,
        }
