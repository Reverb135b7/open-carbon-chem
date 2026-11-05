"""Milestone 11 — End-to-end demonstration using synthetic datasets.

Run:  python m11_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from datetime import date

from opencarbonchem.factors import FactorRegistry
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.factors.models import EmissionFactor
from opencarbonchem.core.calc import compute_emissions
from opencarbonchem.accounting import (
    calculate_scope1, OrganizationReport, ScopeResult,
)
from opencarbonchem.pcf import (
    ProductDefinition, InventoryItem, calculate_pcf,
)
from opencarbonchem.analytics import (
    rank_emissions, run_monte_carlo, InputDistribution,
    default_distributions, analyse_sensitivity, build_parameters,
    product_carbon_intensity,
)
from opencarbonchem.scenarios.levers import (
    RenewableElectricity, EnergyEfficiency, FuelSwitch,
    MaterialSubstitution, WasteReduction, ProcessOptimisation,
    TransportOptimisation, LEVER_KINDS, lever_from_kind,
)
from opencarbonchem.scenarios.engine import ScenarioResult, compare_scenarios
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.core.exceptions import (
    PCFError, AllocationError, DoubleCountingError,
    AnalyticsError, UncertaintyError, ScenarioError,
)
from opencarbonchem.core.calc import EmissionResult
from opencarbonchem.reporting.excel_workbook import build_excel_report
from opencarbonchem.reporting.pdf_generator import build_pdf_report

# ── Base paths ──────────────────────────────────────────────────────────────
DATA = Path(__file__).parent.parent / "data" / "raw" / "synthetic"
DEFAULT_CSV = Path(__file__).parent.parent / "src" / "opencarbonchem" / "factors" / "data" / "illustrative_factors.csv"
st_seed = FactorRegistry.from_csv(DEFAULT_CSV)


def load_activities() -> list[ActivityRecord]:
    csv_path = DATA / "activities_synthetic.csv"
    if not csv_path.exists():
        print(f"❌ {csv_path} not found", file=sys.stderr)
        sys.exit(1)
    import csv
    acts = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            acts.append(
                ActivityRecord(
                    activity_id=r["activity_id"],
                    scope=int(r["scope"]),
                    category=r["category"],
                    substance=r["substance"],
                    quantity=float(r["quantity"]),
                    unit=r["unit"],
                    gas=r.get("gas") or None,
                    **{"period_start": None, "period_end": None, "data_type": "primary",
                       "notes": r.get("notes", "")},
                )
            )
    return acts


def main(argv: list[str] | None = None) -> int:
    print("=" * 60)
    print("🧪 OpenCarbonChem — Milestone 11 End-to-End Demo")
    print("=" * 60)

    # ── 1. Load synthetic data ──────────────────────────────────────
    print("\n[1] Loading synthetic activities…")
    activities = load_activities()
    print(f"   Loaded {len(activities)} activities")

    # ── 2. Corporate Scope 1-3 inventory ────────────────────────────
    print("\n[2] Building corporate Scope 1-3 inventory…")
    reg = FactorRegistry.from_csv(DEFAULT_CSV)
    results = [compute_emissions(a, reg.find(activity_category=a.category,
                                              substance=a.substance,
                                              year=2024, gas=a.gas))
               for a in activities if a.gas or a.category != "stationary_combustion"]
    scope_result = type("S", (), {"results": results})()
    org_report = OrganizationReport.from_results([type("S", (), {"scope": 1, "results": results})()])
    print(f"   Scope 1 total: {scope_result.total_kg:,.1f} kg CO₂e")
    print(f"   Organisation total: {org_report.total_kg:,.1f} kg CO₂e")

    # ── 3. Product Carbon Footprint ─────────────────────────────────
    print("\n[3] Computing Product Carbon Footprint…")
    pcf_id = "M11-PCF-001"
    prod = ProductDefinition(
        pcf_id=pcf_id,
        product_name="Synthetic chemical product",
        functional_unit="1 tonne of product at the factory gate",
        production_qty=1.0,
        production_unit="t",
        system_boundary="cradle_to_gate",
        notes="SYNTHETIC — demo only",
    )
    pcf_items = [
        InventoryItem(
            stage="raw_materials",
            activity=ActivityRecord(
                activity_id="A-S3", scope=3, category="s3_cat01",
                substance="paper", quantity=1000, unit="kg"),
            factor=reg.find(activity_category="s3_cat01", substance="paper", year=2024),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="manufacturing",
            activity=ActivityRecord(
                activity_id="A-MFG", scope=1, category="stationary_combustion",
                substance="natural_gas", quantity=500, unit="kWh", gas="CO2"),
            factor=reg.find(activity_category="stationary_combustion",
                            substance="natural_gas", year=2024, gas="CO2"),
        ),
    ]
    pcf = calculate_pcf(prod, pcf_items)
    print(f"   PCF total: {pcf.total_kg:,.1f} kg CO₂e")
    print(f"   PCF per unit: {pcf.per_unit:,.2f} kg CO₂e/{prod.production_unit}")
    print(f"   Boundary stages: {', '.join(pcf.boundary_stages)}")

    # ── 4. Hotspot analysis ─────────────────────────────────────────
    print("\n[4] Computing hotspot rankings…")
    for dim in ["substance", "category", "scope", "gas", "activity"]:
        try:
            ranked = rank_emissions(results, by=dim)
            top = ranked[0]
            print(f"   {dim:12s}: top={top.key:8s}, kg={top.kg:8.1f}, share={top.share:.2%}, rows={top.rows}")
        except Exception as e:
            print(f"   {dim:12s}: error — {e}")

    # ── 5. Monte Carlo uncertainty ──────────────────────────────────
    print("\n[5] Monte Carlo uncertainty propagation…")
    dists = [InputDistribution(
        name="paper EF", activity_id="A-S3", spread_pct=15.0)]
    try:
        mc = run_monte_carlo(results, dists, n_draws=2000, seed=42)
        print(f"   base={mc.base_kg:,.1f} | mean={mc.mean_kg:,.1f} | median={mc.median_kg:,.1f}")
        print(f"   p5={mc.p5_kg:,.1f} | p95={mc.p95_kg:,.1f} | std={mc.std_kg:,.1f}")
        print(f"   rel_std={mc.relative_std_pct:.1f}% | contributions sum={sum(c.share for c in mc.contributions):.3f}")
    except Exception as e:
        print(f"   Monte Carlo error: {e}")

    # ── 5b. Default distributions from factor uncertainty ─────────────
    print("\n[5b] Default distributions from factor uncertainty…")
    try:
        ddist = default_distributions([(activities[0], reg.find(
            activity_category="s3_cat01", substance="paper", year=2024))])
        print(f"   default spread: {ddist[0].spread_pct:.1f}% ({ddist[0].kind})")
    except Exception as e:
        print(f"   default distributions error: {e}")

    # ── 5c. Variance-share consistency ──────────────────────────────
    print("\n[5c] Variance-share consistency check…")
    dists2 = [
        InputDistribution(name="paper", activity_id="A-S3", spread_pct=20.0),
        InputDistribution(name="gas", activity_id="A-MFG", spread_pct=20.0),
    ]
    try:
        mc2 = run_monte_carlo(results, dists2, n_draws=3000, seed=42)
        shares = {c.name: c.share for c in mc2.contributions}
        print(f"   contributions sum: {sum(shares.values()):.4f} (target ≈1.0)")
        print(f"   paper share: {shares.get('paper', 0):.4f} | gas share: {shares.get('gas', 0):.4f}")
    except Exception as e:
        print(f"   variance-share error: {e}")

    # ── 5d. Reproducibility test ────────────────────────────────────
    print("\n[5d] Reproducibility: same seed → identical output…")
    try:
        mc1 = run_monte_carlo(results, dists, n_draws=1000, seed=123)
        mc2 = run_monte_carlo(results, dists, n_draws=1000, seed=123)
        same = (mc1.mean_kg == mc2.mean_kg and mc1.p95_kg == mc2.p95_kg)
        print(f"   same seed → identical: {same}")
    except Exception as e:
        print(f"   reproducibility error: {e}")

    # ── 6. Decarbonisation scenarios ────────────────────────────────
    print("\n[6] Decarbonisation scenario analysis…")
    # baseline
    base_kg = sum(r.co2e_kg for r in results)
    # renewable electricity lever
    try:
        lever = RenewableElectricity(share=0.3, residual_ef=0.0)
        # compute scenario via engine
        from opencarbonchem.scenarios.engine import apply_lever
        res = apply_lever(lever, results, DEFAULT_CSV)
        red_kg = base_kg - res.scenario_kg
        red_pct = (red_kg / base_kg * 100.0) if base_kg > 0 else None
        print(f"   Renewable electricity {0.3*100:.0f}% lever:")
        print(f"     baseline: {base_kg:,.1f} kg")
        print(f"     scenario: {res.scenario_kg:,.1f} kg")
        print(f"     reduction: {red_kg:,.1f} kg ({red_pct:.1f}%)" if red_pct is not None
              else f"     reduction: N/A (baseline was zero)")
    except Exception as e:
        print(f"   Renewable electricity lever error: {e}")

    # waste reduction lever
    try:
        lever2 = WasteReduction(reduction=0.3)
        res2 = apply_lever(lever2, results, DEFAULT_CSV)
        red2_kg = base_kg - res2.scenario_kg
        red2_pct = (red2_kg / base_kg * 100.0) if base_kg > 0 else None
        print(f"   Waste reduction {0.3*100:.0f}% lever:")
        print(f"     baseline: {base_kg:,.1f} kg")
        print(f"     scenario: {res2.scenario_kg:,.1f} kg")
        print(f"     reduction: {red2_kg:,.1f} kg ({red2_pct:.1f}%)" if red2_pct is not None
              else f"     reduction: N/A (baseline was zero)")
    except Exception as e:
        print(f"   Waste reduction lever error: {e}")

    # ── 7. Report generation ────────────────────────────────────────
    print("\n[7] Generating Excel + PDF reports…")
    try:
        excel = build_excel_report(
            org_report, results, gwp_set="AR6", run_id="m11-demo",
            period_label="2024"
        )
        excel_path = "m11_demo.xlsx"
        excel.save(excel_path)
        print(f"   Excel written: {excel_path}")

        pdf = build_pdf_report(
            org_report, results, gwp_set="AR6", run_id="m11-demo",
            organisation_name="OpenCarbonChem Demo"
        )
        pdf_path = "m11_demo.pdf"
        pdf.save(pdf_path)
        print(f"   PDF written: {pdf_path}")
    except Exception as e:
        print(f"   Report generation error: {e}")

    print("\n" + "=" * 60)
    print("✅ Milestone 11 demo complete")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())