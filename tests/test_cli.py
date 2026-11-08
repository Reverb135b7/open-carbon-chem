"""Milestone 10 — CLI entry point tests.

The console script must work when installed as ``opencarbonchem``: it is a thin
client that loads CSV input, delegates to the accounting API and writes reports.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from opencarbonchem.cli import calculate_inventory, load_activities, main
from opencarbonchem.core.exceptions import MissingFactorError
from opencarbonchem.factors import FactorRegistry

pytestmark = pytest.mark.unit

HEADER = [
    "activity_id", "description", "scope", "category", "substance", "quantity",
    "unit", "gas", "methane_basis", "geography", "data_type", "period_start",
    "period_end", "notes",
]

ROWS = [
    ["A-GAS", "Boiler", "1", "stationary_combustion", "natural_gas", "1000",
     "kWh", "CO2", "", "GLOBAL", "primary", "2024-01-01", "2024-12-31", "SYNTHETIC"],
    ["A-ELEC", "Grid supply", "2", "purchased_electricity", "grid_electricity", "1000",
     "kWh", "CO2e", "", "GLOBAL", "secondary", "2024-01-01", "2024-12-31", "SYNTHETIC"],
    ["A-PAPER", "Packaging", "3", "s3_cat01", "paper", "1000",
     "kg", "", "", "GLOBAL", "secondary", "2024-01-01", "2024-12-31", "SYNTHETIC"],
]


def write_csv(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


@pytest.fixture
def activities_csv(tmp_path: Path) -> Path:
    return write_csv(tmp_path / "activities.csv", ROWS)


def test_load_activities_parses_every_field(activities_csv):
    activities = load_activities(activities_csv)
    assert len(activities) == 3
    assert activities[0].activity_id == "A-GAS"
    assert activities[0].period_start.isoformat() == "2024-01-01"
    assert activities[1].scope == 2
    assert activities[1].data_type == "secondary"


def test_load_activities_rejects_a_malformed_row(tmp_path):
    bad = write_csv(tmp_path / "bad.csv", [["A-X", "", "1", "stationary_combustion",
                                            "natural_gas", "not-a-number", "kWh", "", "",
                                            "GLOBAL", "primary", "", "", ""]])
    with pytest.raises(ValueError, match="line 2"):
        load_activities(bad)


def test_calculate_inventory_rolls_up_all_three_scopes(activities_csv):
    registry = FactorRegistry.from_csv()
    report, rows = calculate_inventory(load_activities(activities_csv), registry)
    # Hand check: 180 + 450 + 1200 = 1830 kg.
    assert report.total_kg == pytest.approx(1830.0)
    assert report.by_scope() == {
        1: pytest.approx(180.0),
        2: pytest.approx(450.0),
        3: pytest.approx(1200.0),
    }
    assert len(rows) == 3
    assert report.reconcile().ok


def test_main_writes_both_reports(activities_csv, tmp_path):
    out = tmp_path / "reports"
    exit_code = main([
        "calculate",
        "--activities", str(activities_csv),
        "--run-id", "cli-test",
        "--out", str(out),
        "--period-label", "2024",
    ])
    assert exit_code == 0
    assert (out / "cli-test.xlsx").exists()
    assert (out / "cli-test.pdf").exists()


def test_main_writes_only_the_requested_report(activities_csv, tmp_path):
    out = tmp_path / "reports"
    assert main([
        "calculate", "--activities", str(activities_csv), "--run-id", "only-excel",
        "--out", str(out), "--report-types", "excel",
    ]) == 0
    assert (out / "only-excel.xlsx").exists()
    assert not (out / "only-excel.pdf").exists()


def test_main_returns_one_without_a_subcommand():
    assert main([]) == 1


def test_main_reports_bad_input_without_a_traceback(tmp_path):
    bad = write_csv(tmp_path / "bad.csv", [["A-X", "", "1", "stationary_combustion",
                                             "natural_gas", "oops", "kWh", "", "",
                                             "GLOBAL", "primary", "", "", ""]])
    assert main(["calculate", "--activities", str(bad), "--run-id", "x"]) == 2


def test_main_returns_two_when_a_factor_is_missing(tmp_path):
    rows = [["A-UNKNOWN", "", "1", "stationary_combustion", "unobtainium", "10",
             "kWh", "", "", "GLOBAL", "primary", "", "", ""]]
    path = write_csv(tmp_path / "unknown.csv", rows)
    assert main(["calculate", "--activities", str(path), "--run-id", "x",
                 "--report-types", "excel", "--out", str(tmp_path)]) == 2


def test_missing_factor_is_the_documented_error_type():
    registry = FactorRegistry.from_csv()
    with pytest.raises(MissingFactorError):
        registry.find(activity_category="stationary_combustion", substance="unobtainium")
