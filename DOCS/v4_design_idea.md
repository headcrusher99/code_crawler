# Code Crawler v4: Component Architecture & Service Boundaries

**Theme**: Service Boundaries & Engineering Scaling  
**Goal**: Transform the monolithic design into a cleanly partitioned, extensible system with strict component boundaries, typed inter-component APIs, an event-driven communication bus, and a formal plugin architecture.

---

## 1. Architecture Philosophy

v4 applies three engineering principles to the existing design:

1. **Component Isolation** — Each module owns its data and exposes only a typed public API. No module reaches into another's internals.
2. **Event-Driven Communication** — Components communicate via a central event bus (pub/sub), not direct imports. This enables async processing, plugin hooks, and testability.
3. **Plugin-First Extensibility** — New crawlers, analyzers, and intelligence features are plugins, not hardcoded modules. The core system is minimal; capability lives in plugins.

---

## 2. Component Map & Service Boundaries

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                              codecrawler CLI                                │
│  (index | mcp | ui | watch | sync | ingest-logs | status)                   │
└─────────────┬───────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CORE ORCHESTRATOR                                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ Pipeline     │ │ Event Bus    │ │ Service      │ │ Config       │       │
│  │ Coordinator  │ │ (Pub/Sub)    │ │ Registry     │ │ Loader       │       │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘       │
│         │                │                │                │               │
│         └────────────────┴────────────────┴────────────────┘               │
└─────────────┬───────────────────────────────────────────────────────────────┘
              │ Events / DTOs
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SERVICE LAYER (Plugins)                             │
│                                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │ Crawlers │ │Analyzers │ │ Tiering  │ │ Intel    │ │ Debugger │         │
│  │ (parse)  │ │(build    │ │(classify │ │(summarize│ │(runtime  │         │
│  │          │ │ detect)  │ │ + score) │ │ + patch) │ │ traces)  │         │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘         │
│       │             │            │             │            │               │
│       └─────────────┴────────────┴─────────────┴────────────┘               │
└─────────────┬───────────────────────────────────────────────────────────────┘
              │ DTOs
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                        │
│  │ Storage      │ │ Graph        │ │ Vector       │                        │
│  │ (DuckDB)     │ │ (DuckPGQ)    │ │ (vss)        │                        │
│  └──────────────┘ └──────────────┘ └──────────────┘                        │
└─────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      INTERFACE LAYER                                        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                        │
│  │ MCP Server   │ │ Collaboration│ │ Code Nebula  │                        │
│  │ (Tools/Res)  │ │ (Swarm Sync) │ │ (3D UI)      │                        │
│  └──────────────┘ └──────────────┘ └──────────────┘                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Inter-Component API Contracts (DTOs)

All cross-boundary data flows through typed dataclasses. No raw dicts cross component lines.

### 3.1 Core DTOs

```python
@dataclass(frozen=True)
class FileInfo:
    """Describes a discovered file before parsing."""
    path: Path
    language: str
    size_bytes: int
    content_hash: str
    tier: int  # 0-3, assigned by tiering component

@dataclass(frozen=True)
class ParseResult:
    """Output of any crawler — the universal parse contract."""
    file_info: FileInfo
    functions: list[FunctionDef]
    structs: list[StructDef]
    macros: list[MacroDef]
    variables: list[VariableDef]
    calls: list[CallEdge]
    includes: list[IncludeEdge]

@dataclass(frozen=True)
class FunctionDef:
    name: str
    signature: str
    start_line: int
    end_line: int
    complexity: int
    body_hash: str

@dataclass(frozen=True)
class TierClassification:
    """Output of the tiering classifier."""
    path: str
    tier: int  # 0-3
    confidence: float
    source: str  # "llm", "git", "build_config", "manual"

@dataclass(frozen=True)
class PriorityScoreResult:
    """Output of the 6-dimension scorer."""
    func_id: int
    tier_weight: float
    usage_frequency: float
    graph_centrality: float
    build_guard_activation: float
    runtime_frequency: float
    recency_score: float
    composite_score: float

@dataclass(frozen=True)
class IndexManifestBundle:
    """Pre-materialized context bundle for LLM agents (~500 tokens)."""
    file_path: str
    manifest_json: dict
```

---

## 4. Event Bus Architecture

The event bus decouples producers from consumers. Every significant action emits an event; interested components subscribe.

### 4.1 Core Events

| Event | Producer | Consumers | Payload |
|-------|----------|-----------|---------|
| `file.discovered` | Pipeline | Tiering, Crawlers | `FileInfo` |
| `file.parsed` | Crawlers | Storage, Tiering | `ParseResult` |
| `tier.classified` | Tiering | Storage, Pipeline | `TierClassification` |
| `priority.scored` | Tiering | Storage, MCP | `PriorityScoreResult` |
| `manifest.built` | Tiering | Storage, MCP | `IndexManifestBundle` |
| `summary.generated` | Intelligence | Storage | `SummaryResult` |
| `patch.suggested` | Intelligence | Storage, UI | `PatchSuggestion` |
| `sync.delta` | Collaboration | Storage | `SyncDelta` |

### 4.2 Event Bus Interface

```python
class EventBus:
    def subscribe(self, event_type: str, handler: Callable) -> None: ...
    def publish(self, event_type: str, payload: Any) -> None: ...
    async def publish_async(self, event_type: str, payload: Any) -> None: ...
```

---

## 5. Plugin System

### 5.1 Plugin Base Class

```python
class PluginBase(ABC):
    """All plugins inherit from this. Lifecycle is managed by the plugin registry."""
    
    @property
    @abstractmethod
    def manifest(self) -> PluginManifest: ...
    
    def register(self, registry: ServiceRegistry) -> None:
        """Called when the plugin is discovered. Register services here."""
        pass
    
    def activate(self, event_bus: EventBus) -> None:
        """Called when the plugin is activated. Subscribe to events here."""
        pass
    
    def deactivate(self) -> None:
        """Called on shutdown. Clean up resources."""
        pass

@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str
    description: str
    author: str
    plugin_type: str  # "crawler", "analyzer", "intelligence", "ui"
    dependencies: list[str] = field(default_factory=list)
```

### 5.2 Plugin Discovery

Plugins are discovered via two mechanisms:
1. **Entry Points** — Third-party packages register via `pyproject.toml` entry points under `codecrawler.plugins`.
2. **File System** — Local plugins in the `plugins/` directory within the project.

### 5.3 Built-in Plugins

The built-in crawlers and analyzers are themselves plugins — they have no special privilege over third-party plugins. This ensures the plugin API is complete.

---

## 6. Service Registry

```python
class ServiceRegistry:
    """Central registry for component discovery and dependency injection."""
    
    def register_service(self, interface: type, implementation: Any) -> None: ...
    def get_service(self, interface: type) -> Any: ...
    def get_all_services(self, interface: type) -> list[Any]: ...
    def has_service(self, interface: type) -> bool: ...
```

Components register their public interfaces at startup. Other components request dependencies through the registry, never through direct imports.

---

## 7. Formalized Directory Structure

```text
code-crawler/
├── pyproject.toml                  # PEP 621 project config + CLI entry point
├── codecrawler/
│   ├── __init__.py                 # Package version + public API
│   ├── __main__.py                 # python -m codecrawler support
│   ├── cli.py                      # Click CLI (index, mcp, ui, watch, sync, status)
│   ├── core/                       # ── CORE ORCHESTRATOR ──
│   │   ├── __init__.py
│   │   ├── pipeline.py             # IndexingPipeline: stage coordinator
│   │   ├── event_bus.py            # Pub/sub event bus
│   │   ├── config.py               # TOML config loader
│   │   ├── registry.py             # ServiceRegistry
│   │   └── types.py                # Shared DTOs (FileInfo, ParseResult, etc.)
│   ├── storage/                    # ── DATA LAYER ──
│   │   ├── __init__.py
│   │   ├── database.py             # DuckDB connection + migrations
│   │   ├── schema.py               # Table DDL definitions
│   │   ├── graph.py                # DuckPGQ property graph
│   │   └── vector.py               # VSS vector index management
│   ├── crawlers/                   # ── PARSING SERVICES ──
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseCrawler ABC
│   │   ├── c_crawler.py            # C/C++ Tree-sitter + libclang
│   │   ├── python_crawler.py       # Python AST parser
│   │   └── shell_crawler.py        # Shell script parser
│   ├── analyzers/                  # ── BUILD INTELLIGENCE ──
│   │   ├── __init__.py
│   │   ├── build_detector.py       # Auto-detect build system
│   │   ├── yocto.py                # Yocto recipe/layer parser
│   │   ├── buildroot.py            # Buildroot config parser
│   │   └── kernel.py               # Linux kernel Kconfig parser
│   ├── tiering/                    # ── CLASSIFICATION & SCORING ──
│   │   ├── __init__.py
│   │   ├── classifier.py           # LLM-based tier classification
│   │   ├── priority_scorer.py      # 6-dimension priority scoring
│   │   └── manifest_builder.py     # IndexManifest pre-computation
│   ├── intelligence/               # ── PROACTIVE AI ──
│   │   ├── __init__.py
│   │   ├── proactive_agent.py      # Background remediation
│   │   ├── summarizer.py           # Confidence-aware summarization
│   │   └── telemetry.py            # Log/crash correlator
│   ├── plugins/                    # ── PLUGIN SYSTEM ──
│   │   ├── __init__.py
│   │   ├── base.py                 # PluginBase ABC + PluginManifest
│   │   ├── loader.py               # Plugin discovery (entry points + filesystem)
│   │   └── registry.py             # Plugin lifecycle management
│   ├── mcp/                        # ── MCP INTERFACE ──
│   │   ├── __init__.py
│   │   └── server.py               # MCP server + tool definitions
│   └── config/                     # ── CONFIGURATION ──
│       ├── __init__.py
│       └── defaults.py             # Default config schema + template
├── tests/                          # Test suite
├── DOCS/                           # Documentation
└── .codecrawler.toml               # Project-level config (example)
```

---

## 8. Data Flow: Complete Indexing Cycle

```text
CLI (index) 
  → Pipeline.run()
    → FileDiscovery: scan project root, emit file.discovered events
    → BuildDetector: detect Yocto/Buildroot/Kernel, emit build.detected
    → TierClassifier: LLM classifies directories → emit tier.classified
    → for each file (tier ≥ 1):
        → CrawlerRegistry.get_crawler(language) → crawler.parse(file)
        → emit file.parsed with ParseResult DTO
    → PriorityScorer: compute 6-dim scores → emit priority.scored
    → ManifestBuilder: pre-compute IndexManifests → emit manifest.built
    → Summarizer (async): background LLM summaries → emit summary.generated
    → Storage: all events consumed, persisted to DuckDB
    → ProactiveAgent (async): scan for write contention → emit patch.suggested
```

---

## 9. Configuration Schema (v4)

```toml
[project]
name = "my-rdk-build"
type = "yocto"
root = "/home/dev/yocto-build"

[index]
tiers = { full = ["meta-custom/**", "meta-vendor/**"], skeleton = ["poky/meta/**"], stub = ["**"] }

[build]
config_file = "build/conf/local.conf"
layers_file = "build/conf/bblayers.conf"
kernel_config = "build/tmp/work/**/linux-*/build/.config"
compile_commands = "auto"

[llm]
provider = "ollama"
model = "llama3.2:8b"

[embeddings]
model = "sentence-transformers/all-MiniLM-L6-v2"
device = "cpu"

[tiering]
llm_proposer_model = "llama3.2:3b"
git_evidence_months = 6

[priority_scoring]
weights = { tier = 0.25, usage = 0.20, centrality = 0.15, build = 0.10, runtime = 0.15, recency = 0.15 }
self_tuning = true

[collaboration]
enabled = true
master_db_path = "shared/codecrawler_master.db"
swarm_compute = true
developer_id = "dev-a"

[git]
semantic_patch_enabled = true
branch_isolation = true

[telemetry]
enabled = true
sources = ["gdb_traces", "valgrind", "asan_logs", "serial_uart_logs"]
auto_patch_generation = true

[plugins]
search_paths = ["./plugins"]
enabled = ["*"]
disabled = []
```

---

## 10. Success Criteria (v4)

| Criterion | Target |
|-----------|--------|
| **Component isolation** | Zero cross-boundary direct imports (all via registry/events) |
| **Plugin coverage** | All crawlers and analyzers loadable as plugins |
| **DTO completeness** | 100% of cross-component data flows use typed DTOs |
| **CLI functional** | All 7 CLI commands respond to `--help` |
| **Import clean** | `python -c "import codecrawler"` succeeds with zero errors |
