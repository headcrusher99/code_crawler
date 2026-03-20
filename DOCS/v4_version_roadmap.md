# Code Crawler: V4 Version Roadmap

This document tracks the v4 milestone and beyond. For v2–v3 history, see [version_roadmap.md](./version_roadmap.md).

---

## v4 — Component Architecture Refinement (Current Focus)
**Theme: Service Boundaries & Engineering Scaling**

Turning the theoretical v3 design into a cleanly partitioned, deployable system with strict component boundaries, inter-component typed APIs, a formal plugin architecture, and a real Python package structure.

### Key Deliverables

#### 4.1 Component Isolation & Service Registry
- [x] Define component boundaries (Core, Storage, Crawlers, Analyzers, Tiering, Intelligence, Plugins, MCP)
- [x] Implement `ServiceRegistry` for dependency injection
- [x] Typed DTO contracts (`FileInfo`, `ParseResult`, `TierClassification`, `PriorityScoreResult`)
- [x] Zero direct cross-boundary imports

#### 4.2 Event Bus Architecture
- [x] Central pub/sub `EventBus` for inter-component communication
- [x] Core event definitions (`file.discovered`, `file.parsed`, `tier.classified`, etc.)
- [x] Async event support for background tasks

#### 4.3 Plugin System
- [x] `PluginBase` ABC with lifecycle hooks (`register`, `activate`, `deactivate`)
- [x] `PluginManifest` schema
- [x] Plugin discovery via entry points + filesystem scanning
- [x] Plugin registry with lifecycle management
- [x] Built-in crawlers/analyzers registered as standard plugins

#### 4.4 Formalized Project Structure
- [x] PEP 621 `pyproject.toml` with CLI entry points
- [x] Click-based CLI (`index`, `mcp`, `ui`, `watch`, `sync`, `ingest-logs`, `status`)
- [x] `python -m codecrawler` support
- [x] Clean `__init__.py` public API exports per component

#### 4.5 Storage Component
- [x] DuckDB connection management with migration support
- [x] Complete schema definitions (all tables from design spec)
- [x] DuckPGQ property graph definition
- [x] VSS vector index management

#### 4.6 Parsing & Analysis Skeleton
- [x] `BaseCrawler` ABC defining the universal parse contract
- [x] C/C++, Python, Shell crawler stubs
- [x] Build detector + Yocto/Buildroot/Kernel analyzer stubs
- [x] LLM tier classifier + priority scorer + manifest builder stubs

---

## v5 — High-Level Technical Implementation & Hardening (Planned)
**Theme: Production-Ready Specification**

Concrete implementation details focusing on optimization, deployment, and security restrictions for enterprise usage.

### Key Objectives
- Flesh out crawler implementations with real Tree-sitter + libclang parsing.
- Full LLM integration (Ollama) for tiering, summarization, and proactive remediation.
- Swarm P2P compute implementation with CRDT-based conflict resolution.
- MCP server with full tool + resource implementations.
- Code Nebula 3D UI (FastAPI + Three.js).
- Performance benchmarking: >1,000 files/min, <200ms MCP query latency.
- Security hardening: path traversal prevention, sandboxed plugin execution.
- Deployment strategies: standalone local mode vs. enterprise swarm.

---

## v6 — Fleet Intelligence & Production Telemetry (Future)
**Theme: Scale Beyond the Team**

- Fleet-wide crash log aggregation and trending.
- Cross-project knowledge transfer (shared pattern libraries).
- CI/CD pipeline integration for auto-index on merge.
- Enterprise SSO + RBAC for shared master databases.
