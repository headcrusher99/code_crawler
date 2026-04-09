"""repo_map — Global repository map builder (Aider-inspired).

Generates a token-budget-aware ranked summary of the entire codebase.
The repo map is the primary context artifact served to LLM agents via MCP,
enabling single-call retrieval of the most important code structure.

Usage:
    builder = RepoMapBuilder(db_connection)
    repo_map = builder.build(token_budget=4096, min_tier=2)
    print(repo_map.to_string())
"""

from __future__ import annotations

import logging

from codecrawler.core.types import RepoMap

logger = logging.getLogger(__name__)


class RepoMapBuilder:
    """Build a global repository map — a ranked summary of all functions.

    The repo map:
      1. Lists all functions ranked by composite_score (PageRank hybrid)
      2. Includes signatures and one-line summaries
      3. Respects a token budget (default 4096 tokens)
      4. Filters by minimum tier (default i2+)
      5. Groups by file for readability
      6. Is served via MCP as a single retrieval

    This replaces the need for LLMs to scan entire codebases at query time.
    """

    # Rough estimate: 1 word ≈ 1.3 tokens on average
    _TOKENS_PER_WORD = 1.3

    def __init__(self, db_connection=None) -> None:
        self.db = db_connection

    def build(
        self,
        token_budget: int = 4096,
        min_tier: int = 2,
        language_filter: str | None = None,
    ) -> RepoMap:
        """Build the repo map from the database.

        Args:
            token_budget: Maximum approximate token count for the map.
            min_tier: Minimum tier to include (0–3).
            language_filter: Optional language to restrict to (e.g., "c").

        Returns:
            RepoMap with ranked function entries.
        """
        if self.db is None:
            logger.warning("No database connection — returning empty repo map")
            return RepoMap(token_budget=token_budget)

        # Query ranked functions with their file paths and summaries
        query = """
            SELECT f.name, f.signature, f.summary,
                   fi.path, fi.language,
                   COALESCE(ps.composite_score, 0.0) AS score,
                   COALESCE(t.tier, 2) AS tier
            FROM Function f
            JOIN File fi ON f.file_id = fi.id
            LEFT JOIN PriorityScore ps ON f.id = ps.func_id
            LEFT JOIN Tier t ON t.path = fi.path
            WHERE COALESCE(t.tier, 2) >= ?
        """
        params: list = [min_tier]

        if language_filter:
            query += " AND fi.language = ?"
            params.append(language_filter)

        query += " ORDER BY COALESCE(ps.composite_score, 0.0) DESC"

        try:
            rows = self.db.execute(query, params).fetchall()
        except Exception:
            logger.exception("Failed to query functions for repo map")
            return RepoMap(token_budget=token_budget)

        total_functions = len(rows)

        # Build entries within token budget
        entries: list[str] = []
        tokens_used = 0
        current_file = ""

        for row in rows:
            name, signature, summary, path, language, score, tier = row

            # Group header when file changes
            if path != current_file:
                file_header = f"\n## {path}"
                header_tokens = self._estimate_tokens(file_header)
                if tokens_used + header_tokens > token_budget:
                    break
                entries.append(file_header)
                tokens_used += header_tokens
                current_file = path

            # Build function entry
            sig = signature or name
            entry = f"  {sig}"
            if summary:
                # Truncate summary to keep entries compact
                short_summary = summary[:80].rstrip(".")
                entry += f"  — {short_summary}"

            entry_tokens = self._estimate_tokens(entry)
            if tokens_used + entry_tokens > token_budget:
                break

            entries.append(entry)
            tokens_used += entry_tokens

        repo_map = RepoMap(
            entries=entries,
            total_functions=total_functions,
            included_functions=sum(1 for e in entries if e.startswith("  ")),
            token_budget=token_budget,
            tokens_used=int(tokens_used),
        )

        logger.info(
            "Built repo map: %d/%d functions, ~%d tokens (budget: %d)",
            repo_map.included_functions,
            repo_map.total_functions,
            repo_map.tokens_used,
            token_budget,
        )
        return repo_map

    def build_from_results(
        self,
        parse_results: list,
        scores: dict[str, float] | None = None,
        token_budget: int = 4096,
    ) -> RepoMap:
        """Build a repo map from in-memory parse results (no DB required).

        Useful during the pipeline before data is persisted.
        """
        func_entries: list[tuple[str, str, str, float]] = []

        for result in parse_results:
            file_path = str(result.file_info.path)
            for func in result.functions:
                score = (scores or {}).get(func.name, 0.0)
                func_entries.append((func.name, func.signature, file_path, score))

        # Sort by score descending
        func_entries.sort(key=lambda x: x[3], reverse=True)

        entries: list[str] = []
        tokens_used = 0
        current_file = ""

        for name, signature, path, score in func_entries:
            if path != current_file:
                file_header = f"\n## {path}"
                header_tokens = self._estimate_tokens(file_header)
                if tokens_used + header_tokens > token_budget:
                    break
                entries.append(file_header)
                tokens_used += header_tokens
                current_file = path

            sig = signature or name
            entry = f"  {sig}"
            entry_tokens = self._estimate_tokens(entry)
            if tokens_used + entry_tokens > token_budget:
                break
            entries.append(entry)
            tokens_used += entry_tokens

        return RepoMap(
            entries=entries,
            total_functions=len(func_entries),
            included_functions=sum(1 for e in entries if e.startswith("  ")),
            token_budget=token_budget,
            tokens_used=int(tokens_used),
        )

    def _estimate_tokens(self, text: str) -> float:
        """Rough token estimate for a string."""
        return len(text.split()) * self._TOKENS_PER_WORD
