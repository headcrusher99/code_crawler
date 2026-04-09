"""scope_resolver — Stack-Graphs-inspired name resolution for call graphs.

Replaces naive "match by function name" with scope-aware resolution that
considers file scope, include chains, namespace proximity, and static
linkage to disambiguate function calls.

Usage:
    resolver = ScopeResolver()
    resolved = resolver.resolve_calls(parse_results, function_index)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from codecrawler.core.types import (
    CallEdge,
    FunctionDef,
    ParseResult,
    ResolvedCall,
    ScopeNode,
)

logger = logging.getLogger(__name__)


class FunctionRecord:
    """Lightweight internal record for a function in the global index."""

    __slots__ = (
        "func_id", "name", "qualified_name", "file_path", "is_static",
        "language", "start_line",
    )

    def __init__(
        self,
        func_id: int,
        name: str,
        file_path: str,
        qualified_name: str = "",
        is_static: bool = False,
        language: str = "",
        start_line: int = 0,
    ) -> None:
        self.func_id = func_id
        self.name = name
        self.qualified_name = qualified_name or name
        self.file_path = file_path
        self.is_static = is_static
        self.language = language
        self.start_line = start_line

    def __repr__(self) -> str:
        return f"<FunctionRecord {self.qualified_name} in {self.file_path}>"


class ScopeResolver:
    """Resolve ambiguous function call targets using scope chains.

    Builds a hierarchy of scopes (file → namespace → class → function)
    and resolves name references by traversing the scope chain outward.

    Resolution priority (highest to lowest):
      1. Same file
      2. In include chain (direct dependency)
      3. Same directory
      4. Same parent directory
      5. Global match
      6. Static linkage penalty (static in a different file → impossible)
    """

    def __init__(self) -> None:
        self._include_graph: dict[str, set[str]] = defaultdict(set)

    def build_function_index(
        self, parse_results: list[ParseResult]
    ) -> dict[str, list[FunctionRecord]]:
        """Build a global name → [FunctionRecord] index from all parse results.

        Also builds the include graph for dependency-based resolution.
        """
        index: dict[str, list[FunctionRecord]] = defaultdict(list)
        func_id_counter = 1

        for result in parse_results:
            file_path = str(result.file_info.path)

            # Build include graph
            for inc in result.includes:
                self._include_graph[inc.source_path].add(inc.target_path)

            for func in result.functions:
                record = FunctionRecord(
                    func_id=func_id_counter,
                    name=func.name,
                    file_path=file_path,
                    is_static=func.is_static,
                    language=func.language or result.file_info.language,
                    start_line=func.start_line,
                )
                index[func.name].append(record)
                func_id_counter += 1

        logger.info(
            "Built function index: %d unique names, %d total functions",
            len(index),
            sum(len(v) for v in index.values()),
        )
        return index

    def resolve_calls(
        self,
        parse_results: list[ParseResult],
        function_index: dict[str, list[FunctionRecord]],
    ) -> list[ResolvedCall]:
        """Resolve all call edges using scope-aware analysis."""
        resolved: list[ResolvedCall] = []
        stats = {"unique": 0, "scoped": 0, "unresolved": 0, "total": 0}

        for result in parse_results:
            file_path = str(result.file_info.path)
            included_files = self._get_transitive_includes(file_path, max_depth=3)

            for call in result.calls:
                stats["total"] += 1
                candidates = function_index.get(call.callee, [])

                if not candidates:
                    # Unresolvable — external/library call
                    resolved.append(ResolvedCall(
                        caller=call.caller,
                        callee=call.callee,
                        resolved=False,
                        confidence=0.0,
                        resolution_method="none",
                    ))
                    stats["unresolved"] += 1

                elif len(candidates) == 1:
                    # Unique match — high confidence
                    c = candidates[0]
                    # Static function in another file is unreachable
                    if c.is_static and c.file_path != file_path:
                        resolved.append(ResolvedCall(
                            caller=call.caller,
                            callee=call.callee,
                            resolved=False,
                            confidence=0.0,
                            resolution_method="static_unreachable",
                        ))
                        stats["unresolved"] += 1
                    else:
                        resolved.append(ResolvedCall(
                            caller=call.caller,
                            callee=c.qualified_name,
                            callee_id=c.func_id,
                            resolved=True,
                            confidence=1.0,
                            resolution_method="unique_name",
                        ))
                        stats["unique"] += 1

                else:
                    # Ambiguous — use scope chain to disambiguate
                    best = self._resolve_by_scope(
                        call, candidates, file_path, included_files
                    )
                    resolved.append(best)
                    stats["scoped"] += 1

        logger.info(
            "Scope resolution: %d total, %d unique, %d scoped, %d unresolved",
            stats["total"], stats["unique"], stats["scoped"], stats["unresolved"],
        )
        return resolved

    # ── Internal resolution ──────────────────────────────────────────

    def _resolve_by_scope(
        self,
        call: CallEdge,
        candidates: list[FunctionRecord],
        caller_file: str,
        included_files: set[str],
    ) -> ResolvedCall:
        """Score each candidate by scope proximity and return the best."""
        scored: list[tuple[FunctionRecord, float]] = []

        caller_dir = str(Path(caller_file).parent)
        caller_parent_dir = str(Path(caller_file).parent.parent)

        for candidate in candidates:
            score = 0.0

            # Static function in another file → impossible
            if candidate.is_static and candidate.file_path != caller_file:
                score -= 10.0

            # Same file — highest priority
            if candidate.file_path == caller_file:
                score += 1.0

            # In include chain
            elif candidate.file_path in included_files:
                score += 0.7

            # Same directory
            elif str(Path(candidate.file_path).parent) == caller_dir:
                score += 0.5

            # Same parent directory
            elif str(Path(candidate.file_path).parent.parent) == caller_parent_dir:
                score += 0.3

            # Exported function bonus
            if not candidate.is_static:
                score += 0.1

            scored.append((candidate, score))

        # Pick highest score
        best, best_score = max(scored, key=lambda x: x[1])
        confidence = min(max(best_score, 0.0), 1.0)

        return ResolvedCall(
            caller=call.caller,
            callee=best.qualified_name,
            callee_id=best.func_id,
            resolved=confidence > 0.1,
            confidence=confidence,
            resolution_method="scope_chain",
        )

    def _get_transitive_includes(
        self, file_path: str, max_depth: int = 3
    ) -> set[str]:
        """BFS through the include graph up to max_depth."""
        visited: set[str] = set()
        frontier = {file_path}

        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for fp in frontier:
                for included in self._include_graph.get(fp, set()):
                    if included not in visited:
                        visited.add(included)
                        next_frontier.add(included)
            frontier = next_frontier
            if not frontier:
                break

        return visited

    def build_scope_tree(self, result: ParseResult) -> ScopeNode:
        """Build a scope tree from a single parse result (for future use)."""
        root = ScopeNode(name=str(result.file_info.path), kind="file")
        for func in result.functions:
            child = ScopeNode(
                name=func.name,
                kind="function",
                parent=root,
            )
            root.children.append(child)
        return root
