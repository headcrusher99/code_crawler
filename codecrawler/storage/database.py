"""Database — DuckDB connection management and migrations."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class Database:
    """DuckDB connection manager with schema migration support.

    Usage:
        db = Database("path/to/index.duckdb")
        db.initialize()
        conn = db.connection
    """

    def __init__(self, db_path: str = ".codecrawler/index.duckdb") -> None:
        self.db_path = db_path
        self._connection = None

    @property
    def connection(self):
        """Lazy-initialize and return the DuckDB connection."""
        if self._connection is None:
            self._connect()
        return self._connection

    def _connect(self) -> None:
        """Create database directory and establish connection."""
        import duckdb

        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        self._connection = duckdb.connect(self.db_path)
        logger.info("Connected to DuckDB at %s", self.db_path)

    def initialize(self) -> None:
        """Create all tables and views if they don't exist."""
        from codecrawler.storage.schema import create_schema

        create_schema(self.connection)
        logger.info("Schema initialized")

    def get_stats(self) -> dict[str, int]:
        """Get index statistics — row counts for key tables."""
        conn = self.connection
        stats = {}
        tables = [
            "Directory", "File", "Function", "Struct", "Macro",
            "Variable", "Tier", "PriorityScore", "IndexManifest",
            "RuntimeTrace", "Annotation",
        ]
        for table in tables:
            try:
                result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                stats[table] = result[0] if result else 0
            except Exception:
                stats[table] = 0
        return stats

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
