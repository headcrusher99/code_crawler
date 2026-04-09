"""Shared DTOs — typed dataclasses for all cross-component data flows.

v5 expansion: adds compile context, foreign-call hints, log literals,
cross-language edges, data-flow edges, graph metrics, repo map, build
system info, and scope-resolution types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
# Build System
# ──────────────────────────────────────────────

@dataclass
class BuildSystemInfo:
    """Detected build system information."""

    type: str  # yocto, buildroot, kernel, aosp, cmake, make, generic
    root: Path = field(default_factory=lambda: Path("."))
    config_paths: dict[str, str] = field(default_factory=dict)
    compile_commands_path: Path | None = None


@dataclass(frozen=True)
class CompileContext:
    """Compilation context for a single file from compile_commands.json."""

    defines: frozenset[str] = field(default_factory=frozenset)
    include_paths: tuple[str, ...] = field(default_factory=tuple)
    compiler: str = "gcc"
    standard: str = ""       # c11, c17, gnu11, etc.
    optimization: str = ""   # -O0, -O2, -Os
    file_path: str = ""


@dataclass
class CompileEntry:
    """A single entry in compile_commands.json."""

    file: str
    directory: str = ""
    command: str = ""
    arguments: list[str] = field(default_factory=list)


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
    return_type: str = ""
    is_static: bool = False
    is_exported: bool = True
    language: str = ""


@dataclass(frozen=True)
class StructDef:
    """A parsed struct/class/union/enum definition."""

    name: str
    members: list[str] = field(default_factory=list)
    member_types: list[str] = field(default_factory=list)
    kind: str = "struct"  # 'struct', 'class', 'union', 'enum'
    start_line: int = 0
    end_line: int = 0
    summary: str = ""


@dataclass(frozen=True)
class MacroDef:
    """A parsed macro definition."""

    name: str
    value: str = ""
    is_config_guard: bool = False
    is_include_guard: bool = False
    is_function_like: bool = False
    line: int = 0


@dataclass(frozen=True)
class VariableDef:
    """A parsed variable definition."""

    name: str
    var_type: str = ""
    is_global: bool = False
    is_static: bool = False
    is_volatile: bool = False
    is_const: bool = False
    scope: str = "local"  # 'global', 'file', 'local', 'parameter'
    line: int = 0


@dataclass(frozen=True)
class CallEdge:
    """A function call relationship."""

    caller: str
    callee: str
    call_site_line: int = 0
    is_direct: bool = True


@dataclass(frozen=True)
class IncludeEdge:
    """A file include/import relationship."""

    source_path: str
    target_path: str
    is_system: bool = False
    line: int = 0


@dataclass(frozen=True)
class LogLiteralDef:
    """A logging literal extracted during parsing."""

    literal_string: str
    log_level: str = ""     # 'error', 'warning', 'info', 'debug'
    log_macro: str = ""     # 'printk', 'ALOGE', 'RDK_LOG', 'syslog'
    line: int = 0


@dataclass(frozen=True)
class ForeignCallHint:
    """Emitted by crawlers when they detect a cross-language call pattern."""

    caller_language: str
    callee_language: str
    mechanism: str           # 'cpython_api', 'system_call', 'ctypes', 'jni', …
    pattern: str             # The detected pattern string
    callee_hint: str = ""    # Hint for resolving the callee
    caller_func_name: str = ""
    line: int = 0


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
    log_literals: list[LogLiteralDef] = field(default_factory=list)
    foreign_call_hints: list[ForeignCallHint] = field(default_factory=list)


# ──────────────────────────────────────────────
# Cross-Language & IPC Edges
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class CrossLanguageEdge:
    """A resolved cross-language function call (C↔Python, C↔Shell, …)."""

    caller_func_id: int
    callee_func_id: int
    caller_language: str
    callee_language: str
    ffi_mechanism: str
    binding_pattern: str = ""
    confidence: float = 0.7


@dataclass(frozen=True)
class IPCEdge:
    """An inter-process communication edge (D-Bus, AIDL, protobuf, …)."""

    caller_func_id: int
    callee_func_id: int
    interface_name: str = ""
    method_name: str = ""
    protocol: str = ""       # 'dbus', 'aidl', 'protobuf', 'json-rpc', 'ubus'
    direction: str = "call"  # 'call', 'signal', 'event'
    is_async: bool = False
    confidence: float = 0.8


# ──────────────────────────────────────────────
# Data Flow (Joern-inspired simplified CPG)
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class DataFlowEdge:
    """A data flow relationship between variables/functions."""

    source_var_name: str
    sink_var_name: str
    source_func_name: str
    sink_func_name: str
    flow_type: str = ""  # 'assignment', 'parameter', 'return', 'global_read', 'global_write'
    confidence: float = 0.8


# ──────────────────────────────────────────────
# Scope Resolution (Stack-Graphs-inspired)
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class ResolvedCall:
    """A fully resolved function call after scope analysis."""

    caller: str
    callee: str
    callee_id: int = 0
    resolved: bool = False
    confidence: float = 0.0
    resolution_method: str = "none"  # 'unique_name', 'scope_chain', 'include_chain', 'heuristic'


@dataclass
class ScopeNode:
    """A node in the scope chain for name resolution."""

    name: str
    kind: str = "file"  # 'file', 'namespace', 'class', 'function', 'block'
    parent: ScopeNode | None = None
    children: list[ScopeNode] = field(default_factory=list)
    symbols: dict[str, int] = field(default_factory=dict)  # name → func_id


# ──────────────────────────────────────────────
# Graph Analysis (PageRank + Centrality)
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class GraphMetrics:
    """Graph analysis results for a function node."""

    func_id: int
    pagerank: float = 0.0
    betweenness: float = 0.0
    in_degree_norm: float = 0.0     # Normalized in-degree
    out_degree: int = 0
    is_hub: bool = False            # High in-degree
    is_bridge: bool = False         # High betweenness


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
    """Output of the hybrid scorer (PageRank + 6-dimension linear)."""

    func_id: int
    tier_weight: float = 0.0
    usage_frequency: float = 0.0
    graph_centrality: float = 0.0
    build_guard_activation: float = 0.0
    runtime_frequency: float = 0.0
    recency_score: float = 0.0
    pagerank: float = 0.0
    linear_score: float = 0.0
    composite_score: float = 0.0


@dataclass(frozen=True)
class IndexManifestBundle:
    """Pre-materialized context bundle for LLM agents (~500 tokens)."""

    file_path: str
    manifest_json: dict = field(default_factory=dict)
    token_count: int = 0


# ──────────────────────────────────────────────
# Repo Map (Aider-inspired)
# ──────────────────────────────────────────────

@dataclass
class RepoMap:
    """Global ranked summary of repository functions."""

    entries: list[str] = field(default_factory=list)
    total_functions: int = 0
    included_functions: int = 0
    token_budget: int = 4096
    tokens_used: int = 0

    def to_string(self) -> str:
        """Render to a plain-text string suitable for LLM context."""
        header = (
            f"# Repository Map ({self.included_functions}/{self.total_functions} "
            f"functions, ~{self.tokens_used} tokens)\n\n"
        )
        return header + "\n".join(self.entries)


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
    rule_id: str = ""


# ──────────────────────────────────────────────
# Pipeline Results
# ──────────────────────────────────────────────

@dataclass
class PipelineResult:
    """Aggregated result of a pipeline run."""

    files_discovered: int = 0
    files_parsed: int = 0
    files_skipped: int = 0
    functions_found: int = 0
    calls_found: int = 0
    cross_lang_edges: int = 0
    ipc_edges: int = 0
    data_flow_edges: int = 0
    timings: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def total_time(self) -> float:
        return self.timings.get("total", 0.0)


# ──────────────────────────────────────────────
# Events
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class IndexEvent:
    """Generic event wrapper for the event bus."""

    event_type: str
    payload: object
    source_component: str = ""
