"""Milestone 6 — Product Carbon Footprint tests.

Every expected value below is hand-computed from the synthetic seed factors
(``EF-ILL-*``) and stated in the test docstring, so the assertions are
independent of the implementation under test.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from opencarbonchem.accounting import OrganizationReport, ScopeResult, calculate_scope1
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.core.exceptions import (
    AllocationError,
    DoubleCountingError,
    IncompatibleUnitError,
    PCFError,
)
from opencarbonchem.factors import FactorRegistry
from opencarbonchem.pcf import (
    STAGE_CATALOGUE,
    AllocationRule,
    InventoryItem,
    ProductDefinition,
    calculate_pcf,
    combine_with_corporate,
    normalise_stage,
    stages_for_boundary,
)

pytestmark = pytest.mark.unit

PERIOD = dict(period_start=date(2024, 1, 1), period_end=date(2024, 12, 31))


@pytest.fixture(scope="module")
def registry() -> FactorRegistry:
    return FactorRegistry.from_csv()


def activity(activity_id: str, category: str, substance: str, quantity: float, unit: str,
             gas: str | None = None) -> ActivityRecord:
    return ActivityRecord(
        activity_id=activity_id,
        scope=3 if category.startswith("s3_") else 1,
        category=category,
        substance=substance,
        quantity=quantity,
        unit=unit,
        gas=gas,
        **PERIOD,
    )


def product(boundary: str = "cradle_to_gate") -> ProductDefinition:
    return ProductDefinition(
        pcf_id="PCF-TEST-001",
        product_name="Synthetic test compound",
        functional_unit="1 tonne of product at the factory gate",
        production_qty=1.0,
        production_unit="t",
        system_boundary=boundary,
        notes="SYNTHETIC product definition for tests",
    )


def five_stage_inventory(registry: FactorRegistry) -> list[InventoryItem]:
    """Raw 1200 + manufacturing 90 + transport 200 + packaging 60 + waste 50 kg CO2e."""
    return [
        InventoryItem(
            stage="raw_materials",
            activity=activity("A-RAW", "s3_cat01", "paper", 1000, "kg"),
            factor=registry.find(activity_category="s3_cat01", substance="paper", year=2024),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="manufacturing",
            activity=activity("A-MFG", "stationary_combustion", "natural_gas", 500, "kWh", gas="CO2"),
            factor=registry.find(activity_category="stationary_combustion",
                                 substance="natural_gas", year=2024, gas="CO2"),
        ),
        InventoryItem(
            stage="inbound_transport",
            activity=activity("A-TRN", "s3_cat04", "road_freight", 2000, "tkm"),
            factor=registry.find(activity_category="s3_cat04", substance="road_freight", year=2024),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="packaging",
            activity=activity("A-PKG", "s3_cat01", "paper", 50, "kg"),
            factor=registry.find(activity_category="s3_cat01", substance="paper", year=2024),
            excluded_from_corporate=True,
        ),
        InventoryItem(
            stage="waste",
            activity=activity("A-WST", "s3_cat05", "mixed_waste", 100, "kg"),
            factor=registry.find(activity_category="s3_cat05", substance="mixed_waste", year=2024),
            excluded_from_corporate=True,
        ),
    ]


# --------------------------------------------------------------------------- #
# Stage catalogue / boundary rules
# --------------------------------------------------------------------------- #
def test_stage_aliases_normalise():
    assert normalise_stage("transport") == "inbound_transport"
    assert normalise_stage("End-Of-Life") == "end_of_life"
    assert normalise_stage("disposal") == "end_of_life"
    assert normalise_stage("Use Phase") == "use"


def test_unknown_stage_is_rejected():
    with pytest.raises(PCFError, match="Unknown life-cycle stage"):
        normalise_stage("logistics_magic")


def test_boundary_stage_sets():
    gate = set(stages_for_boundary("cradle_to_gate"))
    grave = set(stages_for_boundary("cradle_to_grave"))
    assert gate == {"raw_materials", "manufacturing", "inbound_transport", "packaging", "waste"}
    assert grave > gate
    assert {"distribution", "use", "end_of_life"} <= grave
    assert "distribution" not in gate


def test_catalogue_every_stage_has_label_and_description():
    for key, info in STAGE_CATALOGUE.items():
        assert info.key == key
        assert info.label and info.description


# --------------------------------------------------------------------------- #
# Product definition validation
# --------------------------------------------------------------------------- #
def test_production_quantity_must_be_positive():
    with pytest.raises(ValidationError):
        ProductDefinition(
            pcf_id="P", product_name="X", functional_unit="1 t",
            production_qty=0, production_unit="t",
        )


def test_unknown_system_boundary_rejected():
    with pytest.raises(ValidationError):
        ProductDefinition(
            pcf_id="P", product_name="X", functional_unit="1 t",
            production_qty=1, production_unit="t", system_boundary="cradle_to_moon",
        )


# --------------------------------------------------------------------------- #
# Core PCF arithmetic
# --------------------------------------------------------------------------- #
def test_pcf_total_matches_hand_calculation(registry):
    """1200 + 90 + 200 + 60 + 50 = 1600 kg CO2e per 1 t."""
    result = calculate_pcf(product(), five_stage_inventory(registry))
    assert result.total_kg == pytest.approx(1600.0)
    assert result.per_unit == pytest.approx(1600.0)
    assert result.unit_label == "kg CO2e/t"
    assert result.total_t == pytest.approx(1.6)


def test_pcf_stage_breakdown(registry):
    result = calculate_pcf(product(), five_stage_inventory(registry))
    assert result.by_stage() == pytest.approx(
        {
            "raw_materials": 1200.0,
            "manufacturing": 90.0,
            "inbound_transport": 200.0,
            "packaging": 60.0,
            "waste": 50.0,
        }
    )
    shares = result.by_stage_share()
    assert shares["raw_materials"] == pytest.approx(1200 / 1600)


def test_pcf_per_unit_in_other_unit(registry):
    """1600 kg per 1 t == 1.6 kg per kg."""
    result = calculate_pcf(product(), five_stage_inventory(registry))
    assert result.per_unit_in("kg") == pytest.approx(1.6)


def test_line_items_retain_audit_fields(registry):
    result = calculate_pcf(product(), five_stage_inventory(registry))
    raw = next(i for i in result.items if i.activity_id == "A-RAW")
    assert raw.co2e_kg == pytest.approx(1200.0)
    assert raw.allocation_share == 1.0
    assert raw.activity_value == 1000 and raw.activity_unit == "kg"
    assert raw.factor_value == 1.2 and raw.factor_unit == "kg CO2e/kg"
    assert raw.gas == "CO2e"
    assert len(result.to_rows()) == 5


def test_empty_inventory_fails(registry):
    with pytest.raises(PCFError, match="no life-cycle inventory"):
        calculate_pcf(product(), [])


def test_cradle_to_gate_rejects_distribution(registry):
    items = five_stage_inventory(registry)
    items.append(
        InventoryItem(
            stage="distribution",
            activity=activity("A-DIS", "s3_cat04", "road_freight", 1000, "tkm"),
            factor=registry.find(activity_category="s3_cat04", substance="road_freight", year=2024),
        )
    )
    with pytest.raises(PCFError, match="outside the declared cradle_to_gate boundary"):
        calculate_pcf(product("cradle_to_gate"), items)


def test_cradle_to_grave_includes_distribution(registry):
    """1600 + 1000 tkm × 0.10 = 1700 kg."""
    items = five_stage_inventory(registry)
    items.append(
        InventoryItem(
            stage="distribution",
            activity=activity("A-DIS", "s3_cat04", "road_freight", 1000, "tkm"),
            factor=registry.find(activity_category="s3_cat04", substance="road_freight", year=2024),
        )
    )
    result = calculate_pcf(product("cradle_to_grave"), items)
    assert result.total_kg == pytest.approx(1700.0)
    assert "distribution" in result.by_stage()


def test_incompatible_units_fail_loudly(registry):
    """A kWh activity cannot be multiplied by a kg CO2/kg factor."""
    items = [
        InventoryItem(
            stage="manufacturing",
            activity=activity("A-BAD", "s3_cat01", "paper", 10, "kWh"),
            factor=registry.find(activity_category="s3_cat01", substance="paper", year=2024),
        )
    ]
    with pytest.raises(IncompatibleUnitError):
        calculate_pcf(product(), items)


# --------------------------------------------------------------------------- #
# Allocation
# --------------------------------------------------------------------------- #
def test_allocation_by_mass_60_40(registry):
    """Manufacturing 90 kg × 0.6 = 54 kg → total 1600 − 90 + 54 = 1564 kg."""
    rules = [AllocationRule(method="mass", stage="manufacturing", basis_value=600,
                            basis_total=1000, basis_unit="kg")]
    result = calculate_pcf(product(), five_stage_inventory(registry), allocation_rules=rules)
    assert result.total_kg == pytest.approx(1564.0)
    manufacturing = next(i for i in result.items if i.stage == "manufacturing")
    assert manufacturing.allocation_share == pytest.approx(0.6)
    assert manufacturing.co2e_kg == pytest.approx(90.0)       # raw, pre-allocation
    assert manufacturing.allocated_kg == pytest.approx(54.0)  # attributable


def test_default_allocation_rule_applies_to_all_stages(registry):
    """A default 50 % share halves every stage: 1600 × 0.5 = 800 kg."""
    rules = [AllocationRule(method="physical_causality", basis_value=5, basis_total=10,
                            basis_unit="t")]
    result = calculate_pcf(product(), five_stage_inventory(registry), allocation_rules=rules)
    assert result.total_kg == pytest.approx(800.0)
    assert all(i.allocation_share == pytest.approx(0.5) for i in result.items)


def test_stage_rule_overrides_default(registry):
    """Default 50 % but manufacturing keeps 100 %: (1600 − 90) × 0.5 + 90 = 845 kg."""
    rules = [
        AllocationRule(method="physical_causality", basis_value=5, basis_total=10, basis_unit="t"),
        AllocationRule(method="none", stage="manufacturing"),
    ]
    result = calculate_pcf(product(), five_stage_inventory(registry), allocation_rules=rules)
    assert result.total_kg == pytest.approx(845.0)


def test_allocation_rule_validation():
    with pytest.raises(AllocationError, match="requires both basis_value and basis_total"):
        AllocationRule(method="mass", stage="waste", basis_value=1, basis_unit="kg")
    with pytest.raises(AllocationError, match="cannot exceed basis_total"):
        AllocationRule(method="mass", basis_value=2, basis_total=1, basis_unit="kg")
    with pytest.raises(AllocationError, match="requires a mass basis unit"):
        AllocationRule(method="mass", basis_value=1, basis_total=2, basis_unit="USD")
    with pytest.raises(AllocationError, match="requires a currency basis unit"):
        AllocationRule(method="economic", basis_value=1, basis_total=2, basis_unit="kg")
    with pytest.raises(AllocationError, match="Unknown allocation method"):
        AllocationRule(method="vibes", basis_value=1, basis_total=2, basis_unit="kg")
    with pytest.raises(AllocationError, match="not shared"):
        AllocationRule(method="none", basis_value=1, basis_total=2, basis_unit="kg")


def test_duplicate_stage_rules_rejected(registry):
    rules = [
        AllocationRule(method="mass", stage="waste", basis_value=1, basis_total=2, basis_unit="kg"),
        AllocationRule(method="mass", stage="waste", basis_value=1, basis_total=2, basis_unit="kg"),
    ]
    with pytest.raises(AllocationError, match="More than one allocation rule"):
        calculate_pcf(product(), five_stage_inventory(registry), allocation_rules=rules)


# --------------------------------------------------------------------------- #
# Double counting
# --------------------------------------------------------------------------- #
def corporate_report(registry: FactorRegistry) -> OrganizationReport:
    """Corporate inventory containing only the manufacturing row (90 kg)."""
    mfg = activity("A-MFG", "stationary_combustion", "natural_gas", 500, "kWh", gas="CO2")
    return OrganizationReport.from_results([calculate_scope1([mfg], registry)])


def test_overlapping_row_with_matching_value_is_consistent(registry):
    result = calculate_pcf(product(), five_stage_inventory(registry),
                           corporate_report=corporate_report(registry))
    # The manufacturing row matches the corporate row exactly → no warnings about it.
    assert not any("A-MFG" in w for w in result.consistency_warnings)
    # Rows claimed as corporate-included but absent are surfaced, never ignored.
    assert result.consistency_warnings == ()


def test_excluded_flag_contradicting_corporate_report_raises(registry):
    items = five_stage_inventory(registry)
    items[1] = items[1].model_copy(update={"excluded_from_corporate": True})
    with pytest.raises(DoubleCountingError, match="flagged excluded_from_corporate"):
        calculate_pcf(product(), items, corporate_report=corporate_report(registry))


def test_conflicting_values_raise_double_counting(registry):
    """Corporate reports 100 kg for A-MFG but the PCF computes 90 kg."""
    mfg = activity("A-MFG", "stationary_combustion", "natural_gas", 500, "kWh", gas="CO2")
    factor = registry.find(activity_category="stationary_combustion",
                           substance="natural_gas", year=2024, gas="CO2")
    forged = factor.model_copy(update={"value": 0.2})  # 500 kWh × 0.2 = 100 kg
    report = OrganizationReport.from_results([calculate_scope1([mfg], FactorRegistry([forged]))])
    with pytest.raises(DoubleCountingError, match="cannot have two values"):
        calculate_pcf(product(), five_stage_inventory(registry), corporate_report=report)


def test_missing_corporate_row_produces_warning(registry):
    items = five_stage_inventory(registry)
    items[0] = items[0].model_copy(update={"excluded_from_corporate": False})
    result = calculate_pcf(product(), items, corporate_report=corporate_report(registry))
    assert any("A-RAW" in w for w in result.consistency_warnings)


def test_combine_with_corporate_adds_only_excluded_rows(registry):
    """Corporate 90 kg + (1200 + 200 + 60 + 50) = 1600 kg."""
    report = corporate_report(registry)
    pcf = calculate_pcf(product(), five_stage_inventory(registry), corporate_report=report)
    combined = combine_with_corporate(pcf, report)
    assert combined.corporate_kg == pytest.approx(90.0)
    assert combined.additions_kg == pytest.approx(1510.0)
    assert combined.combined_kg == pytest.approx(1600.0)
    assert "A-MFG" not in combined.added_items


def test_combine_rejects_row_already_in_corporate(registry):
    report = corporate_report(registry)
    pcf = calculate_pcf(product(), five_stage_inventory(registry))
    forged = pcf.__class__(
        product=pcf.product,
        gwp_set=pcf.gwp_set,
        items=tuple(
            line if line.activity_id != "A-MFG"
            else type(line)(**{**line.__dict__, "excluded_from_corporate": True})
            for line in pcf.items
        ),
    )
    with pytest.raises(DoubleCountingError, match="already appears in the corporate"):
        combine_with_corporate(forged, report)


# --------------------------------------------------------------------------- #
# Consistency with corporate accounting: same engine, same numbers
# --------------------------------------------------------------------------- #
def test_pcf_manufacturing_row_equals_scope1_row(registry):
    """The shared row must be identical in both workflows (one engine)."""
    pcf = calculate_pcf(product(), five_stage_inventory(registry))
    scope1 = calculate_scope1(
        [activity("A-MFG", "stationary_combustion", "natural_gas", 500, "kWh", gas="CO2")], registry
    )
    pcf_row = next(i for i in pcf.items if i.activity_id == "A-MFG")
    assert pcf_row.co2e_kg == pytest.approx(scope1.total_kg)
    assert isinstance(scope1, ScopeResult)


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def test_pcf_round_trip_through_sqlite(registry):
    items = five_stage_inventory(registry)
    rules = [AllocationRule(method="mass", stage="manufacturing", basis_value=600,
                            basis_total=1000, basis_unit="kg")]
    result = calculate_pcf(product(), items, allocation_rules=rules)
    assert result.total_kg == pytest.approx(1564.0)

    with CarbonDatabase(":memory:") as db:
        db.init_schema()
        for item in items:
            db.save_factor(item.factor)
            db.save_activity(item.activity)
        db.save_pcf_result(result, rules)

        stored_product = db.load_pcf_definition("PCF-TEST-001")
        assert stored_product == result.product

        stored_rules = db.list_allocation_rules("PCF-TEST-001")
        assert len(stored_rules) == 1
        assert stored_rules[0].share == pytest.approx(0.6)
        assert stored_rules[0].stage == "manufacturing"

        lines = db.list_pcf_lines("PCF-TEST-001")
        assert len(lines) == 5
        # The stored table keeps pre-allocation contributions; allocation is applied
        # at report time from the stored rule, so both numbers are always available.
        assert db.pcf_total_kg("PCF-TEST-001") == pytest.approx(1600.0)


def test_pcf_line_requires_stored_activity_and_factor(registry):
    result = calculate_pcf(product(), five_stage_inventory(registry))
    with CarbonDatabase(":memory:") as db:
        db.init_schema()
        with pytest.raises(PCFError, match="must be saved first"):
            db.save_pcf_line("PCF-TEST-001", result.items[0])


def test_default_allocation_rule_can_be_persisted(registry):
    """A rule with stage=None applies to every stage and must be storable."""
    from opencarbonchem.pcf import AllocationRule

    rule = AllocationRule(method="mass", basis_value=1, basis_total=4, basis_unit="kg")
    assert rule.is_default

    with CarbonDatabase(":memory:") as db:
        db.init_schema()
        db.save_pcf_definition(product())
        db.save_allocation_rule(product().pcf_id, rule)

        stored = db.list_allocation_rules(product().pcf_id)
        assert len(stored) == 1
        assert stored[0].stage is None
        assert stored[0].share == pytest.approx(0.25)


def test_legacy_schema_is_migrated_to_allow_a_null_stage(tmp_path):
    """Databases created before the fix declared stage NOT NULL."""
    path = tmp_path / "legacy.db"
    db = CarbonDatabase(path)
    db.init_schema()
    db._conn.executescript(
        """
        DROP TABLE allocation_rules;
        CREATE TABLE allocation_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pcf_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            method TEXT NOT NULL,
            basis_value REAL,
            basis_total REAL,
            basis_unit TEXT,
            notes TEXT NOT NULL DEFAULT ''
        );
        """
    )
    db._conn.commit()
    db.close()

    migrated = CarbonDatabase(path)
    migrated.init_schema()
    columns = {
        row["name"]: row["notnull"]
        for row in migrated._conn.execute("PRAGMA table_info(allocation_rules)")
    }
    assert columns["stage"] == 0
    migrated.close()


def test_stored_pcf_totals_include_allocation(registry):
    """The stored allocated total must equal PCFResult.total_kg."""
    items = five_stage_inventory(registry)
    rules = [AllocationRule(method="mass", stage="manufacturing", basis_value=600,
                            basis_total=1000, basis_unit="kg")]
    result = calculate_pcf(product(), items, allocation_rules=rules)

    with CarbonDatabase(":memory:") as db:
        db.init_schema()
        for item in items:
            db.save_factor(item.factor)
            db.save_activity(item.activity)
        db.save_pcf_result(result, rules)

        assert db.pcf_total_kg(product().pcf_id) == pytest.approx(1600.0)
        assert db.pcf_allocated_total_kg(product().pcf_id) == pytest.approx(result.total_kg)
        lines = db.list_pcf_lines(product().pcf_id)
        assert sum(line["allocated_kg"] for line in lines) == pytest.approx(result.total_kg)


def test_duplicate_activity_in_a_pcf_inventory_is_rejected(registry):
    items = five_stage_inventory(registry)
    with pytest.raises(PCFError, match="appears in both"):
        calculate_pcf(product(), [*items, items[0]])
