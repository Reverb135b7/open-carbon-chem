"""End-to-end demonstration on the synthetic dataset.

Run:  python m11_demo.py

Exercises the same package API the dashboard and CLI use: corporate inventory,
product footprint, hotspots, Monte Carlo, a decarbonisation lever, and both
report formats. Activity data are synthetic; factors are the packaged published
(DESNZ 2024 / IPCC 2006) set.
"""

from __future__ import annotations

import sys
from pathlib import Path

from opencarbonchem.accounting import calculate_inventory
from opencarbonchem.analytics import rank_emissions, run_monte_carlo, InputDistribution
from opencarbonchem.core.activity import ActivityRecord, load_activities_csv
from opencarbonchem.factors import FactorRegistry, default_seed_path
from opencarbonchem.pcf import InventoryItem, ProductDefinition, calculate_pcf
from opencarbonchem.reporting import build_excel_report, build_pdf_report
from opencarbonchem.scenarios import RenewableElectricity, apply_lever

ROOT = Path(__file__).resolve().parent
DATA_CSV = ROOT / "data" / "activities_synthetic.csv"
OUT_DIR = ROOT / "reports"


def _factor(registry, category, substance, *, gas=None):
    return registry.find(
        activity_category=category,
        substance=substance,
        geography="GB",
        year=2024,
        gas=gas,
    )


def demo_entries(registry):
    """Three inventory entries used by the analytics and scenario sections."""
    return [
        (
            ActivityRecord(
                activity_id="A-PAPER", scope=3, category="s3_cat01",
                substance="paper", quantity=1000, unit="kg",
            ),
            _factor(registry, "s3_cat01", "paper"),
        ),
        (
            ActivityRecord(
                activity_id="A-GAS", scope=1, category="stationary_combustion",
                substance="natural_gas", quantity=500, unit="kWh", gas="CO2",
            ),
            _factor(registry, "stationary_combustion", "natural_gas", gas="CO2"),
        ),
        (
            ActivityRecord(
                activity_id="A-ELEC", scope=2, category="purchased_electricity",
                substance="grid_electricity", quantity=1000, unit="kWh", gas="CO2e",
            ),
            _factor(registry, "purchased_electricity", "grid_electricity", gas="CO2e"),
        ),
    ]


def demo_pcf(registry):
    product = ProductDefinition(
        pcf_id="DEMO-PCF-001",
        product_name="Synthetic chemical product",
        functional_unit="1 tonne of product at the factory gate",
        production_qty=1.0,
        production_unit="t",
        system_boundary="cradle_to_gate",
        notes="SYNTHETIC - demonstration only.",
    )
    items = [
        InventoryItem(
            stage="raw_materials",
            activity=ActivityRecord(
                activity_id="P-RAW", scope=3, category="s3_cat01",
                substance="paper", quantity=1000, unit="kg",
            ),
            factor=_factor(registry, "s3_cat01", "paper"),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="manufacturing",
            activity=ActivityRecord(
                activity_id="P-MFG", scope=1, category="stationary_combustion",
                substance="natural_gas", quantity=500, unit="kWh", gas="CO2",
            ),
            factor=_factor(registry, "stationary_combustion", "natural_gas", gas="CO2"),
        ),
        InventoryItem(
            stage="inbound_transport",
            activity=ActivityRecord(
                activity_id="P-TRN", scope=3, category="s3_cat04",
                substance="road_freight", quantity=2000, unit="tkm",
            ),
            factor=_factor(registry, "s3_cat04", "road_freight"),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="packaging",
            activity=ActivityRecord(
                activity_id="P-PKG", scope=3, category="s3_cat01",
                substance="paper", quantity=50, unit="kg",
            ),
            factor=_factor(registry, "s3_cat01", "paper"),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="waste",
            activity=ActivityRecord(
                activity_id="P-WST", scope=3, category="s3_cat05",
                substance="mixed_waste", quantity=100, unit="kg",
            ),
            factor=_factor(registry, "s3_cat05", "mixed_waste"),
            excluded_from_corporate=True,
        ),
    ]
    return product, items


def main() -> int:
    print("=" * 64)
    print("OpenCarbonChem - end-to-end demonstration (SYNTHETIC data)")
    print("=" * 64)

    registry = FactorRegistry.from_csv(default_seed_path())
    activities = load_activities_csv(DATA_CSV)
    print(f"\n[1] Loaded {len(activities)} activity rows from {DATA_CSV.name}")

    report, rows = calculate_inventory(activities, registry)
    print("\n[2] Corporate inventory (all scopes present in the data)")
    for scope, kg in sorted(report.by_scope().items()):
        print(f"    Scope {scope}: {kg:>14,.1f} kg CO2e")
    print(f"    Total:    {report.total_kg:>14,.1f} kg CO2e ({report.total_t:,.3f} t)")
    recon = report.reconcile()
    print(f"    Reconciliation: {'OK' if recon.ok else 'FAILED'} | "
          f"coverage gaps: {len(recon.coverage_gaps)}")

    product, items = demo_pcf(registry)
    pcf = calculate_pcf(product, items)
    print("\n[3] Product carbon footprint (cradle-to-gate)")
    for stage, kg in pcf.by_stage().items():
        print(f"    {stage:18s} {kg:>10,.1f} kg CO2e")
    print(f"    Total: {pcf.total_kg:,.1f} kg CO2e "
          f"({pcf.per_unit:,.2f} kg CO2e/{product.production_unit})")

    print("\n[4] Hotspots (top contributor per dimension)")
    for dimension in ("substance", "category", "scope", "gas"):
        top = rank_emissions(rows, by=dimension)[0]
        print(f"    {dimension:10s} {top.key:20s} {top.kg:>14,.1f} kg "
              f"({top.share:.1%}, {top.rows} rows)")

    entries = demo_entries(registry)
    distributions = [
        InputDistribution(
            name=f"{activity.activity_id} factor",
            activity_id=activity.activity_id,
            field="factor_value",
            spread_pct=15.0,
        )
        for activity, _factor_ in entries
    ]
    monte_carlo = run_monte_carlo(entries, distributions, n_draws=5000, seed=42)
    print("\n[5] Monte Carlo uncertainty (seed 42, 5000 draws)")
    print(f"    base={monte_carlo.base_kg:,.1f} mean={monte_carlo.mean_kg:,.1f} "
          f"p5={monte_carlo.p5_kg:,.1f} p95={monte_carlo.p95_kg:,.1f} "
          f"(relative std {monte_carlo.relative_std_pct:.1f} %)")

    lever = RenewableElectricity(share=0.30)
    scenario = apply_lever(lever, entries)
    print("\n[6] Decarbonisation lever: 30 % renewable electricity (demo entries)")
    print(f"    baseline={scenario.baseline_kg:,.1f} kg -> "
          f"scenario={scenario.scenario_kg:,.1f} kg "
          f"(reduction {scenario.reduction_kg:,.1f} kg / {scenario.reduction_pct:.1f} %)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    excel_path = OUT_DIR / "m11_demo.xlsx"
    pdf_path = OUT_DIR / "m11_demo.pdf"
    build_excel_report(
        report, rows, gwp_set="AR6", run_id="m11-demo", period_label="2024"
    ).save(str(excel_path))
    build_pdf_report(
        report, rows, gwp_set="AR6", run_id="m11-demo",
        period_label="2024", organisation_name="OpenCarbonChem Demo",
    ).save(str(pdf_path))
    print("\n[7] Reports written")
    print(f"    {excel_path.relative_to(ROOT)} ({excel_path.stat().st_size:,} bytes)")
    print(f"    {pdf_path.relative_to(ROOT)} ({pdf_path.stat().st_size:,} bytes)")

    print("\n" + "=" * 64)
    print("Demo complete. Activities are synthetic; factors are published DESNZ/IPCC values.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
