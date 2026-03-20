"""Storage component — DuckDB backend with graph and vector support."""

from codecrawler.storage.database import Database
from codecrawler.storage.schema import SCHEMA_DDL, create_schema

__all__ = ["Database", "SCHEMA_DDL", "create_schema"]
