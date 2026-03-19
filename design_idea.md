# Code Crawler (Semantic Code Indexer) – Enhanced Edition v2

**Version**: 2.0 (March 2026)  
**Goal**: Turn Code Crawler into a production-grade, build-system-aware, multi-language, hybrid-graph/vector MCP server optimized for massive embedded C/C++ projects (Yocto, Buildroot, OpenWrt, Linux kernel, RDK-B) while remaining extensible to Python and beyond.

---

## 1. Why the Original Needs These Improvements

In massive embedded Linux codebases (like OpenWrt or Yocto builds), a developer typically tinkers with only a tiny fraction of the code—custom drivers, specific serial/GPIO pins, device tree configurations (`.dts`), or custom vendor layers. The rest of the codebase contains millions of lines of untouched, upstream code (e.g., `busybox`, `coreutils`, core kernel subsystems).

Raw file parsing and simple `grep` searches fail on these multi-million line codebases because they are heavily gated by `#ifdef` macros and Kconfig options. If an LLM uses traditional tools, it wastes tokens scanning irrelevant code. Existing state-of-the-art tools (like code-graph-rag, CocoIndex, Arbor) prove that AST-based graph processing and smart embeddings work, but they lack build-system awareness.

We will bridge this gap with **build-system-aware selective indexing**. The LLM will only index and analyze what matters, ignoring the untouched core utilities unless explicitly required, ensuring high-speed context resolution.

### 1.1 Lessons from the State-of-the-Art

Recent research (2025–2026) shows that **deterministic AST-derived knowledge bases (DKB) outperform LLM-generated knowledge graphs** for code understanding. They provide more reliable coverage, better multi-hop grounding for GraphRAG, and significantly lower indexing costs. Code Crawler adopts this principle: the graph is built from deterministic AST parsing, and LLMs are used *only* for summarization, never for graph construction.

Key tools and their gaps that Code Crawler fills:

| Tool | Strength | Gap Code Crawler Fills |
|------|----------|----------------------|
| **Arbor** | Structural "Logic Forest" graph via Rust AST engine | No build-system awareness, no `#ifdef` resolution |
| **CocoIndex** | Real-time incremental indexing, Rust core + Python API | No Kconfig/Yocto integration, no embedded focus |
| **Code-Graph-RAG** | Multi-language knowledge graph + MCP | Misses build-config-driven code paths |
| **CodePrism** | Universal AST, cross-file analysis | No selective indexing, no embedded build systems |

---

## 2. High-Level Architecture (Modular by Design)

```text
code-crawler/
├── core/                  # Python orchestrator (main engine)
│   ├── pipeline.py        # Indexing pipeline coordinator
│   ├── file_selector.py   # Build-aware file filtering
│   └── hasher.py          # Content hashing for incremental updates
├── crawlers/
│   ├── c/                 # C/C++ (Tree-sitter + libclang hybrid)
│   │   ├── ts_parser.py   # Tree-sitter: fast structural AST
│   │   └── clang_resolver.py  # libclang: semantic resolution (#ifdef, types, cross-TU)
│   ├── dts/               # Device Tree Source parser
│   ├── python/            # Next phase
│   └── __init__.py        # Plugin loader (importlib + entry points)
├── analyzers/
│   └── build/             # Yocto/Bitbake, Buildroot/OpenWrt, Kernel
│       ├── detector.py    # Auto-detect build system type
│       ├── yocto.py       # Parse recipes, layers, DISTRO_FEATURES
│       ├── buildroot.py   # Parse .config, package selections
│       ├── kernel.py      # Parse Kconfig, generate compile_commands.json
│       └── compile_db.py  # Unified compile_commands.json handler
├── storage/               # DuckDB (graph + vector + full-text in one)
│   ├── schema.py          # Graph schema (DuckPGQ)
│   ├── vector.py          # Vector index (vss extension)
│   └── migrations.py      # Schema versioning
├── mcp/                   # Official Python MCP SDK server
│   ├── server.py          # MCP server entry point
│   ├── tools.py           # Tool definitions (workflow-oriented)
│   └── resources.py       # MCP resource definitions
├── ui/                    # FastAPI + interactive web dashboard
├── config/                # .codecrawler.toml
├── summarizer/            # Cheap LLM pass (Ollama / GPT-4o-mini / local)
│   ├── batch.py           # Async batch summarizer
│   └── prompts.py         # Structured prompt templates
└── plugins/               # Future: Rust extensions for speed
```

**Language support strategy**:
- **Phase 1**: C/C++ only (MVP for embedded) + Device Tree (`.dts`/`.dtsi`).
- **Phase 2**: Python + Shell scripts (common in Yocto recipes).
- **Phase N**: Drop-in folder `crawlers/<lang>/` with a `Parser` class implementing an abstract base `CodeParser`.

---

## 3. Database – Multi-Model Single Backend (Spatially Aware)

> [!CAUTION]
> **KuzuDB was archived by its maintainers in October 2025** and is no longer maintained. The original design selected KuzuDB, but it is no longer a viable choice. We've evaluated alternatives including community forks (Ladybug, Bighorn), but these lack proven stability.

### 3.1 Chosen Backend: DuckDB (Multi-Model)

**DuckDB** with the `DuckPGQ` extension (property graph queries) and the `vss` extension (vector similarity search) provides all three capabilities in a single embedded file:

| Capability | Extension | Purpose |
|-----------|-----------|---------|
| **Graph queries** | `DuckPGQ` | Cypher-like path traversal, call hierarchies |
| **Vector search** | `vss` (HNSW) | Semantic similarity on code embeddings |
| **Full-text search** | Built-in FTS | Keyword search, identifier lookup |
| **Relational** | Core DuckDB | Metadata, configs, file inventory |

**Why DuckDB over alternatives:**
- *Embedded, single-file* – no external server (unlike Neo4j, FalkorDB)
- *Blazing fast analytics* – columnar storage optimized for OLAP queries over millions of nodes
- *Python-native* – first-class Python API, zero-copy integration with Pandas/Polars
- *Actively maintained* – strong community + DuckDB Labs backing (unlike archived KuzuDB)
- *Multi-model* – avoids running separate graph + vector databases

### 3.2 Crucial Database Structure Requirement

The database must maintain a node/folder structure exactly mirroring the source code's physical directory structure. Inside each "folder node", the corresponding data nodes (files, functions, structs) reside. This spatial alignment is critical for LLM context: it lets the AI reason about *where* code lives, not just *what* it does.

### 3.3 Schema (Property Graph via DuckPGQ)

```sql
-- Node Tables
CREATE TABLE Directory (id BIGINT PRIMARY KEY, path TEXT UNIQUE, name TEXT, 
                        summary TEXT, depth INT, is_custom BOOL);
CREATE TABLE File (id BIGINT PRIMARY KEY, path TEXT UNIQUE, hash TEXT, 
                   last_modified TIMESTAMP, is_custom BOOL, language TEXT,
                   loc INT, embedding FLOAT[384]);
CREATE TABLE Function (id BIGINT PRIMARY KEY, file_id BIGINT REFERENCES File(id),
                       name TEXT, signature TEXT, start_line INT, end_line INT,
                       summary TEXT, complexity INT, embedding FLOAT[384]);
CREATE TABLE Struct (id BIGINT PRIMARY KEY, file_id BIGINT REFERENCES File(id),
                     name TEXT, summary TEXT, members TEXT[]);
CREATE TABLE Macro (id BIGINT PRIMARY KEY, file_id BIGINT REFERENCES File(id),
                    name TEXT, value TEXT, is_config_guard BOOL);
CREATE TABLE BuildConfig (id BIGINT PRIMARY KEY, key TEXT, value TEXT, 
                          source_file TEXT, build_system TEXT);
CREATE TABLE DeviceTreeNode (id BIGINT PRIMARY KEY, path TEXT, compatible TEXT[],
                             properties JSONB, source_file TEXT);

-- Edge Tables
CREATE TABLE contains_dir (parent_id BIGINT, child_id BIGINT);
CREATE TABLE contains_file (dir_id BIGINT, file_id BIGINT);
CREATE TABLE contains_func (file_id BIGINT, func_id BIGINT);
CREATE TABLE calls (caller_id BIGINT, callee_id BIGINT, call_site_line INT);
CREATE TABLE uses_struct (func_id BIGINT, struct_id BIGINT);
CREATE TABLE includes_file (source_id BIGINT, target_id BIGINT);
CREATE TABLE guarded_by (func_id BIGINT, config_id BIGINT);  -- #ifdef → BuildConfig
CREATE TABLE dt_binds_driver (dt_node_id BIGINT, func_id BIGINT);  -- DT compatible → probe()

-- Property Graph Definition (DuckPGQ)
CREATE PROPERTY GRAPH code_graph
  VERTEX TABLES (Directory, File, Function, Struct, Macro, BuildConfig, DeviceTreeNode)
  EDGE TABLES (
    contains_dir SOURCE KEY (parent_id) REFERENCES Directory DESTINATION KEY (child_id) REFERENCES Directory,
    contains_file SOURCE KEY (dir_id) REFERENCES Directory DESTINATION KEY (file_id) REFERENCES File,
    contains_func SOURCE KEY (file_id) REFERENCES File DESTINATION KEY (func_id) REFERENCES Function,
    calls SOURCE KEY (caller_id) REFERENCES Function DESTINATION KEY (callee_id) REFERENCES Function,
    uses_struct SOURCE KEY (func_id) REFERENCES Function DESTINATION KEY (struct_id) REFERENCES Struct,
    includes_file SOURCE KEY (source_id) REFERENCES File DESTINATION KEY (target_id) REFERENCES File,
    guarded_by SOURCE KEY (func_id) REFERENCES Function DESTINATION KEY (config_id) REFERENCES BuildConfig,
    dt_binds_driver SOURCE KEY (dt_node_id) REFERENCES DeviceTreeNode DESTINATION KEY (func_id) REFERENCES Function
  );

-- Vector Index for Semantic Search
INSTALL vss; LOAD vss;
CREATE INDEX func_embedding_idx ON Function USING HNSW (embedding)
  WITH (metric = 'cosine');
CREATE INDEX file_embedding_idx ON File USING HNSW (embedding)
  WITH (metric = 'cosine');
```

**Key additions over v1 schema**:
- `Macro` nodes – track `#define` guards and config-dependent macros
- `DeviceTreeNode` – first-class DT support with `compatible` string matching
- `guarded_by` edges – link functions to their `#ifdef CONFIG_*` guards
- `dt_binds_driver` edges – link Device Tree `compatible` strings to driver `probe()` functions
- `includes_file` edges – track `#include` chains for dependency resolution
- Embedding vectors directly on `Function` and `File` nodes for hybrid search
- `complexity` field on functions (cyclomatic complexity from AST)

---

## 4. Main Engine Design (Orchestrator & Smart Indexing)

### 4.1 CLI Entry Point

```bash
codecrawler index --project yocto --image rdk-b --config .codecrawler.toml
codecrawler index --project kernel --config-file /path/to/.config
codecrawler mcp             # starts MCP server
codecrawler ui              # starts interactive dashboard
codecrawler watch           # real-time incremental daemon
codecrawler status          # show index stats and health
codecrawler export          # export graph as JSON/DOT for external tools
```

### 4.2 Core Pipeline & Selective Indexing Flow

```text
┌─────────────────────────────────────────────────────────────────────┐
│                        INDEXING PIPELINE                            │
│                                                                     │
│  ┌──────────┐    ┌───────────┐    ┌────────────┐    ┌───────────┐  │
│  │ 1. Quick  │───▶│ 2. Build  │───▶│ 3. Config  │───▶│ 4. File   │  │
│  │ Dir Scan  │    │ Detector  │    │ Analyzer   │    │ Selector  │  │
│  └──────────┘    └───────────┘    └────────────┘    └───────────┘  │
│                                                          │          │
│                                          ┌───────────────┘          │
│                                          ▼                          │
│  ┌───────────┐    ┌───────────┐    ┌────────────┐                  │
│  │ 7. Graph  │◀───│ 6. LLM    │◀───│ 5. Hybrid  │                  │
│  │ Ingestion │    │ Summarize │    │ AST Parse  │                  │
│  └───────────┘    └───────────┘    └────────────┘                  │
│       │                                                             │
│       ▼                                                             │
│  ┌───────────┐                                                      │
│  │ 8. Vector │                                                      │
│  │ Embedding │                                                      │
│  └───────────┘                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**Step-by-step:**

1. **Quick Initial Directory Structure Study**:  
   Before deep parsing, perform a fast scan of the directory tree. Build the `Directory` graph immediately. This gives the LLM an instant, high-level architectural view, helping it reason about code organization before any detailed parsing happens.

2. **Project Auto-Detector**:  
   Automatically detect the build system by probing for signature files:
   - `meta-*/conf/layer.conf` → Yocto/Bitbake
   - `.config` + `Config.in` → Buildroot
   - `feeds.conf.default` → OpenWrt
   - `Kconfig` + `Makefile` at root → Linux kernel
   - `CMakeLists.txt` → CMake project
   - `Makefile` only → Generic Make
   
   **If detection fails or is ambiguous, interactively prompt the user** with detected candidates and let them choose.

3. **Build Config Analyzer** (The Killer Feature):
   - **Yocto**: Parse selected recipes + `bblayers.conf` + `local.conf` → extract `DISTRO_FEATURES`, enabled packages, `PREFERRED_VERSION`, applied patches, `IMAGE_INSTALL` manifest.
   - **Buildroot/OpenWrt**: Parse `.config` → extract `BR2_PACKAGE_*` selections, toolchain config, enabled kernel modules.
   - **Kernel**: Parse `.config` + run `scripts/clang-tools/gen_compile_commands.py` (if kernel already built) or use `Bear` to intercept a build → generate `compile_commands.json`.
   - **compile_commands.json handler**: For CMake projects, use `CMAKE_EXPORT_COMPILE_COMMANDS=ON` (Yocto's `cmake.bbclass` does this automatically). For Makefile projects, use `Bear` or `compiledb`. This gives libclang *exact* compiler flags per file.
   - **Output**: Set of active source files, enabled `#ifdef` symbols, active Device Tree files (`.dts`), and the resolved `compile_commands.json`.

4. **File Selector & Progressive Indexing**:
   - Filter out untouched upstream code (`busybox/`, `coreutils/`, unconfigured `kernel/drivers/`) based on build config analysis results.
   - Focus parsing on developer-modified code (custom drivers, serial/GPIO pins, vendor layers, custom subsystems).
   - **Tiered indexing strategy**:
     - **Tier 1 (Full)**: Custom/modified files → full AST + summaries + embeddings.
     - **Tier 2 (Skeleton)**: Direct dependencies of Tier 1 → signatures + call edges only (no summaries).
     - **Tier 3 (Stub)**: Everything else → file name + path + hash only. Promoted on demand.
   - Allow user overrides via `[include]` and `[exclude]` sections in `.codecrawler.toml`.
   - **Progressive DB Growth**: As the developer queries new files or asks about untouched code, use **Lazy Indexing** to dynamically upgrade Tier 3 → Tier 2 → Tier 1 in the background.

5. **Hybrid AST Parser** (Tree-sitter + libclang):
   - **Tree-sitter (fast pass)**: Rapidly extract structural AST—function signatures, struct definitions, `#include` directives, macro definitions. Fault-tolerant, works on incomplete/broken code. Runs on *all* selected files.
   - **libclang (deep pass)**: For Tier 1 files with a valid `compile_commands.json`, run libclang to get:
     - Fully resolved `#ifdef` paths (which code paths are actually compiled)
     - Accurate cross-translation-unit call graphs
     - Type-resolved symbol references
     - Preprocessor macro expansion
   - **Merge strategy**: Tree-sitter provides the structural skeleton. libclang overlays semantic precision. If libclang fails (missing headers, broken build), tree-sitter results are used as fallback.

6. **Cheap LLM Summarizer**:
   - Batch process function/struct summaries using a cost-effective model.
   - **Structured prompt** per function:
     ```
     Function: {name}
     Signature: {signature}
     Calls: {callee_list}
     Uses structs: {struct_list}
     Build guards: {ifdef_list}
     Source (lines {start}-{end}):
     {code_snippet}
     
     Write a 2-3 sentence summary of what this function does.
     Tag it with categories: [driver|init|config|network|storage|security|util|other]
     ```
   - Run asynchronously with rate limiting. Retry on failures.

7. **Graph Ingestion**: Insert all nodes and edges into the DuckDB graph with proper spatial organization.

8. **Vector Embedding**: Generate embeddings for function summaries and file-level summaries using `sentence-transformers/all-MiniLM-L6-v2` (384-dim, runs locally). Store in HNSW-indexed columns.

---

## 5. Build-System Awareness & Embedded Superpowers

This is the part no other tool has for Yocto/Buildroot/OpenWrt.

### 5.1 compile_commands.json Generation Strategy

| Build System | Method | Tool |
|-------------|--------|------|
| CMake | `CMAKE_EXPORT_COMPILE_COMMANDS=ON` | Native CMake |
| Yocto + CMake | `cmake.bbclass` auto-sets it | Yocto SDK |
| Yocto + Make | `devtool ide-sdk` + Bear | Bear 2.4.4 |
| Linux Kernel | `scripts/clang-tools/gen_compile_commands.py` | Kernel scripts |
| Buildroot | `BR2_PACKAGE_HOST_BEAR=y` or post-build Bear | Bear |
| Generic Make | `bear -- make` | Bear / compiledb |

### 5.2 `#ifdef` Resolution Pipeline

```text
.config file → Parse CONFIG_* symbols → Build symbol table
    │
    ▼
For each C file: tree-sitter finds #ifdef/#if blocks
    │
    ▼
Cross-reference with symbol table → Mark active/inactive branches
    │
    ▼
Create guarded_by edges: Function → BuildConfig
    │
    ▼
libclang confirms (if compile_commands.json available)
```

### 5.3 Device Tree Awareness

Embedded Linux heavily relies on Device Trees. Code Crawler will:
- Parse `.dts` and `.dtsi` files → extract nodes, `compatible` strings, properties
- Match `compatible` strings to kernel driver `of_match_table` entries
- Create `dt_binds_driver` edges linking DT nodes to their driver `probe()` functions
- Enable queries like: *"What driver handles the UART at address 0x12340000?"*

### 5.4 MCP Tools for Build Context

- `analyze_build_context(query)`: Returns a plain-English summary of enabled features, custom layers, patches, and `#ifdef` chains active in the current image.
- `lazy_index_directory(path)`: Force the system to index a previously excluded directory on-demand, upgrading it from Tier 3 to Tier 1.
- `resolve_ifdef_chain(symbol)`: Trace a `CONFIG_*` symbol from Kconfig definition → `.config` value → guarded code paths.
- `trace_dt_to_driver(dt_path)`: Given a Device Tree node path, return the full chain: DT node → compatible string → driver module → probe function → initialization sequence.

---

## 6. MCP Integration (Official SDK) – Agent-Centric Design

Use the `mcp` Python SDK. Following MCP best practices, tools are designed around **complete workflows** (not raw API endpoints) to minimize the LLM's cognitive load and token usage.

### 6.1 Design Principles

- **Workflow-oriented tools**: Each tool handles a complete user goal internally, reducing multi-step orchestration by the LLM.
- **Managed tool budget**: Keep tool count under ~15 to avoid agent confusion and token waste.
- **Rich documentation**: Every tool includes purpose, parameter schemas, usage examples, and error semantics so the LLM knows exactly when and how to use it.
- **Structured output**: Return JSON with consistent schemas so the LLM can parse results reliably.

### 6.2 Tool Definitions

| Tool | Description | Returns |
|------|-------------|---------|
| `search_code(query, scope?)` | Hybrid vector + graph + FTS search. Scope can be customized. | Ranked results with file paths, line numbers, summaries, and relevance scores |
| `get_folder_structure(path?, depth?)` | Returns the spatial folder graph | Tree with metadata (file count, custom flag, summary) |
| `get_call_hierarchy(func, direction, depth?)` | Graph traversal for callers/callees | Call tree with signatures, files, and summaries |
| `get_build_context(query)` | Resolves active `#ifdef` configs for a query | Active configs, their sources, and affected code paths |
| `get_code_snippet(file, start, end)` | Retrieve raw source code | Source text with line numbers |
| `trace_data_flow(symbol, scope?)` | Track a variable/struct through call chains | Ordered list of functions that read/write the symbol |
| `get_dt_binding(compatible_or_path)` | Device Tree → driver resolution | DT node, compatible string, driver file, probe function |
| `analyze_impact(file_or_func)` | What depends on this? What breaks if it changes? | Dependency tree: callers, includers, DT bindings |
| `lazy_index(path)` | On-demand indexing of previously excluded code | Status + summary of newly indexed entities |
| `get_index_status()` | Index health, coverage stats, stale files | Dashboard data |

### 6.3 MCP Resources

Expose key data as MCP resources for context injection:
- `codecrawler://project/summary` – High-level project description + build system info
- `codecrawler://tree/{path}` – Directory tree at a given path
- `codecrawler://config/active` – Currently active build configuration summary

---

## 7. UI for Developers (Human-Readable Interactive View)

**FastAPI + HTMX + Vis.js (or D3.js)** powered dashboard designed for code comprehension.

### 7.1 Core UI Features

- **Source-Tree Graph Explorer**: A visual directory tree that mirrors the physical folder structure, but overlays interconnected graph edges (function calls, includes, DT bindings) across files. Click any node to drill into its details.

- **Tinker Focus Mode**: A toggle that visually dims upstream/untouched code (like `coreutils`) and highlights custom layers, modified files, and active `.dts` files. This is the "show me only what I care about" button.

- **AI Chat + Code-Map Integration**: When a developer asks *"How is UART2 initialized?"*, the UI not only answers but physically highlights the path in the graph explorer, spanning from the Device Tree file → compatible match → driver probe function → register initialization.

- **Build Config Dashboard**: A navigable Kconfig/Bitbake tree showing which flags are enabled, which files they activate, and the `#ifdef` chains they control. Toggle a config and see which code paths light up.

- **"What changed since last index?"**: An incremental diff view showing new nodes, new edges, deleted entities, and changed summaries since the last indexing run.

### 7.2 New UI Ideas

- **Dependency Blast Radius**: Select a file or function and visualize everything that depends on it. Useful before refactoring: *"If I change this struct, what breaks?"*

- **Cross-Layer View** (Yocto-specific): Visualize which Yocto layers contribute to the final image. Overlay patches, `bbappend` files, and recipe overrides in a stacked view.

- **Code Heatmap**: Color files by modification frequency (from git history), complexity, or LLM-determined "risk score". Identify hotspots at a glance.

- **Interactive Query Builder**: A visual Cypher/SQL query builder that generates graph queries without writing raw syntax.

---

## 8. LLM Write-Back & Knowledge Enrichment

> [!IMPORTANT]
> This is a bidirectional system: LLMs don't just *read* from the graph—they can *write back* to enrich it.

### 8.1 Write-Back Mechanism

When an LLM (via MCP or the UI chat) discovers insights during a conversation, it can propose annotations:

```python
# MCP tool for LLM write-back
annotate_entity(entity_type, entity_id, annotation_type, content)
# Example: annotate_entity("Function", 42, "insight", 
#   "This function is the main entry point for WiFi credential provisioning. 
#    It's called during first-boot only when CONFIG_WIFI_ONBOARDING is set.")
```

### 8.2 Annotation Types
- **`insight`**: High-level understanding the LLM derived from multi-hop reasoning
- **`warning`**: Potential bugs, race conditions, or security concerns the LLM identified
- **`relationship`**: New edges the LLM discovered (e.g., an indirect functional dependency)
- **`tag`**: Categorical tags (e.g., "security-critical", "init-sequence", "hardware-specific")

### 8.3 Rules for Write-Back
- All LLM annotations are stored separately from deterministic AST data (in an `Annotation` table)
- Annotations include the LLM model name, timestamp, and confidence score
- Human developers can review, approve, or reject annotations via the UI
- Approved annotations are promoted to first-class graph properties

---

## 9. Incremental Indexing & Real-Time Watch

### 9.1 File Change Detection

```text
watchdog (OS file events)
    │
    ├── File modified → Compare content hash
    │   ├── Hash unchanged → Skip
    │   └── Hash changed → Re-parse affected file
    │       ├── Update AST nodes (functions, structs, macros)
    │       ├── Re-compute edges (calls, includes)
    │       ├── Invalidate & regenerate summaries
    │       └── Update embeddings
    │
    ├── File created → Index new file (respect tier rules)
    └── File deleted → Remove nodes + cascade-delete edges
```

### 9.2 Git-Aware Incremental Updates
- On `git pull` or branch switch, diff the file list and re-index only changed files
- Track `git blame` to identify which files are actively developed vs. old/stable
- Use git history to compute the **Code Heatmap** feature

---

## 10. Configuration (`.codecrawler.toml`)

```toml
[project]
name = "my-rdk-build"
type = "yocto"                    # auto-detected, or user-specified
root = "/home/dev/yocto-build"
build_dir = "/home/dev/yocto-build/build"

[index]
tiers = { full = ["meta-custom/**", "meta-vendor/**"], 
          skeleton = ["poky/meta/**"],
          stub = ["**"] }           # everything else
exclude = ["build/tmp/**", "downloads/**", ".git/**"]

[build]
config_file = "build/conf/local.conf"      # Yocto
layers_file = "build/conf/bblayers.conf"   # Yocto
kernel_config = "build/tmp/work/**/linux-*/build/.config"  # glob pattern
compile_commands = "auto"                  # auto-generate, or path to existing

[llm]
provider = "ollama"               # ollama | openai | anthropic
model = "llama3.2:8b"            # or "gpt-4o-mini" for OpenAI
batch_size = 50
max_concurrent = 4
retry_count = 3

[embeddings]
model = "sentence-transformers/all-MiniLM-L6-v2"
device = "cpu"                    # cpu | cuda

[mcp]
host = "127.0.0.1"
port = 8765
transport = "stdio"               # stdio | sse

[ui]
host = "0.0.0.0"
port = 8080

[watch]
enabled = false
debounce_ms = 500
```

---

## 11. Tech Stack (Technically Sound & Lightweight)

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Language** | Python 3.12+ | Core + MCP + UI, rich ecosystem |
| **Fast parsing** | `tree-sitter` + Python bindings | Incremental, fault-tolerant, all languages |
| **Deep parsing** | `libclang` (Python `clang` package) | Precise `#ifdef` resolution, type info, cross-TU |
| **DB** | DuckDB + DuckPGQ + vss | Embedded, graph + vector + FTS in one file |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` | 384-dim, fast, runs locally on CPU |
| **Code embeddings** | Microsoft UniXcoder (optional) | Code-aware embeddings, better for code search |
| **LLM summarizer** | Ollama (Llama 3.2 / Deepseek) | Local, free, configurable |
| **LLM fallback** | GPT-4o-mini / Claude Haiku | Cloud API for higher quality summaries |
| **Web UI** | FastAPI + HTMX + Vis.js or D3.js | Lightweight, no heavy JS framework needed |
| **File watching** | `watchdog` | Cross-platform file system events |
| **Build interception** | Bear 2.4.4 / compiledb | Generate compile_commands.json from Make |
| **DT parsing** | `dtc` (Device Tree Compiler) Python bindings | Parse .dts/.dtsi files |
| **Packaging** | `uv` + PyInstaller | Fast dependency management + single binary |
| **Testing** | `pytest` + `pytest-asyncio` | Async-friendly testing |

---

## 12. Error Handling & Resilience

### 12.1 Graceful Degradation

Code Crawler should work even when parts of the pipeline fail:

| Failure | Degraded Behavior |
|---------|-------------------|
| No `compile_commands.json` | Skip libclang pass; tree-sitter only (less precise `#ifdef` resolution) |
| LLM unavailable | Index without summaries; summaries generated later when LLM comes online |
| Embedding model fails to load | Skip vector indexing; graph + FTS search still works |
| Build config not found | Index all files without tier filtering; warn user |
| Partial parse failure | Log error, skip file, continue indexing; report failed files in status |

### 12.2 Logging & Observability
- Structured JSON logging with severity levels
- Index run reports: files processed, errors, duration, coverage percentage
- MCP request logging with timing for performance debugging

---

## 13. Security Considerations

Since Code Crawler acts as an MCP server that LLMs interact with:

- **Input validation**: Sanitize all file paths and queries to prevent path traversal
- **No arbitrary code execution**: MCP tools return data only, never execute user-supplied code
- **Scoped access**: The MCP server only accesses files within the configured project root
- **Annotation review**: LLM write-backs require human approval before modifying core graph data
- **Transport security**: Support stdio (local) and SSE with optional TLS for remote access

---

## 14. Phases (Updated & Realistic)

### Phase 0 – Foundation (1–2 weeks)
- [ ] Project skeleton with `uv` + proper package structure
- [ ] DuckDB schema with DuckPGQ property graph + vss vector index
- [ ] C/C++ tree-sitter parser MVP: extract functions, structs, includes
- [ ] Directory tree scanner → build spatial graph
- [ ] Basic `.codecrawler.toml` config loading
- [ ] **Milestone**: Can index a small C project and query the graph via Python

### Phase 1 – Build System Intelligence (2–3 weeks)
- [ ] Build system auto-detector (Yocto/Buildroot/Kernel/CMake/Make)
- [ ] Interactive fallback prompts when detection fails
- [ ] Yocto recipe parser (`bblayers.conf`, `local.conf`, recipe metadata)
- [ ] Kernel `.config` parser + `compile_commands.json` generation
- [ ] Buildroot `.config` parser
- [ ] Tiered file selector (Full / Skeleton / Stub)
- [ ] **Milestone**: Can detect a Yocto build and selectively index custom layers only

### Phase 2 – Deep Analysis (2 weeks)
- [ ] libclang integration: `#ifdef` resolution using `compile_commands.json`
- [ ] Cross-TU call graph resolution via libclang
- [ ] Device Tree parser: `.dts`/`.dtsi` → DeviceTreeNode + driver binding edges
- [ ] `guarded_by` edge creation (`#ifdef CONFIG_*` → BuildConfig)
- [ ] **Milestone**: Can resolve which code paths are active for a given kernel config

### Phase 3 – AI Layer (1–2 weeks)
- [ ] Cheap LLM summarizer with structured prompts + async batching
- [ ] Embedding generation (MiniLM or UniXcoder)
- [ ] Vector index creation + hybrid search (graph + vector + FTS)
- [ ] **Milestone**: Can answer semantic queries like "how is WiFi initialized?"

### Phase 4 – MCP Server (1 week)
- [ ] MCP server with all tool definitions (using official `mcp` SDK)
- [ ] MCP resource definitions
- [ ] Workflow-oriented tool design with rich documentation
- [ ] Test with Claude Desktop / Cursor / VS Code
- [ ] **Milestone**: LLM can query the codebase through MCP tools

### Phase 5 – Real-Time & UI (2–3 weeks)
- [ ] `watchdog`-based incremental watcher
- [ ] Git-aware diffing for re-indexing
- [ ] FastAPI web dashboard: tree explorer, graph visualization
- [ ] Tinker Focus Mode
- [ ] Build Config Dashboard
- [ ] AI chat integration with graph highlighting
- [ ] **Milestone**: Developer can visually explore and query their codebase

### Phase 6 – Enrichment & Polish (1–2 weeks)
- [ ] LLM write-back / annotation system
- [ ] Lazy indexing (Tier 3 → Tier 1 on demand)
- [ ] Dependency blast radius visualization
- [ ] Code heatmap from git history
- [ ] Export graph as JSON/DOT
- [ ] **Milestone**: Complete bidirectional system with visual insights

### Phase 7 – Extensibility (ongoing)
- [ ] Python crawler + Shell script parsing
- [ ] Plugin system for new languages
- [ ] Rust-based performance-critical extensions (optional)
- [ ] Community plugin marketplace

---

## 15. Success Metrics

| Metric | Target |
|--------|--------|
| Indexing speed (Tier 1) | > 1,000 files/minute on commodity hardware |
| Query latency (MCP) | < 500ms for graph queries, < 1s for hybrid search |
| Token savings | > 80% reduction vs. raw file scanning for typical queries |
| `#ifdef` accuracy | > 95% when `compile_commands.json` is available |
| First useful query | < 5 minutes from `codecrawler index` on a medium project |
| Incremental re-index | < 10 seconds for single-file changes |
