"""Decarbonisation scenario engine: baseline vs scenario comparison.

The engine recomputes totals through the same calculation engine
(:func:`opencarbonchem.core.calc.compute_emissions`), so there is no
hand-rolled arithmetic that can drift from the accounting methodology.

Reduction formulas (architecture §2.1)::

    Reduction      = Baseline − Scenario
    Reduction (%)  = Reduction / Baseline × 100

Fail-safe rules:

* A zero baseline cannot yield a percentage — ``reduction_pct`` is ``None``,
  never 0 % and never infinity.
* A lever that matches no inventory rows raises :class:`ScenarioError` upstream
  in :mod:`opencarbonchem.scenarios.levers`; modelling nothing would let a user
  publish a "reduction" that was never applied.
* A lever that *increases* emissions reports a negative reduction. The engine
  never hides an adverse result.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from typing import Iterable

from ..core.exceptions import ScenarioError
from ..core.gwp import DEFAULT_GWP_SET
from ..core.inventory import InventoryEntry, base_rows, validate_entries
from .levers import LEVER_KINDS, Lever, lever_from_kind

__all__ = [
    "ScenarioResult",
    "Scenario",
    "baseline_result",
    "apply_lever",
    "run_levers",
    "compare_scenarios",
    "scenario_from_kind",
    "persist_scenarios",
    "LEVER_KINDS",
]


@dataclass(frozen=True)
class ScenarioResult:
    """Outcome of one scenario run: a baseline total and the scenario total."""

    name: str
    lever: str
    baseline_kg: float
    scenario_kg: float
    reduction_kg: float
    reduction_pct: float | None

    @property
    def total_kg(self) -> float:
        """The scenario's CO2e total (kg)."""
        return self.scenario_kg

    @property
    def changed(self) -> bool:
        """True when the lever actually moved the total."""
        return self.scenario_kg != self.baseline_kg

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "lever": self.lever,
            "baseline_kg": self.baseline_kg,
            "scenario_kg": self.scenario_kg,
            "reduction_kg": self.reduction_kg,
            "reduction_pct": self.reduction_pct,
        }


def _total_kg(entries: Iterable[InventoryEntry], gwp_set: str) -> float:
    return sum(row.co2e_kg for row in base_rows(tuple(entries), gwp_set))


def _percent(reduction_kg: float, baseline_kg: float) -> float | None:
    """Reduction as a percentage of the baseline, or ``None`` when undefined."""
    if baseline_kg <= 0:
        return None
    return reduction_kg / baseline_kg * 100.0


def baseline_result(
    entries: Iterable[InventoryEntry], *, gwp_set: str = DEFAULT_GWP_SET
) -> ScenarioResult:
    """The unmodified inventory total, used as the comparison baseline."""
    validated = validate_entries(entries)
    total = _total_kg(validated, gwp_set)
    return ScenarioResult(
        name="Baseline",
        lever="baseline",
        baseline_kg=total,
        scenario_kg=total,
        reduction_kg=0.0,
        reduction_pct=0.0 if total > 0 else None,
    )


def apply_lever(
    lever: Lever,
    entries: Iterable[InventoryEntry],
    *,
    gwp_set: str = DEFAULT_GWP_SET,
) -> ScenarioResult:
    """Apply ``lever`` to ``entries`` and recompute both totals.

    The transformed inventory is recomputed through the normal engine. A lever
    that removes every row (e.g. 100 % renewable electricity with a zero
    residual factor) legitimately yields a scenario total of ``0.0``.
    """
    validated = validate_entries(entries)
    baseline_kg = _total_kg(validated, gwp_set)

    transformed = tuple(lever.apply(validated))
    scenario_kg = sum(row.co2e_kg for row in base_rows(transformed, gwp_set))

    reduction_kg = baseline_kg - scenario_kg
    return ScenarioResult(
        name=f"{lever.name} scenario",
        lever=lever.kind,
        baseline_kg=baseline_kg,
        scenario_kg=scenario_kg,
        reduction_kg=reduction_kg,
        reduction_pct=_percent(reduction_kg, baseline_kg),
    )


@dataclass(frozen=True)
class Scenario:
    """A named lever application, so results carry a meaningful label."""

    name: str
    lever: Lever

    def apply_to(
        self, entries: Iterable[InventoryEntry], *, gwp_set: str = DEFAULT_GWP_SET
    ) -> ScenarioResult:
        result = apply_lever(self.lever, entries, gwp_set=gwp_set)
        return replace(result, name=self.name)


def run_levers(
    entries: Iterable[InventoryEntry],
    levers: Iterable[Lever],
    *,
    gwp_set: str = DEFAULT_GWP_SET,
) -> tuple[ScenarioResult, ...]:
    """Baseline followed by one result per lever (dashboard/report order)."""
    validated = validate_entries(entries)
    results = [baseline_result(validated, gwp_set=gwp_set)]
    results.extend(apply_lever(lever, validated, gwp_set=gwp_set) for lever in levers)
    return tuple(results)


def compare_scenarios(
    baseline: ScenarioResult, alternative: ScenarioResult
) -> dict:
    """Absolute and percentage change from ``baseline`` to ``alternative``."""
    baseline_kg = baseline.scenario_kg
    alternative_kg = alternative.scenario_kg
    reduction_kg = baseline_kg - alternative_kg
    return {
        "baseline_kg": baseline_kg,
        "alternative_kg": alternative_kg,
        "reduction_kg": reduction_kg,
        "reduction_pct": _percent(reduction_kg, baseline_kg),
        "status": "compared" if baseline_kg > 0 else "baseline_is_zero",
    }


def scenario_from_kind(kind: str, **kwargs: object) -> Lever:
    """Build a lever from its kind string (used by the UI and persistence)."""
    return lever_from_kind(kind)(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def persist_scenarios(
    db,
    run_id: str,
    results: Iterable[ScenarioResult],
    period_id: str | None = None,
    *,
    gwp_set: str = DEFAULT_GWP_SET,
) -> None:
    """Store scenario headers and their results under one calculation run.

    ``run_id`` must be new: re-using an existing run would silently overwrite
    the audit trail of an earlier calculation.
    """
    materialised = tuple(results)
    if not materialised:
        raise ScenarioError("no scenario results to persist")

    try:
        db.start_run(run_id, gwp_set, period_id)
    except sqlite3.IntegrityError as exc:
        raise ScenarioError(
            f"calculation run {run_id!r} already exists; choose a new run id "
            "so earlier results are not overwritten"
        ) from exc

    for result in materialised:
        db.save_scenario(
            scenario_id=result.name,
            name=result.name,
            lever=result.lever,
            description=(
                f"SYNTHETIC scenario run {run_id}: baseline "
                f"{result.baseline_kg:.3f} kg -> scenario "
                f"{result.scenario_kg:.3f} kg CO2e"
            ),
        )

    db.save_scenario_results(
        run_id,
        [
            (result.name, "", result.baseline_kg, result.scenario_kg, result.reduction_kg)
            for result in materialised
        ],
    )
