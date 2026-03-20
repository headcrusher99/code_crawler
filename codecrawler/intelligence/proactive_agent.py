"""Proactive Agent — background remediation for thread-unsafe shared state."""

from __future__ import annotations

import logging

from codecrawler.core.types import PatchSuggestion

logger = logging.getLogger(__name__)


class ProactiveAgent:
    """Background AI agent that scans for thread-safety vulnerabilities.

    Detects global variables with write_count > 1 spanning multiple
    execution contexts (threads/interrupts) without mutex protection,
    and generates git patches to secure the data.
    """

    def __init__(self, db_connection=None) -> None:
        self.db = db_connection

    def scan_shared_state(self) -> list[PatchSuggestion]:
        """Scan for variables with unsafe multi-writer patterns.

        Queries the LLM_SharedState view for globals with write_count > 1,
        then checks if mutex/spinlock protection exists in the AST.

        Returns:
            List of PatchSuggestion objects for unsafe variables.
        """
        if self.db is None:
            logger.warning("No database connection — skipping shared state scan")
            return []

        suggestions = []

        try:
            results = self.db.execute("""
                SELECT name, func_name, file_path, write_count
                FROM LLM_SharedState
                WHERE write_count > 1
                ORDER BY write_count DESC
                LIMIT 50
            """).fetchall()
        except Exception as e:
            logger.error("Shared state query failed: %s", e)
            return []

        for row in results:
            var_name, func_name, file_path, write_count = row
            logger.info(
                "Potential thread-safety issue: %s (written %d times in %s)",
                var_name,
                write_count,
                file_path,
            )

            # In v5: use LLM to check if mutex exists and generate a patch
            suggestions.append(PatchSuggestion(
                file_path=file_path,
                description=(
                    f"Variable '{var_name}' is written by {write_count} contexts "
                    f"in {func_name}. Consider adding mutex protection."
                ),
                diff="",  # Placeholder — LLM patch generation in v5
                confidence=0.6,
            ))

        logger.info("Found %d potential thread-safety issues", len(suggestions))
        return suggestions

    def generate_patch(self, suggestion: PatchSuggestion) -> str:
        """Use an LLM to generate a git patch for a vulnerability.

        Planned for full implementation in v5.
        """
        logger.info("LLM patch generation planned for v5")
        return ""
