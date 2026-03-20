"""Indexing Pipeline — stage coordinator for the full indexing cycle."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from codecrawler.core.config import CodeCrawlerConfig
from codecrawler.core.event_bus import EventBus
from codecrawler.core.registry import ServiceRegistry
from codecrawler.core.types import FileInfo

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
    parsing, scoring, and manifest generation via the event bus.

    Usage:
        pipeline = IndexingPipeline(config=config, registry=registry)
        pipeline.run()
    """

    def __init__(
        self,
        config: CodeCrawlerConfig,
        registry: ServiceRegistry,
        event_bus: EventBus | None = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus or EventBus()
        self._discovered_files: list[FileInfo] = []

    def run(self) -> None:
        """Execute the full indexing pipeline."""
        logger.info("Starting indexing pipeline for %s", self.config.project.root)

        # Stage 1: Discover files
        self._discover_files()

        # Stage 2: Detect build system
        self._detect_build_system()

        # Stage 3: Classify tiers
        self._classify_tiers()

        # Stage 4: Parse files
        self._parse_files()

        # Stage 5: Score priorities
        self._score_priorities()

        # Stage 6: Build manifests
        self._build_manifests()

        logger.info(
            "Pipeline complete. Discovered %d files.",
            len(self._discovered_files),
        )

    def _discover_files(self) -> None:
        """Walk the project root and emit file.discovered events."""
        root = Path(self.config.project.root).resolve()
        logger.info("Discovering files in %s", root)

        for dirpath, _dirnames, filenames in os.walk(root):
            # Skip hidden directories and common non-code dirs
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

    def _detect_build_system(self) -> None:
        """Detect the build system and emit build.detected event."""
        from codecrawler.analyzers.build_detector import detect_build_system

        build_type = detect_build_system(Path(self.config.project.root))
        if build_type:
            logger.info("Detected build system: %s", build_type)
            self.event_bus.publish("build.detected", build_type)
        else:
            logger.info("No specific build system detected, using generic mode")

    def _classify_tiers(self) -> None:
        """Run tier classification on discovered files."""
        from codecrawler.tiering.classifier import TierClassifier

        classifier = TierClassifier(config=self.config.tiering)
        classifications = classifier.classify(self._discovered_files)
        for classification in classifications:
            self.event_bus.publish("tier.classified", classification)

    def _parse_files(self) -> None:
        """Parse files using appropriate crawlers based on language."""
        from codecrawler.crawlers.base import BaseCrawler

        crawlers = self.registry.get_all(BaseCrawler)
        crawler_map: dict[str, BaseCrawler] = {}
        for crawler in crawlers:
            for lang in crawler.supported_languages:
                crawler_map[lang] = crawler

        for file_info in self._discovered_files:
            if file_info.tier == 0:
                continue  # Skip i0 (ignored) files

            crawler = crawler_map.get(file_info.language)
            if crawler:
                try:
                    result = crawler.parse(file_info)
                    self.event_bus.publish("file.parsed", result)
                except Exception:
                    logger.exception("Failed to parse %s", file_info.path)

    def _score_priorities(self) -> None:
        """Compute priority scores for all parsed functions."""
        from codecrawler.tiering.priority_scorer import PriorityScorer

        scorer = PriorityScorer(config=self.config.priority_scoring)
        logger.info("Computing priority scores...")
        # Scoring requires DB data — placeholder for now
        self.event_bus.publish("priority.scoring.started", None)

    def _build_manifests(self) -> None:
        """Build pre-materialized IndexManifests for LLM agents."""
        from codecrawler.tiering.manifest_builder import ManifestBuilder

        builder = ManifestBuilder()
        logger.info("Building IndexManifests...")
        self.event_bus.publish("manifest.building.started", None)


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
