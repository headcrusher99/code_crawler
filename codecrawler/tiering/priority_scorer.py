"""Priority Scorer — 6-dimension self-tuning priority scoring engine."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from codecrawler.core.config import PriorityScoringConfig
from codecrawler.core.types import PriorityScoreResult

logger = logging.getLogger(__name__)


class PriorityScorer:
    """Computes the 6-dimension composite priority score for functions.

    composite_score = (tier_weight    × W_t) +
                      (usage_freq     × W_u) +
                      (centrality     × W_c) +
                      (build_active   × W_b) +
                      (runtime_freq   × W_r) +
                      (recency        × W_e)
    """

    def __init__(self, config: PriorityScoringConfig | None = None) -> None:
        self.config = config or PriorityScoringConfig()
        self.weights = self.config.weights.copy()

    def score(
        self,
        func_id: int,
        *,
        tier_level: int = 0,
        call_count: int = 0,
        max_call_count: int = 1,
        betweenness: float = 0.0,
        build_guard_active: bool = False,
        runtime_hits: int = 0,
        max_runtime_hits: int = 1,
        last_modified: datetime | None = None,
    ) -> PriorityScoreResult:
        """Compute the composite priority score for a single function.

        Args:
            func_id: The database ID of the function.
            tier_level: Tier (0–3) of the file containing this function.
            call_count: Number of times this function is called.
            max_call_count: Maximum call count across all functions (for normalization).
            betweenness: Betweenness centrality from the call graph.
            build_guard_active: Whether the function's #ifdef guard is active.
            runtime_hits: Number of runtime trace hits.
            max_runtime_hits: Maximum runtime hits (for normalization).
            last_modified: When the file was last modified.

        Returns:
            PriorityScoreResult with all dimension scores and composite.
        """
        w = self.weights

        # Dimension 1: Tier weight
        tier_weight = tier_level / 3.0

        # Dimension 2: Usage frequency (normalized)
        usage_frequency = call_count / max(max_call_count, 1)

        # Dimension 3: Graph centrality
        graph_centrality = min(betweenness, 1.0)

        # Dimension 4: Build guard activation
        build_guard_activation = 1.0 if build_guard_active else 0.0

        # Dimension 5: Runtime frequency (normalized)
        runtime_frequency = runtime_hits / max(max_runtime_hits, 1)

        # Dimension 6: Recency (smooth decay)
        if last_modified:
            now = datetime.now(timezone.utc)
            days_since = max((now - last_modified).total_seconds() / 86400, 0)
            recency_score = 1.0 / (1.0 + days_since)
        else:
            recency_score = 0.0

        # Composite score
        composite_score = (
            tier_weight * w.get("tier", 0.25)
            + usage_frequency * w.get("usage", 0.20)
            + graph_centrality * w.get("centrality", 0.15)
            + build_guard_activation * w.get("build", 0.10)
            + runtime_frequency * w.get("runtime", 0.15)
            + recency_score * w.get("recency", 0.15)
        )

        return PriorityScoreResult(
            func_id=func_id,
            tier_weight=tier_weight,
            usage_frequency=usage_frequency,
            graph_centrality=graph_centrality,
            build_guard_activation=build_guard_activation,
            runtime_frequency=runtime_frequency,
            recency_score=recency_score,
            composite_score=round(composite_score, 6),
        )

    def adjust_weights(self, query_logs: list[dict]) -> None:
        """Self-tuning: adjust weights based on historical query patterns.

        If engineers heavily query recency-based functions, increase W_e.
        Planned for full implementation in v5.
        """
        if not self.config.self_tuning:
            return

        logger.info("Weight self-tuning is planned for full implementation in v5")
