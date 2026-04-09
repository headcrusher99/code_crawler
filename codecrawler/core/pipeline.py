"""Indexing Pipeline — 12-stage coordinator for the full indexing cycle.

v5 pipeline stages:
  S1:  File Discovery (Rust-accelerated)
  S2:  Build System Detection
  S3:  Tier Classification
  S4:  File Parsing
  S5:  Cross-Language Linking
  S6:  Scope Resolution
  S7:  Data Flow Analysis
  S8:  Graph Analysis (PageRank)
  S9:  Priority Scoring (Hybrid)
  S10: Manifest Building
  S11: Repo Map Generation
  S12: Flush & Finalise
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

from codecrawler.core.config import CodeCrawlerConfig
from codecrawler.core.event_bus import EventBus
from codecrawler.core.registry import ServiceRegistry
from codecrawler.core.types import (
    FileInfo,
    ParseResult,
    PipelineResult,
)

logger = logging.getLogger(__name__)

# Language detection by file extension
LANGUAGE_MAP: dict[str, str] = {
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hxx": "cpp",
    ".py": "python", ".pyw": "python",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".dts": "devicetree", ".dtsi": "devicetree",
    ".bb": "bitbake", ".bbappend": "bitbake", ".bbclass": "bitbake",
    ".rs": "rust",
    ".go": "go",
    ".java": "java", ".kt": "kotlin",
    ".aidl": "aidl",
    ".proto": "protobuf",
    ".mk": "makefile",
    ".conf": "config", ".cfg": "config",
    ".toml": "toml", ".json": "json",
    ".yaml": "yaml", ".yml": "yaml", ".xml": "xml",
}


class IndexingPipeline:
    """Orchestrates the v5 12-stage indexing pipeline.

    Coordinates file discovery, build detection, tier classification,
    parsing, cross-language linking, scope resolution, data flow,
    graph analysis, scoring, manifest building, and repo map generation.

    Usage:
        pipeline = IndexingPipeline(config=config, registry=registry, db=db)
        result = pipeline.run()
    """

    # Stage definitions: (stage_name, method_name)
    STAGES = [
        ("discover",       "_discover_files"),
        ("build_detect",   "_detect_build_system"),
        ("classify",       "_classify_tiers"),
        ("parse",          "_parse_files"),
        ("cross_lang",     "_detect_cross_language"),
        ("scope_resolve",  "_resolve_scopes"),
        ("data_flow",      "_analyze_data_flow"),
        ("graph_analyze",  "_run_graph_analysis"),
        ("score",          "_score_priorities"),
        ("manifest",       "_build_manifests"),
        ("repo_map",       "_build_repo_map"),
        ("flush",          "_flush"),
    ]

    def __init__(
        self,
        config: CodeCrawlerConfig,
        registry: ServiceRegistry,
        event_bus: EventBus | None = None,
        db_connection=None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus or EventBus()
        self.db = db_connection
        self._writer = None

        # Pipeline state
        self._discovered_files: list[FileInfo] = []
        self._parse_results: list[ParseResult] = []
        self._tier_lookup: dict[str, int] = {}
        self._graph_metrics: dict[int, object] = {}
        self._stage_times: dict[str, float] = {}

    def run(self) -> PipelineResult:
        """Execute the full indexing pipeline.

        Returns:
            PipelineResult with aggregated statistics.
        """
        logger.info("Starting v5 indexing pipeline for %s", self.config.project.root)
        total_t0 = time.perf_counter()

        result = PipelineResult()

        # Wire up IndexWriter if we have a DB connection
        if self.db is not None:
            from codecrawler.storage.writer import IndexWriter
            self._writer = IndexWriter(self.db)
            self._writer.subscribe(self.event_bus)

        # Execute all stages
        for stage_name, method_name in self.STAGES:
            self._run_stage(stage_name, method_name, result)

        total_dt = time.perf_counter() - total_t0
        self._stage_times["total"] = total_dt
        result.timings = self._stage_times

        # Populate result stats
        result.files_discovered = len(self._discovered_files)
        result.files_parsed = len(self._parse_results)
        result.functions_found = sum(
            len(r.functions) for r in self._parse_results
        )
        result.calls_found = sum(
            len(r.calls) for r in self._parse_results
        )

        rate = result.files_discovered / total_dt if total_dt > 0 else 0
        logger.info(
            "Pipeline complete: %d files → %d functions in %.2fs (%.0f files/sec)",
            result.files_discovered, result.functions_found, total_dt, rate,
        )

        return result

    def _run_stage(self, name: str, method_name: str, result: PipelineResult) -> None:
        """Run a single pipeline stage with timing and error handling."""
        t0 = time.perf_counter()
        try:
            method = getattr(self, method_name)
            method()
            self.event_bus.publish(f"stage.{name}.complete", None)
        except Exception as exc:
            logger.exception("Stage '%s' failed: %s", name, exc)
            result.errors.append(f"{name}: {exc}")
            self.event_bus.publish(f"stage.{name}.failed", str(exc))
        finally:
            dt = time.perf_counter() - t0
            self._stage_times[name] = dt
            logger.info("  Stage '%s' completed in %.3fs", name, dt)

    # ── Stage 1: File Discovery ──────────────────────────────────────

    def _discover_files(self) -> None:
        """Walk the project root and emit file.discovered events."""
        root = Path(self.config.project.root).resolve()
        logger.info("Discovering files in %s", root)

        # Try native accelerated walker first
        try:
            from codecrawler.native_accel import fast_discover_files
            discovered = fast_discover_files(str(root))
            for entry in discovered:
                file_info = FileInfo(
                    path=Path(entry["path"]),
                    language=LANGUAGE_MAP.get(entry["ext"], ""),
                    size_bytes=entry["size"],
                    content_hash=entry["hash"],
                )
                if file_info.language:
                    self._discovered_files.append(file_info)
                    self.event_bus.publish("file.discovered", file_info)
            logger.info(
                "Native walker: discovered %d indexable files",
                len(self._discovered_files),
            )
            return
        except ImportError:
            pass  # Fall through to Python walker

        # Pure-Python walker
        for dirpath, _dirnames, filenames in os.walk(root):
            dir_path = Path(dirpath)
            if any(part.startswith(".") for part in dir_path.parts):
                continue

            for filename in filenames:
                file_path = dir_path / filename
                ext = file_path.suffix.lower()
                language = LANGUAGE_MAP.get(ext, "")

                if not language:
                    continue

                try:
                    stat = file_path.stat()
                    content_hash = _hash_file(file_path)
                except OSError:
                    continue

                file_info = FileInfo(
                    path=file_path,
                    language=language,
                    size_bytes=stat.st_size,
                    content_hash=content_hash,
                )
                self._discovered_files.append(file_info)
                self.event_bus.publish("file.discovered", file_info)

        logger.info("Discovered %d indexable files", len(self._discovered_files))

    # ── Stage 2: Build Detection ─────────────────────────────────────

    def _detect_build_system(self) -> None:
        """Detect the build system and load compile_commands.json."""
        from codecrawler.analyzers.build_detector import detect_build_system

        build_type = detect_build_system(Path(self.config.project.root))
        if build_type:
            logger.info("Detected build system: %s", build_type)
            self.event_bus.publish("build.detected", build_type)
        else:
            logger.info("No specific build system detected, using generic mode")

        # Try loading compile_commands.json
        root = Path(self.config.project.root)
        compile_db_path = root / "compile_commands.json"
        if not compile_db_path.exists():
            compile_db_path = root / "build" / "compile_commands.json"

        if compile_db_path.exists():
            from codecrawler.analyzers.compile_db import CompilationDatabaseHandler
            self._compile_db = CompilationDatabaseHandler.from_file(compile_db_path)
            logger.info(
                "Loaded compile_commands.json: %d entries",
                self._compile_db.entry_count,
            )
        else:
            self._compile_db = None

    # ── Stage 3: Tier Classification ─────────────────────────────────

    def _classify_tiers(self) -> None:
        """Run tier classification on discovered files."""
        from codecrawler.tiering.classifier import TierClassifier

        classifier = TierClassifier(config=self.config.tiering)
        classifications = classifier.classify(self._discovered_files)

        for classification in classifications:
            self._tier_lookup[classification.path] = classification.tier
            self.event_bus.publish("tier.classified", classification)

    # ── Stage 4: Parse Files ─────────────────────────────────────────

    def _parse_files(self) -> None:
        """Parse files using appropriate crawlers based on language."""
        from codecrawler.crawlers import CRAWLER_MAP

        parsed = 0
        skipped = 0
        errors = 0

        for file_info in self._discovered_files:
            # Check tier: only skip if explicitly classified as i0
            tier = self._tier_lookup.get(str(file_info.path), 2)
            if tier == 0:
                skipped += 1
                continue

            crawler = CRAWLER_MAP.get(file_info.language)
            if crawler:
                try:
                    result = crawler.parse(file_info)
                    self._parse_results.append(result)
                    self.event_bus.publish("file.parsed", result)
                    parsed += 1
                except Exception:
                    logger.exception("Failed to parse %s", file_info.path)
                    errors += 1

        logger.info("Parsed %d files (%d skipped, %d errors)", parsed, skipped, errors)

    # ── Stage 5: Cross-Language Linking ──────────────────────────────

    def _detect_cross_language(self) -> None:
        """Detect cross-language call patterns (FFI, system calls, etc.)."""
        from codecrawler.core.cross_linker import CrossLanguageLinker

        linker = CrossLanguageLinker()
        edges = linker.detect_edges(self._parse_results)
        for edge in edges:
            self.event_bus.publish("cross_lang.detected", edge)

        logger.info("Detected %d cross-language edges", len(edges))

    # ── Stage 6: Scope Resolution ────────────────────────────────────

    def _resolve_scopes(self) -> None:
        """Resolve ambiguous function call targets using scope analysis."""
        from codecrawler.core.scope_resolver import ScopeResolver

        resolver = ScopeResolver()
        func_index = resolver.build_function_index(self._parse_results)
        resolved = resolver.resolve_calls(self._parse_results, func_index)

        resolved_count = sum(1 for r in resolved if r.resolved)
        logger.info(
            "Scope resolution: %d/%d calls resolved",
            resolved_count, len(resolved),
        )

    # ── Stage 7: Data Flow Analysis ──────────────────────────────────

    def _analyze_data_flow(self) -> None:
        """Analyse global variable read/write patterns across functions."""
        from codecrawler.core.data_flow import DataFlowAnalyzer

        analyzer = DataFlowAnalyzer(event_bus=self.event_bus)
        edges = analyzer.analyze(self._parse_results)

        logger.info("Detected %d data-flow edges", len(edges))

    # ── Stage 8: Graph Analysis ──────────────────────────────────────

    def _run_graph_analysis(self) -> None:
        """Compute PageRank and centrality on the call graph."""
        from codecrawler.core.graph_analysis import GraphAnalyzer

        # Build call edge list from parse results
        call_edges: list[tuple[int, int]] = []
        func_id_map: dict[str, int] = {}
        fid = 1
        for result in self._parse_results:
            for func in result.functions:
                if func.name not in func_id_map:
                    func_id_map[func.name] = fid
                    fid += 1

        for result in self._parse_results:
            for call in result.calls:
                caller_id = func_id_map.get(call.caller)
                callee_id = func_id_map.get(call.callee)
                if caller_id and callee_id:
                    call_edges.append((caller_id, callee_id))

        analyzer = GraphAnalyzer()
        self._graph_metrics = analyzer.analyze(call_edges)

        hubs = sum(1 for m in self._graph_metrics.values() if m.is_hub)
        bridges = sum(1 for m in self._graph_metrics.values() if m.is_bridge)
        logger.info(
            "Graph analysis: %d nodes, %d hubs, %d bridges",
            len(self._graph_metrics), hubs, bridges,
        )

    # ── Stage 9: Priority Scoring ────────────────────────────────────

    def _score_priorities(self) -> None:
        """Compute priority scores for all parsed functions."""
        from codecrawler.tiering.priority_scorer import PriorityScorer

        scorer = PriorityScorer(config=self.config.priority_scoring)
        scored = 0

        if self.db is not None:
            try:
                functions = self.db.execute(
                    "SELECT id, file_id, name FROM Function"
                ).fetchall()
            except Exception:
                functions = []

            try:
                max_calls_row = self.db.execute(
                    """SELECT MAX(cnt) FROM (
                        SELECT COUNT(*) AS cnt FROM calls GROUP BY callee_id
                    )"""
                ).fetchone()
                max_calls = max_calls_row[0] if max_calls_row and max_calls_row[0] else 1
            except Exception:
                max_calls = 1

            for row in functions:
                func_id = row[0]

                try:
                    call_row = self.db.execute(
                        "SELECT COUNT(*) FROM calls WHERE callee_id = ?",
                        [func_id],
                    ).fetchone()
                    call_count = call_row[0] if call_row else 0
                except Exception:
                    call_count = 0

                score = scorer.score(
                    func_id=func_id,
                    tier_level=2,
                    call_count=call_count,
                    max_call_count=max_calls,
                )

                if self._writer:
                    self._writer.write_priority_score(score)
                scored += 1

        logger.info("Scored %d functions", scored)

    # ── Stage 10: Build Manifests ────────────────────────────────────

    def _build_manifests(self) -> None:
        """Build pre-materialized IndexManifests for LLM agents."""
        from codecrawler.tiering.manifest_builder import ManifestBuilder

        builder = ManifestBuilder()
        built = 0

        for result in self._parse_results:
            try:
                manifest = builder.build(result)
                if self._writer:
                    self._writer.write_manifest(manifest)
                built += 1
            except Exception:
                logger.exception("Failed to build manifest for %s", result.file_info.path)

        logger.info("Built %d IndexManifests", built)

    # ── Stage 11: Repo Map ───────────────────────────────────────────

    def _build_repo_map(self) -> None:
        """Build global ranked repository map."""
        from codecrawler.tiering.repo_map import RepoMapBuilder

        builder = RepoMapBuilder(self.db)
        repo_map = builder.build_from_results(self._parse_results)

        logger.info(
            "Repo map: %d/%d functions, ~%d tokens",
            repo_map.included_functions,
            repo_map.total_functions,
            repo_map.tokens_used,
        )

    # ── Stage 12: Flush ──────────────────────────────────────────────

    def _flush(self) -> None:
        """Flush all pending writes to the database."""
        if self._writer:
            self._writer.flush()
            logger.info("Writer flushed: %s", self._writer.stats)


def _hash_file(path: Path, block_size: int = 65536) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(block_size), b""):
                hasher.update(block)
    except OSError:
        return ""
    return hasher.hexdigest()
