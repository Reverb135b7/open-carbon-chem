"""Inventory entries: activity data paired with the factor that applies to it.

An *inventory entry* is the unit of work shared by every higher-level module:
corporate accounting, PCF, sensitivity, Monte Carlo and scenarios all operate on
the same ``(ActivityRecord, EmissionFactor)`` pairs and always recompute through
:func:`opencarbonchem.core.calc.compute_emissions`. Keeping the alias here (in
``core``) means no higher layer needs to import another higher layer.
"""

from __future__ import annotations

from typing import Iterable

from ..factors.models import EmissionFactor
from .activity import ActivityRecord
from .calc import EmissionResult, compute_emissions
from .exceptions import AnalyticsError
from .gwp import DEFAULT_GWP_SET

__all__ = ["InventoryEntry", "validate_entries", "base_rows"]

InventoryEntry = tuple[ActivityRecord, EmissionFactor]


def validate_entries(entries: Iterable[InventoryEntry]) -> tuple[InventoryEntry, ...]:
    """Return the entries as a tuple, rejecting empty input and duplicate activity IDs."""
    materialised = tuple(entries)
    if not materialised:
        raise AnalyticsError("At least one inventory entry (activity + factor) is required.")
    seen: set[str] = set()
    for activity, _factor in materialised:
        if activity.activity_id in seen:
            raise AnalyticsError(
                f"Duplicate activity_id {activity.activity_id!r}: analysis targets rows by "
                "activity ID, so IDs must be unique."
            )
        seen.add(activity.activity_id)
    return materialised


def base_rows(
    entries: tuple[InventoryEntry, ...], gwp_set: str = DEFAULT_GWP_SET
) -> tuple[EmissionResult, ...]:
    """Compute the unperturbed emission rows through the normal engine."""
    return tuple(
        compute_emissions(activity, factor, gwp_set=gwp_set) for activity, factor in entries
    )
