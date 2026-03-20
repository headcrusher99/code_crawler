"""DuckDB schema definitions — all tables from the design specification."""

from __future__ import annotations

# ──────────────────────────────────────────────
# Complete DDL (from design_idea.md §3.1)
# ──────────────────────────────────────────────

SCHEMA_DDL = """
-- ════════════════════════════════════════════
-- Core Structural Tables
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS Directory (
    id        BIGINT PRIMARY KEY,
    path      TEXT UNIQUE,
    name      TEXT,
    summary   TEXT,
    depth     INT,
    is_custom BOOL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS File (
    id            BIGINT PRIMARY KEY,
    path          TEXT UNIQUE,
    hash          TEXT,
    last_modified TIMESTAMP,
    is_custom     BOOL DEFAULT FALSE,
    language      TEXT,
    loc           INT DEFAULT 0,
    embedding     FLOAT[384]
);

CREATE TABLE IF NOT EXISTS Function (
    id         BIGINT PRIMARY KEY,
    file_id    BIGINT REFERENCES File(id),
    name       TEXT,
    signature  TEXT,
    start_line INT,
    end_line   INT,
    summary    TEXT,
    complexity INT DEFAULT 1,
    embedding  FLOAT[384]
);

CREATE TABLE IF NOT EXISTS Struct (
    id      BIGINT PRIMARY KEY,
    file_id BIGINT REFERENCES File(id),
    name    TEXT,
    summary TEXT,
    members TEXT[]
);

CREATE TABLE IF NOT EXISTS Macro (
    id              BIGINT PRIMARY KEY,
    file_id         BIGINT REFERENCES File(id),
    name            TEXT,
    value           TEXT,
    is_config_guard BOOL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS BuildConfig (
    id           BIGINT PRIMARY KEY,
    key          TEXT,
    value        TEXT,
    source_file  TEXT,
    build_system TEXT
);

CREATE TABLE IF NOT EXISTS DeviceTreeNode (
    id          BIGINT PRIMARY KEY,
    path        TEXT,
    compatible  TEXT[],
    properties  JSON,
    source_file TEXT
);

-- ════════════════════════════════════════════
-- Edge Tables (Relationships)
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS contains_dir (
    parent_id BIGINT,
    child_id  BIGINT,
    PRIMARY KEY (parent_id, child_id)
);

CREATE TABLE IF NOT EXISTS contains_file (
    dir_id  BIGINT,
    file_id BIGINT,
    PRIMARY KEY (dir_id, file_id)
);

CREATE TABLE IF NOT EXISTS contains_func (
    file_id BIGINT,
    func_id BIGINT,
    PRIMARY KEY (file_id, func_id)
);

CREATE TABLE IF NOT EXISTS calls (
    caller_id      BIGINT,
    callee_id      BIGINT,
    call_site_line INT,
    PRIMARY KEY (caller_id, callee_id, call_site_line)
);

CREATE TABLE IF NOT EXISTS uses_struct (
    func_id   BIGINT,
    struct_id BIGINT,
    PRIMARY KEY (func_id, struct_id)
);

CREATE TABLE IF NOT EXISTS includes_file (
    source_id BIGINT,
    target_id BIGINT,
    PRIMARY KEY (source_id, target_id)
);

CREATE TABLE IF NOT EXISTS guarded_by (
    func_id   BIGINT,
    config_id BIGINT,
    PRIMARY KEY (func_id, config_id)
);

CREATE TABLE IF NOT EXISTS dt_binds_driver (
    dt_node_id BIGINT,
    func_id    BIGINT,
    PRIMARY KEY (dt_node_id, func_id)
);

-- ════════════════════════════════════════════
-- Cross-Boundary & Telemetry Tables
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS calls_over_ipc (
    caller_func_id BIGINT,
    callee_func_id BIGINT,
    interface_name TEXT,
    PRIMARY KEY (caller_func_id, callee_func_id)
);

CREATE TABLE IF NOT EXISTS LogLiteral (
    id             BIGINT PRIMARY KEY,
    hash           TEXT,
    literal_string TEXT,
    log_level      TEXT
);

CREATE TABLE IF NOT EXISTS emits_log (
    func_id BIGINT REFERENCES Function(id),
    log_id  BIGINT REFERENCES LogLiteral(id),
    PRIMARY KEY (func_id, log_id)
);

-- ════════════════════════════════════════════
-- Tiering & Intelligence Tracking
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS Tier (
    id              BIGINT PRIMARY KEY,
    path            TEXT UNIQUE,
    tier            INT CHECK (tier BETWEEN 0 AND 3),
    source          TEXT,
    confidence      FLOAT,
    last_classified TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Variable (
    id             BIGINT PRIMARY KEY,
    func_id        BIGINT REFERENCES Function(id),
    file_id        BIGINT REFERENCES File(id),
    name           TEXT,
    var_type       TEXT,
    is_global      BOOL DEFAULT FALSE,
    is_static      BOOL DEFAULT FALSE,
    usage_count    INT DEFAULT 0,
    write_count    INT DEFAULT 0,
    priority_score FLOAT DEFAULT 0.0,
    embedding      FLOAT[384]
);

CREATE TABLE IF NOT EXISTS IndexManifest (
    file_id       BIGINT PRIMARY KEY REFERENCES File(id),
    manifest_json JSON
);

CREATE TABLE IF NOT EXISTS PriorityScore (
    func_id                BIGINT PRIMARY KEY REFERENCES Function(id),
    tier_weight            FLOAT DEFAULT 0.0,
    usage_frequency        FLOAT DEFAULT 0.0,
    graph_centrality       FLOAT DEFAULT 0.0,
    build_guard_activation FLOAT DEFAULT 0.0,
    runtime_frequency      FLOAT DEFAULT 0.0,
    recency_score          FLOAT DEFAULT 0.0,
    composite_score        FLOAT DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS SummaryMeta (
    entity_id   BIGINT,
    entity_type TEXT,
    model_used  TEXT,
    confidence  FLOAT,
    version     INT DEFAULT 1,
    created_at  TIMESTAMP,
    PRIMARY KEY (entity_id, entity_type)
);

-- ════════════════════════════════════════════
-- Runtime & Debug Data
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS RuntimeTrace (
    id               BIGINT PRIMARY KEY,
    func_id          BIGINT REFERENCES Function(id),
    source           TEXT,
    hit_count        INT DEFAULT 0,
    avg_stack_depth  FLOAT DEFAULT 0.0,
    has_memory_error BOOL DEFAULT FALSE,
    last_seen        TIMESTAMP,
    trace_data       JSON
);

-- ════════════════════════════════════════════
-- Collaboration & Feedback
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS SyncLog (
    id          BIGINT PRIMARY KEY,
    entity_id   BIGINT,
    entity_type TEXT,
    change_type TEXT,
    changed_by  TEXT,
    commit_sha  TEXT,
    timestamp   TIMESTAMP,
    delta_json  JSON
);

CREATE TABLE IF NOT EXISTS Annotation (
    id              BIGINT PRIMARY KEY,
    entity_id       BIGINT,
    entity_type     TEXT,
    annotation_type TEXT,
    content         TEXT,
    model           TEXT,
    confidence      FLOAT,
    approved        BOOL DEFAULT FALSE,
    created_at      TIMESTAMP
);

-- ════════════════════════════════════════════
-- Pre-Materialized LLM Views
-- ════════════════════════════════════════════

CREATE OR REPLACE VIEW LLM_HighPriority AS
    SELECT f.*, ps.composite_score, t.tier, sm.confidence AS summary_confidence
    FROM Function f
    JOIN PriorityScore ps ON f.id = ps.func_id
    JOIN contains_func cf ON f.id = cf.func_id
    JOIN contains_file cfl ON cf.file_id = cfl.file_id
    JOIN Tier t ON t.path = (SELECT path FROM File WHERE id = cf.file_id)
    LEFT JOIN SummaryMeta sm ON f.id = sm.entity_id AND sm.entity_type = 'function'
    WHERE t.tier >= 2
    ORDER BY ps.composite_score DESC;

CREATE OR REPLACE VIEW LLM_SharedState AS
    SELECT v.*, f.name AS func_name, fi.path AS file_path
    FROM Variable v
    JOIN Function f ON v.func_id = f.id
    JOIN File fi ON v.file_id = fi.id
    WHERE v.is_global = TRUE AND v.write_count > 1
    ORDER BY v.write_count DESC;

CREATE OR REPLACE VIEW LLM_RuntimeHotspots AS
    SELECT f.*, rt.hit_count, rt.has_memory_error, rt.source AS trace_source,
           ps.composite_score
    FROM Function f
    JOIN RuntimeTrace rt ON f.id = rt.func_id
    LEFT JOIN PriorityScore ps ON f.id = ps.func_id
    ORDER BY rt.hit_count DESC;
"""


def create_schema(connection) -> None:
    """Execute the full schema DDL on a DuckDB connection."""
    connection.execute(SCHEMA_DDL)
