"""Database tests: schema initialisation and typed round-trips."""

from datetime import date

import pytest
from pydantic import ValidationError

from opencarbonchem.accounting.base import ScopeResult
from opencarbonchem.accounting.boundary import BoundaryEntity, OrganisationalBoundary
from opencarbonchem.core.activity import ActivityRecord
from opencarbonchem.core.exceptions import BoundaryError
from opencarbonchem.core.calc import compute_emissions
from opencarbonchem.database import CarbonDatabase
from opencarbonchem.factors.registry import FactorRegistry, illustrative_seed_path


@pytest.fixture(scope="module")
def registry() -> FactorRegistry:
    return FactorRegistry.from_csv(illustrative_seed_path())


@pytest.mark.integration
def test_schema_initialisation_is_idempotent():
    with CarbonDatabase() as db:
        db.init_schema()
        db.init_schema()  # second run must not fail


@pytest.mark.integration
def test_activity_round_trip():
    activity = ActivityRecord(
        activity_id="ACT-DB1",
        description="Natural gas boiler",
        scope=1,
        category="stationary_combustion",
        substance="natural_gas",
        quantity=500.0,
        unit="kWh",
        gas="CO2",
        geography="GLOBAL",
        data_type="primary",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        notes="SYNTHETIC test record",
    )
    with CarbonDatabase() as db:
        db.init_schema()
        db.save_activity(activity)
        restored = db.list_activities()
        assert len(restored) == 1
        assert restored[0] == activity
        assert restored[0].reporting_year == 2024


@pytest.mark.integration
def test_invalid_activity_is_rejected_by_model():
    with pytest.raises(ValidationError):
        ActivityRecord(
            activity_id="ACT-BAD",
            scope=1,
            category="stationary_combustion",
            substance="natural_gas",
            quantity=-5.0,  # negative activity data is invalid
            unit="kWh",
        )


@pytest.mark.integration
def test_results_round_trip_and_total(registry, tmp_path):
    activity = ActivityRecord(
        activity_id="ACT-DB2",
        scope=1,
        category="stationary_combustion",
        substance="natural_gas",
        quantity=1000.0,
        unit="kWh",
        gas="CO2",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
    )
    factor = registry.find(
        activity_category=activity.category,
        substance=activity.substance,
        geography=activity.geography,
        year=activity.reporting_year,
        gas=activity.gas,
    )
    result = compute_emissions(activity, factor)
    # Hand check: 1000 kWh × 0.18 kg CO2/kWh = 180 kg CO2e.
    assert result.co2e_kg == pytest.approx(180.0)

    db_path = tmp_path / "occ.db"
    with CarbonDatabase(db_path) as db:
        db.init_schema()
        db.save_factor(factor)
        db.save_activity(activity)
        db.start_run("RUN-1", "AR6")
        db.save_scope_result("RUN-1", ScopeResult.from_results(1, [result]))
        assert db.total_co2e_kg("RUN-1") == pytest.approx(180.0)
        assert db.total_co2e_kg("RUN-NOPE") == 0.0

    # The file persists across connections.
    with CarbonDatabase(db_path) as db:
        db.init_schema()
        assert db.total_co2e_kg("RUN-1") == pytest.approx(180.0)


@pytest.mark.integration
def test_boundary_round_trip(tmp_path):
    boundary = OrganisationalBoundary(
        org_id="ORG-1",
        name="Synthetic Chemicals Ltd",
        method="equity_share",
        entities=(
            BoundaryEntity("ENT-001", "Owned plant", equity_share=0.6, geography="GB"),
            BoundaryEntity("ENT-002", "JV plant", equity_share=1.0, geography="FR"),
        ),
        notes="SYNTHETIC test boundary",
    )
    db_path = tmp_path / "org.db"
    with CarbonDatabase(db_path) as db:
        db.init_schema()
        db.save_boundary(boundary)
        db.save_boundary(boundary)  # re-save replaces entities, no duplicates
        assert db.load_boundary("ORG-1") == boundary

    # Persisted across connections and still validated on load.
    with CarbonDatabase(db_path) as db:
        db.init_schema()
        loaded = db.load_boundary("ORG-1")
        assert loaded.entities[0].equity_share == 0.6
        assert loaded.method == "equity_share"

    with CarbonDatabase(db_path) as db:
        db.init_schema()
        with pytest.raises(BoundaryError):
            db.load_boundary("ORG-MISSING")
