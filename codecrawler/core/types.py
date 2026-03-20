"""Shared DTOs — typed dataclasses for all cross-component data flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# ──────────────────────────────────────────────
# File Discovery
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class FileInfo:
    """Describes a discovered file before parsing."""

    path: Path
    language: str
    size_bytes: int
    content_hash: str
    tier: int = 0  # 0–3, assigned by tiering component


# ──────────────────────────────────────────────
# Parse Output
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class FunctionDef:
    """A parsed function definition."""

    name: str
    signature: str
    start_line: int
    end_line: int
    complexity: int = 1
    body_hash: str = ""


@dataclass(frozen=True)
class StructDef:
    """A parsed struct/class definition."""

    name: str
    members: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass(frozen=True)
class MacroDef:
    """A parsed macro definition."""

    name: str
    value: str = ""
    is_config_guard: bool = False


@dataclass(frozen=True)
class VariableDef:
    """A parsed variable definition."""

    name: str
    var_type: str = ""
    is_global: bool = False
    is_static: bool = False
    line: int = 0


@dataclass(frozen=True)
class CallEdge:
    """A function call relationship."""

    caller: str
    callee: str
    call_site_line: int = 0


@dataclass(frozen=True)
class IncludeEdge:
    """A file include/import relationship."""

    source_path: str
    target_path: str


@dataclass(frozen=True)
class ParseResult:
    """Universal output of any crawler — the cross-component parse contract."""

    file_info: FileInfo
    functions: list[FunctionDef] = field(default_factory=list)
    structs: list[StructDef] = field(default_factory=list)
    macros: list[MacroDef] = field(default_factory=list)
    variables: list[VariableDef] = field(default_factory=list)
    calls: list[CallEdge] = field(default_factory=list)
    includes: list[IncludeEdge] = field(default_factory=list)


# ──────────────────────────────────────────────
# Tiering & Scoring
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class TierClassification:
    """Output of the tiering classifier."""

    path: str
    tier: int  # 0–3
    confidence: float = 1.0
    source: str = "manual"  # "llm", "git", "build_config", "manual"


@dataclass(frozen=True)
class PriorityScoreResult:
    """Output of the 6-dimension scorer."""

    func_id: int
    tier_weight: float = 0.0
    usage_frequency: float = 0.0
    graph_centrality: float = 0.0
    build_guard_activation: float = 0.0
    runtime_frequency: float = 0.0
    recency_score: float = 0.0
    composite_score: float = 0.0


@dataclass(frozen=True)
class IndexManifestBundle:
    """Pre-materialized context bundle for LLM agents (~500 tokens)."""

    file_path: str
    manifest_json: dict = field(default_factory=dict)


# ──────────────────────────────────────────────
# Intelligence
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class SummaryResult:
    """Output of the summarizer."""

    entity_id: int
    entity_type: str
    summary: str
    model_used: str = ""
    confidence: float = 0.6


@dataclass(frozen=True)
class PatchSuggestion:
    """A proactive patch suggestion from the intelligence agent."""

    file_path: str
    description: str
    diff: str
    confidence: float = 0.0


# ──────────────────────────────────────────────
# Events
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class IndexEvent:
    """Generic event wrapper for the event bus."""

    event_type: str
    payload: object
    source_component: str = ""
