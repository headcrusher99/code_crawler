"""DuckDB schema definitions — v5 complete DDL.

All tables from the v5 architecture specification including:
  - Core structural tables (Directory, File, Function, Struct, Macro, Variable)
  - Edge tables (calls, calls_over_ipc, calls_cross_language, data_flow, etc.)
  - Telemetry tables (RuntimeTrace, LogLiteral)
  - Intelligence tables (Tier, PriorityScore, IndexManifest, Annotation)
  - Collaboration tables (SyncLog, GitBranch)
  - Pre-materialized LLM views

Usage:
    from codecrawler.storage.schema import create_schema
    create_schema(connection)
"""

from __future__ import annotations

# ──────────────────────────────────────────────
# Complete DDL (v5 Specification)
# ──────────────────────────────────────────────

SCHEMA_DDL = """
-- ════════════════════════════════════════════
-- Sequences for auto-incrementing IDs
-- ════════════════════════════════════════════

CREATE SEQUENCE IF NOT EXISTS dir_seq START 1;
CREATE SEQUENCE IF NOT EXISTS file_seq START 1;
CREATE SEQUENCE IF NOT EXISTS func_seq START 1;
CREATE SEQUENCE IF NOT EXISTS struct_seq START 1;
CREATE SEQUENCE IF NOT EXISTS macro_seq START 1;
CREATE SEQUENCE IF NOT EXISTS var_seq START 1;
CREATE SEQUENCE IF NOT EXISTS call_seq START 1;
CREATE SEQUENCE IF NOT EXISTS ipc_seq START 1;
CREATE SEQUENCE IF NOT EXISTS cross_lang_seq START 1;
CREATE SEQUENCE IF NOT EXISTS dt_seq START 1;
CREATE SEQUENCE IF NOT EXISTS bc_seq START 1;
CREATE SEQUENCE IF NOT EXISTS log_seq START 1;
CREATE SEQUENCE IF NOT EXISTS rt_seq START 1;
CREATE SEQUENCE IF NOT EXISTS tier_seq START 1;
CREATE SEQUENCE IF NOT EXISTS annot_seq START 1;
CREATE SEQUENCE IF NOT EXISTS sync_seq START 1;
CREATE SEQUENCE IF NOT EXISTS branch_seq START 1;
CREATE SEQUENCE IF NOT EXISTS df_seq START 1;
CREATE SEQUENCE IF NOT EXISTS repomap_seq START 1;

-- ════════════════════════════════════════════
-- Core Structural Tables
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS Directory (
    id          BIGINT PRIMARY KEY DEFAULT nextval('dir_seq'),
    path        TEXT UNIQUE,
    name        TEXT,
    parent_path TEXT,
    depth       INT DEFAULT 0,
    summary     TEXT,
    is_custom   BOOL DEFAULT FALSE,
    file_count  INT DEFAULT 0,
    total_loc   INT DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS File (
    id            BIGINT PRIMARY KEY DEFAULT nextval('file_seq'),
    path          TEXT UNIQUE,
    directory_id  BIGINT,
    filename      TEXT,
    extension     TEXT,
    language      TEXT,
    content_hash  TEXT,
    size_bytes    INT DEFAULT 0,
    loc           INT DEFAULT 0,
    loc_blank     INT DEFAULT 0,
    loc_comment   INT DEFAULT 0,
    last_modified TIMESTAMP,
    is_custom     BOOL DEFAULT FALSE,
    is_header     BOOL DEFAULT FALSE,
    is_generated  BOOL DEFAULT FALSE,
    compile_flags TEXT,
    summary       TEXT,
    embedding     FLOAT[384],
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Function (
    id             BIGINT PRIMARY KEY DEFAULT nextval('func_seq'),
    file_id        BIGINT REFERENCES File(id),
    name           TEXT,
    qualified_name TEXT,
    signature      TEXT,
    return_type    TEXT,
    parameters     TEXT[],
    start_line     INT,
    end_line       INT,
    body_loc       INT DEFAULT 0,
    complexity     INT DEFAULT 1,
    body_hash      TEXT,
    is_static      BOOL DEFAULT FALSE,
    is_inline      BOOL DEFAULT FALSE,
    is_exported    BOOL DEFAULT TRUE,
    is_callback    BOOL DEFAULT FALSE,
    is_init        BOOL DEFAULT FALSE,
    is_isr         BOOL DEFAULT FALSE,
    language       TEXT,
    summary        TEXT,
    embedding      FLOAT[384],
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Struct (
    id             BIGINT PRIMARY KEY DEFAULT nextval('struct_seq'),
    file_id        BIGINT REFERENCES File(id),
    name           TEXT,
    qualified_name TEXT,
    kind           TEXT DEFAULT 'struct',
    members        TEXT[],
    member_types   TEXT[],
    start_line     INT,
    end_line       INT,
    summary        TEXT,
    embedding      FLOAT[384],
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Macro (
    id               BIGINT PRIMARY KEY DEFAULT nextval('macro_seq'),
    file_id          BIGINT REFERENCES File(id),
    name             TEXT,
    value            TEXT,
    parameters       TEXT[],
    is_config_guard  BOOL DEFAULT FALSE,
    is_include_guard BOOL DEFAULT FALSE,
    is_function_like BOOL DEFAULT FALSE,
    line             INT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Variable (
    id              BIGINT PRIMARY KEY DEFAULT nextval('var_seq'),
    func_id         BIGINT REFERENCES Function(id),
    file_id         BIGINT REFERENCES File(id),
    name            TEXT,
    var_type        TEXT,
    qualified_name  TEXT,
    is_global       BOOL DEFAULT FALSE,
    is_static       BOOL DEFAULT FALSE,
    is_volatile     BOOL DEFAULT FALSE,
    is_const        BOOL DEFAULT FALSE,
    is_atomic       BOOL DEFAULT FALSE,
    scope           TEXT DEFAULT 'local',
    line            INT,
    usage_count     INT DEFAULT 0,
    write_count     INT DEFAULT 0,
    priority_score  FLOAT DEFAULT 0.0,
    embedding       FLOAT[384],
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════
-- Build & Hardware Tables
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS BuildConfig (
    id            BIGINT PRIMARY KEY DEFAULT nextval('bc_seq'),
    key           TEXT NOT NULL,
    value         TEXT,
    source_file   TEXT,
    build_system  TEXT,
    scope         TEXT DEFAULT 'global',
    is_enabled    BOOL DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS DeviceTreeNode (
    id            BIGINT PRIMARY KEY DEFAULT nextval('dt_seq'),
    path          TEXT,
    name          TEXT,
    compatible    TEXT[],
    status        TEXT DEFAULT 'okay',
    reg           TEXT,
    interrupts    TEXT,
    properties    JSON,
    source_file   TEXT,
    parent_path   TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════
-- Containment Edge Tables
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

-- ════════════════════════════════════════════
-- Call Graph Edge Tables
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS calls (
    id              BIGINT PRIMARY KEY DEFAULT nextval('call_seq'),
    caller_id       BIGINT,
    callee_id       BIGINT,
    call_site_line  INT,
    call_site_col   INT,
    is_direct       BOOL DEFAULT TRUE,
    is_conditional  BOOL DEFAULT FALSE,
    is_loop         BOOL DEFAULT FALSE,
    call_count      INT DEFAULT 1,
    confidence      FLOAT DEFAULT 1.0,
    resolved_by     TEXT DEFAULT 'name'
);

CREATE TABLE IF NOT EXISTS calls_over_ipc (
    id                BIGINT PRIMARY KEY DEFAULT nextval('ipc_seq'),
    caller_func_id    BIGINT,
    callee_func_id    BIGINT,
    interface_name    TEXT,
    method_name       TEXT,
    protocol          TEXT,
    direction         TEXT DEFAULT 'call',
    is_async          BOOL DEFAULT FALSE,
    confidence        FLOAT DEFAULT 0.8
);

CREATE TABLE IF NOT EXISTS calls_cross_language (
    id                BIGINT PRIMARY KEY DEFAULT nextval('cross_lang_seq'),
    caller_func_id    BIGINT,
    callee_func_id    BIGINT,
    caller_language   TEXT,
    callee_language   TEXT,
    ffi_mechanism     TEXT,
    binding_pattern   TEXT,
    confidence        FLOAT DEFAULT 0.7
);

-- ════════════════════════════════════════════
-- Structural Edge Tables
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS uses_struct (
    func_id    BIGINT,
    struct_id  BIGINT,
    usage_type TEXT DEFAULT 'reference',
    PRIMARY KEY (func_id, struct_id, usage_type)
);

CREATE TABLE IF NOT EXISTS includes_file (
    source_id BIGINT,
    target_id BIGINT,
    is_system BOOL DEFAULT FALSE,
    line      INT,
    PRIMARY KEY (source_id, target_id)
);

CREATE TABLE IF NOT EXISTS guarded_by (
    func_id   BIGINT,
    config_id BIGINT,
    guard_type TEXT DEFAULT 'ifdef',
    PRIMARY KEY (func_id, config_id)
);

CREATE TABLE IF NOT EXISTS dt_binds_driver (
    dt_node_id BIGINT,
    func_id    BIGINT,
    binding    TEXT,
    PRIMARY KEY (dt_node_id, func_id)
);

-- ════════════════════════════════════════════
-- Data Flow Edges (Joern-inspired)
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS data_flow (
    id              BIGINT PRIMARY KEY DEFAULT nextval('df_seq'),
    source_var_id   BIGINT,
    sink_var_id     BIGINT,
    source_func_id  BIGINT,
    sink_func_id    BIGINT,
    flow_type       TEXT,
    via_call_id     BIGINT,
    confidence      FLOAT DEFAULT 0.8
);

-- ════════════════════════════════════════════
-- Telemetry & Runtime Tables
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS LogLiteral (
    id              BIGINT PRIMARY KEY DEFAULT nextval('log_seq'),
    hash            TEXT UNIQUE,
    literal_string  TEXT,
    log_level       TEXT,
    log_macro       TEXT,
    format_args     INT DEFAULT 0,
    normalized      TEXT
);

CREATE TABLE IF NOT EXISTS emits_log (
    func_id BIGINT REFERENCES Function(id),
    log_id  BIGINT REFERENCES LogLiteral(id),
    line    INT,
    PRIMARY KEY (func_id, log_id, line)
);

CREATE TABLE IF NOT EXISTS RuntimeTrace (
    id                BIGINT PRIMARY KEY DEFAULT nextval('rt_seq'),
    func_id           BIGINT REFERENCES Function(id),
    source            TEXT,
    device_id         TEXT,
    hit_count         INT DEFAULT 0,
    avg_exec_time_us  FLOAT,
    max_exec_time_us  FLOAT,
    avg_stack_depth   FLOAT DEFAULT 0.0,
    has_memory_error  BOOL DEFAULT FALSE,
    error_type        TEXT,
    error_details     TEXT,
    stack_trace       TEXT[],
    last_seen         TIMESTAMP,
    trace_data        JSON,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════
-- Intelligence & Scoring Tables
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS Tier (
    id               BIGINT PRIMARY KEY DEFAULT nextval('tier_seq'),
    path             TEXT UNIQUE,
    tier             INT CHECK (tier BETWEEN 0 AND 3),
    source           TEXT DEFAULT 'manual',
    confidence       FLOAT DEFAULT 1.0,
    llm_model        TEXT,
    git_commit_count INT DEFAULT 0,
    last_classified  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS PriorityScore (
    func_id                BIGINT PRIMARY KEY REFERENCES Function(id),
    tier_weight            FLOAT DEFAULT 0.0,
    usage_frequency        FLOAT DEFAULT 0.0,
    graph_centrality       FLOAT DEFAULT 0.0,
    pagerank               FLOAT DEFAULT 0.0,
    build_guard_activation FLOAT DEFAULT 0.0,
    runtime_frequency      FLOAT DEFAULT 0.0,
    recency_score          FLOAT DEFAULT 0.0,
    composite_score        FLOAT DEFAULT 0.0,
    linear_score           FLOAT DEFAULT 0.0,
    last_scored            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    score_version          INT DEFAULT 1
);

CREATE TABLE IF NOT EXISTS IndexManifest (
    file_id       BIGINT PRIMARY KEY REFERENCES File(id),
    manifest_json JSON,
    token_count   INT DEFAULT 0,
    tier          INT,
    version       INT DEFAULT 1,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS RepoMap (
    id                 BIGINT PRIMARY KEY DEFAULT nextval('repomap_seq'),
    generation         INT NOT NULL,
    tier_filter        INT DEFAULT 2,
    token_budget       INT DEFAULT 4096,
    map_json           JSON,
    total_functions    INT DEFAULT 0,
    included_functions INT DEFAULT 0,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS SummaryMeta (
    entity_id   BIGINT,
    entity_type TEXT,
    model_used  TEXT,
    confidence  FLOAT,
    version     INT DEFAULT 1,
    token_cost  INT DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (entity_id, entity_type)
);

CREATE TABLE IF NOT EXISTS Annotation (
    id              BIGINT PRIMARY KEY DEFAULT nextval('annot_seq'),
    entity_id       BIGINT,
    entity_type     TEXT,
    annotation_type TEXT,
    title           TEXT,
    content         TEXT,
    diff            TEXT,
    model           TEXT,
    confidence      FLOAT DEFAULT 0.0,
    approved        BOOL DEFAULT FALSE,
    dismissed       BOOL DEFAULT FALSE,
    created_by      TEXT DEFAULT 'system',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════
-- Collaboration Tables
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS SyncLog (
    id             BIGINT PRIMARY KEY DEFAULT nextval('sync_seq'),
    entity_id      BIGINT,
    entity_type    TEXT,
    change_type    TEXT,
    changed_by     TEXT,
    commit_sha     TEXT,
    branch         TEXT,
    timestamp      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delta_json     JSON,
    synced         BOOL DEFAULT FALSE,
    sync_timestamp TIMESTAMP
);

CREATE TABLE IF NOT EXISTS GitBranch (
    id          BIGINT PRIMARY KEY DEFAULT nextval('branch_seq'),
    branch_name TEXT UNIQUE,
    base_commit TEXT,
    head_commit TEXT,
    is_merged   BOOL DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS BranchEntity (
    branch_id   BIGINT REFERENCES GitBranch(id),
    entity_id   BIGINT,
    entity_type TEXT,
    action      TEXT,
    PRIMARY KEY (branch_id, entity_id, entity_type)
);

-- ════════════════════════════════════════════
-- Pre-Materialized LLM Views
-- ════════════════════════════════════════════

CREATE OR REPLACE VIEW LLM_HighPriority AS
    SELECT f.id, f.name, f.signature, f.summary, f.complexity,
           fi.path AS file_path, fi.language,
           COALESCE(t.tier, 2) AS tier,
           COALESCE(ps.composite_score, 0.0) AS composite_score,
           ps.pagerank,
           sm.confidence AS summary_confidence
    FROM Function f
    JOIN File fi ON f.file_id = fi.id
    LEFT JOIN PriorityScore ps ON f.id = ps.func_id
    LEFT JOIN Tier t ON t.path = fi.path
    LEFT JOIN SummaryMeta sm ON f.id = sm.entity_id AND sm.entity_type = 'function'
    WHERE COALESCE(t.tier, 2) >= 2
    ORDER BY COALESCE(ps.composite_score, 0.0) DESC;

CREATE OR REPLACE VIEW LLM_SharedState AS
    SELECT v.id, v.name, v.var_type, v.write_count, v.usage_count,
           v.is_volatile, v.is_atomic,
           f.name AS func_name, fi.path AS file_path
    FROM Variable v
    JOIN Function f ON v.func_id = f.id
    JOIN File fi ON v.file_id = fi.id
    WHERE v.is_global = TRUE AND v.write_count > 1
    ORDER BY v.write_count DESC;

CREATE OR REPLACE VIEW LLM_RuntimeHotspots AS
    SELECT f.id, f.name, f.signature, fi.path AS file_path,
           rt.hit_count, rt.has_memory_error, rt.error_type,
           rt.source AS trace_source,
           COALESCE(ps.composite_score, 0.0) AS composite_score
    FROM Function f
    JOIN RuntimeTrace rt ON f.id = rt.func_id
    JOIN File fi ON f.file_id = fi.id
    LEFT JOIN PriorityScore ps ON f.id = ps.func_id
    ORDER BY rt.hit_count DESC;

CREATE OR REPLACE VIEW LLM_CrossBoundary AS
    SELECT
        f1.name AS source_func, f1_file.path AS source_file,
        f1_file.language AS source_lang,
        f2.name AS target_func, f2_file.path AS target_file,
        f2_file.language AS target_lang,
        'ipc' AS edge_type, ipc.protocol, ipc.method_name
    FROM calls_over_ipc ipc
    JOIN Function f1 ON ipc.caller_func_id = f1.id
    JOIN File f1_file ON f1.file_id = f1_file.id
    JOIN Function f2 ON ipc.callee_func_id = f2.id
    JOIN File f2_file ON f2.file_id = f2_file.id
    UNION ALL
    SELECT
        f1.name, f1_file.path, cl.caller_language,
        f2.name, f2_file.path, cl.callee_language,
        'ffi', cl.ffi_mechanism, cl.binding_pattern
    FROM calls_cross_language cl
    JOIN Function f1 ON cl.caller_func_id = f1.id
    JOIN File f1_file ON f1.file_id = f1_file.id
    JOIN Function f2 ON cl.callee_func_id = f2.id
    JOIN File f2_file ON f2.file_id = f2_file.id;
"""


def create_schema(connection) -> None:
    """Execute the full v5 schema DDL on a DuckDB connection."""
    connection.execute(SCHEMA_DDL)
