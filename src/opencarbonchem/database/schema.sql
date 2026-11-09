-- OpenCarbonChem SQLite schema (idempotent).
-- See docs/architecture.md §3 for the entity relationship summary.
-- Isolation rule: calculation_results always reference both the activity and
-- the factor that produced them, so any reported total can be re-derived.

CREATE TABLE IF NOT EXISTS organizations (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    boundary_method TEXT NOT NULL DEFAULT 'operational_control'
                    CHECK (boundary_method IN ('equity_share', 'financial_control', 'operational_control')),
    consolidation   TEXT NOT NULL DEFAULT 'operational_control',
    notes           TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS facilities (
    id           TEXT PRIMARY KEY,
    org_id       TEXT NOT NULL REFERENCES organizations(id),
    name         TEXT NOT NULL,
    geography    TEXT NOT NULL DEFAULT 'GLOBAL',
    industry     TEXT NOT NULL DEFAULT '',
    equity_share REAL NOT NULL DEFAULT 1.0
                 CHECK (equity_share > 0 AND equity_share <= 1),
    notes        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS reporting_periods (
    id         TEXT PRIMARY KEY,
    org_id     TEXT NOT NULL REFERENCES organizations(id),
    label      TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date   TEXT NOT NULL,
    CHECK (start_date <= end_date)
);

CREATE TABLE IF NOT EXISTS activity_data (
    id             TEXT PRIMARY KEY,
    period_id      TEXT REFERENCES reporting_periods(id),
    scope          INTEGER NOT NULL CHECK (scope IN (1, 2, 3)),
    category       TEXT NOT NULL,
    substance      TEXT NOT NULL,
    quantity       REAL NOT NULL CHECK (quantity >= 0),
    unit           TEXT NOT NULL,
    gas            TEXT,
    methane_basis  TEXT CHECK (methane_basis IS NULL OR methane_basis IN ('fossil', 'non_fossil')),
    geography      TEXT NOT NULL DEFAULT 'GLOBAL',
    data_type      TEXT NOT NULL DEFAULT 'primary'
                   CHECK (data_type IN ('primary', 'secondary')),
    period_start   TEXT,
    period_end     TEXT,
    description    TEXT NOT NULL DEFAULT '',
    notes          TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_activity_period ON activity_data(period_id);
CREATE INDEX IF NOT EXISTS idx_activity_scope ON activity_data(scope);

-- Canonical factor store. Provenance columns mirror handover §6 exactly.
CREATE TABLE IF NOT EXISTS emission_factors (
    factor_id          TEXT PRIMARY KEY,
    activity_category  TEXT NOT NULL,
    substance          TEXT NOT NULL,
    value              REAL NOT NULL CHECK (value > 0),
    unit               TEXT NOT NULL,
    gas                TEXT NOT NULL,
    gases_covered      TEXT NOT NULL DEFAULT '',
    geography          TEXT NOT NULL DEFAULT 'GLOBAL',
    reporting_year     INTEGER NOT NULL,
    source_org         TEXT NOT NULL,
    source_reference   TEXT NOT NULL,
    version            TEXT NOT NULL DEFAULT '',
    uncertainty_pct    REAL CHECK (uncertainty_pct IS NULL OR (uncertainty_pct >= 0 AND uncertainty_pct <= 100)),
    review_status      TEXT NOT NULL DEFAULT 'illustrative'
                       CHECK (review_status IN ('illustrative', 'published', 'verified')),
    methane_basis      TEXT CHECK (methane_basis IS NULL OR methane_basis IN ('fossil', 'non_fossil')),
    notes              TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_ef_lookup
    ON emission_factors(activity_category, substance, geography, reporting_year);

CREATE TABLE IF NOT EXISTS gwp_values (
    gwp_set        TEXT NOT NULL,
    gas            TEXT NOT NULL,
    methane_basis  TEXT CHECK (methane_basis IS NULL OR methane_basis IN ('fossil', 'non_fossil')),
    value          REAL NOT NULL CHECK (value > 0),
    reference      TEXT NOT NULL,
    PRIMARY KEY (gwp_set, gas, methane_basis)
);

-- One engine execution; results below belong to exactly one run.
CREATE TABLE IF NOT EXISTS calculation_runs (
    id         TEXT PRIMARY KEY,
    period_id  TEXT REFERENCES reporting_periods(id),
    gwp_set    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS calculation_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL REFERENCES calculation_runs(id),
    activity_id   TEXT NOT NULL,
    factor_id     TEXT NOT NULL REFERENCES emission_factors(factor_id),
    scope         INTEGER NOT NULL CHECK (scope IN (1, 2, 3)),
    category      TEXT NOT NULL,
    gas           TEXT NOT NULL,
    emissions_kg  REAL NOT NULL,
    gwp           REAL,
    co2e_kg       REAL NOT NULL,
    CHECK (gwp IS NULL OR gwp > 0)
);

CREATE INDEX IF NOT EXISTS idx_results_run ON calculation_results(run_id);
CREATE INDEX IF NOT EXISTS idx_results_scope ON calculation_results(scope);

-- Product carbon footprint (populated from milestone 6 onwards).
CREATE TABLE IF NOT EXISTS pcf_definitions (
    id               TEXT PRIMARY KEY,
    product_name     TEXT NOT NULL,
    functional_unit  TEXT NOT NULL,
    production_qty   REAL NOT NULL CHECK (production_qty > 0),
    production_unit  TEXT NOT NULL,
    system_boundary  TEXT NOT NULL CHECK (system_boundary IN ('cradle_to_gate', 'cradle_to_grave')),
    notes            TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS pcf_inventory (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pcf_id       TEXT NOT NULL REFERENCES pcf_definitions(id),
    stage        TEXT NOT NULL,
    activity_id  TEXT REFERENCES activity_data(id),
    factor_id    TEXT REFERENCES emission_factors(factor_id),
    co2e_kg      REAL NOT NULL,
    allocation_share REAL,
    allocated_kg REAL,
    excluded_from_corporate INTEGER NOT NULL DEFAULT 0 CHECK (excluded_from_corporate IN (0, 1))
);

CREATE TABLE IF NOT EXISTS allocation_rules (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pcf_id       TEXT NOT NULL REFERENCES pcf_definitions(id),
    -- NULL stage is the default rule, applied to every stage without its own.
    stage        TEXT,
    method       TEXT NOT NULL CHECK (method IN ('mass', 'economic', 'physical_causality', 'none')),
    basis_value  REAL,
    basis_total  REAL,
    basis_unit   TEXT,
    notes        TEXT NOT NULL DEFAULT ''
);

-- Decarbonisation scenarios (populated from milestone 8 onwards).
CREATE TABLE IF NOT EXISTS scenarios (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    lever       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scenario_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id   TEXT NOT NULL REFERENCES scenarios(id),
    run_id        TEXT NOT NULL REFERENCES calculation_runs(id),
    category      TEXT NOT NULL,
    baseline_kg   REAL NOT NULL,
    scenario_kg   REAL NOT NULL,
    reduction_kg  REAL NOT NULL
);
