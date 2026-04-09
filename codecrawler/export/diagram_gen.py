"""diagram_gen — Auto-generate Mermaid architecture and call-graph diagrams.

Inspired by Ericsson CodeCompass's diagram generation capabilities.
Produces Mermaid-formatted diagrams from the knowledge graph that can
be embedded in documentation, served via MCP, or rendered in the UI.

Usage:
    gen = DiagramGenerator(db_connection)
    mermaid = gen.call_graph("wifi_hal_init", depth=3)
    mermaid = gen.file_dependency_graph("src/wifi/")
"""

from __future__ import annotations

import logging
from collections import deque

logger = logging.getLogger(__name__)


class DiagramGenerator:
    """Auto-generate Mermaid diagrams from the Code Crawler knowledge graph.

    Supported diagram types:
      - Call graph (rooted at a function, BFS to depth N)
      - File dependency graph (include edges)
      - IPC flow diagram (cross-process edges)
      - Tier treemap (code distribution by tier)
    """

    # Mermaid node colours by language
    _LANG_STYLES = {
        "c":          "fill:#4ecdc4,color:#000",
        "cpp":        "fill:#45b7d1,color:#000",
        "python":     "fill:#ffa726,color:#000",
        "shell":      "fill:#7e57c2,color:#fff",
        "rust":       "fill:#ff7043,color:#fff",
        "go":         "fill:#26a69a,color:#fff",
        "java":       "fill:#ef5350,color:#fff",
        "bitbake":    "fill:#ab47bc,color:#fff",
        "devicetree": "fill:#78909c,color:#fff",
    }

    def __init__(self, db_connection=None) -> None:
        self.db = db_connection

    def call_graph(
        self,
        root_function: str,
        depth: int = 3,
        include_ipc: bool = True,
        include_ffi: bool = True,
    ) -> str:
        """Generate a Mermaid call graph rooted at a function.

        Args:
            root_function: Name of the root function.
            depth: Maximum BFS depth.
            include_ipc: Include IPC (cross-process) edges.
            include_ffi: Include cross-language (FFI) edges.

        Returns:
            Mermaid diagram string.
        """
        if self.db is None:
            return self._empty_diagram("No database connection")

        edges: list[tuple[str, str, str, str]] = []  # (from, to, edge_type, label)
        visited: set[str] = set()
        node_langs: dict[str, str] = {}
        queue: deque[tuple[str, int]] = deque([(root_function, 0)])

        while queue:
            func_name, current_depth = queue.popleft()
            if current_depth >= depth or func_name in visited:
                continue
            visited.add(func_name)

            # Direct calls
            try:
                rows = self.db.execute("""
                    SELECT DISTINCT f2.name, f2_file.language
                    FROM Function f1
                    JOIN calls c ON f1.id = c.caller_id
                    JOIN Function f2 ON f2.id = c.callee_id
                    JOIN File f2_file ON f2.file_id = f2_file.id
                    WHERE f1.name = ?
                """, [func_name]).fetchall()
                for callee_name, lang in rows:
                    edges.append((func_name, callee_name, "call", ""))
                    node_langs[callee_name] = lang
                    queue.append((callee_name, current_depth + 1))
            except Exception:
                pass

            # IPC edges
            if include_ipc:
                try:
                    rows = self.db.execute("""
                        SELECT DISTINCT f2.name, ipc.protocol,
                               ipc.method_name, f2_file.language
                        FROM Function f1
                        JOIN calls_over_ipc ipc ON f1.id = ipc.caller_func_id
                        JOIN Function f2 ON f2.id = ipc.callee_func_id
                        JOIN File f2_file ON f2.file_id = f2_file.id
                        WHERE f1.name = ?
                    """, [func_name]).fetchall()
                    for callee_name, protocol, method, lang in rows:
                        label = f"{protocol}:{method}" if method else protocol
                        edges.append((func_name, callee_name, "ipc", label))
                        node_langs[callee_name] = lang
                        queue.append((callee_name, current_depth + 1))
                except Exception:
                    pass

            # FFI edges
            if include_ffi:
                try:
                    rows = self.db.execute("""
                        SELECT DISTINCT f2.name, cl.ffi_mechanism,
                               f2_file.language
                        FROM Function f1
                        JOIN calls_cross_language cl ON f1.id = cl.caller_func_id
                        JOIN Function f2 ON f2.id = cl.callee_func_id
                        JOIN File f2_file ON f2.file_id = f2_file.id
                        WHERE f1.name = ?
                    """, [func_name]).fetchall()
                    for callee_name, mechanism, lang in rows:
                        edges.append((func_name, callee_name, "ffi", mechanism))
                        node_langs[callee_name] = lang
                        queue.append((callee_name, current_depth + 1))
                except Exception:
                    pass

            # Get language for root
            if func_name not in node_langs:
                try:
                    row = self.db.execute("""
                        SELECT fi.language FROM Function f
                        JOIN File fi ON f.file_id = fi.id
                        WHERE f.name = ? LIMIT 1
                    """, [func_name]).fetchone()
                    if row:
                        node_langs[func_name] = row[0]
                except Exception:
                    pass

        return self._render_call_graph(edges, visited, node_langs, root_function)

    def call_graph_from_results(
        self,
        parse_results: list,
        root_function: str,
        depth: int = 3,
    ) -> str:
        """Generate a call graph directly from ParseResult objects (no DB).

        Useful for quick diagrams during development.
        """
        # Build adjacency from parse results
        adjacency: dict[str, list[str]] = {}
        func_langs: dict[str, str] = {}
        for result in parse_results:
            for func in result.functions:
                func_langs[func.name] = result.file_info.language
            for call in result.calls:
                adjacency.setdefault(call.caller, []).append(call.callee)

        edges: list[tuple[str, str, str, str]] = []
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(root_function, 0)])

        while queue:
            func_name, d = queue.popleft()
            if d >= depth or func_name in visited:
                continue
            visited.add(func_name)
            for callee in adjacency.get(func_name, []):
                edges.append((func_name, callee, "call", ""))
                queue.append((callee, d + 1))

        return self._render_call_graph(edges, visited, func_langs, root_function)

    def file_dependency_graph(self, directory_filter: str = "") -> str:
        """Generate a file-level dependency diagram (include edges)."""
        if self.db is None:
            return self._empty_diagram("No database connection")

        query = """
            SELECT f1.path, f2.path
            FROM includes_file inc
            JOIN File f1 ON inc.source_id = f1.id
            JOIN File f2 ON inc.target_id = f2.id
        """
        params: list = []
        if directory_filter:
            query += " WHERE f1.path LIKE ?"
            params.append(f"%{directory_filter}%")

        try:
            rows = self.db.execute(query, params).fetchall()
        except Exception:
            return self._empty_diagram("Query failed")

        if not rows:
            return self._empty_diagram("No include edges found")

        lines = ["```mermaid", "graph LR"]
        seen_edges: set[tuple[str, str]] = set()
        for source, target in rows:
            # Use short filenames for readability
            src_short = self._short_name(source)
            tgt_short = self._short_name(target)
            edge_key = (src_short, tgt_short)
            if edge_key not in seen_edges:
                lines.append(f"    {src_short}-->{tgt_short}")
                seen_edges.add(edge_key)

        lines.append("```")
        return "\n".join(lines)

    def tier_summary(self) -> str:
        """Generate a Mermaid pie chart of tier distribution."""
        if self.db is None:
            return self._empty_diagram("No database connection")

        try:
            rows = self.db.execute("""
                SELECT tier, COUNT(*) as cnt
                FROM Tier
                GROUP BY tier
                ORDER BY tier
            """).fetchall()
        except Exception:
            return self._empty_diagram("Query failed")

        if not rows:
            return self._empty_diagram("No tier data")

        tier_labels = {0: "i0: Ignore", 1: "i1: Stub", 2: "i2: Skeleton", 3: "i3: Full"}
        lines = ['```mermaid', 'pie title Tier Distribution']
        for tier, count in rows:
            label = tier_labels.get(tier, f"Tier {tier}")
            lines.append(f'    "{label}" : {count}')
        lines.append("```")
        return "\n".join(lines)

    # ── Internal rendering ───────────────────────────────────────────

    def _render_call_graph(
        self,
        edges: list[tuple[str, str, str, str]],
        visited: set[str],
        node_langs: dict[str, str],
        root: str,
    ) -> str:
        """Render edges and nodes into a Mermaid graph string."""
        lines = ["```mermaid", "graph TD"]

        # Sanitise node names for Mermaid (no special chars)
        def safe(name: str) -> str:
            return name.replace("-", "_").replace(".", "_")

        # Edges
        seen: set[tuple[str, str]] = set()
        for src, dst, edge_type, label in edges:
            key = (src, dst)
            if key in seen:
                continue
            seen.add(key)

            s, d = safe(src), safe(dst)
            if edge_type == "ipc":
                arrow = f'-. "{label}" .->' if label else "-..->"
            elif edge_type == "ffi":
                arrow = f'== "{label}" ==>' if label else "===>"
            else:
                arrow = "-->"
            lines.append(f"    {s}[{src}]{arrow}{d}[{dst}]")

        # Style nodes by language
        for node in visited:
            lang = node_langs.get(node, "")
            style = self._LANG_STYLES.get(lang)
            if style:
                lines.append(f"    style {safe(node)} {style}")

        # Highlight root
        lines.append(f"    style {safe(root)} stroke:#ff0,stroke-width:3px")

        lines.append("```")
        return "\n".join(lines)

    @staticmethod
    def _short_name(path: str) -> str:
        """Shorten a file path to its basename for readability."""
        from pathlib import Path as P
        return P(path).name.replace(".", "_").replace("-", "_")

    @staticmethod
    def _empty_diagram(reason: str) -> str:
        return f"```mermaid\ngraph TD\n    A[{reason}]\n```"
