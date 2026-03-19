# Code Crawler (Semantic Code Indexer)

**Code Crawler** is a persistent, AI-driven codebase indexer and Model Context Protocol (MCP) server aimed at large, macro-heavy embedded C/C++ projects (e.g., Yocto, OpenWrt, Linux kernel, RDK-B).

## The Problem
Modern Large Language Models (LLMs) cannot fit massive codebases (millions of lines) into their context windows. Simple text search often fails to capture semantic relationships, nested call graphs, and build-system nuances (like complex `#ifdef` chains).

## The Solution
Instead of feeding raw code files to high-tier LLMs directly, Code Crawler preprocesses the codebase, creates an intelligent database graph, and acts as a Model Context Protocol (MCP) service. The LLM simply asks Code Crawler a question ("How does the Mac address get initialized?"), and Code Crawler responds with precise summaries and code pointers.

---

## 🏗️ Architecture Requirements

1. **Pre-Indexing Engine (The Crawler)**
   An offline pipeline that scans the codebase, reads compile commands, and builds an Abstract Syntax Tree (AST) using tools like `tree-sitter` or `libclang`. It extracts structural data: functions, structs, global variables, and call graphs.

2. **Summary Generation (Cost-Effective LLM Pass)**
   A local or cheap API-driven LLM (e.g., Llama 3, GPT-4o-mini) ingests the raw structural AST data. It function-by-function writes a plain-English, AI-friendly summary of what each component does.

3. **Storage & Database Backend**
   - **Graph Database** (Node/Edge relations like Neo4j or NetworkX) for relational queries (e.g., *Who calls this function?*).
   - **Vector Database / SQLite** for semantic search (e.g., *Where is the driver initialized?*).

4. **Modular Language Support**
   Initial focus strictly on C/C++ to target 90% of embedded/router/kernel platforms, but keeping a pluggable architecture for eventual Python/Rust support.

5. **API/Integration Layer (MCP)**
   Expose the indexed data through the standard Model Context Protocol (MCP) so IDEs (VS Code, Cursor) and Agents (Claude Desktop) can natively search the indexed database.

---

## 🚀 Phases of Implementation

### Phase 1: Minimum Viable Product (MVP) - C/C++ Extractor
- Set up the Python project structure.
- Write a basic parser using `tree-sitter-c` or `libclang`.
- Given a sample Linux C file, extract function signatures, starting lines, and ending lines into a local JSON or SQLite database.

### Phase 2: Cheap LLM Summarizer
- Setup API calls to a cost-effective model.
- Pass the extracted AST data function-by-function to generate AI-readable documentation strings for the database.

### Phase 3: Fast Graph Query System
- Organize functions into a lightweight graph to map control/data flow (caller/callee).

### Phase 4: MCP Server Integration
- Build a Python MCP Server using the official `mcp` SDK.
- Create tools like `get_component_summary(name)`, `get_call_hierarchy(func)`, and `search_functions_semantically(query)`.

---

## Development Environment
- Primary Langs: Python (for tooling & MCP), C/C++ (target)
- Core Libraries: `tree-sitter`, `sqlite3`, `mcp` SDK.
