# Code Crawler v3 Workflow

This architectural diagram illustrates the complete 12-step **Indexing Swarm Pipeline**, detailing how raw source code is ingested, pruned, analyzed by AI models, and compiled into zero-latency manifests for autonomous agents.

```mermaid
flowchart TD
    %% Custom Styling for a Cyber/Terminal look
    classDef phase fill:#0a0a0a,stroke:#ff0033,stroke-width:2px,color:#ffffff,font-weight:bold;
    classDef step fill:#1a1a1a,stroke:#666666,stroke-width:1px,color:#dddddd;
    classDef ai fill:#331111,stroke:#ff3366,stroke-width:1px,color:#ffcccc;
    classDef final fill:#440000,stroke:#ff0000,stroke-width:3px,color:#ffffff,font-weight:900;

    subgraph Phase1 [Phase 1: Discovery & Filtering]
        A[1. Quick Dir Scan] --> B[2. Build Detector]
        B --> C[3. LLM Tier Classification]:::ai
        C --> D[4. Hybrid Tier Merge]
    end

    subgraph Phase2 [Phase 2: Semantic Intelligence]
        D --> E[5. Intersect IPC + AST]
        E --> F[6. LLM Summarization]:::ai
        F --> G[7. Fleet Telemetry Ingest]
        G --> H[8. Graph DB Ingest]
    end

    subgraph Phase3 [Phase 3: Deep Calculation]
        H --> I[9. Vector Embeddings]
        I --> J[10. Math Priority Scorer]
    end

    subgraph Phase4 [Phase 4: Agent Delivery & Sync]
        J --> K[11. Bundle Index Manifests]:::final
        K --> L[12. P2P Swarm Sync]:::final
    end

    A:::step
    B:::step
    D:::step
    E:::step
    G:::step
    H:::step
    I:::step
    J:::step
    
    style Phase1 fill:none,stroke:#444,stroke-dasharray: 5 5
    style Phase2 fill:none,stroke:#444,stroke-dasharray: 5 5
    style Phase3 fill:none,stroke:#444,stroke-dasharray: 5 5
    style Phase4 fill:none,stroke:#444,stroke-dasharray: 5 5
```

### Pipeline Overview

* **Phase 1** focuses on drastically reducing the context scale. By intelligently identifying build boundaries and using lightweight LLMs (like Llama-3 8B) to classify code into tiers, we skip massive unneeded subsystems (like upstream Linux networking).
* **Phase 2** is the core semantic layer. Deep abstract syntax trees (ASTs) are bound to inter-process communication definitions, and LLMs write detailed function summaries. Crash trace telemetry is folded into the graph here.
* **Phase 3** calculates spatial priority. The **Math Priority Scorer** algorithm assigns weights based on usage frequency, recency, and crash hits, isolating what truly matters.
* **Phase 4** concludes with static bundle generation. Instead of the LLM searching live DBs constantly, it is fed entirely pre-materialized **Index Manifests**, eliminating expensive multi-hop tool routing. Team changes are instantly shared via **Swarm Sync**.
