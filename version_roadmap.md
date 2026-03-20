# Code Crawler: Version Roadmap

This document outlines the evolutionary stages of the Code Crawler project, tracking the shift from a robust heuristic-based indexer to a fully agentic, team-synchronized intelligence layer.

---

## v2 — Build-System-Aware Selective Indexing (Complete)
**Theme: The Deterministic Foundation**

v2 established the core of the engine. It proved that deterministic AST-derived knowledge bases strictly outperform pure LLM-generated graphs, and that build-config-driven filtering can cut irrelevant code by 80%+.

**Key Features Delivered:**
- Build-system awareness (Yocto, Buildroot, OpenWrt, Linux Kernel).
- DuckDB as a single-file multi-model backend (Graph via DuckPGQ + Vector via `vss` + FTS).
- Hybrid C/C++ AST parsing (Tree-sitter + libclang).
- 3-tier selective indexing (Full / Skeleton / Stub).
- Precision `#ifdef` logic resolution.
- Device Tree (`.dts`) hardware-to-driver awareness.
- Initial MCP server integration for agent queries.
- LLM bidirectional write-back annotations.

---

## v3 — LLM-First Tiering + Team Live-Sync (Current Focus)
**Theme: The Agent & Intelligence Layer**

v3 is the transition from a "better search tool" to an active intelligent agent. It adds the missing piece: deploying the **LLM's own pre-trained knowledge** at index-time alongside Swarm computing architecture to process massive scale zero-overhead workflows.

**Key Features (per the System Design Document):**
- **4-Tier LLM Classification (i0–i3)**: Using small local models (3B-7B) to categorize code importance based on pre-trained open-source familiarity.
- **Priority Scoring System**: 6-dimension mathematical scoring (Centrality, Build status, Recency, etc.) to optimize token context windows.
- **Cross-Boundary IPC Edges**: Connecting D-Bus, Ubus, and Android Binder boundaries smoothly inside the graph for uninterrupted tracing.
- **Log & Telemetry Correlation**: FTS-mapping serial logs and crash dumps direct to the AST.
- **Debugger Data Integration**: Prioritizing runtime hot-paths based on GDB traces and sanitisers.
- **Swarm Compute & Master Sync**: Distributing heavy indexing parsing across the team's local workstations over P2P, syncing back to a shared master persistence DB.
- **Proactive AI**: Background remediation agent auto-generating path adjustments for variable thread/interrupt vulnerabilities.
- **Code Nebula UI**: 3D spatial mapping with Nebula Flythrough Tours for onboarding.

---

## v4 — Component Architecture Refinement (Planned)
**Theme: Service Boundaries & Engineering Scaling**

Turning the theoretical v3 models into a cleanly partitioned, deployable cluster. Defining exactly how each component communicates, what data flows where, and establishing plugin boundaries.

**Key Objectives:**
- Component-level architecture breakdown and service boundaries.
- Inter-component API definitions and strict schemas.
- Defining a formal plugin/extension system.
- Formalized project directory structure separation.

---

## v5 — High-Level Technical Implementation & Hardening (Planned)
**Theme: Production-Ready Specification**

Concrete implementation details focusing on optimization, deployment, and security restrictions for enterprise usage. 

**Key Objectives:**
- Explicit library selections, wire protocols, and serialization formats.
- Deployment strategies (Local standalone vs. Enterprise Swarm configurations).
- Performance benchmarking and caching mechanisms.
- Database scaling limits testing.
- Hardening against infinite indexing loops and path-traversal vulnerabilities.
