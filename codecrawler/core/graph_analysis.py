"""graph_analysis — PageRank and centrality computation on the call graph.

Inspired by Aider's repo-map PageRank ranking, combined with betweenness
centrality to identify structural bottleneck (bridge) functions.

Operates on the call-edge list produced by parsing and scope resolution,
computing per-function metrics that feed into the hybrid priority scorer.

Usage:
    analyzer = GraphAnalyzer()
    metrics = analyzer.analyze(call_edges)
    # metrics: dict[int, GraphMetrics]  —  func_id → metrics
"""

from __future__ import annotations

import logging
from collections import defaultdict

from codecrawler.core.types import GraphMetrics

logger = logging.getLogger(__name__)


class GraphAnalyzer:
    """Compute graph centrality metrics on the function call graph.

    Metrics computed:
      - **PageRank** — recursive importance (a function is important if
        it's called by important functions). Captures structural relevance.
      - **Betweenness centrality** — how often a function lies on shortest
        paths between other functions. Identifies bridging/bottleneck code.
      - **In-degree** — raw count of how many callers a function has.
        Proxy for usage frequency.
      - **Hub / bridge classification** — high in-degree = hub,
        high betweenness = structural bridge.
    """

    def __init__(
        self,
        pagerank_alpha: float = 0.85,
        pagerank_max_iter: int = 100,
        pagerank_tol: float = 1e-6,
    ) -> None:
        self._alpha = pagerank_alpha
        self._max_iter = pagerank_max_iter
        self._tol = pagerank_tol

    def analyze(
        self, call_edges: list[tuple[int, int]]
    ) -> dict[int, GraphMetrics]:
        """Compute all graph metrics for the call graph.

        Args:
            call_edges: List of (caller_id, callee_id) tuples.

        Returns:
            Dictionary mapping func_id → GraphMetrics.
        """
        if not call_edges:
            return {}

        # Try networkx first (more accurate), fall back to built-in
        try:
            return self._analyze_networkx(call_edges)
        except ImportError:
            logger.info("networkx not available, using built-in graph analysis")
            return self._analyze_builtin(call_edges)

    def _analyze_networkx(
        self, call_edges: list[tuple[int, int]]
    ) -> dict[int, GraphMetrics]:
        """Analysis using networkx for accuracy."""
        import networkx as nx

        G = nx.DiGraph()
        for caller, callee in call_edges:
            G.add_edge(caller, callee)

        node_count = len(G)
        logger.info("Graph analysis: %d nodes, %d edges", node_count, len(call_edges))

        # PageRank
        try:
            pagerank = nx.pagerank(
                G, alpha=self._alpha, max_iter=self._max_iter, tol=self._tol
            )
        except nx.PowerIterationFailedConvergence:
            logger.warning("PageRank did not converge, using uniform distribution")
            pagerank = {n: 1.0 / node_count for n in G.nodes()}

        # Betweenness centrality (expensive for large graphs — sample if needed)
        if node_count > 5000:
            betweenness = nx.betweenness_centrality(G, k=min(500, node_count))
        else:
            betweenness = nx.betweenness_centrality(G, normalized=True)

        # In-degree
        in_degree = dict(G.in_degree())
        max_in = max(in_degree.values()) if in_degree else 1

        # Out-degree
        out_degree = dict(G.out_degree())

        # Classification thresholds
        hub_threshold = max_in * 0.3   # Top 30% by in-degree
        bridge_threshold = 0.05        # Top 5% betweenness

        metrics: dict[int, GraphMetrics] = {}
        for node in G.nodes():
            in_deg = in_degree.get(node, 0)
            metrics[node] = GraphMetrics(
                func_id=node,
                pagerank=pagerank.get(node, 0.0),
                betweenness=betweenness.get(node, 0.0),
                in_degree_norm=in_deg / max_in if max_in > 0 else 0.0,
                out_degree=out_degree.get(node, 0),
                is_hub=in_deg >= hub_threshold,
                is_bridge=betweenness.get(node, 0.0) >= bridge_threshold,
            )

        return metrics

    def _analyze_builtin(
        self, call_edges: list[tuple[int, int]]
    ) -> dict[int, GraphMetrics]:
        """Pure-Python fallback analysis without external dependencies.

        Implements a simplified PageRank using power iteration and
        approximates betweenness with an in/out-degree heuristic.
        """
        # Build adjacency
        outgoing: dict[int, list[int]] = defaultdict(list)
        incoming: dict[int, list[int]] = defaultdict(list)
        nodes: set[int] = set()

        for caller, callee in call_edges:
            outgoing[caller].append(callee)
            incoming[callee].append(caller)
            nodes.add(caller)
            nodes.add(callee)

        n = len(nodes)
        if n == 0:
            return {}

        node_list = sorted(nodes)
        node_idx = {nid: i for i, nid in enumerate(node_list)}

        # Power-iteration PageRank
        pr = [1.0 / n] * n
        for _ in range(self._max_iter):
            new_pr = [(1 - self._alpha) / n] * n
            for i, nid in enumerate(node_list):
                out = outgoing.get(nid, [])
                out_count = len(out)
                if out_count == 0:
                    # Dangling node distributes evenly
                    share = pr[i] / n
                    for j in range(n):
                        new_pr[j] += self._alpha * share
                else:
                    share = pr[i] / out_count
                    for callee in out:
                        j = node_idx.get(callee)
                        if j is not None:
                            new_pr[j] += self._alpha * share

            # Check convergence
            diff = sum(abs(new_pr[i] - pr[i]) for i in range(n))
            pr = new_pr
            if diff < self._tol:
                break

        # In-degree & out-degree
        in_degree = {nid: len(incoming.get(nid, [])) for nid in nodes}
        out_degree = {nid: len(outgoing.get(nid, [])) for nid in nodes}
        max_in = max(in_degree.values()) if in_degree else 1

        # Approximate betweenness: bridge = high in+out relative to average
        avg_connections = sum(in_degree.values()) / n if n > 0 else 0
        bridge_threshold = max(avg_connections * 2, 3)

        metrics: dict[int, GraphMetrics] = {}
        for i, nid in enumerate(node_list):
            in_deg = in_degree.get(nid, 0)
            out_deg = out_degree.get(nid, 0)
            # Heuristic betweenness proxy
            betweenness_proxy = (
                (in_deg * out_deg) / (max_in * max(out_degree.values() or [1]))
                if max_in > 0
                else 0.0
            )

            metrics[nid] = GraphMetrics(
                func_id=nid,
                pagerank=pr[i],
                betweenness=betweenness_proxy,
                in_degree_norm=in_deg / max_in if max_in > 0 else 0.0,
                out_degree=out_deg,
                is_hub=in_deg >= max_in * 0.3,
                is_bridge=(in_deg + out_deg) >= bridge_threshold,
            )

        logger.info(
            "Built-in graph analysis: %d nodes, %d hubs, %d bridges",
            n,
            sum(1 for m in metrics.values() if m.is_hub),
            sum(1 for m in metrics.values() if m.is_bridge),
        )
        return metrics

    @staticmethod
    def extract_edges_from_db(db_connection) -> list[tuple[int, int]]:
        """Extract call edges from the DuckDB database.

        Combines direct calls, IPC calls, and cross-language calls.
        """
        edges: list[tuple[int, int]] = []
        try:
            rows = db_connection.execute(
                "SELECT caller_id, callee_id FROM calls"
            ).fetchall()
            edges.extend((r[0], r[1]) for r in rows)
        except Exception:
            pass

        try:
            rows = db_connection.execute(
                "SELECT caller_func_id, callee_func_id FROM calls_over_ipc"
            ).fetchall()
            edges.extend((r[0], r[1]) for r in rows)
        except Exception:
            pass

        try:
            rows = db_connection.execute(
                "SELECT caller_func_id, callee_func_id FROM calls_cross_language"
            ).fetchall()
            edges.extend((r[0], r[1]) for r in rows)
        except Exception:
            pass

        return edges
