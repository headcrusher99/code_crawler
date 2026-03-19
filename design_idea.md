# Code Crawler (Semantic Code Indexer) - Technical Design Specification

**Version**: 2.1  
**Status**: Pre-Phase 0 (Design & Architecture)  
**Target Domain**: Massive embedded C/C++ codebases (Yocto, Buildroot, Linux kernel, RDK-B) and future languages via strict API plugins.

---

## 1. Executive Summary
**Code Crawler** is an intelligent, build-system-aware code indexer and Model Context Protocol (MCP) server. It bridges the gap between massive codebases and Large Language Models (LLMs). By extracting Abstract Syntax Trees (ASTs), understanding complex builds, generating semantic summaries, and mapping the entire directory/file structure, it creates a highly optimized hybrid Graph+Vector database. High-tier LLMs can read from or **write directly to** this database, creating a living knowledge web.

## 2. Problem Statement
Modern LLMs struggle with large-scale software engineering:
1. **Context Limits**: A typical Yocto/Bitbake image contains >5M Lines of Code (LOC).
2. **The `#ifdef` Hell**: Full-text search indexes *everything*. AI fails to know which code is actually compiled for a specific hardware target.
3. **Loss of Spatial Awareness**: LLMs lose the "folder structure" context. They don't know that `/drivers/net/wireless` is physically and logically distinct from `/fs/ext4/`.
4. **Static Tooling**: Current code indexers are read-only. When an AI discovers a complex bug or deduces an indirect function pointer, it cannot save that knowledge back to the database for future sessions.

---

## 3. High-Level Architecture (Strictly Decoupled)

To accommodate any future language (Python, Rust, Go), the architecture strictly separates the **Core Engine** from the **Language Crawlers**. 

```text
code-crawler/
├── pyproject.toml              
├── core/                       # MAIN ENGINE (Database, MCP, File Watcher)
│   ├── engine.py               # Orchestrator
│   ├── interfaces.py           # ABSTRACT API CONTRACT (Defines how crawlers talk to Core)
│   ├── build_analyzer.py       
│   └── tracker.py              
├── crawlers/                   # LANGUAGE PLUGINS (Dumb parsers)
│   ├── c_cpp/                  # Implements interfaces.py for C/C++ (Tree-sitter)
│   ├── python/                 # Implements interfaces.py for Python
│   └── rust/                   # Implements interfaces.py for Rust
├── storage/                    
│   └── kuzu_db.py              # Single source of truth (Graph + Vector)
└── mcp/                        
    └── server.py               # Exposes BOTH Read and Write APIs to LLMs
```

---

## 4. The Unified Crawler API Contract

Language plugins (`crawlers/`) are NOT allowed to talk to the database. They must strictly use the standard APIs defined in `core/interfaces.py`. 

**The Flow:**
1. Core Engine tells a crawler: `Parse file at /src/wifi.c`.
2. Crawler runs its language-specific AST tools (Tree-sitter, libclang).
3. Crawler yields highly standardized dataclasses back to Core: `SymbolNode`, `ReferenceEdge`.
4. Core Engine securely injects these into the Graph.

*Result: Adding a new language takes 1 day, as you only have to write a regex/AST parser that outputs standard `SymbolNode` objects.*

---

## 5. Storage Model: The Hybrid Database
Using **KuzuDB**, we blend structural relationships, directory trees, and vector similarity into one queryable space.

### The Spatial Graph Schema
- **Nodes**: `Directory`, `File`, `Symbol` (Function, Class, Struct), `BuildConfig`.
- **Edges**: 
  - `(Directory)-[:CONTAINS_DIR]->(Directory)` *(Creates the folder tree natively)*
  - `(Directory)-[:CONTAINS_FILE]->(File)`
  - `(File)-[:CONTAINS_SYMBOL]->(Symbol)`
  - `(Symbol)-[:CALLS]->(Symbol)`
  - `(Symbol)-[:DEPENDS_ON]->(BuildConfig)`

### The Vector Index (Semantic Layer)
Every Node (even Directories) gets an AI-generated text summary that is converted into a 384-dimensional mathematical vector.

---

## 6. Bi-Directional AI Agents (Read & Write APIs)

Traditionally, MCP servers are Read-Only. Code Crawler provides **Bi-directional APIs** so external apps or LLMs can actively construct the knowledge base.

### Reading Data (Context Gathering)
- `get_folder_structure(path="/drivers/net")`: AI retrieves the spatial directory tree.
- `get_call_hierarchy_up(func="wlan_init")`: AI asks what calls this function.
- `semantic_search(query="Where are IV vectors verified?", filter="scope=/drivers")`

### Writing Data (Active Knowledge Injection)
When an LLM figures something out, it can call these APIs to permanently enrich the database:
- `add_architecture_note(node_id, note)`: AI attaches a human-readable engineering note to a `Directory` or `File`. (e.g., *"This folder handles legacy WEP encryption, do not refactor."*)
- `tag_symbol(symbol_id, tag)`: AI tags a function dynamically (e.g. `[SECURITY_CRITICAL]`, `[RACE_CONDITION_PRONE]`).
- `inject_relationship(source_id, target_id, type="CALLS_VIA_POINTER")`: C code uses many function pointers which AST parsers miss. An AI can deduce the pointer and manually draw a `[:CALLS]` line in the database so future queries know they are connected!

---

## 7. Execution Flow & Real-Time Sync

1. **Crawler Pass**: Indexer walks directories, generating `Directory` and `File` nodes.
2. **Parser Pass**: Standardized language plugins extract `Symbol` nodes.
3. **Summarizer Pass**: Cheap background AI summarizes functions.
4. **Developer Session**: Dev opens IDE -> AI queries the graph to solve a problem -> AI discovers an undocumented struct relation -> AI calls `inject_relationship()` to improve the Graph for all future developers.
