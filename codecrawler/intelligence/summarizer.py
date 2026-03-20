"""Summarizer — confidence-aware tiered summarization."""

from __future__ import annotations

import logging

from codecrawler.core.types import SummaryResult

logger = logging.getLogger(__name__)


class Summarizer:
    """Generates summaries for code entities with confidence tracking.

    Two-phase approach:
    1. Quick local model (3B) produces 0.6-confidence, 2-sentence summaries.
    2. When a developer examines an entity, a background thread lazily
       upgrades via a larger model (0.9-confidence, detailed explanation).
    """

    def __init__(self, llm_provider: str = "ollama", model: str = "llama3.2:8b") -> None:
        self.llm_provider = llm_provider
        self.model = model

    def summarize_function(
        self,
        func_id: int,
        name: str,
        signature: str,
        body: str = "",
    ) -> SummaryResult:
        """Generate a summary for a function.

        In the current v4 skeleton, returns a template summary.
        Full LLM integration planned for v5.
        """
        summary = f"Function '{name}' with signature: {signature}"

        if body:
            line_count = body.count("\n") + 1
            summary += f" ({line_count} lines)"

        return SummaryResult(
            entity_id=func_id,
            entity_type="function",
            summary=summary,
            model_used="heuristic",
            confidence=0.3,
        )

    def summarize_file(self, file_id: int, path: str, language: str) -> SummaryResult:
        """Generate a summary for a file."""
        summary = f"{language.upper()} source file at {path}"

        return SummaryResult(
            entity_id=file_id,
            entity_type="file",
            summary=summary,
            model_used="heuristic",
            confidence=0.3,
        )

    def upgrade_summary(
        self,
        entity_id: int,
        entity_type: str,
        context: str,
    ) -> SummaryResult:
        """Upgrade a summary using a larger/better LLM model.

        Called lazily when a developer examines an entity.
        Full implementation planned for v5.
        """
        logger.info(
            "Summary upgrade requested for %s:%d (LLM integration in v5)",
            entity_type,
            entity_id,
        )
        return SummaryResult(
            entity_id=entity_id,
            entity_type=entity_type,
            summary=f"[Upgrade pending] {context[:200]}",
            model_used=self.model,
            confidence=0.6,
        )
