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
from ..core.exceptions import BoundaryError, PCFError
from ..core.calc import EmissionResult
from ..factors.models import EmissionFactor
from ..pcf.allocation import AllocationRule
from ..pcf.calculator import PCFLineItem, PCFResult
from ..pcf.models import ProductDefinition

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
        self._migrate()
        # Databases created before milestone 5 lack facilities.equity_share.
        columns = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(facilities)")
        }
        if "equity_share" not in columns:
            self._conn.execute(
                "ALTER TABLE facilities ADD COLUMN equity_share REAL NOT NULL DEFAULT 1.0"
            )
        self._conn.commit()

    def _migrate(self) -> None:
        """Bring databases created by earlier milestones up to the current schema."""
        allocation_columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(allocation_rules)")
        }
        if "basis_total" not in allocation_columns:
            self._conn.execute("ALTER TABLE allocation_rules ADD COLUMN basis_total REAL")

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
            ON CONFLICT(factor_id) DO UPDATE SET
                activity_category = excluded.activity_category,
                substance = excluded.substance,
                value = excluded.value,
                unit = excluded.unit,
                gas = excluded.gas,
                gases_covered = excluded.gases_covered,
                geography = excluded.geography,
                reporting_year = excluded.reporting_year,
                source_org = excluded.source_org,
                source_reference = excluded.source_reference,
                version = excluded.version,
                uncertainty_pct = excluded.uncertainty_pct,
                review_status = excluded.review_status,
                methane_basis = excluded.methane_basis,
                notes = excluded.notes
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
            ON CONFLICT(id) DO UPDATE SET
                period_id = excluded.period_id,
                scope = excluded.scope,
                category = excluded.category,
                substance = excluded.substance,
                quantity = excluded.quantity,
                unit = excluded.unit,
                gas = excluded.gas,
                methane_basis = excluded.methane_basis,
                geography = excluded.geography,
                data_type = excluded.data_type,
                period_start = excluded.period_start,
                period_end = excluded.period_end,
                description = excluded.description,
                notes = excluded.notes
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

    # -- product carbon footprint (milestone 6) ----------------------------- #
    def save_pcf_definition(self, product: ProductDefinition) -> None:
        """Persist a product definition; re-saving replaces the stored row."""
        self._conn.execute(
            """
            INSERT INTO pcf_definitions (
                id, product_name, functional_unit, production_qty,
                production_unit, system_boundary, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                product_name = excluded.product_name,
                functional_unit = excluded.functional_unit,
                production_qty = excluded.production_qty,
                production_unit = excluded.production_unit,
                system_boundary = excluded.system_boundary,
                notes = excluded.notes
            """,
            (
                product.pcf_id, product.product_name, product.functional_unit,
                product.production_qty, product.production_unit,
                product.system_boundary, product.notes,
            ),
        )
        self._conn.commit()

    def load_pcf_definition(self, pcf_id: str) -> ProductDefinition:
        row = self._conn.execute(
            "SELECT * FROM pcf_definitions WHERE id = ?", (pcf_id,)
        ).fetchone()
        if row is None:
            raise PCFError(f"no PCF definition recorded for {pcf_id!r}")
        return ProductDefinition(
            pcf_id=row["id"],
            product_name=row["product_name"],
            functional_unit=row["functional_unit"],
            production_qty=row["production_qty"],
            production_unit=row["production_unit"],
            system_boundary=row["system_boundary"],
            notes=row["notes"],
        )

    def save_allocation_rule(self, pcf_id: str, rule: AllocationRule) -> None:
        """Persist an allocation rule; re-saving replaces rules for that stage."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM allocation_rules WHERE pcf_id = ? AND stage IS ?",
                (pcf_id, rule.stage),
            )
            self._conn.execute(
                """
                INSERT INTO allocation_rules (
                    pcf_id, stage, method, basis_value, basis_total, basis_unit, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (pcf_id, rule.stage, rule.method, rule.basis_value,
                 rule.basis_total, rule.basis_unit, rule.notes),
            )

    def list_allocation_rules(self, pcf_id: str) -> list[AllocationRule]:
        rows = self._conn.execute(
            "SELECT * FROM allocation_rules WHERE pcf_id = ? ORDER BY id", (pcf_id,)
        ).fetchall()
        return [
            AllocationRule(
                method=row["method"],
                stage=row["stage"],
                basis_value=row["basis_value"],
                basis_total=row["basis_total"],
                basis_unit=row["basis_unit"],
                notes=row["notes"],
            )
            for row in rows
        ]

    def save_pcf_line(self, pcf_id: str, line: PCFLineItem) -> None:
        """Persist one inventory line.

        The referenced activity and factor must already be stored: the PCF
        inventory is an audit trail and must not contain untraceable rows.
        """
        try:
            self._conn.execute(
                """
                INSERT INTO pcf_inventory (
                    pcf_id, stage, activity_id, factor_id, co2e_kg,
                    excluded_from_corporate
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (pcf_id, line.stage, line.activity_id, line.factor_id,
                 line.co2e_kg, int(line.excluded_from_corporate)),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise PCFError(
                f"cannot store PCF line {line.activity_id}/{line.factor_id}: the "
                f"activity and factor must be saved first ({exc})"
            ) from exc

    def save_pcf_result(self, result: PCFResult,
                        rules: Iterable[AllocationRule] = ()) -> None:
        """Persist a complete PCF: definition, allocation rules and inventory."""
        self.save_pcf_definition(result.product)
        for rule in rules:
            self.save_allocation_rule(result.product.pcf_id, rule)
        self._conn.execute(
            "DELETE FROM pcf_inventory WHERE pcf_id = ?", (result.product.pcf_id,)
        )
        self._conn.commit()
        for line in result.items:
            self.save_pcf_line(result.product.pcf_id, line)

    def list_pcf_lines(self, pcf_id: str) -> list[dict]:
        """Stored inventory rows (numbers as persisted, not recomputed)."""
        rows = self._conn.execute(
            "SELECT stage, activity_id, factor_id, co2e_kg, excluded_from_corporate "
            "FROM pcf_inventory WHERE pcf_id = ? ORDER BY id",
            (pcf_id,),
        ).fetchall()
        return [
            {
                "stage": row["stage"],
                "activity_id": row["activity_id"],
                "factor_id": row["factor_id"],
                "co2e_kg": row["co2e_kg"],
                "excluded_from_corporate": bool(row["excluded_from_corporate"]),
            }
            for row in rows
        ]

    def pcf_total_kg(self, pcf_id: str) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(co2e_kg), 0) AS total FROM pcf_inventory WHERE pcf_id = ?",
            (pcf_id,),
        ).fetchone()
        return float(row["total"])

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
