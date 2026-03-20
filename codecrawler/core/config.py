"""Configuration loader — TOML-based config with typed defaults."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Config Dataclasses
# ──────────────────────────────────────────────

@dataclass
class ProjectConfig:
    name: str = "untitled"
    type: str = "generic"  # yocto, buildroot, kernel, generic
    root: str = "."


@dataclass
class IndexConfig:
    tiers: dict[str, list[str]] = field(default_factory=lambda: {
        "full": [],
        "skeleton": [],
        "stub": ["**"],
    })


@dataclass
class BuildConfig:
    config_file: str = ""
    layers_file: str = ""
    kernel_config: str = ""
    compile_commands: str = "auto"


@dataclass
class LLMConfig:
    provider: str = "ollama"
    model: str = "llama3.2:8b"


@dataclass
class EmbeddingsConfig:
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: str = "cpu"


@dataclass
class TieringConfig:
    llm_proposer_model: str = "llama3.2:3b"
    git_evidence_months: int = 6


@dataclass
class PriorityScoringConfig:
    weights: dict[str, float] = field(default_factory=lambda: {
        "tier": 0.25,
        "usage": 0.20,
        "centrality": 0.15,
        "build": 0.10,
        "runtime": 0.15,
        "recency": 0.15,
    })
    self_tuning: bool = True


@dataclass
class CollaborationConfig:
    enabled: bool = False
    master_db_path: str = "shared/codecrawler_master.db"
    swarm_compute: bool = False
    developer_id: str = "dev-default"


@dataclass
class GitConfig:
    semantic_patch_enabled: bool = True
    branch_isolation: bool = True


@dataclass
class TelemetryConfig:
    enabled: bool = False
    sources: list[str] = field(default_factory=lambda: [
        "gdb_traces", "valgrind", "asan_logs", "serial_uart_logs"
    ])
    auto_patch_generation: bool = False


@dataclass
class PluginsConfig:
    search_paths: list[str] = field(default_factory=lambda: ["./plugins"])
    enabled: list[str] = field(default_factory=lambda: ["*"])
    disabled: list[str] = field(default_factory=list)


@dataclass
class StorageConfig:
    db_path: str = ".codecrawler/index.duckdb"


@dataclass
class CodeCrawlerConfig:
    """Root configuration object."""

    project: ProjectConfig = field(default_factory=ProjectConfig)
    index: IndexConfig = field(default_factory=IndexConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    tiering: TieringConfig = field(default_factory=TieringConfig)
    priority_scoring: PriorityScoringConfig = field(default_factory=PriorityScoringConfig)
    collaboration: CollaborationConfig = field(default_factory=CollaborationConfig)
    git: GitConfig = field(default_factory=GitConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    plugins: PluginsConfig = field(default_factory=PluginsConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)


# ──────────────────────────────────────────────
# Loader
# ──────────────────────────────────────────────

def load_config(
    config_path: str = ".codecrawler.toml",
    *,
    project_type: str | None = None,
    root: str | None = None,
    image: str | None = None,
) -> CodeCrawlerConfig:
    """Load configuration from TOML file with CLI overrides.

    Falls back to defaults if the config file doesn't exist.
    """
    config = CodeCrawlerConfig()
    path = Path(config_path)

    if path.exists():
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

        with open(path, "rb") as f:
            data = tomllib.load(f)

        _apply_toml_data(config, data)
        logger.info("Loaded config from %s", path)
    else:
        logger.debug("Config file %s not found, using defaults", path)

    # CLI overrides
    if project_type:
        config.project.type = project_type
    if root:
        config.project.root = root

    return config


def _apply_toml_data(config: CodeCrawlerConfig, data: dict) -> None:
    """Apply parsed TOML data to config dataclasses."""
    section_map = {
        "project": config.project,
        "index": config.index,
        "build": config.build,
        "llm": config.llm,
        "embeddings": config.embeddings,
        "tiering": config.tiering,
        "priority_scoring": config.priority_scoring,
        "collaboration": config.collaboration,
        "git": config.git,
        "telemetry": config.telemetry,
        "plugins": config.plugins,
        "storage": config.storage,
    }

    for section_name, section_obj in section_map.items():
        section_data = data.get(section_name, {})
        for key, value in section_data.items():
            if hasattr(section_obj, key):
                setattr(section_obj, key, value)
