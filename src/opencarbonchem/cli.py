"""Command-line entry point for OpenCarbonChem.

Thin client (requirement N3): it loads activity data and factors, delegates all
accounting to the package API, and writes the requested reports. No calculation
logic lives here.

Usage::

    opencarbonchem calculate --activities data/activities_synthetic.csv --run-id run-2024
    opencarbonchem calculate --activities data/activities_synthetic.csv --run-id run-2024 \
        --gwp-set AR5 --report-types pdf --out reports/

Every failure is reported as a message and a non-zero exit status — the CLI
never prints a total it could not derive.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .accounting import (
    OrganizationReport,
    calculate_inventory as accounting_calculate_inventory,
)
from .core.activity import ActivityRecord, load_activities_csv
from .core.exceptions import OpenCarbonChemError
from .core.gwp import DEFAULT_GWP_SET
from .factors import FactorRegistry

__all__ = ["main"]

_GWP_SETS = ("AR6", "AR5", "AR6-ERRATA-2025")


def load_activities(csv_path: str | Path) -> list[ActivityRecord]:
    """Load activity records from a CSV (strict: a malformed row is an error)."""
    return load_activities_csv(csv_path)


def calculate_inventory(
    activities: list[ActivityRecord],
    registry: FactorRegistry,
    *,
    gwp_set: str = DEFAULT_GWP_SET,
) -> tuple[OrganizationReport, list]:
    """Run every scope present in ``activities`` and roll them up."""
    return accounting_calculate_inventory(activities, registry, gwp_set=gwp_set)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``opencarbonchem`` console script."""
    parser = argparse.ArgumentParser(
        prog="opencarbonchem",
        description=(
            "OpenCarbonChem — carbon accounting and sustainability analytics for "
            "chemical and process industries"
        ),
    )
    sub = parser.add_subparsers(dest="command")

    calc = sub.add_parser("calculate", help="Run the inventory and write reports")
    calc.add_argument("--activities", required=True,
                      help="Activity-data CSV (columns as in data/activities_synthetic.csv)")
    calc.add_argument("--factors", default=None,
                      help="Emission-factor CSV; defaults to the packaged seed set")
    calc.add_argument("--run-id", required=True,
                      help="Run identifier, used as the report filename prefix")
    calc.add_argument("--gwp-set", default=DEFAULT_GWP_SET, choices=_GWP_SETS,
                      help=f"GWP set to apply (default {DEFAULT_GWP_SET})")
    calc.add_argument("--period-label", default="",
                      help="Reporting-period label for the report header")
    calc.add_argument("--organisation-name", default="OpenCarbonChem Demo",
                      help="Organisation name for the PDF report")
    calc.add_argument("--report-types", nargs="+", choices=["excel", "pdf"],
                      default=["excel", "pdf"], help="Reports to generate")
    calc.add_argument("--out", default=".", help="Output directory for the reports")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 1

    try:
        registry = FactorRegistry.from_csv(args.factors)
        activities = load_activities(args.activities)
        if not activities:
            print("No activity records found; nothing to calculate.", file=sys.stderr)
            return 1

        report, rows = calculate_inventory(activities, registry, gwp_set=args.gwp_set)
        print(f"Scope 1: {report.by_scope().get(1, 0.0):,.3f} kg CO2e")
        print(f"Scope 2: {report.by_scope().get(2, 0.0):,.3f} kg CO2e")
        print(f"Scope 3: {report.by_scope().get(3, 0.0):,.3f} kg CO2e")
        print(f"Total:   {report.total_kg:,.3f} kg CO2e ({report.total_t:,.3f} t)")

        for gap in report.reconcile().coverage_gaps:
            print(f"Coverage note: {gap.detail}", file=sys.stderr)

        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)

        if "excel" in args.report_types:
            from .reporting import build_excel_report

            path = out_dir / f"{args.run_id}.xlsx"
            build_excel_report(
                report, rows, gwp_set=args.gwp_set, run_id=args.run_id,
                period_label=args.period_label,
            ).save(str(path))
            print(f"Excel report: {path}")

        if "pdf" in args.report_types:
            from .reporting import build_pdf_report

            path = out_dir / f"{args.run_id}.pdf"
            build_pdf_report(
                report, rows, gwp_set=args.gwp_set, run_id=args.run_id,
                period_label=args.period_label,
                organisation_name=args.organisation_name,
            ).save(str(path))
            print(f"PDF report: {path}")

    except OpenCarbonChemError as exc:
        print(f"Calculation failed: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
