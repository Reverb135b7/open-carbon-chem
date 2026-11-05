"""Typed SQLite persistence for factors, activities and calculation results.

The store is deliberately thin: it validates through the same Pydantic models
the engine uses, so a record read back from the database is identical to one
constructed in memory. Results are written with their factor ID and GWP set so
a report can always be reconciled against its inputs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from ..accounting.base import ScopeResult
from ..accounting.boundary import BoundaryEntity, OrganisationalBoundary
from ..core.activity import ActivityRecord
from ..core.exceptions import BoundaryError
from ..core.calc import EmissionResult
from ..factors.models import EmissionFactor

__all__ = ["CarbonDatabase"]

_SCHEMA = Path(__file__).parent / "schema.sql"


class CarbonDatabase:
    """SQLite-backed store for factors, activity data and calculation results."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    # -- schema ------------------------------------------------------------- #
    def init_schema(self) -> None:
        """Execute the packaged DDL (idempotent, upgrades older databases)."""
        self._conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
        # Databases created before milestone 5 lack facilities.equity_share.
        columns = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(facilities)")
        }
        if "equity_share" not in columns:
            self._conn.execute(
                "ALTER TABLE facilities ADD COLUMN equity_share REAL NOT NULL DEFAULT 1.0"
            )
        self._conn.commit()

    # -- emission factors --------------------------------------------------- #
    def save_factor(self, factor: EmissionFactor) -> None:
        self._conn.execute(
            """
            INSERT INTO emission_factors (
                factor_id, activity_category, substance, value, unit, gas,
                gases_covered, geography, reporting_year, source_org,
                source_reference, version, uncertainty_pct, review_status,
                methane_basis, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                factor.factor_id, factor.activity_category, factor.substance,
                factor.value, factor.unit, factor.gas,
                ";".join(factor.gases_covered), factor.geography,
                factor.reporting_year, factor.source_org, factor.source_reference,
                factor.version, factor.uncertainty_pct, factor.review_status,
                factor.methane_basis, factor.notes,
            ),
        )
        self._conn.commit()

    # -- activity data ------------------------------------------------------ #
    def save_activity(self, activity: ActivityRecord, period_id: str | None = None) -> None:
        self._conn.execute(
            """
            INSERT INTO activity_data (
                id, period_id, scope, category, substance, quantity, unit, gas,
                methane_basis, geography, data_type, period_start, period_end,
                description, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity.activity_id, period_id, activity.scope, activity.category,
                activity.substance, activity.quantity, activity.unit, activity.gas,
                activity.methane_basis, activity.geography, activity.data_type,
                activity.period_start.isoformat() if activity.period_start else None,
                activity.period_end.isoformat() if activity.period_end else None,
                activity.description, activity.notes,
            ),
        )
        self._conn.commit()

    def list_activities(self, period_id: str | None = None) -> list[ActivityRecord]:
        if period_id is None:
            rows = self._conn.execute(
                "SELECT * FROM activity_data ORDER BY id"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM activity_data WHERE period_id = ? ORDER BY id",
                (period_id,),
            ).fetchall()
        return [_row_to_activity(r) for r in rows]

    # -- results ------------------------------------------------------------ #
    def start_run(self, run_id: str, gwp_set: str, period_id: str | None = None) -> None:
        self._conn.execute(
            "INSERT INTO calculation_runs (id, period_id, gwp_set) VALUES (?, ?, ?)",
            (run_id, period_id, gwp_set),
        )
        self._conn.commit()

    def save_results(self, run_id: str, results: Iterable[EmissionResult]) -> None:
        self._conn.executemany(
            """
            INSERT INTO calculation_results (
                run_id, activity_id, factor_id, scope, category, gas,
                emissions_kg, gwp, co2e_kg
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (run_id, r.activity_id, r.factor_id, r.scope, r.category, r.gas,
                 r.emissions_kg, r.gwp, r.co2e_kg)
                for r in results
            ],
        )
        self._conn.commit()

    def save_scope_result(self, run_id: str, result: ScopeResult) -> None:
        self.save_results(run_id, result.results)

    def total_co2e_kg(self, run_id: str) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(co2e_kg), 0) AS total FROM calculation_results "
            "WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return float(row["total"])

    # -- organisational boundary ------------------------------------------- #
    def save_boundary(self, boundary: OrganisationalBoundary) -> None:
        """Persist the documented boundary; re-saving replaces its entities."""
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO organizations (id, name, boundary_method, consolidation, notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    boundary_method = excluded.boundary_method,
                    consolidation = excluded.consolidation,
                    notes = excluded.notes
                """,
                (boundary.org_id, boundary.name, boundary.method,
                 boundary.method, boundary.notes),
            )
            self._conn.execute(
                "DELETE FROM facilities WHERE org_id = ?", (boundary.org_id,)
            )
            self._conn.executemany(
                """
                INSERT INTO facilities (id, org_id, name, geography, equity_share, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (e.entity_id, boundary.org_id, e.name, e.geography,
                     e.equity_share, e.notes)
                    for e in boundary.entities
                ],
            )

    def load_boundary(self, org_id: str) -> OrganisationalBoundary:
        """Read a persisted boundary back into the validated model."""
        row = self._conn.execute(
            "SELECT id, name, boundary_method, notes FROM organizations WHERE id = ?",
            (org_id,),
        ).fetchone()
        if row is None:
            raise BoundaryError(f"no organisational boundary recorded for {org_id!r}")
        entities = tuple(
            BoundaryEntity(
                entity_id=facility["id"],
                name=facility["name"],
                equity_share=facility["equity_share"],
                geography=facility["geography"],
                notes=facility["notes"],
            )
            for facility in self._conn.execute(
                "SELECT id, name, geography, equity_share, notes "
                "FROM facilities WHERE org_id = ? ORDER BY id",
                (org_id,),
            )
        )
        return OrganisationalBoundary(
            org_id=row["id"],
            name=row["name"],
            method=row["boundary_method"],
            entities=entities,
            notes=row["notes"],
        )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "CarbonDatabase":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _row_to_activity(row: sqlite3.Row) -> ActivityRecord:
    return ActivityRecord(
        activity_id=row["id"],
        description=row["description"],
        scope=row["scope"],
        category=row["category"],
        substance=row["substance"],
        quantity=row["quantity"],
        unit=row["unit"],
        gas=row["gas"],
        methane_basis=row["methane_basis"],
        geography=row["geography"],
        data_type=row["data_type"],
        period_start=row["period_start"],
        period_end=row["period_end"],
        notes=row["notes"],
    )
