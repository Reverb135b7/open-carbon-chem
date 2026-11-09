"""Generate the published DESNZ factor CSV from official flat-format workbooks.

The published set is not typed by hand: ``tools/factor_spec.json`` names, for each
factor, the exact row in DESNZ's machine-readable "flat format" workbook
(Level 1-4 category, column text, unit and gas basis). This script resolves every
selector, asserts it matches exactly one value, and writes the packaged CSV.

Usage (from the repository root)::

    python tools/extract_factors.py \
        --set 2024=build/tmp/defra2024-flat.xlsx \
        --set 2025=build/tmp/defra2025-flat.xlsx

Downloads are not committed; see docs/FACTOR_SOURCES.md for the URLs and SHA-256
hashes of the workbooks used. Regenerating is deterministic: the same workbooks
and spec always produce byte-identical output.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "tools" / "factor_spec.json"
DEFAULT_OUT = ROOT / "src" / "opencarbonchem" / "factors" / "data" / "published_factors.csv"

# DESNZ release metadata per factor year. The version string is the one printed
# on the workbook's front page.
RELEASES = {
    2024: ("2024 UK Government GHG Conversion Factors for Company Reporting, "
           "full set v1.1 (30 October 2024)", "2024-v1.1"),
    2025: ("2025 UK Government GHG Conversion Factors for Company Reporting, "
           "full set v1.0 (10 June 2025)", "2025-v1.0"),
}

# IPCC 2006 process factors are not in the DESNZ workbook; they are transcribed
# from the Guidelines table named in each reference and are kept here so the
# packaged CSV is produced by one tool.
IPCC_ROWS = [
    {
        "factor_id": "EF-IPCC-2006-01", "activity_category": "process_emissions",
        "substance": "limestone", "value": "0.43971", "unit": "kg CO2/kg", "gas": "CO2",
        "gases_covered": "CO2", "geography": "GLOBAL", "reporting_year": "2006",
        "source_org": "IPCC",
        "source_reference": (
            "2006 IPCC Guidelines for National Greenhouse Gas Inventories, Vol. 3 Ch. 2, "
            "Table 2.1 (CaCO3 / calcite); IPCC EFDB entry 2.A.4.d"),
        "version": "2006", "uncertainty_pct": "", "review_status": "published",
        "methane_basis": "",
        "notes": ("Stoichiometric calcination factor for calcite assuming 100 % calcination. "
                  "Limestone is assumed to be calcite."),
    },
    {
        "factor_id": "EF-IPCC-2006-02", "activity_category": "process_emissions",
        "substance": "dolomite", "value": "0.47732", "unit": "kg CO2/kg", "gas": "CO2",
        "gases_covered": "CO2", "geography": "GLOBAL", "reporting_year": "2006",
        "source_org": "IPCC",
        "source_reference": (
            "2006 IPCC Guidelines for National Greenhouse Gas Inventories, Vol. 3 Ch. 2, "
            "Table 2.1 (CaMg(CO3)2 / dolomite)"),
        "version": "2006", "uncertainty_pct": "", "review_status": "published",
        "methane_basis": "", "notes": "Stoichiometric calcination factor for dolomite.",
    },
    {
        "factor_id": "EF-IPCC-2006-03", "activity_category": "process_emissions",
        "substance": "magnesite", "value": "0.52197", "unit": "kg CO2/kg", "gas": "CO2",
        "gases_covered": "CO2", "geography": "GLOBAL", "reporting_year": "2006",
        "source_org": "IPCC",
        "source_reference": (
            "2006 IPCC Guidelines for National Greenhouse Gas Inventories, Vol. 3 Ch. 2, "
            "Table 2.1 (MgCO3 / magnesite)"),
        "version": "2006", "uncertainty_pct": "", "review_status": "published",
        "methane_basis": "", "notes": "Stoichiometric calcination factor for magnesite.",
    },
    {
        "factor_id": "EF-IPCC-2006-04", "activity_category": "process_emissions",
        "substance": "siderite", "value": "0.37987", "unit": "kg CO2/kg", "gas": "CO2",
        "gases_covered": "CO2", "geography": "GLOBAL", "reporting_year": "2006",
        "source_org": "IPCC",
        "source_reference": (
            "2006 IPCC Guidelines for National Greenhouse Gas Inventories, Vol. 3 Ch. 2, "
            "Table 2.1 (FeCO3 / siderite)"),
        "version": "2006", "uncertainty_pct": "", "review_status": "published",
        "methane_basis": "", "notes": "Stoichiometric calcination factor for siderite.",
    },
    {
        "factor_id": "EF-IPCC-2006-05", "activity_category": "process_emissions",
        "substance": "soda_ash", "value": "0.41492", "unit": "kg CO2/kg", "gas": "CO2",
        "gases_covered": "CO2", "geography": "GLOBAL", "reporting_year": "2006",
        "source_org": "IPCC",
        "source_reference": (
            "2006 IPCC Guidelines for National Greenhouse Gas Inventories, Vol. 3 Ch. 2, "
            "Table 2.1 (Na2CO3 / soda ash)"),
        "version": "2006", "uncertainty_pct": "", "review_status": "published",
        "methane_basis": "", "notes": "Stoichiometric calcination factor for soda ash.",
    },
]

COLUMNS = ["factor_id", "activity_category", "substance", "value", "unit", "gas",
           "gases_covered", "geography", "reporting_year", "source_org",
           "source_reference", "version", "uncertainty_pct", "review_status",
           "methane_basis", "notes"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_flat(path: Path) -> list[dict[str, object]]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if "Factors by Category" not in workbook.sheetnames:
        raise SystemExit(f"{path} is not a DESNZ flat-format workbook")
    sheet = workbook["Factors by Category"]
    rows = []
    for raw in list(sheet.iter_rows(values_only=True))[6:]:
        if not raw[2]:
            continue
        rows.append({
            "l1": str(raw[2]).strip(), "l2": str(raw[3] or "").strip(),
            "l3": str(raw[4] or "").strip(), "l4": str(raw[5] or "").strip(),
            "col": str(raw[6] or "").strip(), "uom": str(raw[7] or "").strip(),
            "ghg": str(raw[8] or "").strip(), "value": raw[9],
        })
    if not rows:
        raise SystemExit(f"{path}: no factor rows found")
    return rows


def describe(selector: dict[str, object]) -> str:
    def text(value: object) -> str:
        return " or ".join(str(item) for item in value) if isinstance(value, list) else str(value)

    parts = [text(selector["l1"]), text(selector["l2"]), text(selector["l3"])]
    parts += [text(selector[key]) for key in ("l4", "col") if selector[key]]
    parts += [text(selector["uom"]), text(selector["ghg"])]
    return " / ".join(part for part in parts if part)


def selector_matches(row: dict[str, object], selector: dict[str, object]) -> bool:
    for key, expected in selector.items():
        allowed = expected if isinstance(expected, list) else [expected]
        if str(row[key]) not in {str(item) for item in allowed}:
            return False
    return True


def resolve(rows: list[dict[str, object]], selector: dict[str, object],
            label: str) -> float:
    matches = [row for row in rows if selector_matches(row, selector)]
    if len(matches) != 1:
        raise SystemExit(f"{label}: selector matched {len(matches)} rows: {describe(selector)}")
    value = matches[0]["value"]
    if not isinstance(value, (int, float)):
        raise SystemExit(f"{label}: non-numeric value {value!r} for {describe(selector)}")
    return float(value)


def build(sets: list[tuple[int, Path]]) -> list[dict[str, str]]:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    out: list[dict[str, str]] = []
    for year, path in sorted(sets):
        release, version = RELEASES[year]
        rows = load_flat(path)
        for entry in spec:
            label = f"{year} {entry['substance']} {entry['unit']}"
            raw = resolve(rows, entry["selector"], label)
            value = raw / float(entry["divisor"])
            out.append({
                "factor_id": f"EF-DESNZ-{year}-{entry['nn']:02d}",
                "activity_category": entry["category"],
                "substance": entry["substance"],
                "value": f"{value:.10g}",
                "unit": entry["unit"],
                "gas": entry["gas"],
                "gases_covered": entry["gas"],
                "geography": entry["geography"],
                "reporting_year": str(year),
                "source_org": "DESNZ",
                "source_reference": f"{release}, flat file: {describe(entry['selector'])}",
                "version": version,
                "uncertainty_pct": "",
                "review_status": "published",
                "methane_basis": "",
                "notes": entry["notes"],
            })
        print(f"{year}: {len(spec)} DESNZ factors from {path.name} (sha256 {sha256(path)[:16]}…)")
    out.extend(IPCC_ROWS)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", action="append", required=True, metavar="YEAR=PATH",
                        help="factor year and flat-format workbook, e.g. 2025=defra2025-flat.xlsx")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    sets = []
    for item in args.set:
        year_text, path_text = item.split("=", 1)
        sets.append((int(year_text), Path(path_text)))

    rows = build(sets)
    assert len({(r["factor_id"]) for r in rows}) == len(rows), "duplicate factor ids"
    keys = [(r["activity_category"], r["substance"], r["unit"], r["gas"],
             r["reporting_year"]) for r in rows]
    assert len(set(keys)) == len(keys), "duplicate (category, substance, unit, gas, year)"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
