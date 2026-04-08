"""Indexing Pipeline — stage coordinator for the full indexing cycle."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

from codecrawler.core.config import CodeCrawlerConfig
from codecrawler.core.event_bus import EventBus
from codecrawler.core.registry import ServiceRegistry
from codecrawler.core.types import FileInfo, ParseResult

logger = logging.getLogger(__name__)

# Language detection by file extension
LANGUAGE_MAP: dict[str, str] = {
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".py": "python",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".dts": "devicetree",
    ".dtsi": "devicetree",
    ".bb": "bitbake",
    ".bbappend": "bitbake",
    ".bbclass": "bitbake",
    ".conf": "config",
    ".cfg": "config",
    ".toml": "toml",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".mk": "makefile",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".aidl": "aidl",
}


class IndexingPipeline:
    """Orchestrates the complete indexing cycle.

    Coordinates file discovery, build detection, tier classification,
    parsing, scoring, and manifest generation.  Data flows through the
    event bus and is persisted by the IndexWriter.

    Usage:
        pipeline = IndexingPipeline(config=config, registry=registry, db=db)
        pipeline.run()
    """

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
        self._discovered_files: list[FileInfo] = []
        self._parse_results: list[ParseResult] = []
        self._stage_times: dict[str, float] = {}

    def run(self) -> dict[str, int]:
        """Execute the full indexing pipeline.

        Returns:
            Dictionary of statistics from the IndexWriter.
        """
        logger.info("Starting indexing pipeline for %s", self.config.project.root)
        total_t0 = time.perf_counter()

        # Wire up IndexWriter if we have a DB connection
        writer = None
        if self.db is not None:
            from codecrawler.storage.writer import IndexWriter

            writer = IndexWriter(self.db)
            writer.subscribe(self.event_bus)

        # Stage 1: Discover files
        self._timed("discover", self._discover_files)

        # Stage 2: Detect build system
        self._timed("build_detect", self._detect_build_system)

        # Stage 3: Classify tiers
        self._timed("classify", self._classify_tiers)

        # Stage 4: Parse files
        self._timed("parse", self._parse_files)

        # Flush discovered files + parse results to DB
        if writer:
            self._timed("flush", writer.flush)

        # Stage 5: Score priorities
        self._timed("score", lambda: self._score_priorities(writer))

        # Stage 6: Build manifests
        self._timed("manifest", lambda: self._build_manifests(writer))

        total_dt = time.perf_counter() - total_t0
        self._stage_times["total"] = total_dt

        file_count = len(self._discovered_files)
        rate = file_count / total_dt if total_dt > 0 else 0
        logger.info(
            "Pipeline complete: %d files in %.2fs (%.0f files/sec)",
            file_count, total_dt, rate,
        )

        stats = writer.stats if writer else {}
        stats["stage_times"] = self._stage_times
        return stats

    def _timed(self, name: str, func) -> None:
        """Run a function and record its wall-clock time."""
        t0 = time.perf_counter()
        func()
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
                "Native walker: discovered %d indexable files", len(self._discovered_files)
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
        """Detect the build system and emit build.detected event."""
        from codecrawler.analyzers.build_detector import detect_build_system

        build_type = detect_build_system(Path(self.config.project.root))
        if build_type:
            logger.info("Detected build system: %s", build_type)
            self.event_bus.publish("build.detected", build_type)
        else:
            logger.info("No specific build system detected, using generic mode")

    # ── Stage 3: Tier Classification ─────────────────────────────────

    def _classify_tiers(self) -> None:
        """Run tier classification on discovered files."""
        from codecrawler.tiering.classifier import TierClassifier

        classifier = TierClassifier(config=self.config.tiering)
        classifications = classifier.classify(self._discovered_files)

        # Build a path → tier lookup for the parse stage
        self._tier_lookup: dict[str, int] = {}
        for classification in classifications:
            self._tier_lookup[classification.path] = classification.tier
            self.event_bus.publish("tier.classified", classification)

    # ── Stage 4: Parse Files ─────────────────────────────────────────

    def _parse_files(self) -> None:
        """Parse files using appropriate crawlers based on language."""
        from codecrawler.crawlers.base import BaseCrawler

        crawlers = self.registry.get_all(BaseCrawler)
        crawler_map: dict[str, BaseCrawler] = {}
        for crawler in crawlers:
            for lang in crawler.supported_languages:
                crawler_map[lang] = crawler

        parsed = 0
        skipped = 0
        errors = 0

        tier_lookup = getattr(self, "_tier_lookup", {})

        for file_info in self._discovered_files:
            # Check tier: only skip if explicitly classified as i0
            tier = tier_lookup.get(str(file_info.path), 2)  # Default to i2 (skeleton)
            if tier == 0:
                skipped += 1
                continue

            crawler = crawler_map.get(file_info.language)
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

    # ── Stage 5: Priority Scoring ────────────────────────────────────

    def _score_priorities(self, writer=None) -> None:
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

            # Get max call count for normalization
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

                # Get call count for this function
                try:
                    call_row = self.db.execute(
                        "SELECT COUNT(*) FROM calls WHERE callee_id = ?", [func_id]
                    ).fetchone()
                    call_count = call_row[0] if call_row else 0
                except Exception:
                    call_count = 0

                score = scorer.score(
                    func_id=func_id,
                    tier_level=2,  # Default tier
                    call_count=call_count,
                    max_call_count=max_calls,
                )

                if writer:
                    writer.write_priority_score(score)
                scored += 1

        logger.info("Scored %d functions", scored)

    # ── Stage 6: Build Manifests ─────────────────────────────────────

    def _build_manifests(self, writer=None) -> None:
        """Build pre-materialized IndexManifests for LLM agents."""
        from codecrawler.tiering.manifest_builder import ManifestBuilder

        builder = ManifestBuilder()
        built = 0

        for result in self._parse_results:
            try:
                manifest = builder.build(result)
                if writer:
                    writer.write_manifest(manifest)
                built += 1
            except Exception:
                logger.exception("Failed to build manifest for %s", result.file_info.path)

        logger.info("Built %d IndexManifests", built)


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
