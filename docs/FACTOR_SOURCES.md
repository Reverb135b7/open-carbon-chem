# Emission factor sources

The packaged factor set `src/opencarbonchem/factors/data/published_factors.csv` is
transcribed from primary publications. Every row carries `review_status=published`,
a source organisation, a document/table reference, a version and a vintage year;
nothing here is an estimate made by OpenCarbonChem.

## Vintage

The demo activity data cover calendar year **2024**, so the **2024** UK Government
conversion factors (full set, v1.1, updated 30 October 2024) are used. Using a later
annual set against 2024 activity data would break the registry's "newest factor at or
before the reporting year" rule. To report another year, add the corresponding annual
DESNZ set and use the matching `reporting_year`.

Source page: <https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2024>
(full set spreadsheet `ghg-conversion-factors-2024-full_set__for_advanced_users__v1_1.xlsx`).

## Packaged factors

| ID | Category / substance | Value | Unit | Geography | Source and location |
|----|----------------------|-------|------|-----------|---------------------|
| EF-DESNZ-2024-01 | stationary_combustion / natural_gas | 0.18253 | kg CO2/kWh | GB | DESNZ 2024 full set, `Fuels`, Natural gas, kWh (Gross CV), CO2 component |
| EF-DESNZ-2024-02 | stationary_combustion / natural_gas | 0.18290 | kg CO2e/kWh | GB | same row, total kg CO2e column |
| EF-DESNZ-2024-03 | mobile_combustion / diesel | 2.62818 | kg CO2/L | GB | `Fuels`, Diesel (100% mineral diesel), litres, CO2 component |
| EF-DESNZ-2024-04 | fugitive_emissions / r134a | 1300 | kg CO2e/kg | GB | `Refrigerant & other`, HFC-134a, kg CO2e |
| EF-IPCC-2006-01 | process_emissions / limestone | 0.43971 | kg CO2/kg | GLOBAL | IPCC 2006 Guidelines Vol. 3 Ch. 2 Table 2.1 (CaCO3 / calcite) |
| EF-DESNZ-2024-05 | purchased_electricity / grid_electricity | 0.20705 | kg CO2e/kWh | GB | `UK electricity`, Electricity generated, Electricity: UK |
| EF-DESNZ-2024-06 | purchased_steam / steam | 0.17965 | kg CO2e/kWh | GB | `Heat and steam`, Onsite heat and steam |
| EF-DESNZ-2024-07 | s3_cat04 / road_freight | 0.11926 | kg CO2e/tkm | GB | `Freighting goods`, HGV (all diesel), All HGVs, 50 % laden |
| EF-DESNZ-2024-08 | s3_cat06 / air_travel | 0.18592 | kg CO2e/pkm | GB | `Business travel- air`, Short-haul to/from UK, average passenger, with RF |
| EF-DESNZ-2024-09 | s3_cat01 / paper | 1.33931834 | kg CO2e/kg | GB | `Material use`, Paper and board: paper (1339.31834 kg CO2e per tonne) |
| EF-DESNZ-2024-10 | s3_cat05 / mixed_waste | 0.5203342 | kg CO2e/kg | GB | `Waste disposal`, Commercial and industrial waste, landfill (520.3342 per tonne) |

IPCC reference: <https://www.ipcc-nggip.iges.or.jp/public/2006gl/pdf/3_Volume3/V3_2_Ch2_Mineral_Industry.pdf>
(the EFDB entry 2.A.4.d records the same 0.43971 t CO2/t for CaCO3).

## Choices and conversions that matter

- **Natural gas, gross CV.** UK gas billing is on a gross calorific value basis, so the
  gross-CV kWh factor is used. A net-CV factor would understate emissions for the same
  billed kWh.
- **Diesel, 100 % mineral.** The dataset models fossil diesel, so the mineral-diesel row
  is used. Forecourt fuel containing biodiesel should use the "average biofuel blend"
  row (2.51279 kg CO2e/L) and report the biogenic part outside the scopes.
- **R-134a, top-up method.** The DEFRA factor is 1300 kg CO2e per kg of refrigerant
  released (AR5 GWP basis). The activity row is therefore the mass topped up
  (7.5 kg = 1.5 % of a 500 kg charge), not the charge itself. DEFRA's factor already
  embeds the GWP: it is not re-multiplied by the project's GWP set.
- **Limestone.** 0.43971 kg CO2/kg is the stoichiometric calcination factor for calcite
  at 100 % calcination. Limestone is assumed to be calcite; dolomite would be 0.47732.
- **Electricity** is the location-based generation factor and excludes transmission and
  distribution losses, which belong in Scope 3.
- **Steam** is per kWh of steam energy. The activity must therefore be recorded in kWh;
  a mass of steam needs an enthalpy conversion that this project does not assume.
- **Freight** uses the 50 % laden HGV band (0.11926). Fully laden movements should use
  0.07240 kg CO2e/tkm.
- **Air travel** includes radiative forcing (0.18592); the without-RF value is 0.10974.
- **Paper** and **mixed waste** are converted from the published per-tonne values to
  per-kg. The waste factor covers landfill only; combustion is 6.41061 kg CO2e/t.

## GWP basis caveat

DEFRA's 2024 combined CO2e factors use **AR5** GWPs, while the project's gas-level
conversions use the selected GWP set (AR6 by default). Published CO2e factors are used
as published and are not recomputed, so a report can contain both an AR5-based CO2e
factor and AR6-converted gas rows. The GWP set actually used for each row is recorded
in `EmissionResult` and in the Excel/PDF detail columns. For a single-basis inventory,
supply gas-level factors and let the engine apply one GWP set throughout.

## Uncertainty

`uncertainty_pct` is left blank for the published rows because the conversion-factor
spreadsheets do not publish a per-factor uncertainty. Monte Carlo therefore falls back
to its documented default spread; treat those intervals as sensitivity experiments, not
as published confidence intervals.

## Updating

1. Download the full set for the reporting year, confirm the version and date.
2. Add rows with `reporting_year` equal to the year the factors are valid for.
3. Copy values at full published precision; note any unit conversion in `notes`.
4. Run `python -m pytest` — the published-seed tests check provenance completeness and
   the demo dataset's arithmetic.
