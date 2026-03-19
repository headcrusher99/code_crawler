# Code Crawler (Semantic Code Indexer) - Technical Design Specification

**Version**: 2.0  
**Status**: Pre-Phase 0 (Design & Architecture)  
**Target Domain**: Massive embedded C/C++ codebases (Yocto, Buildroot, Linux kernel, RDK-B, Android AOSP).

---

## 1. Executive Summary
**Code Crawler** is an intelligent, build-system-aware code indexer and Model Context Protocol (MCP) server. It bridges the gap between massive embedded C/C++ codebases and Large Language Models (LLMs). By extracting Abstract Syntax Trees (ASTs), understanding complex build configurations (like Yocto/BitBake), and generating semantic summaries via cost-effective local AI, it creates a highly optimized hybrid Graph+Vector database. High-tier LLMs can then query this database via MCP, bypassing context window limits and reducing "hallucinations."

## 2. Problem Statement
Modern LLMs struggle with large-scale embedded engineering:
1. **Context Limits**: A typical Yocto/Bitbake image contains >5M Lines of Code (LOC). LLMs max out around 128k-200k tokens.
2. **The `#ifdef` Hell**: Full-text search and naive RAG (Retrieval-Augmented Generation) index *everything*. In the Linux kernel or RDK-B, 50% of the code might be `#ifdef`'d out for a specific hardware target. If the AI doesn't know the build config, it gives wrong answers.
3. **Complex Call Graphs**: Embedded issues often span hardware abstraction layers (HALs) and kernel spaces. Simple grep cannot follow indirect function calls or macro expansions.

## 3. Core Differentiators
Existing tools (like standard RAG, Sourcegraph, or Bloop) are language-agnostic but lack build-system awareness. Code Crawler wins by offering:
- **Build-Context-Aware Indexing**: Only parses files compiled in the *active* Yocto/Buildroot layer or kernel `.config`.
- **Hybrid Storage (KuzuDB)**: A single embedded database containing both Property Graph (relational mapping) and Vector Embeddings (semantic search).
- **Official MCP Support**: Instantly plugs into IDEs like Cursor, Claude Desktop, and VS Code.
- **Selective Background Summarization**: Uses cheap, local models (like `llama-3` via Ollama) to summarize function intents *before* you need them.

---

## 4. High-Level Architecture

Code Crawler is composed of modular plugins orchestrated by a central engine.

```text
code-crawler/
├── pyproject.toml              # Modern Python package tracking (uv/hatchling)
├── core/
│   ├── engine.py               # Orchestrator (index, watch, mcp)
│   ├── build_analyzer.py       # Yocto/Bitbake/Kconfig/CompileCommands interface
│   └── incremental_tracker.py  # Cache invalidation (hashes/mtimes)
├── crawlers/                   # Plugin System for Parsers
│   ├── c_cpp/                  # Tree-sitter + libclang parser
│   └── rust/                   # Future extensible support
├── analyzers/
│   └── summarizer.py           # Background LLM prompt orchestrator
├── storage/                    
│   └── kuzu_db.py              # Embedded Graph+Vector DB schema and queries
├── ui/                         # Human-readable diagnostic dashboard
│   └── web_viewer/             # FastAPI + Vis.js + CodeMirror
└── mcp/                        
    └── server.py               # MCP Server exposing tools
```

---

## 5. Storage Model: The Hybrid Database
Using **KuzuDB** (an embedded property-graph database), we seamlessly blend relationships and vector similarity.

### The Graph Schema
- **Nodes**: `File`, `Symbol` (Function, Struct, Macro, Global), `BuildConfig`.
- **Edges**: 
  - `(File)-[:CONTAINS]->(Symbol)`
  - `(Symbol)-[:CALLS]->(Symbol)`
  - `(Symbol)-[:USES_MACRO]->(Symbol)`
  - `(Symbol)-[:DEPENDS_ON]->(BuildConfig)` (e.g., linking a function to `CONFIG_WIFI_MAC`)

### The Vector Index
Each `Symbol` node gets a 384-dimensional embedding generated from its AI summary, mapped directly within KuzuDB, allowing queries like:
> "Find functions similar to 'mac address initialization' but ONLY if they depend on CONFIG_ATH11K."

---

## 6. Pipeline Execution Flow

### 1. Build Analysis (The "What to Index" Phase)
- Detects `bitbake`, Kconfig (`.config`), or `compile_commands.json`.
- Extracts active `SRC_URI`, include directories, and `#define` flags.
- Throws away standard libraries or unused hardware layers to save tokens.

### 2. AST Extraction (The "Crawler" Phase)
- Runs `tree-sitter-c`/`tree-sitter-cpp` to walk the code.
- Captures signatures, start/end lines, and extracts relationships (`CALLS`, `USES`).
- Fallback to `libclang` for complex macro expansions if Tree-sitter fails.

### 3. AI Summarization (The "Enrichment" Phase)
- For every captured function, an asynchronous task calls a local LLM (e.g., Ollama).
- **Prompt strategy**: *"Summarize this C function in 2 sentences. Note any hardware register interactions, locking semantics, and what build flags gate it."*
- Generates the vector embedding and saves it to KuzuDB.

### 4. Agent Consumption (The MCP Phase)
- Developer asks their IDE a question.
- IDE calls MCP Tools: `get_call_hierarchy(func)`, `search_semantic(query)`, `get_build_context(file)`.
- Tools run Cypher queries against KuzuDB and return compressed, hyper-relevant context.

---

## 7. Suggested Improvements & Refinements (V2.0 Addition)

Based on the initial design, here are critical improvements to ensure success in the embedded domain:

### A. Contextual "Locking & Concurrency" Extraction
Embedded systems (especially kernel drivers) crash due to bad locking (Spinlocks, Mutexes, IRQ contexts). 
**Improvement**: The AI Summarizer prompt must explicitly be instructed to extract and document *Locking Semantics* (e.g., *"Takes `wlan_mac_lock` before executing"*). This is priceless data for an LLM trying to debug a race condition.

### B. Multi-Architecture / Variant Scoping
In Yocto, the exact same C file might be compiled twice in one build (e.g., `native` toolchain vs `target` ARM toolchain), having different active `#ifdef` paths. 
**Improvement**: The Graph database nodes must be namespace-aware. A file parsed under the `x86` context shouldn't overwrite the `ARM` context's data.

### C. Language Server Protocol (LSP) Piggybacking
Instead of building the C/C++ parser entirely from scratch, embedded devs usually already have `clangd` running. 
**Improvement**: Add an adapter that can ingest an existing `.cache/clangd` index. `clangd` already computes the perfect call graph natively; Code Crawler could just ingest this graph and focus solely on the AI Summarization and MCP layers, saving massive CPU time.

### D. File-Watcher Delta Updates
Re-indexing a 5M LOC repo is costly. 
**Improvement**: Integrate a filesystem watcher (`watchdog`) combined with git hooks. If a developer edits `wifi_drv.c`, only that file's AST is re-parsed, and only its altered functions are sent back to the local LLM for re-summarization. Incremental updates keep the database real-time.