"""Index Writer — persists pipeline data into DuckDB.

Subscribes to event bus events and writes discovered files, parsed AST
elements, tier classifications, priority scores, and manifests into the
database.  All inserts are batched for performance.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from codecrawler.core.event_bus import EventBus
from codecrawler.core.types import (
    FileInfo,
    IndexManifestBundle,
    ParseResult,
    PriorityScoreResult,
    TierClassification,
)

logger = logging.getLogger(__name__)


class IndexWriter:
    """Writes indexing results to DuckDB.

    Usage:
        writer = IndexWriter(db_connection)
        writer.subscribe(event_bus)
        # ... pipeline runs, events fire, data is persisted ...
        writer.flush()
        print(writer.stats)
    """

    def __init__(self, connection) -> None:
        self._conn = connection
        self._next_id: dict[str, int] = {}
        self._file_path_to_id: dict[str, int] = {}
        self._func_name_to_id: dict[str, int] = {}
        self._dir_path_to_id: dict[str, int] = {}

        # Batch buffers
        self._pending_dirs: list[tuple] = []
        self._pending_files: list[tuple] = []
        self._pending_functions: list[tuple] = []
        self._pending_structs: list[tuple] = []
        self._pending_macros: list[tuple] = []
        self._pending_variables: list[tuple] = []
        self._pending_calls: list[tuple] = []
        self._pending_includes: list[tuple] = []
        self._pending_contains_dir: list[tuple] = []
        self._pending_contains_file: list[tuple] = []
        self._pending_contains_func: list[tuple] = []

        # Stats
        self.stats: dict[str, int] = {
            "files": 0,
            "functions": 0,
            "structs": 0,
            "macros": 0,
            "variables": 0,
            "calls": 0,
            "includes": 0,
            "directories": 0,
        }

        self._init_id_counters()

    def _init_id_counters(self) -> None:
        """Initialize ID counters from existing DB state."""
        tables = [
            "Directory", "File", "Function", "Struct",
            "Macro", "Variable", "LogLiteral",
        ]
        for table in tables:
            try:
                result = self._conn.execute(
                    f"SELECT COALESCE(MAX(id), 0) FROM {table}"
                ).fetchone()
                self._next_id[table] = (result[0] if result else 0) + 1
            except Exception:
                self._next_id[table] = 1

    def _get_id(self, table: str) -> int:
        """Get the next auto-increment ID for a table."""
        current = self._next_id.get(table, 1)
        self._next_id[table] = current + 1
        return current

    def subscribe(self, event_bus: EventBus) -> None:
        """Subscribe to pipeline events."""
        event_bus.subscribe("file.discovered", self._on_file_discovered)
        event_bus.subscribe("file.parsed", self._on_file_parsed)
        event_bus.subscribe("tier.classified", self._on_tier_classified)
        logger.debug("IndexWriter subscribed to pipeline events")

    def _ensure_directory(self, file_path: Path) -> int:
        """Ensure all parent directories exist in the DB, return leaf dir ID."""
        parts = file_path.parent.parts
        parent_id = None

        for i in range(len(parts)):
            dir_path = str(Path(*parts[: i + 1]))
            if dir_path in self._dir_path_to_id:
                parent_id = self._dir_path_to_id[dir_path]
                continue

            dir_id = self._get_id("Directory")
            self._dir_path_to_id[dir_path] = dir_id
            depth = i
            name = parts[i]

            self._pending_dirs.append((dir_id, dir_path, name, depth))
            self.stats["directories"] += 1

            if parent_id is not None:
                self._pending_contains_dir.append((parent_id, dir_id))

            parent_id = dir_id

        return parent_id or 0

    def _on_file_discovered(self, file_info: FileInfo) -> None:
        """Handle file.discovered event — insert into File table."""
        path_str = str(file_info.path)

        if path_str in self._file_path_to_id:
            return  # Already indexed

        file_id = self._get_id("File")
        self._file_path_to_id[path_str] = file_id

        self._pending_files.append((
            file_id,
            path_str,
            file_info.content_hash,
            file_info.language,
            file_info.size_bytes,
        ))
        self.stats["files"] += 1

        # Link to directory
        dir_id = self._ensure_directory(file_info.path)
        if dir_id:
            self._pending_contains_file.append((dir_id, file_id))

    def _on_file_parsed(self, result: ParseResult) -> None:
        """Handle file.parsed event — insert functions, structs, etc."""
        path_str = str(result.file_info.path)
        file_id = self._file_path_to_id.get(path_str)

        if file_id is None:
            logger.warning("Parsed file %s not in file index", path_str)
            return

        # Functions
        for func in result.functions:
            func_id = self._get_id("Function")
            qualified_name = f"{path_str}::{func.name}"
            self._func_name_to_id[qualified_name] = func_id
            # Also store just-name for call resolution
            if func.name not in self._func_name_to_id:
                self._func_name_to_id[func.name] = func_id

            self._pending_functions.append((
                func_id, file_id, func.name, func.signature,
                func.start_line, func.end_line, func.complexity,
            ))
            self._pending_contains_func.append((file_id, func_id))
            self.stats["functions"] += 1

        # Structs
        for struct in result.structs:
            struct_id = self._get_id("Struct")
            self._pending_structs.append((
                struct_id, file_id, struct.name, struct.members,
            ))
            self.stats["structs"] += 1

        # Macros
        for macro in result.macros:
            macro_id = self._get_id("Macro")
            self._pending_macros.append((
                macro_id, file_id, macro.name, macro.value, macro.is_config_guard,
            ))
            self.stats["macros"] += 1

        # Variables
        for var in result.variables:
            var_id = self._get_id("Variable")
            self._pending_variables.append((
                var_id, file_id, var.name, var.var_type,
                var.is_global, var.is_static,
            ))
            self.stats["variables"] += 1

        # Call edges (callee resolution happens at flush time)
        for call in result.calls:
            self._pending_calls.append((
                path_str, call.callee, call.call_site_line,
            ))
            self.stats["calls"] += 1

        # Include edges
        for inc in result.includes:
            self._pending_includes.append((inc.source_path, inc.target_path))
            self.stats["includes"] += 1

    def _on_tier_classified(self, classification: TierClassification) -> None:
        """Handle tier.classified event — upsert into Tier table."""
        try:
            # Use INSERT OR REPLACE to avoid the ambiguous Tier.tier column issue
            self._conn.execute(
                """INSERT OR REPLACE INTO Tier (id, path, tier, source, confidence, last_classified)
                   VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                [self._get_id("Directory"), classification.path,
                 classification.tier, classification.source,
                 classification.confidence],
            )
        except Exception as e:
            logger.debug("Tier upsert: %s", e)

    def write_priority_score(self, score: PriorityScoreResult) -> None:
        """Write a priority score directly (not event-driven)."""
        try:
            self._conn.execute(
                """INSERT INTO PriorityScore
                   (func_id, tier_weight, usage_frequency, graph_centrality,
                    build_guard_activation, runtime_frequency, recency_score,
                    composite_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (func_id) DO UPDATE SET
                       composite_score = EXCLUDED.composite_score""",
                [score.func_id, score.tier_weight, score.usage_frequency,
                 score.graph_centrality, score.build_guard_activation,
                 score.runtime_frequency, score.recency_score,
                 score.composite_score],
            )
        except Exception as e:
            logger.debug("Priority score write: %s", e)

    def write_manifest(self, manifest: IndexManifestBundle) -> None:
        """Write an IndexManifest bundle."""
        file_id = self._file_path_to_id.get(manifest.file_path)
        if file_id is None:
            return
        try:
            self._conn.execute(
                """INSERT INTO IndexManifest (file_id, manifest_json)
                   VALUES (?, ?::JSON)
                   ON CONFLICT (file_id) DO UPDATE SET
                       manifest_json = EXCLUDED.manifest_json""",
                [file_id, json.dumps(manifest.manifest_json)],
            )
        except Exception as e:
            logger.debug("Manifest write: %s", e)

    def flush(self) -> None:
        """Flush all pending batches to DuckDB."""
        t0 = time.perf_counter()

        self._flush_batch(
            "Directory", self._pending_dirs,
            "INSERT INTO Directory (id, path, name, depth) VALUES (?, ?, ?, ?)",
        )
        self._flush_batch(
            "contains_dir", self._pending_contains_dir,
            "INSERT OR IGNORE INTO contains_dir (parent_id, child_id) VALUES (?, ?)",
        )
        self._flush_batch(
            "File", self._pending_files,
            "INSERT INTO File (id, path, hash, language, loc) VALUES (?, ?, ?, ?, ?)",
        )
        self._flush_batch(
            "contains_file", self._pending_contains_file,
            "INSERT OR IGNORE INTO contains_file (dir_id, file_id) VALUES (?, ?)",
        )
        self._flush_batch(
            "Function", self._pending_functions,
            "INSERT INTO Function (id, file_id, name, signature, start_line, end_line, complexity) VALUES (?, ?, ?, ?, ?, ?, ?)",
        )
        self._flush_batch(
            "contains_func", self._pending_contains_func,
            "INSERT OR IGNORE INTO contains_func (file_id, func_id) VALUES (?, ?)",
        )
        self._flush_batch(
            "Struct", self._pending_structs,
            "INSERT INTO Struct (id, file_id, name, members) VALUES (?, ?, ?, ?)",
        )
        self._flush_batch(
            "Macro", self._pending_macros,
            "INSERT INTO Macro (id, file_id, name, value, is_config_guard) VALUES (?, ?, ?, ?, ?)",
        )
        self._flush_batch(
            "Variable", self._pending_variables,
            "INSERT INTO Variable (id, file_id, name, var_type, is_global, is_static) VALUES (?, ?, ?, ?, ?, ?)",
        )

        # Resolve call edges: map callee names to IDs
        self._resolve_and_flush_calls()

        # Resolve include edges: map paths to file IDs
        self._resolve_and_flush_includes()

        dt = time.perf_counter() - t0
        logger.info("IndexWriter flushed in %.2fs", dt)

    def _flush_batch(self, table: str, buffer: list[tuple], sql: str) -> None:
        """Execute a batch insert."""
        if not buffer:
            return
        try:
            self._conn.executemany(sql, buffer)
            logger.debug("Flushed %d rows to %s", len(buffer), table)
        except Exception as e:
            logger.error("Batch insert to %s failed: %s", table, e)
        buffer.clear()

    def _resolve_and_flush_calls(self) -> None:
        """Resolve callee names to function IDs and insert call edges."""
        resolved = 0
        for source_path, callee_name, line in self._pending_calls:
            # Try qualified name first, then bare name
            caller_file_id = self._file_path_to_id.get(source_path)
            callee_id = self._func_name_to_id.get(callee_name)

            if callee_id is None or caller_file_id is None:
                continue

            # Find a caller function that contains this call site line
            caller_id = self._find_caller_at_line(source_path, line)
            if caller_id is None:
                continue

            try:
                self._conn.execute(
                    "INSERT OR IGNORE INTO calls (caller_id, callee_id, call_site_line) VALUES (?, ?, ?)",
                    [caller_id, callee_id, line],
                )
                resolved += 1
            except Exception:
                pass

        logger.debug("Resolved %d / %d call edges", resolved, len(self._pending_calls))
        self._pending_calls.clear()

    def _find_caller_at_line(self, file_path: str, line: int) -> int | None:
        """Find the function ID that contains a given line number."""
        try:
            result = self._conn.execute(
                """SELECT id FROM Function f
                   JOIN contains_func cf ON f.id = cf.func_id
                   JOIN File fi ON cf.file_id = fi.id
                   WHERE fi.path = ? AND f.start_line <= ? AND f.end_line >= ?
                   LIMIT 1""",
                [file_path, line, line],
            ).fetchone()
            return result[0] if result else None
        except Exception:
            return None

    def _resolve_and_flush_includes(self) -> None:
        """Resolve include paths to file IDs and insert edges."""
        resolved = 0
        for source_path, target_path in self._pending_includes:
            source_id = self._file_path_to_id.get(source_path)
            if source_id is None:
                continue

            # Try to find target by exact path or by filename match
            target_id = self._file_path_to_id.get(target_path)
            if target_id is None:
                # Try matching by filename suffix
                for known_path, fid in self._file_path_to_id.items():
                    if known_path.endswith(target_path):
                        target_id = fid
                        break

            if target_id is None:
                continue

            try:
                self._conn.execute(
                    "INSERT OR IGNORE INTO includes_file (source_id, target_id) VALUES (?, ?)",
                    [source_id, target_id],
                )
                resolved += 1
            except Exception:
                pass

        logger.debug("Resolved %d / %d include edges", resolved, len(self._pending_includes))
        self._pending_includes.clear()
