"""CLI entry point for OpenCarbonChem.

Thin client (N3) that delegates to the package API.

Usage
-----
    opencarbonchem calculate --activities data/raw/synthetic/activities_synthetic.csv
        --out run-2024-01 --gwp-set AR6
    opencarbonchem --help
"""

from __future__ import annotations

import sys
import argparse
import csv
import traceback

from ..database import CarbonDatabase
from ..factors import FactorRegistry
from ..core.activity import ActivityRecord
from ..core.calc import compute_emissions
from ..accounting.aggregate import calculate_scope1, OrganizationReport, ScopeResult
from ..reporting.excel_workbook import build_excel_report
from ..reporting.pdf_generator import build_pdf_report
from ..reporting.__init__ import __all__ as reporting_all

__all__ = ["main"]


def _load_activities(csv_path: str) -> list[ActivityRecord]:
    """Load activities from a CSV file whose columns match ``ActivityRecord`` fields."""
    activities: list[ActivityRecord] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                a = ActivityRecord(
                    activity_id=row.get("activity_id", "").strip(),
                    scope=int(row.get("scope", "1").strip()) if row.get("scope") else 1,
                    category=row.get("category", "").strip() or "stationary_combustion",
                    substance=row.get("substance", "").strip() or "natural_gas",
                    quantity=float(row.get("quantity", "0").strip() or "0"),
                    unit=row.get("unit", "").strip() or "kWh",
                    gas=row.get("gas", "").strip() or None,
                    period_start=None
                    if not row.get("period_start", "").strip()
                    else None,  # simplified: no date parsing
                    period_end=None
                    if not row.get("period_end", "").strip()
                    else None,  # simplified
                    data_type=row.get("data_type", "primary").strip() or "primary",
                    notes=row.get("notes", "").strip() or "",
                )
                activities.append(a)
            except Exception as exc:
                print(f"Skipping row due to error: {exc}", file=sys.stderr)
    return activities


def _load_factors(csv_path: str | None) -> FactorRegistry:
    """Load emission factors from the packaged seed CSV; fall back to default."""
    default_path = "src/opencarbonchem/factors/data/illustrative_factors.csv"
    path = csv_path or default_path
    try:
        return FactorRegistry.from_csv(path)
    except Exception:
        # fallback to in-memory default factors
        from ..factors import FactorRegistry as FR
        return FR.from_csv()


def _run_calculation(
    activities: list[ActivityRecord], factors: FactorRegistry, gwp_set: str
) -> tuple[list, OrganizationReport]:
    """Run Scope 1 calculation and return results + organisation report."""
    scope1_results = calculate_scope1(activities, factors)
    report = OrganizationReport.from_results([scope1_results])
    return scope1_results.results, report


def _run_excel(
    activities: list[ActivityRecord],
    factors: FactorRegistry,
    gwp_set: str,
    run_id: str,
    period_label: str,
) -> None:
    """Run calculation and emit an Excel workbook."""
    results, report = _run_calculation(activities, factors, gwp_set)
    excel = build_excel_report(
        report,
        results,
        gwp_set=gwp_set,
        run_id=run_id,
        period_label=period_label,
    )
    out_path = f"{run_id}.xlsx"
    excel.save(out_path)
    print(f"Excel report written to {out_path}")


def _run_pdf(
    activities: list[ActivityRecord],
    factors: FactorRegistry,
    gwp_set: str,
    run_id: str,
    period_label: str,
    organisation_name: str = "OpenCarbonChem Demo",
) -> None:
    """Run calculation and emit a PDF executive summary."""
    results, report = _run_calculation(activities, factors, gwp_set)
    pdf = build_pdf_report(
        report,
        results,
        gwp_set=gwp_set,
        run_id=run_id,
        period_label=period_label,
        organisation_name=organisation_name,
    )
    out_path = f"{run_id}.pdf"
    pdf.save(out_path)
    print(f"PDF report written to {out_path}")


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``opencarbonchem`` console script."""
    parser = argparse.ArgumentParser(
        prog="opencarbonchem",
        description="OpenCarbonChem — carbon accounting and sustainability analytics",
    )
    sub = parser.add_subparsers(dest="command")

    # ---- calculate ---- #
    calc_parser = sub.add_parser("calculate", help="Run calculation and emit reports")
    calc_parser.add_argument(
        "--activities",
        required=True,
        help="Path to CSV file with activity data (see --help for expected columns)",
    )
    calc_parser.add_argument(
        "--gwp-set",
        default="AR6",
        help="GWP set to use (AR6, AR5, AR6-ERRATA-2025)",
    )
    calc_parser.add_argument(
        "--run-id",
        required=True,
        help="Identifier for the calculation run (used as output filename prefix)",
    )
    calc_parser.add_argument(
        "--period-label",
        default="",
        help="Label for the reporting period (e.g. '2024-01-01 to 2024-12-31')",
    )
    calc_parser.add_argument(
        "--organisation-name",
        default="OpenCarbonChem Demo",
        help="Organisation name for PDF reports",
    )
    calc_parser.add_argument(
        "--report-types",
        nargs="+",
        choices=["excel", "pdf"],
        default=["excel", "pdf"],
        help="Report types to generate",
    )

    # ---- help ---- #
    parser.print_help = lambda: print(parser.format_help())

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    try:
        factors = _load_factors(args.activities)

        activities = _load_activities(args.activities)

        if not activities:
            print("No activities loaded; nothing to calculate.", file=sys.stderr)
            return 1

        if "excel" in args.report_types:
            _run_excel(activities, factors, args.gwp_set, args.run_id, args.period_label)

        if "pdf" in args.report_types:
            _run_pdf(
                activities,
                factors,
                args.gwp_set,
                args.run_id,
                args.period_label,
                args.organisation_name,
        )

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())