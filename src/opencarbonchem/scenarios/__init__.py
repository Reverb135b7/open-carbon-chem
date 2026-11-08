"""Decarbonisation scenario modelling (milestone 8).

Seven levers transform the inventory as pure functions; the engine recomputes
baseline and scenario totals through the normal calculation engine and reports
absolute and percentage reductions (``None`` when the baseline is zero).
"""

from .engine import (
    LEVER_KINDS,
    Scenario,
    ScenarioResult,
    apply_lever,
    baseline_result,
    compare_scenarios,
    persist_scenarios,
    run_levers,
    scenario_from_kind,
)
from .levers import (
    EnergyEfficiency,
    FuelSwitch,
    Lever,
    MaterialSubstitution,
    ProcessOptimisation,
    RenewableElectricity,
    TransportOptimisation,
    WasteReduction,
    lever_from_kind,
)

__all__ = [
    "LEVER_KINDS",
    "Lever",
    "RenewableElectricity",
    "EnergyEfficiency",
    "FuelSwitch",
    "MaterialSubstitution",
    "WasteReduction",
    "ProcessOptimisation",
    "TransportOptimisation",
    "lever_from_kind",
    "Scenario",
    "ScenarioResult",
    "baseline_result",
    "apply_lever",
    "run_levers",
    "compare_scenarios",
    "scenario_from_kind",
    "persist_scenarios",
]
