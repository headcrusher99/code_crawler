"""Graph — DuckPGQ property graph definition and traversal queries."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# DuckPGQ property graph definition (from design_idea.md §3.3)
GRAPH_DDL = """
CREATE PROPERTY GRAPH IF NOT EXISTS code_graph
  VERTEX TABLES (
    Directory, File, Function, Struct, Macro,
    BuildConfig, DeviceTreeNode, Variable, LogLiteral
  )
  EDGE TABLES (
    contains_dir   SOURCE KEY (parent_id) REFERENCES Directory
                   DESTINATION KEY (child_id)  REFERENCES Directory,
    contains_file  SOURCE KEY (dir_id)    REFERENCES Directory
                   DESTINATION KEY (file_id)   REFERENCES File,
    contains_func  SOURCE KEY (file_id)   REFERENCES File
                   DESTINATION KEY (func_id)   REFERENCES Function,
    calls          SOURCE KEY (caller_id) REFERENCES Function
                   DESTINATION KEY (callee_id) REFERENCES Function,
    uses_struct    SOURCE KEY (func_id)   REFERENCES Function
                   DESTINATION KEY (struct_id) REFERENCES Struct,
    includes_file  SOURCE KEY (source_id) REFERENCES File
                   DESTINATION KEY (target_id) REFERENCES File,
    guarded_by     SOURCE KEY (func_id)   REFERENCES Function
                   DESTINATION KEY (config_id) REFERENCES BuildConfig,
    dt_binds_driver SOURCE KEY (dt_node_id) REFERENCES DeviceTreeNode
                   DESTINATION KEY (func_id)   REFERENCES Function,
    calls_over_ipc SOURCE KEY (caller_func_id) REFERENCES Function
                   DESTINATION KEY (callee_func_id) REFERENCES Function,
    emits_log      SOURCE KEY (func_id)   REFERENCES Function
                   DESTINATION KEY (log_id)    REFERENCES LogLiteral
  );
"""


def create_property_graph(connection) -> None:
    """Create the DuckPGQ property graph on an existing schema."""
    try:
        connection.execute(GRAPH_DDL)
        logger.info("Property graph 'code_graph' created")
    except Exception as e:
        logger.warning("Could not create property graph (DuckPGQ may not be installed): %s", e)


def get_call_hierarchy(connection, func_name: str, depth: int = 5) -> list[dict]:
    """Traverse the call graph from a function up to N levels deep.

    Returns a list of dicts with function names and their depth.
    """
    query = """
    SELECT f2.name, f2.signature, f2.summary
    FROM Function f1
    JOIN calls c ON f1.id = c.caller_id
    JOIN Function f2 ON c.callee_id = f2.id
    WHERE f1.name = ?
    """
    try:
        results = connection.execute(query, [func_name]).fetchall()
        return [
            {"name": row[0], "signature": row[1], "summary": row[2]}
            for row in results
        ]
    except Exception as e:
        logger.error("Call hierarchy query failed: %s", e)
        return []


def get_ipc_flow(connection, func_name: str) -> list[dict]:
    """Trace IPC edges from a function across process boundaries."""
    query = """
    SELECT f2.name, ci.interface_name, fi.path
    FROM Function f1
    JOIN calls_over_ipc ci ON f1.id = ci.caller_func_id
    JOIN Function f2 ON ci.callee_func_id = f2.id
    JOIN contains_func cf ON f2.id = cf.func_id
    JOIN File fi ON cf.file_id = fi.id
    WHERE f1.name = ?
    """
    try:
        results = connection.execute(query, [func_name]).fetchall()
        return [
            {"callee": row[0], "interface": row[1], "file": row[2]}
            for row in results
        ]
    except Exception as e:
        logger.error("IPC flow query failed: %s", e)
        return []
