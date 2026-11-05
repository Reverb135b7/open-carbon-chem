"""Decarbonisation scenario engine: baseline vs scenario comparison.

The engine recomputes totals through the same accounting engine, so there is
no hand-rolled math that can drift from the calculation methodology.

Baseline and scenario runs are persisted through ``CarbonDatabase`` and the
reduction formulas (architecture §2.1) are applied automatically:

    Reduction      = Baseline − Scenario
    Reduction (%)  = Reduction / Baseline × 100

Fail-safe: a zero baseline produces ``delta_pct = None``, never 0 % or inf.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..accounting.aggregate import OrganizationReport
from ..core.calc import EmissionResult, compute_emissions
from ..core.exceptions import ScenarioError
from ..core.gwp import DEFAULT_GWP_SET
from ..factors.models import EmissionFactor
from ..scenarios.levers import (
    EnergyEfficiency,
    FuelSwitch,
    Lever,
    MaterialSubstitution,
    ProcessOptimisation,
    RenewableElectricity,
    TransportOptimisation,
    WasteReduction,
    LEVER_KINDS,
    lever_from_kind,
)
from ..database import CarbonDatabase
from .models import AllocationRule


__all__ = [
    "ScenarioResult",
    "Scenario",
    "ScenarioEngine",
    "apply_lever",
    "compare_scenarios",
]


@dataclass(frozen=True)
class ScenarioResult:
    """Outcome of one scenario run (baseline or alternative)."""

    name: str
    baseline_kg: float
    scenario_kg: float
    reduction_kg: float
    reduction_pct: float | None

    @property
    def kind(self) -> str:
        # 'baseline' means the original run with no lever applied
        return self.name.split()[0].lower() if self.name else "unknown"


@dataclass(frozen=True)
class Scenario:
    """A named scenario that applies a single lever to the baseline entries."""

    name: str
    kind: str = ""
    lever: Lever | None = None

    def apply_to(
        self,
        baseline_entries: Iterable[InventoryEntry],
        gwp_set: str = DEFAULT_GWP_SET,
    ) -> ScenarioResult:
        if self.lever is None:
            raise ScenarioError("Scenario has no lever attached.")

        materialised = InventoryEntry.validate_entries(baseline_entries)
        results = InventoryEntry.base_rows(materialised, gwp_set)
        baseline_kg = sum(r.co2e_kg for r in results)

        # Apply the lever; if it raises ScenarioError, the caller should
        // catch it and inform the user.
        try:
            after = self.lever.apply(baseline_entries)
        except ScenarioError:
            raise

        # Recompute totals after the transformation.
        updated = InventoryEntry.validate_entries(after)
        updated_results = InventoryEntry.base_rows(updated, gwp_set)
        scenario_kg = sum(r.co2e_kg for r in updated_results)

        reduction_kg = baseline_kg - scenario_kg
        reduction_pct = (reduction_kg / baseline_kg * 100.0) if baseline_kg > 0 else None

        return ScenarioResult(
            name=self.name if self.name else "unnamed scenario",
            baseline_kg=baseline_kg,
            scenario_kg=scenario_kg,
            reduction_kg=reduction_kg,
            reduction_pct=reduction_pct,
        )


def apply_lever(
    lever: Lever,
    entries: Iterable[InventoryEntry],
    gwp_set: str = DEFAULT_GWP_SET,
) -> ScenarioResult:
    """Convenience wrapper that creates an empty-scenario and applies the lever."""
    return Scenario(name=f"{lever.name} scenario", lever=lever).apply_to(entries, gwp_set)


def compare_scenarios(
    baseline: ScenarioResult,
    alternative: ScenarioResult,
) -> dict:
    """Return absolute and % reductions between two ScenarioResults."""
    if baseline.baseline_kg == 0:
        return {
            "baseline_kg": baseline.baseline_kg,
            "alternative_kg": alternative.scenario_kg,
            "reduction_kg": None,
            "reduction_pct": None,
            "status": "baseline_is_zero",
        }

    reduction_kg = baseline.baseline_kg - alternative.scenario_kg
    reduction_pct = (reduction_kg / baseline.baseline_kg * 100.0) if baseline.baseline_kg > 0 else None

    status = (
        "compared"
        if reduction_kg is not None and reduction_pct is not None
        else ("partial" if reduction_kg is None else "no_data")
    )

    return {
        "baseline_kg": baseline.baseline_kg,
        "alternative_kg": alternative.scenario_kg,
        "reduction_kg": reduction_kg,
        "reduction_pct": reduction_pct,
        "status": status,
    }


def engine_run(
    entries: Iterable[InventoryEntry],
    gwp_set: str = DEFAULT_GWP_SET,
    lever: Lever | None = None,
    lever_name: str | None = None,
) -> tuple[ScenarioResult, ...]:
    """Run a full baseline (optional lever) and return one ScenarioResult per lever."""
    materialised = InventoryEntry.validate_entries(entries)
    results = InventoryEntry.base_rows(materialised, gwp_set)
    baseline_kg = sum(r.co2e_kg for r in results)

    results: list[ScenarioResult] = []

    # Always include the baseline with no lever.
    results.append(
        ScenarioResult(
            name="baseline",
            baseline_kg=baseline_kg,
            scenario_kg=baseline_kg,
            reduction_kg=0.0,
            reduction_pct=0.0,
        )
    )

    if lever is not None:
        scenario = Scenario(name=lever_name or lever.name, lever=lever)
        try:
            res = scenario.apply_to(entries, gwp_set)
            results.append(res)
        except ScenarioError as exc:
            # Record it so the UI can show "this lever does not apply".
            results.append(
                ScenarioResult(
                    name=lever.name,
                    baseline_kg=baseline_kg,
                    scenario_kg=baseline_kg,
                    reduction_kg=None,
                    reduction_pct=None,
                )
            )
    else:
        # No lever specified – just the baseline.
        pass

    return tuple(results)


def scenario_from_kind(
    kind: str,
    **kwargs,
) -> Lever:
    """Factory: map a kind string to a lever class with keyword overrides."""
    cls = lever_from_kind(kind)
    # The dataclass constructor fills missing fields with defaults; we re-inject
    # the user-supplied kwargs (or the default from __post_init__).
    return cls(**kwargs)


# --------------------------------------------------------------------------- #
# Persistence helpers
# --------------------------------------------------------------------------- #
def save_scenario_results(
    db: CarbonDatabase,
    run_id: str,
    period_id: str,
    results: Iterable[ScenarioResult],
    gwp_set: str = DEFAULT_GWP_SET,
) -> None:
    """Persist ``results`` in ``scenario_results``; the run already exists."""
    db.start_run(run_id, gwp_set, period_id)
    db.save_results(run_id, [row for r in results for row in []])  # placeholder
    # NOTE: scenario results have their own table (schema.sql §5); the engine
    # engine that persisted via `save_scope_result` / `save_results` is not
    # designed for ``ScenarioResult`` — this is a hand-crafted extension.
    with db._conn:
        db._conn.execute("DELETE FROM scenario_results WHERE run_id = ?", (run_id,))
    for result in results:
        db._conn.execute(
            """
            INSERT INTO scenario_results
                (scenario_id, run_id, category, baseline_kg, scenario_kg, reduction_kg)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result.name,
                run_id,
                "",  # category not broken down here; future work
                result.baseline_kg,
                result.scenario_kg,
                result.reduction_kg,
            ),
        )
    db._conn.commit()