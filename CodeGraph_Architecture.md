# CodeGraph AI - Project Ideation & Architecture Tracker

## 1. Project Vision
An industry-standard, API-driven application designed to index massive C/C++ embedded codebases (like Linux kernel, Yocto, OpenWrt, RDK-B). It analyzes code logic, generates AI-friendly summaries using a cost-effective LLM, and creates a highly optimized database. Top-tier LLMs can then query this database to solve complex problems without overwhelming their context windows.

## 2. Target Audience & Use Case
- **Target Audience:** Embedded Linux developers, systems engineers, and AI companies needing tools to navigate macro-heavy, complex C/C++ build systems.
- **Primary Problem:** Current LLMs fail at large codebases because they cannot fit millions of lines of code into their context window, and simple text search misses the semantic relationships, call graphs, and build-system nuances (like `#ifdef` chains).

## 3. Core Architecture
- **Pre-indexing Engine:** A standalone pipeline that runs ahead of time.
- **Language Components (Modular):**
  - Starts with C/C++ (handles 90% of embedded projects).
  - Uses tools like `tree-sitter` or `libclang` to generate Abstract Syntax Trees (AST) and capture call graphs.
- **Cheap LLM Pass:** Interrogates the AST, function by function, writing human/AI-readable descriptions of what the components do.
- **Database Backend:** Stores relationships (Graph Database like Neo4j) and semantic meaning (Vector Database).
- **Standardized API (Model Context Protocol - MCP):** Exposes search and retrieval endpoints so IDEs (VS Code, Cursor) can natively let their AI ask questions to the database.

## 4. Current Status
- [x] Initial concept defined.
- [x] Explaining AI basics and IDE integration to the user.
- [x] Drafting the structured prompt for ongoing use.
- [ ] Investigate existing similar tools (Bloop, Sourcegraph, Greptile).
- [ ] Define MVP (Minimum Viable Product) features.
