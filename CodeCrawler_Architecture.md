# Code Crawler - Project Ideation & Architecture Tracker

## 1. Project Vision
An industry-standard, API-driven application designed to index massive C/C++ embedded codebases (like Linux kernel, Yocto, OpenWrt, RDK-B). It analyzes code logic, generates AI-friendly summaries using a cost-effective LLM, and creates a highly optimized database. Top-tier LLMs can then query this database to solve complex problems without overwhelming their context windows.

## 2. Target Audience & Use Case
- **Target Audience:** Embedded Linux developers, systems engineers, and AI companies needing tools to navigate macro-heavy, complex C/C++ build systems.
- **Primary Problem:** Current LLMs fail at large codebases because they cannot fit millions of lines of code into their context window, and simple text search misses the semantic relationships, call graphs, and build-system nuances (like `#ifdef` chains).

## 3. Core Architecture & Implementation Pipeline

### Phase A: The Ingestion Engine (Crawler)
- **Language Parsers:** `tree-sitter` (fast, fault-tolerant AST parsing) instead of rigid compilers.
- **Node Extraction:** Identifies functions, struct definitions, enums, global variables, and macros.
- **Edge Extraction:** Maps dependencies. Identifies `CALLS` (function calls function), `INCLUDES` (file includes file), `READS`/`WRITES` (function modifies state).

### Phase B: The AI Summarization Pass (Background Process)
- **Batch Processing:** Runs a cost-effective model (like `gpt-4o-mini`, `claude-3-haiku`, or local `llama3-8b`) asynchronously over the codebase.
- **The Prompt Structure:** For each function, the model is fed: 
  * "Here is the C function `xyz`. It takes arguments `A`, `B`. It calls `foo` and `bar`. What does it do in 2-3 sentences?"
- **Metadata Tagging:** Models categorize the code (e.g., "Network Driver", "Memory Management", "Init Script").

### Phase C: The Hybrid Database Layer
- **Graph Database (SQLite / NetworkX):** Stores relationships. Examples: querying all functions that touch the `wlan` pointer.
- **Vector Database (ChromaDB / LanceDB):** Stores semantic embeddings of the AI summaries. Allows "fuzzy" natural language searches by top-tier models.

### Phase D: The Agent API (Model Context Protocol)
- **MCP Server:** Runs a local JSON-RPC server conforming to the MCP standard.
- **Tools Exposed to AI:**
  - `get_function_summary(name="wlan_init")`
  - `get_call_hierarchy_up(name="mac_start")` -> returns callers
  - `search_codebase_intent(query="how is the ip address assigned?")` -> query the vector DB.

## 4. Current Status
- [x] Initial concept defined.
- [x] Explaining AI basics and IDE integration to the user.
- [x] Renamed project to "Code Crawler".
- [x] Detailed implementation pipeline designed.
- [ ] Initialize Python environment and dependencies (`tree-sitter`, `mcp`, `sqlite3`).
- [ ] Build the first script: parsing a dummy C file and extracting functions.
