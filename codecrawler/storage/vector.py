"""Vector — VSS (Vector Similarity Search) index management."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


VECTOR_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS func_embedding_idx ON Function USING HNSW (embedding)
    WITH (metric = 'cosine');
CREATE INDEX IF NOT EXISTS file_embedding_idx ON File USING HNSW (embedding)
    WITH (metric = 'cosine');
CREATE INDEX IF NOT EXISTS var_embedding_idx ON Variable USING HNSW (embedding)
    WITH (metric = 'cosine');
"""


def install_vss(connection) -> bool:
    """Install and load the VSS extension."""
    try:
        connection.execute("INSTALL vss; LOAD vss;")
        logger.info("VSS extension loaded")
        return True
    except Exception as e:
        logger.warning("Could not load VSS extension: %s", e)
        return False


def create_vector_indexes(connection) -> None:
    """Create HNSW vector indexes on embedding columns."""
    try:
        connection.execute(VECTOR_INDEX_DDL)
        logger.info("Vector indexes created")
    except Exception as e:
        logger.warning("Could not create vector indexes: %s", e)


def semantic_search(
    connection,
    query_embedding: list[float],
    table: str = "Function",
    limit: int = 10,
) -> list[dict]:
    """Search for semantically similar entities using cosine distance.

    Args:
        connection: DuckDB connection.
        query_embedding: Query vector (384 dimensions).
        table: Table to search (Function, File, or Variable).
        limit: Max results.

    Returns:
        List of dicts with entity data and similarity scores.
    """
    query = f"""
    SELECT *, array_cosine_distance(embedding, ?::FLOAT[384]) AS distance
    FROM {table}
    WHERE embedding IS NOT NULL
    ORDER BY distance ASC
    LIMIT ?
    """
    try:
        results = connection.execute(query, [query_embedding, limit]).fetchall()
        columns = [desc[0] for desc in connection.description]
        return [dict(zip(columns, row)) for row in results]
    except Exception as e:
        logger.error("Semantic search failed on %s: %s", table, e)
        return []
